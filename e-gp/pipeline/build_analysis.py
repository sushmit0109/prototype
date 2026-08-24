#!/usr/bin/env python3
"""
The findings the dashboard is built around.

Everything else in the pipeline answers "what is in the data". This answers
"what does the data say" -- the handful of claims worth leading with, each
precomputed into data/analysis.json so the page ships a narrative rather
than a pile of tables. Each block below corresponds to one section of the
dashboard, and each carries the numbers needed to state the claim *and* the
numbers needed to qualify it.

    python3 build_analysis.py <data/contracts/> <data/tenders/> <out.json>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from entity import normalize_company
from eras import ERA_NAMES, era_of

LAKH = 100_000
CRORE = 10_000_000
# An office needs enough contracts before "one vendor won most of the money"
# means anything -- with 3 contracts it's noise, not concentration.
MIN_CONTRACTS_FOR_CONCENTRATION = 50
MIN_VALUE_FOR_CONCENTRATION = 50 * CRORE


def load(data_dir):
    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def seasonality(rows):
    """Bangladesh's fiscal year ends 30 June. Does spending pile up there?"""
    by_month = defaultdict(lambda: {"count": 0, "value_bdt": 0.0})
    by_year_june = defaultdict(lambda: {"total": 0, "june": 0})
    for r in rows:
        d = r.get("contract_signing_date")
        if not d:
            continue
        m = d[5:7]
        by_month[m]["count"] += 1
        by_month[m]["value_bdt"] += r.get("value_bdt") or 0
        y = d[:4]
        by_year_june[y]["total"] += 1
        if m == "06":
            by_year_june[y]["june"] += 1

    total = sum(v["count"] for v in by_month.values()) or 1
    return {
        "by_month": {m: {"count": v["count"], "value_bdt": round(v["value_bdt"], 2),
                         "share": round(v["count"] / total, 4)}
                     for m, v in sorted(by_month.items())},
        # 2026 is a partial year (crawled mid-August), so its June share is
        # inflated by a truncated denominator -- flagged, not silently mixed in.
        "june_share_by_year": {y: {"share": round(v["june"] / v["total"], 4), "total": v["total"],
                                   "partial_year": y == "2026"}
                               for y, v in sorted(by_year_june.items()) if v["total"] >= 500},
    }


def method_mix(rows):
    """Share of contract *value* by procurement method, per year."""
    by_year = defaultdict(lambda: defaultdict(float))
    overall = defaultdict(lambda: {"count": 0, "value_bdt": 0.0})
    for r in rows:
        y = (r.get("contract_signing_date") or "")[:4]
        method = r.get("procurement_method") or "Unknown"
        value = r.get("value_bdt") or 0
        overall[method]["count"] += 1
        overall[method]["value_bdt"] += value
        if y:
            by_year[y][method] += value
    return {
        "overall": {m: {"count": v["count"], "value_bdt": round(v["value_bdt"], 2)}
                    for m, v in sorted(overall.items(), key=lambda kv: -kv[1]["value_bdt"])},
        "value_share_by_year": {
            y: {m: round(v / (sum(methods.values()) or 1), 4) for m, v in methods.items()}
            for y, methods in sorted(by_year.items()) if sum(methods.values()) > 0
        },
    }


def concentration(rows, dims):
    """The aggregation trap: competitive nationally, monopolised office by office."""
    national = defaultdict(float)
    by_ministry = defaultdict(lambda: defaultdict(float))
    by_office = defaultdict(lambda: {"value": 0.0, "count": 0, "ministry": None, "vendors": defaultdict(float)})
    display_name = {}  # normalised key -> most common spelling, for readable output

    for r in rows:
        value = r.get("value_bdt") or 0
        key = normalize_company(r.get("awarded_to"))
        ministry = dims["ministries"][r["ministry_id"]] if r.get("ministry_id") is not None else "Unknown"
        office = dims["procuring_entities"][r["procuring_entity_id"]] if r.get("procuring_entity_id") is not None else "Unknown"
        if key:
            display_name.setdefault(key, r.get("awarded_to"))
            national[key] += value
            by_ministry[ministry][key] += value
            o = by_office[office]
            o["vendors"][key] += value
        o = by_office[office]
        o["value"] += value
        o["count"] += 1
        o["ministry"] = ministry

    def hhi(shares_by_key):
        t = sum(shares_by_key.values()) or 1
        return round(sum((v / t) ** 2 for v in shares_by_key.values()) * 10000, 1)

    ministries = sorted(
        [{"ministry": m, "hhi": hhi(v), "vendors": len(v), "value_bdt": round(sum(v.values()), 2),
          "top5_share": round(sum(sorted(v.values(), reverse=True)[:5]) / (sum(v.values()) or 1), 4)}
         for m, v in by_ministry.items()],
        key=lambda x: -x["value_bdt"])[:15]

    # Distribution of "how much of this office's money went to its single
    # biggest vendor", across offices big enough for the question to mean
    # something.
    buckets = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    worst = []
    qualifying = 0
    for name, o in by_office.items():
        if o["count"] < MIN_CONTRACTS_FOR_CONCENTRATION or o["value"] < MIN_VALUE_FOR_CONCENTRATION or not o["vendors"]:
            continue
        qualifying += 1
        top_key = max(o["vendors"], key=o["vendors"].get)
        share = o["vendors"][top_key] / (o["value"] or 1)
        b = min(int(share * 5), 4)
        buckets[list(buckets)[b]] += 1
        worst.append({
            "office": name, "ministry": o["ministry"],
            "top_vendor_share": round(share, 4),
            "value_bdt": round(o["value"], 2), "count": o["count"],
            "top_vendor": display_name.get(top_key, top_key),
        })
    worst.sort(key=lambda x: -x["top_vendor_share"])

    return {
        "national": {
            "vendors": len(national),
            "hhi": hhi(national),
            "top10_share": round(sum(sorted(national.values(), reverse=True)[:10]) / (sum(national.values()) or 1), 4),
        },
        "by_ministry": ministries,
        "office_top_vendor_share_buckets": buckets,
        "offices_qualifying": qualifying,
        "most_concentrated_offices": worst[:20],
        "thresholds": {
            "min_contracts": MIN_CONTRACTS_FOR_CONCENTRATION,
            "min_value_bdt": MIN_VALUE_FOR_CONCENTRATION,
        },
    }


