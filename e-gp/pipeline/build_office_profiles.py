#!/usr/bin/env python3
"""
Two views neither build_contracts.py nor build_insights.py gives you: what
each office actually buys (spend profile, by procurement nature where
known, and its top vendors), and which vendors work across more than one
ministry -- the "cross-departmental" vendors, since a company doing
business with a single ministry is unremarkable but one spanning several is
worth a second look regardless of any debarment angle.

Procurement nature (Goods/Works/Services) isn't on the awarded-contracts
list itself (SearchNOA doesn't carry it) -- it's joined in from the master
tender list by tender_id. Coverage is partial: the tender list only matches
53% of contract tender_ids (it has thinner coverage of pre-2018 tenders
than the award list does), so `procurement_nature` is null on the rest.
Read nature-based breakdowns as based on the ~53% that matched, not the
full corpus.

    python3 build_office_profiles.py <data/contracts/> <data/tenders/> <out.json>
"""
import glob
import json
import sys
from collections import Counter, defaultdict

from entity import normalize_company

TOP_N = 30


def load_records(data_dir):
    for path in sorted(glob.glob(f"{data_dir}/*.json")):
        if path.endswith(("summary.json", "dimensions.json")):
            continue
        with open(path) as fh:
            yield from json.load(fh)


def load_dims(data_dir):
    with open(f"{data_dir}/dimensions.json") as fh:
        return json.load(fh)


def main(contracts_dir, tenders_dir, out_path):
    tender_nature = {}
    for r in load_records(tenders_dir):
        if r.get("procurement_nature"):
            tender_nature[r["tender_id"]] = r["procurement_nature"]

    cdims = load_dims(contracts_dir)

    entity_stats = defaultdict(lambda: {
        "count": 0, "value_bdt": 0.0, "by_nature": Counter(), "vendors": Counter(), "ministry": None,
    })
    ministry_stats = defaultdict(lambda: {"count": 0, "value_bdt": 0.0, "by_nature": Counter(), "vendors": Counter()})
    vendor_ministries = defaultdict(lambda: {"display": Counter(), "ministries": Counter(), "value_bdt": 0.0, "count": 0})

    nature_matched = 0
    total = 0
    for r in load_records(contracts_dir):
        total += 1
        value = r.get("value_bdt") or 0.0
        entity = cdims["procuring_entities"][r["procuring_entity_id"]] if r.get("procuring_entity_id") is not None else "Unknown"
        ministry = cdims["ministries"][r["ministry_id"]] if r.get("ministry_id") is not None else "Unknown"
        nature = tender_nature.get(r["tender_id"])
        if nature:
            nature_matched += 1
        vendor_key = normalize_company(r.get("awarded_to"))

        es = entity_stats[entity]
        es["count"] += 1
        es["value_bdt"] += value
        es["ministry"] = ministry
        if nature:
            es["by_nature"][nature] += 1
        if vendor_key:
            es["vendors"][r.get("awarded_to")] += value

        ms = ministry_stats[ministry]
        ms["count"] += 1
        ms["value_bdt"] += value
        if nature:
            ms["by_nature"][nature] += 1
        if vendor_key:
            ms["vendors"][r.get("awarded_to")] += value

        if vendor_key:
            vm = vendor_ministries[vendor_key]
            vm["display"][r.get("awarded_to")] += 1
            vm["ministries"][ministry] += value
            vm["value_bdt"] += value
            vm["count"] += 1

    offices = sorted([
        {
            "procuring_entity": name, "ministry": s["ministry"],
            "count": s["count"], "value_bdt": round(s["value_bdt"], 2),
            "by_nature": dict(s["by_nature"]),
            "top_vendors": [{"company": c, "value_bdt": round(v, 2)} for c, v in s["vendors"].most_common(5)],
        }
        for name, s in entity_stats.items()
    ], key=lambda o: -o["value_bdt"])[:TOP_N]

    ministries = sorted([
        {
            "ministry": name, "count": s["count"], "value_bdt": round(s["value_bdt"], 2),
            "by_nature": dict(s["by_nature"]),
            "top_vendors": [{"company": c, "value_bdt": round(v, 2)} for c, v in s["vendors"].most_common(5)],
        }
        for name, s in ministry_stats.items()
    ], key=lambda m: -m["value_bdt"])

    cross_departmental = sorted(
        [
            {
                "company": vm["display"].most_common(1)[0][0],
                "value_bdt": round(vm["value_bdt"], 2),
                "count": vm["count"],
                "distinct_ministries": len(vm["ministries"]),
                "ministries": [{"ministry": m, "value_bdt": round(v, 2)} for m, v in vm["ministries"].most_common(10)],
            }
            for vm in vendor_ministries.values() if len(vm["ministries"]) >= 3
        ],
        key=lambda v: (-v["distinct_ministries"], -v["value_bdt"]),
    )[:TOP_N]

    payload = {
        "meta": {
            "record_count": total,
            "nature_matched": nature_matched,
            "nature_match_rate": round(nature_matched / total, 3) if total else 0,
        },
        "top_offices_by_value": offices,
        "ministries_by_value": ministries,
        "cross_departmental_vendors": cross_departmental,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{total} contracts, nature matched for {nature_matched} ({100*nature_matched/total:.1f}%)")
    print(f"{len(entity_stats)} distinct procuring entities, {len(cross_departmental)} cross-departmental vendors (>=3 ministries)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
