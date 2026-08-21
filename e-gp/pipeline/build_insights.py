#!/usr/bin/env python3
"""
Spending trends, vendor concentration and recurrence, procurement-method mix
-- the analysis that doesn't depend on the debarment register at all.

871K contracts is a lot to ship to a browser for this, so this precomputes
everything the dashboard's "Spending & vendors" section needs into one
compact data/insights.json: national spend by year, by ministry, and by
procurement method; and a vendor table with two signals worth having next to
each other -- how much a company has won in total, and how concentrated its
wins are with a single procuring entity (a vendor whose contracts are almost
all from one office is a very different story from one that wins broadly
across government, even at the same total value).

Also folds in the tender funnel, when data/tenders/ has been built: the
master tender list's own `status` field (Live / Being processed / Contract
Awarded / Cancelled / Re-Tendered / Rejected / Amendment stages) by publish
year -- a richer view than the portal's own funnel-counts page, which only
gives three buckets (invited/processing/awarded) with no historical trend.

    python3 build_insights.py <data/contracts/> <data/insights.json> [data/tenders/]
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from entity import normalize_company

SKIP_FILES = {"summary.json", "dimensions.json"}
DIRECT_METHODS = {"DPM"}  # Direct Procurement Method: no competitive bidding
TOP_N = 40
MIN_VENDOR_CONTRACTS_FOR_CONCENTRATION = 5


def load_dimensions(contracts_dir):
    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        return json.load(fh)


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in SKIP_FILES:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def build_funnel(tenders_dir):
    """Tenders by publish year x status, from the master tender list's own summary."""
    summary_path = os.path.join(tenders_dir, "summary.json")
    if not os.path.isfile(summary_path):
        return None
    with open(summary_path) as fh:
        tenders_summary = json.load(fh)

    by_year_status = defaultdict(lambda: defaultdict(int))
    for path in sorted(glob.glob(os.path.join(tenders_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        year = os.path.basename(path).removesuffix(".json")
        with open(path) as fh:
            for r in json.load(fh):
                by_year_status[year][r.get("status") or "Unknown"] += 1

    return {
        "record_count": tenders_summary["meta"]["record_count"],
        "by_status": tenders_summary["by_status"],
        "by_year_status": {y: dict(s) for y, s in sorted(by_year_status.items())},
    }


def main(contracts_dir, out_path, tenders_dir=None):
    dims = load_dimensions(contracts_dir)

    by_year = defaultdict(lambda: {"count": 0, "value_bdt": 0.0})
    by_year_method = defaultdict(lambda: defaultdict(lambda: {"count": 0, "value_bdt": 0.0}))
    by_ministry_year = defaultdict(lambda: defaultdict(lambda: {"count": 0, "value_bdt": 0.0}))
    by_district = defaultdict(lambda: {"count": 0, "value_bdt": 0.0})

    vendors = defaultdict(lambda: {
        "display_name": Counter(), "count": 0, "value_bdt": 0.0,
        "entities": Counter(), "ministries": Counter(), "years": set(),
    })

    total = 0
    for r in load_contracts(contracts_dir):
        total += 1
        year = (r.get("contract_signing_date") or "")[:4] or "unknown"
        value = r.get("value_bdt") or 0.0
        method = r.get("procurement_method") or "Unknown"
        ministry = dims["ministries"][r["ministry_id"]] if r.get("ministry_id") is not None else "Unknown"
        entity = dims["procuring_entities"][r["procuring_entity_id"]] if r.get("procuring_entity_id") is not None else "Unknown"
        district = r.get("district") or "Unknown"

        by_year[year]["count"] += 1
        by_year[year]["value_bdt"] += value
        by_year_method[year][method]["count"] += 1
        by_year_method[year][method]["value_bdt"] += value
        by_ministry_year[ministry][year]["count"] += 1
        by_ministry_year[ministry][year]["value_bdt"] += value
        by_district[district]["count"] += 1
        by_district[district]["value_bdt"] += value

        vkey = normalize_company(r.get("awarded_to"))
        if not vkey:
            continue
        v = vendors[vkey]
        v["display_name"][r.get("awarded_to")] += 1
        v["count"] += 1
        v["value_bdt"] += value
        v["entities"][entity] += 1
        v["ministries"][ministry] += 1
        v["years"].add(year)

    vendor_rows = []
    for key, v in vendors.items():
        top_entity, top_entity_n = v["entities"].most_common(1)[0]
        vendor_rows.append({
            "company_key": key,
            "company": v["display_name"].most_common(1)[0][0],
            "count": v["count"],
            "value_bdt": round(v["value_bdt"], 2),
            "distinct_procuring_entities": len(v["entities"]),
            "distinct_ministries": len(v["ministries"]),
            "years_active": len(v["years"]),
            "top_entity": top_entity,
            "top_entity_share": round(top_entity_n / v["count"], 3),
        })

    top_by_value = sorted(vendor_rows, key=lambda v: -v["value_bdt"])[:TOP_N]
    top_by_count = sorted(vendor_rows, key=lambda v: -v["count"])[:TOP_N]
    concentrated = sorted(
        (v for v in vendor_rows
         if v["count"] >= MIN_VENDOR_CONTRACTS_FOR_CONCENTRATION and v["top_entity_share"] >= 0.8),
        key=lambda v: -v["value_bdt"],
    )[:TOP_N]

    ministry_totals = Counter()
    for ministry, years in by_ministry_year.items():
        ministry_totals[ministry] = sum(y["value_bdt"] for y in years.values())

    payload = {
        "meta": {
            "record_count": total,
            "distinct_vendors": len(vendors),
        },
        "national_by_year": {
            y: {"count": s["count"], "value_bdt": round(s["value_bdt"], 2)}
            for y, s in sorted(by_year.items())
        },
        "procurement_method_by_year": {
            y: {m: {"count": s["count"], "value_bdt": round(s["value_bdt"], 2)} for m, s in methods.items()}
            for y, methods in sorted(by_year_method.items())
        },
        "top_ministries_by_value": [
            {"ministry": m, "value_bdt": round(v, 2)} for m, v in ministry_totals.most_common(20)
        ],
        "ministry_by_year": {
            m: {y: {"count": s["count"], "value_bdt": round(s["value_bdt"], 2)} for y, s in years.items()}
            for m, years in sorted(by_ministry_year.items(), key=lambda kv: -ministry_totals[kv[0]])[:20]
        },
        "top_districts_by_value": sorted(
            [{"district": d, "count": s["count"], "value_bdt": round(s["value_bdt"], 2)}
             for d, s in by_district.items()],
            key=lambda r: -r["value_bdt"],
        )[:20],
        "top_vendors_by_value": top_by_value,
        "top_vendors_by_count": top_by_count,
        "concentrated_vendors": concentrated,
        "tender_funnel": build_funnel(tenders_dir) if tenders_dir else None,
    }

    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{total} contracts, {len(vendors)} distinct vendors -> {out_path}")
    print(f"top vendor by value: {top_by_value[0]['company']} (BDT {top_by_value[0]['value_bdt']:,.0f})")
    print(f"{len(concentrated)} vendors with >=80% of contracts from one procuring entity "
          f"(>= {MIN_VENDOR_CONTRACTS_FOR_CONCENTRATION} contracts)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
