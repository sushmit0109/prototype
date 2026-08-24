#!/usr/bin/env python3
"""
The Tk 50 crore ceiling: a package below that value can be approved inside
the ministry; above it, in Bangladesh's development-project approval chain,
it needs to clear ECNEC (the Executive Committee of the National Economic
Council) -- a slower, more visible review. A well-known way to dodge that
review is to slice one job that should be a single ~Tk 50+ crore package
into several smaller ones, each safely under the line, awarded to the same
contractor in quick succession.

This is not provable from award data alone -- nothing here says a package
*should* have been bigger, only that its shape is the one that gaming would
produce. Two independent tests for that shape:

  1. Bunching: does the value distribution spike just BELOW Tk 50 crore and
     drop sharply just above it? Competitive/organic pricing gives a smooth
     curve; a threshold being deliberately dodged gives a cliff.
  2. Split clusters: the same (procuring office, vendor) pair awarded two or
     more contracts, each individually under Tk 50 crore, within a short
     window of each other, that SUM to Tk 50 crore or more. A single large
     need does not naturally arrive as several near-simultaneous small ones.

Both run on data/contracts/ (already deduplicated, dimension-encoded).

    python3 build_ceiling.py <data/contracts/> <out.json>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from eras import ERA_NAMES, era_of

CRORE = 1e7
THRESHOLD_BDT = 50 * CRORE
WINDOW_DAYS = 45          # how close together sub-threshold awards must land
MIN_CLUSTER_TOTAL = THRESHOLD_BDT


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def fine_histogram(values_crore, lo, hi, step):
    hist = Counter()
    for v in values_crore:
        if lo <= v < hi:
            hist[round(round(v / step) * step, 2)] += 1
    return {f"{k:.2f}": n for k, n in sorted(hist.items())}


def band(values_crore, lo, hi):
    return sum(1 for v in values_crore if lo <= v < hi)


def find_split_clusters(contracts, dims):
    """Same (procuring office, vendor), each award < threshold, clustered
    tightly in time, summing past it. A sliding window over sorted dates
    per group -- not a fixed calendar bucket -- so a cluster is only counted
    once even if the group has other, unrelated contracts years apart."""
    groups = defaultdict(list)
    for c in contracts:
        v = c.get("value_bdt")
        d = c.get("contract_signing_date")
        pe = c.get("procuring_entity_id")
        vendor = c.get("awarded_to")
        if not v or v >= THRESHOLD_BDT or not d or pe is None or not vendor:
            continue
        groups[(pe, vendor)].append({
            "date": datetime.fromisoformat(d),
            "value_bdt": v,
            "package_ref": c.get("package_ref"),
            "ministry_id": c.get("ministry_id"),
        })

    clusters = []
    for (pe, vendor), items in groups.items():
        items.sort(key=lambda x: x["date"])
        n = len(items)
        i = 0
        best = None
        for j in range(n):
            while items[j]["date"] - items[i]["date"] > timedelta(days=WINDOW_DAYS):
                i += 1
            window = items[i:j + 1]
            if len(window) < 2:
                continue
            total = sum(w["value_bdt"] for w in window)
            if total >= MIN_CLUSTER_TOTAL and (best is None or total > best["total_bdt"]):
                best = {
                    "total_bdt": total,
                    "count": len(window),
                    "first_date": window[0]["date"].date().isoformat(),
                    "last_date": window[-1]["date"].date().isoformat(),
                    "package_refs": [w["package_ref"] for w in window if w["package_ref"]][:8],
                    "ministry_id": window[0]["ministry_id"],
                }
        if best:
            best["procuring_entity_id"] = pe
            best["vendor"] = vendor
            clusters.append(best)

    clusters.sort(key=lambda x: -x["total_bdt"])
    for c in clusters:
        c["ministry"] = dims["ministries"][c["ministry_id"]] if c["ministry_id"] is not None else "Unknown"
        c["procuring_entity"] = dims["procuring_entities"][c["procuring_entity_id"]] \
            if c["procuring_entity_id"] is not None else "Unknown"
        c["era"] = era_of(c["first_date"])
        del c["ministry_id"], c["procuring_entity_id"]
    return clusters


def bunching_by_era(contracts):
    by_era = defaultdict(list)
    for c in contracts:
        v = c.get("value_bdt")
        era = era_of(c.get("contract_signing_date"))
        if v and era:
            by_era[era].append(v / CRORE)
    return [
        {"era": e, "just_under_45_50": band(by_era[e], 45, 50), "just_over_50_55": band(by_era[e], 50, 55),
         "contracts_in_era": len(by_era[e])}
        for e in ERA_NAMES if by_era.get(e)
    ]


def main(contracts_dir, out_path):
    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)

    contracts = list(load_contracts(contracts_dir))
    values_crore = [c["value_bdt"] / CRORE for c in contracts if c.get("value_bdt")]

    just_under = band(values_crore, 45, 50)
    just_over = band(values_crore, 50, 55)
    wide_under = band(values_crore, 35, 50)
    wide_over = band(values_crore, 50, 65)

    clusters = find_split_clusters(contracts, dims)
    clusters_by_era = Counter(c["era"] for c in clusters if c["era"])

    payload = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/SearchNOA.jsp",
            "threshold_bdt": THRESHOLD_BDT,
            "window_days": WINDOW_DAYS,
            "contracts_scanned": len(contracts),
            "contracts_with_value": len(values_crore),
        },
        "bunching": {
            "fine_histogram_crore": fine_histogram(values_crore, 30, 65, 0.5),
            "just_under_45_50": just_under,
            "just_over_50_55": just_over,
            "asymmetry_ratio": round(just_under / just_over, 2) if just_over else None,
            "wide_under_35_50": wide_under,
            "wide_over_50_65": wide_over,
            "by_era": bunching_by_era(contracts),
        },
        "split_clusters": clusters[:40],
        "split_clusters_total_count": len(clusters),
        "split_clusters_by_era": dict(clusters_by_era),
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{len(contracts):,} contracts scanned, {len(values_crore):,} with a value")
    print(f"just under 50cr (45-50): {just_under}, just over (50-55): {just_over}, "
          f"asymmetry {payload['bunching']['asymmetry_ratio']}x")
    print(f"{len(clusters)} split-pattern clusters found (same office+vendor, "
          f"sub-threshold awards within {WINDOW_DAYS} days summing past Tk 50cr)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
