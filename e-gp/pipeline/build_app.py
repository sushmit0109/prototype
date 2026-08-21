#!/usr/bin/env python3
"""
Build the Annual Procurement Plan dashboard JSON from the raw archive.

45,719 records across 18 financial years -- small enough for one flat
data/app_plans.json, no bucketing or dimension-encoding needed at this size.

    python3 build_app.py <raw/app_plans.jsonl> <data/app_plans.json>
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


def main(raw_path, out_path):
    with open(raw_path) as fh:
        records = [json.loads(line) for line in fh]

    by_year = Counter(r["financial_year"] for r in records)
    by_ministry_year = defaultdict(lambda: defaultdict(int))
    for r in records:
        by_ministry_year[r["ministry"] or "Unknown"][r["financial_year"]] += 1

    ministry_totals = Counter({m: sum(years.values()) for m, years in by_ministry_year.items()})

    payload = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/SearchAPP.jsp",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
            "financial_years": sorted(by_year),
        },
        "summary": {
            "by_financial_year": dict(sorted(by_year.items())),
            "top_ministries_by_project_count": dict(ministry_totals.most_common(20)),
        },
        "records": records,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))

    print(f"{len(records)} APP records across {len(by_year)} financial years -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
