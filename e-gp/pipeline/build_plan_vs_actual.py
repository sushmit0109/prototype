#!/usr/bin/env python3
"""
Plan versus outcome: what an office said a package would cost and how it
said it would buy it, against what actually happened.

Every other source here describes spending after the fact. The itemised
Annual Procurement Plan (scrape_app_items.py) is the only one that records
intent beforehand -- an estimated cost and a planned procurement method per
package -- which makes two questions answerable that the award data alone
cannot touch:

  1. Do awards come in above or below the government's own estimate?
  2. Does a package planned for open tendering actually get tendered openly?

The join is APP `package_no` against the contract list's `package_ref`,
exact match after case/whitespace normalisation. It is partial by nature:
plan and award are entered by hand into different forms, and only around a
fifth of planned packages carry a reference that matches an award exactly.
Everything below is therefore computed on the matched subset, and the match
rate is reported alongside so the reader can weigh it.

Some offices type office-shorthand ("se", "ee"), a bare running number
("01", "280"), or a short lot label ("W-01") into the package-reference
field instead of an actual package code. Those values are not unique, so
joining on them attaches one plan estimate to whichever unrelated contract
happens to share the same short text -- the exact false-positive shape as
the debarment name-collision bug (see flag_debarred_awards.py). Two
independent signals catch this, since neither alone is sufficient: a
reference used by contracts from more than GENERIC_PE_SPREAD different
procuring entities nationally clearly isn't a per-package identifier; and a
reference shorter than MIN_REF_LEN characters can collide by pure
coincidence even at low usage counts ("W-01" appears at only two procuring
entities nationally -- too few to trip the spread test -- yet still paired a
Tk 0.6 crore Water Board plan line with an unrelated Tk 44 crore Ministry of
Education scout-hall contract, purely because both used that label). This
matters most for the overrun tail: a single bogus match like that one lands
at the very top of a list sorted by absolute overrun, exactly where it looks
most convincing. Real package codes in this data run long and structured
(median matched reference is 26 characters); both filters combined exclude
under 1% of otherwise-matchable pairs.

    python3 build_plan_vs_actual.py <raw/app_items.jsonl> <data/contracts/> <out.json>
"""
import glob
import gzip
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

from eras import ERA_NAMES, era_of

# Methods ordered by how open the competition is, most open first. Used only
# to say whether a change between plan and award opened the process up or
# closed it down -- not to rank methods as good or bad in themselves.
OPENNESS = {
    "OTM": 5, "OSTETM": 4, "QCBS": 4, "SFB": 4,
    "RFQU": 3, "RFQ": 3, "RFQL": 3,
    "LTM": 2, "IC": 2,
    "DPM": 1, "SSS": 1,
}


