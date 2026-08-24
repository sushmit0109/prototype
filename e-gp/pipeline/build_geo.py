#!/usr/bin/env python3
"""
Contract spend and counts by district -- the data half of the geographic
finding (build_district_geo.py builds the map geometry itself, a one-off
step; this is the daily aggregation, run like every other build_*.py).

Per district: total value/count, an era breakdown (see eras.py) so the map
can be filtered by government, and the top ministry and vendor by value.

    python3 build_geo.py <data/contracts/> <out.json>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from districts import canonical, display_name
from eras import ERA_NAMES, era_of


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def main(contracts_dir, out_path):
    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)

    by_district = defaultdict(lambda: {
        "value_bdt": 0.0, "count": 0,
        "by_era": {e: {"value_bdt": 0.0, "count": 0} for e in ERA_NAMES},
        "ministries": Counter(), "ministry_value": Counter(),
        "vendors": Counter(),
    })
    unmatched = Counter()
    total_contracts = 0

    for c in load_contracts(contracts_dir):
        total_contracts += 1
        key = canonical(c.get("district"))
        if not key:
            unmatched[c.get("district")] += 1
            continue
        v = c.get("value_bdt") or 0
        d = by_district[key]
        d["value_bdt"] += v
        d["count"] += 1
        era = era_of(c.get("contract_signing_date"))
        if era:
            d["by_era"][era]["value_bdt"] += v
            d["by_era"][era]["count"] += 1
        mid = c.get("ministry_id")
        if mid is not None:
            ministry = dims["ministries"][mid]
            d["ministries"][ministry] += 1
            d["ministry_value"][ministry] += v
        if c.get("awarded_to"):
            d["vendors"][c["awarded_to"]] += v

    districts = {}
    for key, d in by_district.items():
        top_ministry = d["ministry_value"].most_common(1)
        top_vendor = d["vendors"].most_common(1)
        districts[display_name(key)] = {
            "value_bdt": round(d["value_bdt"], 2),
            "count": d["count"],
            "by_era": {e: {"value_bdt": round(v["value_bdt"], 2), "count": v["count"]}
                       for e, v in d["by_era"].items()},
            "top_ministry": top_ministry[0][0] if top_ministry else None,
            "top_vendor": top_vendor[0][0] if top_vendor else None,
        }

    payload = {
        "meta": {
            "contracts_scanned": total_contracts,
            "districts_mapped": len(districts),
            "unmatched_district_strings": dict(unmatched),
        },
        "districts": districts,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    ranked = sorted(districts.items(), key=lambda kv: -kv[1]["value_bdt"])
    print(f"{total_contracts:,} contracts -> {len(districts)} districts")
    if unmatched:
        print(f"WARNING: {sum(unmatched.values())} contracts with unmatched district strings: {dict(unmatched)}")
    for name, d in ranked[:5]:
        print(f"  {d['value_bdt']/1e7:>10,.0f} cr  {name}")
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
