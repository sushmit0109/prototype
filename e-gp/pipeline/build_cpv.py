#!/usr/bin/env python3
"""
Trim the raw CPV category snapshot to what the dashboard needs: the top 25
categories by tender count, plus the true (non-overlapping) overall total
-- and, for those same top 25, the actual awarded contract value behind
each one, joined by tender_id against data/contracts.

Value coverage is necessarily partial: a category's tender_id list includes
tenders that are still live, cancelled, or otherwise never awarded, and
only awarded ones have a value at all. Reported per category so a reader
can see how much of a category's total is actually priced.

    python3 build_cpv.py <raw/cpv_categories.json> <data/contracts/> <out.json>
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

TOP_N = 25


def load_contract_values(contracts_dir):
    values = {}
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            for r in json.load(fh):
                if r.get("value_bdt"):
                    values[r["tender_id"]] = r["value_bdt"]
    return values


def main(raw_path, contracts_dir, out_path):
    with open(raw_path) as fh:
        raw = json.load(fh)
    contract_values = load_contract_values(contracts_dir)

    top = sorted(raw["categories"], key=lambda c: -c["count"])[:TOP_N]
    top_categories = []
    for c in top:
        tender_ids = c.get("tender_ids", [])
        matched = [contract_values[tid] for tid in tender_ids if tid in contract_values]
        top_categories.append({
            "name": c["name"],
            "count": c["count"],
            "by_era": c.get("by_era", {}),
            "value_bdt": round(sum(matched), 2),
            "awarded_matched": len(matched),
            "awarded_match_rate": round(len(matched) / len(tender_ids), 4) if tender_ids else 0,
        })

    payload = {
        "meta": {
            "source": raw["source"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "all_tenders": raw["all_tenders"],
            "all_tenders_by_era": raw.get("all_tenders_by_era", {}),
            "categories_tracked": len(raw["categories"]),
            "note": "A tender can carry more than one CPV category, so category "
                    "counts overlap and do not sum to all_tenders. value_bdt is "
                    "the sum of awarded contract value for that category's tenders "
                    "that were actually awarded -- see awarded_match_rate per category.",
        },
        "top_categories": top_categories,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"top {len(top)} of {len(raw['categories'])} CPV categories -> {out_path}")
    by_value = sorted(top_categories, key=lambda c: -c["value_bdt"])[:8]
    for c in by_value:
        print(f"  Tk {c['value_bdt']/1e7:>10,.0f} cr  ({100*c['awarded_match_rate']:.0f}% of tenders awarded)  {c['name']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
