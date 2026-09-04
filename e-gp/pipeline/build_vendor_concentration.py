#!/usr/bin/env python3
"""
Per-district, per-month vendor concentration -- a second, independent way
a political favour could show up in this data besides "more total money":
the SAME total going to fewer, more favoured vendors. A district getting
the same envelope of e-GP spending both before and after an election could
still look very different underneath if one contractor started winning a
much larger share of it.

Herfindahl-Hirschman Index (HHI): sum of each vendor's squared share of a
district-month's total contract value, on a 0-1 scale (1.0 = one vendor
took everything; near 0 = many vendors split it evenly). Standard
antitrust/market-concentration statistic, repurposed here for public
contracting. Vendor identity uses entity.normalize_company -- the same key
build_growth.py and build_ownership.py use, so a company appearing under
minor spelling variants doesn't get double-counted as two "competitors"
artificially lowering its own HHI contribution.

A district-month with very few contracts produces a degenerate, meaningless
HHI (one contract = HHI of 1.0 by construction, regardless of anything
political) -- MIN_CONTRACTS_FOR_HHI filters those out rather than letting
them pollute the panel with noise that looks like "total concentration."

    python3 build_vendor_concentration.py <data/contracts/> <out.json>
"""
import glob
import json
import os
import sys
from collections import defaultdict

from districts import canonical, display_name
from entity import normalize_company

MIN_CONTRACTS_FOR_HHI = 3


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def main(contracts_dir, out_path):
    # (district, month) -> vendor_key -> {"value_bdt": float, "display": str}
    cells = defaultdict(lambda: defaultdict(lambda: {"value_bdt": 0.0, "display": None, "count": 0}))
    unmatched_districts = defaultdict(int)
    total_contracts = 0

    for c in load_contracts(contracts_dir):
        total_contracts += 1
        dist_key = canonical(c.get("district"))
        if not dist_key:
            unmatched_districts[c.get("district")] += 1
            continue
        month = (c.get("contract_signing_date") or "")[:7]
        if len(month) != 7:
            continue
        vkey = normalize_company(c.get("awarded_to"))
        if not vkey:
            continue
        cell = cells[(dist_key, month)][vkey]
        cell["value_bdt"] += c.get("value_bdt") or 0
        cell["display"] = cell["display"] or c.get("awarded_to")
        cell["count"] += 1

    districts = defaultdict(lambda: {"by_month": {}})
    n_cells_total, n_cells_kept = 0, 0
    for (dist_key, month), vendors in cells.items():
        n_cells_total += 1
        n_contracts = sum(v["count"] for v in vendors.values())
        if n_contracts < MIN_CONTRACTS_FOR_HHI:
            continue
        n_cells_kept += 1
        total_value = sum(v["value_bdt"] for v in vendors.values())
        if total_value <= 0:
            continue
        shares = sorted(((v["value_bdt"] / total_value, v) for v in vendors.values()), key=lambda x: -x[0])
        hhi = sum(s ** 2 for s, _ in shares)
        top_share, top_vendor = shares[0]
        districts[display_name(dist_key)]["by_month"][month] = {
            "hhi": round(hhi, 4),
            "n_vendors": len(vendors),
            "n_contracts": n_contracts,
            "total_value_bdt": round(total_value, 2),
            "top_vendor_share": round(top_share, 4),
            "top_vendor_display": top_vendor["display"],
        }

    payload = {
        "meta": {
            "method": "Herfindahl-Hirschman Index (sum of squared vendor value-shares, 0-1 scale) "
                      "per district per calendar month, vendor identity via entity.normalize_company. "
                      f"Cells with fewer than {MIN_CONTRACTS_FOR_HHI} contracts are dropped as too thin "
                      "to produce a meaningful concentration estimate (a single contract is HHI=1.0 by "
                      "construction, regardless of anything about the district).",
            "total_contracts": total_contracts,
            "district_month_cells_total": n_cells_total,
            "district_month_cells_kept": n_cells_kept,
            "min_contracts_for_hhi": MIN_CONTRACTS_FOR_HHI,
            "unmatched_district_strings": dict(unmatched_districts),
        },
        "districts": districts,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"{total_contracts:,} contracts -> {n_cells_kept:,}/{n_cells_total:,} district-months kept "
          f"(>= {MIN_CONTRACTS_FOR_HHI} contracts) across {len(districts)} districts -> {out_path}")
    if unmatched_districts:
        print(f"WARNING: {sum(unmatched_districts.values())} contracts with unmatched district strings: "
              f"{dict(unmatched_districts)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