def era_breakdown(rows):
    """Spend, count, and OTM/LTM method mix by political era.

    The three eras span very different lengths of time (the Awami League
    era is ~15 years of data, the interim government ~18 months, the
    elected government a few months as of this run) -- comparing raw totals
    would mostly just measure duration. Everything here is reported as a
    daily rate too, using each era's *actual observed* span in this dataset
    (not its nominal calendar length), so the eras are comparable on pace,
    not just on total.
    """
    from datetime import date

    agg = {e: {"count": 0, "value_bdt": 0.0, "methods": defaultdict(float), "dates": []}
           for e in ERA_NAMES}
    for r in rows:
        d = r.get("contract_signing_date")
        era = era_of(d)
        if not era:
            continue
        a = agg[era]
        v = r.get("value_bdt") or 0
        a["count"] += 1
        a["value_bdt"] += v
        a["methods"][r.get("procurement_method") or "Unknown"] += v
        a["dates"].append(d)

    out = {}
    for e in ERA_NAMES:
        a = agg[e]
        total_method_value = sum(a["methods"].values()) or 1
        span_days = 1
        if a["dates"]:
            lo, hi = min(a["dates"]), max(a["dates"])
            span_days = max((date.fromisoformat(hi) - date.fromisoformat(lo)).days, 1)
        out[e] = {
            "count": a["count"],
            "value_bdt": round(a["value_bdt"], 2),
            "observed_span_days": span_days,
            "contracts_per_day": round(a["count"] / span_days, 2),
            "value_bdt_per_day": round(a["value_bdt"] / span_days, 2),
            "otm_share": round(a["methods"].get("OTM", 0) / total_method_value, 4),
            "ltm_share": round(a["methods"].get("LTM", 0) / total_method_value, 4),
        }
    return out


def price_points(rows):
    """Contracts pile up on a few identical prices -- and those are mostly LTM.

    The portal quotes value in crore to 3 decimals, so every value is a
    multiple of Tk 10,000 and each "exact value" below is really a
    10,000-wide bin. That rounding is uniform, though, so it can't create a
    spike: a value carrying 8x its immediate neighbours is real clustering,
    not an artefact of the quoting precision.
    """
    counts = Counter()
    method_at = defaultdict(Counter)
    for r in rows:
        v = r.get("value_bdt")
        if not v:
            continue
        counts[v] += 1
        method_at[v][r.get("procurement_method") or "Unknown"] += 1

    total = sum(counts.values()) or 1
    top = []
    for v, n in counts.most_common(25):
        methods = method_at[v]
        ltm = methods.get("LTM", 0)
        top.append({
            "value_bdt": v, "count": n,
            "ltm_share": round(ltm / n, 4),
            "top_method": methods.most_common(1)[0][0],
        })
    top20_count = sum(t["count"] for t in top[:20])
    all_ltm = sum(1 for r in rows if r.get("procurement_method") == "LTM")

    # A coarse histogram for the shape of the distribution (1-lakh bins to 60 lakh).
    hist = Counter()
    for r in rows:
        v = r.get("value_bdt")
        if v and v < 60 * LAKH:
            hist[int(v // LAKH)] += 1

    return {
        "top_price_points": top,
        "top20_share_of_all_contracts": round(top20_count / total, 4),
        "distinct_values": len(counts),
        "ltm_share_overall": round(all_ltm / len(rows), 4),
        "histogram_lakh_bins": {str(k): v for k, v in sorted(hist.items())},
    }


def main(contracts_dir, tenders_dir, out_path):
    dims = json.load(open(os.path.join(contracts_dir, "dimensions.json")))
    rows = list(load(contracts_dir))

    total_value = sum(r.get("value_bdt") or 0 for r in rows)
    payload = {
        "meta": {
            "contracts": len(rows),
            "total_value_bdt": round(total_value, 2),
            "years": sorted({(r.get("contract_signing_date") or "")[:4] for r in rows} - {""}),
        },
        "seasonality": seasonality(rows),
        "method_mix": method_mix(rows),
        "concentration": concentration(rows, dims),
        "price_points": price_points(rows),
        "by_era": era_breakdown(rows),
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    s = payload["seasonality"]["by_month"]
    c = payload["concentration"]
    print(f"{len(rows):,} contracts, Tk {total_value/CRORE:,.0f} Cr")
    print(f"June share of contracts: {100*s['06']['share']:.1f}% (vs 8.3% uniform)")
    print(f"national HHI {c['national']['hhi']} across {c['national']['vendors']:,} vendors; "
          f"{c['offices_qualifying']} offices qualify for the concentration test")
    print(f"office top-vendor-share buckets: {c['office_top_vendor_share_buckets']}")
    print(f"top-20 price points = {100*payload['price_points']['top20_share_of_all_contracts']:.1f}% of all contracts")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