def open_batch(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def norm_ref(s):
    return (s or "").strip().lower()


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


MIN_PAIRS_FOR_MINISTRY = 30
GENERIC_PE_SPREAD = 3
MIN_REF_LEN = 6


def ministry_and_year_breakdown(pairs, dims):
    """Same award/estimate ratio, sliced by ministry and by signing year.

    There is no external benchmark in this dataset -- no independent "true"
    cost to compare against -- so this cannot say a price is objectively too
    high. What it can test is whether the deviation from the government's
    own estimate is a uniform, roughly-random spread (what honest estimation
    error looks like) or whether it has structure: some ministries running
    consistently hotter than others, or the pattern drifting over time.
    Structure is itself the finding, independent of any external price.
    """
    by_ministry = defaultdict(list)
    by_year = defaultdict(list)
    by_era = defaultdict(list)
    for p, c in pairs:
        r = c["value_bdt"] / p["estimated_cost_bdt"]
        mid = c.get("ministry_id")
        ministry = dims["ministries"][mid] if mid is not None and mid < len(dims["ministries"]) else None
        if ministry:
            by_ministry[ministry].append(r)
        date = c.get("contract_signing_date") or ""
        year = date[:4]
        if year:
            by_year[year].append(r)
        era = era_of(date)
        if era:
            by_era[era].append(r)

    def summarize(ratios):
        rs = sorted(ratios)
        n = len(rs)
        return {
            "matched_pairs": n,
            "median_ratio": round(statistics.median(rs), 4),
            "iqr": round(rs[int(n * 0.75)] - rs[int(n * 0.25)], 4) if n >= 4 else None,
            "share_above_115": round(sum(1 for r in rs if r > 1.15) / n, 4),
            "share_at_10pct_below": round(sum(1 for r in rs if 0.895 <= r <= 0.905) / n, 4),
        }

    ministries = [
        {"ministry": m, **summarize(rs)}
        for m, rs in by_ministry.items() if len(rs) >= MIN_PAIRS_FOR_MINISTRY
    ]
    ministries.sort(key=lambda x: -x["share_above_115"])

    years = [
        {"year": y, **summarize(rs)}
        for y, rs in by_year.items() if len(rs) >= 10
    ]
    years.sort(key=lambda x: x["year"])

    eras = [{"era": e, **summarize(rs)} for e, rs in by_era.items() if rs]
    eras.sort(key=lambda x: ERA_NAMES.index(x["era"]))

    return ministries, years, eras


def main(items_path, contracts_dir, out_path):
    plan = {}
    plan_rows = 0
    with open_batch(items_path) as fh:
        for line in fh:
            r = json.loads(line)
            plan_rows += 1
            k = norm_ref(r.get("package_no"))
            if k and r.get("estimated_cost_bdt"):
                plan.setdefault(k, r)

    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)

    contracts = list(load_contracts(contracts_dir))
    contracts_seen = len(contracts)

    # A package reference is generic -- office shorthand, a bare number, a
    # short lot label -- if it shows up under contracts from more than a few
    # different procuring entities nationally (a real package code belongs
    # to one project), OR if it's simply too short to be trusted even at low
    # usage counts (a short label can coincide by chance without ever
    # crossing the spread test).
    ref_entities = defaultdict(set)
    for c in contracts:
        k = norm_ref(c.get("package_ref"))
        if k:
            ref_entities[k].add(c.get("procuring_entity_id"))
    generic_keys = {k for k, pes in ref_entities.items() if len(pes) > GENERIC_PE_SPREAD}
    generic_keys |= {k for k in ref_entities if len(k) < MIN_REF_LEN}

    # A handful of surviving matches still come in at ratios like 90,000x --
    # not a real procurement outcome by any reading, but a decimal/unit slip
    # on one side of the source data or a package number reused across two
    # completely different jobs at the same office. No legitimate estimate-
    # to-award relationship plausibly differs by more than an order of
    # magnitude, so these are dropped rather than trusted.
    SANITY_RATIO_MIN, SANITY_RATIO_MAX = 0.1, 10

    pairs = []
    pairs_excluded_generic = 0
    pairs_excluded_sanity = 0
    for c in contracts:
        k = norm_ref(c.get("package_ref"))
        p = plan.get(k)
        if not (p and c.get("value_bdt") and p["estimated_cost_bdt"] > 0):
            continue
        if k in generic_keys:
            pairs_excluded_generic += 1
            continue
        r = c["value_bdt"] / p["estimated_cost_bdt"]
        if not (SANITY_RATIO_MIN <= r <= SANITY_RATIO_MAX):
            pairs_excluded_sanity += 1
            continue
        pairs.append((p, c))

    ratios = sorted(c["value_bdt"] / p["estimated_cost_bdt"] for p, c in pairs)

    def q(f):
        return round(ratios[min(int(len(ratios) * f), len(ratios) - 1)], 4) if ratios else None

    # Ratio distribution, bucketed for a readable chart.
    buckets = Counter()
    for r in ratios:
        if r < 0.7: buckets["<70%"] += 1
        elif r < 0.85: buckets["70-85%"] += 1
        elif r < 0.95: buckets["85-95%"] += 1
        elif r <= 1.0: buckets["95-100%"] += 1
        elif r <= 1.15: buckets["100-115%"] += 1
        else: buckets[">115%"] += 1

    # A fine 1-percentage-point histogram over the same ratios. The coarse
    # buckets above hide the actual story: competitive price discovery would
    # give a smooth spread, but the real distribution has narrow spikes on
    # round discounts (notably exactly 10% and 5% below the estimate), which
    # is the signature of a discount being applied by convention rather than
    # arrived at by bidding.
    fine = Counter()
    for r in ratios:
        if 0.6 <= r <= 1.2:
            fine[round(round(r, 2), 2)] += 1

    # The overrun tail, banded rather than at 1-point resolution: unlike the
    # discount side, there's no round-number convention to reveal here, so a
    # fine histogram would just be sparse and noisy. Widening bands toward
    # the far tail keeps every band populated enough to read.
    overrun_bands = Counter()
    for r in ratios:
        if r <= 1.0: continue
        elif r <= 1.05: overrun_bands["100-105%"] += 1
        elif r <= 1.10: overrun_bands["105-110%"] += 1
        elif r <= 1.15: overrun_bands["110-115%"] += 1
        elif r <= 1.25: overrun_bands["115-125%"] += 1
        elif r <= 1.50: overrun_bands["125-150%"] += 1
        elif r <= 2.00: overrun_bands["150-200%"] += 1
        else: overrun_bands[">200%"] += 1

    def band(lo, hi):
        n = sum(1 for r in ratios if lo <= r <= hi)
        return {"count": n, "share": round(n / len(ratios), 4) if ratios else 0}

    discount_spikes = {
        "at_10pct_below": band(0.895, 0.905),
        "at_5pct_below": band(0.945, 0.955),
        "at_15pct_below": band(0.845, 0.855),
        "exactly_at_estimate": band(0.999, 1.001),
    }

    transitions = Counter()
    looser = tighter = same = 0
    for p, c in pairs:
        pm, am = p.get("planned_method"), c.get("procurement_method")
        if not pm or not am:
            continue
        transitions[f"{pm}->{am}"] += 1
        if pm == am:
            same += 1
        elif OPENNESS.get(am, 0) < OPENNESS.get(pm, 0):
            looser += 1          # planned open, bought less openly
        else:
            tighter += 1

    overruns = [c["value_bdt"] / p["estimated_cost_bdt"] for p, c in pairs if c["value_bdt"] > p["estimated_cost_bdt"]]
    over_115 = [r for r in overruns if r > 1.15]
    overrun_summary = {
        "count_above_estimate": len(overruns),
        "count_above_115": len(over_115),
        "share_above_115_of_matched": round(len(over_115) / len(pairs), 4) if pairs else 0,
        "median_ratio_above_115": round(statistics.median(over_115), 4) if over_115 else None,
        "total_extra_bdt": round(sum(
            c["value_bdt"] - p["estimated_cost_bdt"] for p, c in pairs
            if c["value_bdt"] / p["estimated_cost_bdt"] > 1.15), 2),
    }

    biggest_overruns = sorted(
        [{
            "package_no": p.get("package_no"),
            "description": (p.get("package_description") or p.get("project_name") or "")[:150],
            "estimated_cost_bdt": p["estimated_cost_bdt"],
            "awarded_bdt": c["value_bdt"],
            "ratio": round(c["value_bdt"] / p["estimated_cost_bdt"], 3),
            "awarded_to": c.get("awarded_to"),
            "planned_method": p.get("planned_method"),
            "actual_method": c.get("procurement_method"),
        } for p, c in pairs if c["value_bdt"] > p["estimated_cost_bdt"]],
        key=lambda x: -(x["awarded_bdt"] - x["estimated_cost_bdt"]))[:20]

    downgrades = sorted(
        [{
            "package_no": p.get("package_no"),
            "description": (p.get("package_description") or p.get("project_name") or "")[:150],
            "planned_method": p.get("planned_method"),
            "actual_method": c.get("procurement_method"),
            "awarded_bdt": c["value_bdt"],
            "awarded_to": c.get("awarded_to"),
        } for p, c in pairs
            if p.get("planned_method") and c.get("procurement_method")
            and OPENNESS.get(c["procurement_method"], 0) < OPENNESS.get(p["planned_method"], 0)],
        key=lambda x: -(x["awarded_bdt"] or 0))[:20]

    ministries, years, eras = ministry_and_year_breakdown(pairs, dims)

    payload = {
        "meta": {
            "plan_line_items": plan_rows,
            "plan_packages_with_estimate": len(plan),
            "contracts_scanned": contracts_seen,
            "matched_pairs": len(pairs),
            "match_rate_of_plan": round(len(pairs) / len(plan), 4) if plan else 0,
            "generic_refs_excluded": len(generic_keys),
            "pairs_excluded_generic": pairs_excluded_generic,
            "pairs_excluded_sanity": pairs_excluded_sanity,
        },
        "award_vs_estimate": {
            "median_ratio": round(statistics.median(ratios), 4) if ratios else None,
            "p10": q(0.10), "p25": q(0.25), "p75": q(0.75), "p90": q(0.90),
            "share_above_estimate": round(sum(1 for r in ratios if r > 1) / len(ratios), 4) if ratios else None,
            "buckets": dict(buckets),
            "fine_histogram": {f"{k:.2f}": v for k, v in sorted(fine.items())},
            "overrun_bands": dict(overrun_bands),
            "discount_spikes": discount_spikes,
            "overrun_summary": overrun_summary,
        },
        "method_change": {
            "unchanged": same,
            "less_open_than_planned": looser,
            "more_open_than_planned": tighter,
            "top_transitions": dict(transitions.most_common(15)),
        },
        "biggest_overruns": biggest_overruns,
        "biggest_openness_downgrades": downgrades,
        "cost_structure": {
            "by_ministry": ministries,
            "by_year": years,
            "by_era": eras,
            "min_pairs_for_ministry": MIN_PAIRS_FOR_MINISTRY,
        },
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    m, a, mc = payload["meta"], payload["award_vs_estimate"], payload["method_change"]
    print(f"{m['plan_line_items']:,} plan line items -> {m['matched_pairs']:,} matched to awards "
          f"({100*m['match_rate_of_plan']:.1f}% of planned packages), "
          f"{m['pairs_excluded_generic']:,} excluded as generic-reference false matches, "
          f"{m['pairs_excluded_sanity']:,} excluded as implausible ratios")
    if ratios:
        print(f"award/estimate median {a['median_ratio']}, {100*a['share_above_estimate']:.1f}% came in above estimate")
        for k, v in a["discount_spikes"].items():
            print(f"  {k}: {v['count']:,} ({100*v['share']:.1f}%)")
        os_ = a["overrun_summary"]
        print(f"  overrun >115%: {os_['count_above_115']:,} ({100*os_['share_above_115_of_matched']:.1f}% of matched), "
              f"৳{os_['total_extra_bdt']/1e7:,.1f} crore above estimate on those alone")
    print(f"method: {mc['unchanged']} unchanged, {mc['less_open_than_planned']} less open than planned, "
          f"{mc['more_open_than_planned']} more open")
    print(f"cost structure: {len(ministries)} ministries with >={MIN_PAIRS_FOR_MINISTRY}+ matched pairs, "
          f"{len(years)} years with 10+")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
