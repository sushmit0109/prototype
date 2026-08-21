#!/usr/bin/env python3
"""
Bucket the raw master-tender-list archive by year, dimension-encode the
administrative hierarchy, and build the summary the dashboard reads --
same shape and same reasoning as build_contracts.py (see that file for why
free text gets dropped and ministry/PE become small integer IDs instead of
repeated strings).

This is also what makes the "invited vs awarded" funnel possible: it's the
only source that includes tenders that never got awarded (still Live,
Cancelled) -- SearchNOA only has the ones that were.

    python3 build_tenders.py <raw/tenders/> <data/tenders/>
"""
import glob
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

SKIP_FILES = set()
DATE_RE = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})")


def open_batch(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def parse_year(raw):
    m = DATE_RE.search(raw or "")
    if not m:
        return "unknown"
    try:
        return datetime.strptime(m.group(0), "%d-%b-%Y").year
    except ValueError:
        return "unknown"


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


def main(raw_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    by_year = defaultdict(list)
    seen_ids = set()
    dupes = 0

    ministries, divisions, orgs, entities = Dimension(), Dimension(), Dimension(), Dimension()

    batch_paths = sorted(glob.glob(os.path.join(raw_dir, "*.jsonl"))
                          + glob.glob(os.path.join(raw_dir, "*.jsonl.gz")))
    for path in batch_paths:
        with open_batch(path) as fh:
            for line in fh:
                rec = json.loads(line)
                key = rec["tender_id"]
                if key in seen_ids:
                    dupes += 1
                    continue
                seen_ids.add(key)

                year = parse_year(rec.get("publish_date"))
                by_year[year].append({
                    "tender_id": rec["tender_id"],
                    "package_ref": rec.get("package_ref"),
                    "status": rec.get("status"),
                    "procurement_nature": rec.get("procurement_nature"),
                    "ministry_id": ministries.id_of(rec.get("ministry")),
                    "division_id": divisions.id_of(rec.get("division")),
                    "organization_id": orgs.id_of(rec.get("organization")),
                    "procuring_entity_id": entities.id_of(rec.get("procuring_entity")),
                    "procurement_type": rec.get("procurement_type"),
                    "procurement_method": rec.get("procurement_method"),
                    "publish_date": rec.get("publish_date"),
                    "close_date": rec.get("close_date"),
                })

    for year, records in by_year.items():
        with open(os.path.join(out_dir, f"{year}.json"), "w") as fh:
            json.dump(records, fh, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(out_dir, "dimensions.json"), "w") as fh:
        json.dump({
            "ministries": ministries.names, "divisions": divisions.names,
            "organizations": orgs.names, "procuring_entities": entities.names,
        }, fh, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in by_year.values())
    by_status = Counter(r["status"] for records in by_year.values() for r in records)
    by_ministry = Counter()
    for records in by_year.values():
        for r in records:
            by_ministry[ministries.names[r["ministry_id"]] if r["ministry_id"] is not None else "Unknown"] += 1

    summary = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/AllTenders.jsp?h=t",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": total,
            "duplicate_records_skipped": dupes,
            "years": sorted(str(y) for y in by_year),
        },
        "by_year_count": {str(y): len(v) for y, v in sorted(by_year.items(), key=lambda kv: str(kv[0]))},
        "by_status": dict(by_status),
        "by_ministry_count": dict(by_ministry.most_common(50)),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    print(f"{total} tenders from {len(batch_paths)} raw batches, across {len(by_year)} year-buckets -> {out_dir}")
    print(f"status breakdown: {dict(by_status)}")
    if dupes:
        print(f"skipped {dupes} duplicate tender_id rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
