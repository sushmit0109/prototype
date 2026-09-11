#!/usr/bin/env python3
"""
Full ministry -> division -> office navigation, for readers who want one
specific office's buying habits rather than a national aggregate.
build_office_profiles.py already does this for the top 30 offices by value;
this covers all ~9,800 procuring entities that ever signed a contract, so a
reader can look up their own upazila's LGED office or a small district
hospital, not just the handful of billion-taka national agencies.

Two outputs, split for load size the same way contracts/tenders already are
sharded by year:

  <index_out>            -- one row per ministry, division and office (id,
                             name, parent ids, count, value_bdt). Small
                             enough to load eagerly: it drives the
                             ministry/division/office pickers and the
                             free-text office search.
  <offices_out_dir>/<ministry_id>.json
                          -- full profile for every office under that
                             ministry, fetched only when a reader picks it:
                             yearly trend, procurement-nature mix, top
                             vendors, top districts, and its largest
                             individual contracts.

A minority of offices appear under more than one division or ministry
across the years (reorganisations, or two spellings of a parent ministry
resolving to the same office) -- see MULTI_PARENT below. Each is filed
under whichever parent it worked with most often; this only ever
misattributes a small share of an office's own history, never another
office's.

Procurement nature (Goods/Works/Services) is joined from the master tender
list exactly as build_office_profiles.py and build_geo.py do it, with the
same partial (~53%) coverage -- read nature mixes as based on the matched
subset, not the office's full contract history.

    python3 build_office_explorer.py <data/contracts/> <data/tenders/> <office_index.json> <data/offices/>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from entity import normalize_company

TOP_VENDORS = 5
TOP_DISTRICTS = 5
TOP_CONTRACTS = 5


def load_records(data_dir):
    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def main(contracts_dir, tenders_dir, index_out, offices_out_dir):
    tender_nature = {}
    for r in load_records(tenders_dir):
        if r.get("procurement_nature"):
            tender_nature[r["tender_id"]] = r["procurement_nature"]

    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)
    ministry_names = dims["ministries"]
    division_names = dims["divisions"]
    entity_names = dims["procuring_entities"]

    offices = defaultdict(lambda: {
        "value_bdt": 0.0, "count": 0,
        "ministry_votes": Counter(), "division_votes": Counter(),
        "by_year": defaultdict(lambda: {"value_bdt": 0.0, "count": 0}),
        "nature": Counter(), "vendors": Counter(), "vendor_count": Counter(),
        "districts": Counter(),
        "contracts": [],
    })

    total = 0
    nature_matched = 0
    for c in load_records(contracts_dir):
        total += 1
        eid = c.get("procuring_entity_id")
        if eid is None:
            continue
        o = offices[eid]
        v = c.get("value_bdt") or 0.0
        o["value_bdt"] += v
        o["count"] += 1
        if c.get("ministry_id") is not None:
            o["ministry_votes"][c["ministry_id"]] += 1
        if c.get("division_id") is not None:
            o["division_votes"][c["division_id"]] += 1
        date = c.get("contract_signing_date") or ""
        if date:
            y = o["by_year"][date[:4]]
            y["value_bdt"] += v
            y["count"] += 1
        nature = tender_nature.get(c.get("tender_id"))
        if nature:
            nature_matched += 1
            o["nature"][nature] += 1
        vendor = c.get("awarded_to")
        if vendor and normalize_company(vendor):
            o["vendors"][vendor] += v
            o["vendor_count"][vendor] += 1
        if c.get("district"):
            o["districts"][c["district"]] += 1
        o["contracts"].append({
            "package_ref": c.get("package_ref"),
            "awarded_to": vendor,
            "value_bdt": v,
            "contract_signing_date": date or None,
        })

    ministry_agg = defaultdict(lambda: {"value_bdt": 0.0, "count": 0, "office_ids": set()})
    division_agg = defaultdict(lambda: {"value_bdt": 0.0, "count": 0, "office_ids": set(), "ministry_id": None})

    index_offices = []
    by_ministry_profiles = defaultdict(dict)

    for eid, o in offices.items():
        mid = o["ministry_votes"].most_common(1)[0][0] if o["ministry_votes"] else None
        did = o["division_votes"].most_common(1)[0][0] if o["division_votes"] else None
        name = entity_names[eid] if eid < len(entity_names) else f"Office #{eid}"

        index_offices.append({
            "id": eid, "name": name, "ministry_id": mid, "division_id": did,
            "value_bdt": round(o["value_bdt"], 2), "count": o["count"],
        })

        if mid is not None:
            ma = ministry_agg[mid]
            ma["value_bdt"] += o["value_bdt"]
            ma["count"] += o["count"]
            ma["office_ids"].add(eid)
        if did is not None:
            da = division_agg[did]
            da["value_bdt"] += o["value_bdt"]
            da["count"] += o["count"]
            da["office_ids"].add(eid)
            da["ministry_id"] = mid

        top_contracts = sorted(o["contracts"], key=lambda r: -(r["value_bdt"] or 0))[:TOP_CONTRACTS]
        for r in top_contracts:
            r["value_bdt"] = round(r["value_bdt"], 2)

        profile = {
            "value_bdt": round(o["value_bdt"], 2),
            "count": o["count"],
            "by_year": {y: {"value_bdt": round(v["value_bdt"], 2), "count": v["count"]}
                        for y, v in sorted(o["by_year"].items())},
            "by_nature": dict(o["nature"]),
            "top_vendors": [
                {"company": c, "value_bdt": round(v, 2), "count": o["vendor_count"][c]}
                for c, v in o["vendors"].most_common(TOP_VENDORS)
            ],
            "top_districts": [
                {"district": d, "count": n} for d, n in o["districts"].most_common(TOP_DISTRICTS)
            ],
            "top_contracts": top_contracts,
        }
        target = mid if mid is not None else "unknown"
        by_ministry_profiles[target][str(eid)] = profile

    index_ministries = sorted([
        {
            "id": mid, "name": ministry_names[mid] if mid < len(ministry_names) else f"Ministry #{mid}",
            "value_bdt": round(a["value_bdt"], 2), "count": a["count"], "office_count": len(a["office_ids"]),
        }
        for mid, a in ministry_agg.items()
    ], key=lambda m: -m["value_bdt"])

    index_divisions = sorted([
        {
            "id": did, "name": division_names[did] if did < len(division_names) else f"Division #{did}",
            "ministry_id": a["ministry_id"],
            "value_bdt": round(a["value_bdt"], 2), "count": a["count"], "office_count": len(a["office_ids"]),
        }
        for did, a in division_agg.items()
    ], key=lambda d: -d["value_bdt"])

    index_offices.sort(key=lambda o: -o["value_bdt"])

    os.makedirs(offices_out_dir, exist_ok=True)
    with open(index_out, "w") as fh:
        json.dump({
            "meta": {
                "generated_office_count": len(index_offices),
                "ministry_count": len(index_ministries),
                "division_count": len(index_divisions),
                "contracts_scanned": total,
                "nature_matched": nature_matched,
                "nature_match_rate": round(nature_matched / total, 4) if total else 0,
            },
            "ministries": index_ministries,
            "divisions": index_divisions,
            "offices": index_offices,
        }, fh, ensure_ascii=False, indent=1)

    for target, profiles in by_ministry_profiles.items():
        with open(os.path.join(offices_out_dir, f"{target}.json"), "w") as fh:
            json.dump(profiles, fh, ensure_ascii=False, indent=1)

    print(f"{total:,} contracts -> {len(index_offices):,} offices, {len(index_ministries)} ministries, "
          f"{len(index_divisions)} divisions")
    print(f"wrote -> {index_out} and {len(by_ministry_profiles)} per-ministry office-profile files in {offices_out_dir}/")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
