#!/usr/bin/env python3
"""
Bucket the eExperience (eCMS) archive by year and dimension-encode the
administrative hierarchy -- same reasoning as build_contracts.py and
build_tenders.py. A first version of this wrote one flat data/ecms.json with
everything in it and came out to 138MB: `title` (free text describing the
work) was 45% of that on its own, and division/organization/procuring_entity
text repeated per row another 24%. This buckets by contract_start_date year,
resolves the hierarchy to small integer IDs, and caps title length -- the
same fix, applied a third time now that the pattern is obvious.

    python3 build_ecms.py <raw/ecms.jsonl> <data/ecms/>
"""
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dates import parse_dmy


def open_batch(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)

TITLE_MAX = 160


class Dimension:
    def __init__(self):
        self._id_of = {}
        self.names = []

    def id_of(self, name):
        if not name:
            return None
        if name not in self._id_of:
            self._id_of[name] = len(self.names)
            self.names.append(name)
        return self._id_of[name]


def parse_amount(raw):
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return None


def truncate(text, n=TITLE_MAX):
    if not text or len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] + "…"


def main(raw_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    divisions, orgs, entities = Dimension(), Dimension(), Dimension()
    by_year = defaultdict(list)

    with open_batch(raw_path) as fh:
        for line in fh:
            r = json.loads(line)
            d = parse_dmy(r.get("contract_start_date"))
            year = d.year if d else "unknown"
            by_year[year].append({
                "tender_id": r.get("tender_id"),
                "app_id": r.get("app_id"),
                "title": truncate(r.get("title")),
                "division_id": divisions.id_of(r.get("division")),
                "organization_id": orgs.id_of(r.get("organization")),
                "procuring_entity_id": entities.id_of(r.get("procuring_entity")),
                "procurement_nature": r.get("procurement_nature"),
                "procurement_type": r.get("procurement_type"),
                "procurement_method": r.get("procurement_method"),
                "awarded_to": r.get("awarded_to"),
                "company_unique_id": r.get("company_unique_id"),
                "contract_amount": parse_amount(r.get("contract_amount")),
                "contract_start_date": r.get("contract_start_date"),
                "contract_end_date": r.get("contract_end_date"),
                "work_status": r.get("work_status"),
            })

    for year, records in by_year.items():
        with open(os.path.join(out_dir, f"{year}.json"), "w") as fh:
            json.dump(records, fh, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(out_dir, "dimensions.json"), "w") as fh:
        json.dump({
            "divisions": divisions.names, "organizations": orgs.names,
            "procuring_entities": entities.names,
        }, fh, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in by_year.values())
    by_status = Counter(r["work_status"] for records in by_year.values() for r in records)
    by_nature = Counter(r["procurement_nature"] for records in by_year.values() for r in records)

    summary = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/SearcheCMS.jsp",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": total,
            "years": sorted(str(y) for y in by_year),
        },
        "by_work_status": dict(by_status),
        "by_procurement_nature": dict(by_nature),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    print(f"{total} eExperience records across {len(by_year)} year-buckets -> {out_dir}")
    print(f"work status: {dict(by_status)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
