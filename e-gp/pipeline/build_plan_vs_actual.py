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

    python3 build_plan_vs_actual.py <raw/app_items.jsonl> <data/contracts/> <out.json>
"""
import glob
import gzip
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

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

    pairs = []
    contracts_seen = 0
    for c in load_contracts(contracts_dir):
        contracts_seen += 1
        p = plan.get(norm_ref(c.get("package_ref")))
        if p and c.get("value_bdt") and p["estimated_cost_bdt"] > 0:
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

    payload = {
        "meta": {
            "plan_line_items": plan_rows,
            "plan_packages_with_estimate": len(plan),
            "contracts_scanned": contracts_seen,
            "matched_pairs": len(pairs),
            "match_rate_of_plan": round(len(pairs) / len(plan), 4) if plan else 0,
        },
        "award_vs_estimate": {
            "median_ratio": round(statistics.median(ratios), 4) if ratios else None,
            "p10": q(0.10), "p25": q(0.25), "p75": q(0.75), "p90": q(0.90),
            "share_above_estimate": round(sum(1 for r in ratios if r > 1) / len(ratios), 4) if ratios else None,
            "buckets": dict(buckets),
            "fine_histogram": {f"{k:.2f}": v for k, v in sorted(fine.items())},
            "discount_spikes": discount_spikes,
        },
        "method_change": {
            "unchanged": same,
            "less_open_than_planned": looser,
            "more_open_than_planned": tighter,
            "top_transitions": dict(transitions.most_common(15)),
        },
        "biggest_overruns": biggest_overruns,
        "biggest_openness_downgrades": downgrades,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    m, a, mc = payload["meta"], payload["award_vs_estimate"], payload["method_change"]
    print(f"{m['plan_line_items']:,} plan line items -> {m['matched_pairs']:,} matched to awards "
          f"({100*m['match_rate_of_plan']:.1f}% of planned packages)")
    if ratios:
        print(f"award/estimate median {a['median_ratio']}, {100*a['share_above_estimate']:.1f}% came in above estimate")
        for k, v in a["discount_spikes"].items():
            print(f"  {k}: {v['count']:,} ({100*v['share']:.1f}%)")
    print(f"method: {mc['unchanged']} unchanged, {mc['less_open_than_planned']} less open than planned, "
          f"{mc['more_open_than_planned']} more open")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
