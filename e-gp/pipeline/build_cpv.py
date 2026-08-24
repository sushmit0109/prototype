#!/usr/bin/env python3
"""
Trim the raw CPV category snapshot to what the dashboard needs: the top 25
categories by tender count, plus the true (non-overlapping) overall total.
The raw file is already small and re-crawled in full each run, so this is
just a copy-and-trim rather than a real transform.

    python3 build_cpv.py <raw/cpv_categories.json> <out.json>
"""
import json
import sys
from datetime import datetime, timezone

TOP_N = 25


def main(raw_path, out_path):
    with open(raw_path) as fh:
        raw = json.load(fh)

    top = sorted(raw["categories"], key=lambda c: -c["count"])[:TOP_N]
    payload = {
        "meta": {
            "source": raw["source"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "all_tenders": raw["all_tenders"],
            "categories_tracked": len(raw["categories"]),
            "note": "A tender can carry more than one CPV category, so category "
                    "counts overlap and do not sum to all_tenders.",
        },
        "top_categories": [{"name": c["name"], "count": c["count"]} for c in top],
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"top {len(top)} of {len(raw['categories'])} CPV categories -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
