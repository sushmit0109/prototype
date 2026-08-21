#!/usr/bin/env python3
"""
Merge every raw contracts batch, bucket by year, and build the summary the
high-level dashboard reads.

raw/contracts/ is an append-only log: one file per crawl (the initial
backfill split into one gzipped file per year purely to stay under GitHub's
per-file size limits, then one small plain .jsonl per incremental daily run)
-- nothing already committed there is ever rewritten, so daily diffs stay
tiny. This is the step that turns that log into something usable: read every
batch, drop duplicate (tender_id, pkg_lot_id) rows (the incremental
crawler's own --stop-known early-stop should prevent most of these, but
build-time dedup is what actually guarantees no double-counting), and write
one data/contracts/<year>.json per year plus a summary.json.

The per-year JSON is NOT a straight dump of the raw record. A first pass at
this file wrote the full raw shape and produced 50-77MB *per year* -- the
free-text `description` field alone was 38% of that, and the ministry /
division / procuring-entity names (a small, repetitive vocabulary) another
27%, both spelled out in full on every single record. That's the textbook
case for an ontology: those three are dimension tables, not repeated
strings. This resolves them to small integer IDs (written once to
dimensions.json) and drops `description` and the other detail-page-only
fields from the bulk file entirely -- raw/ still has everything, verbatim,
for provenance.

    python3 build_contracts.py <raw/contracts/> <data/contracts/>
"""
import glob
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dates import parse_dmy


def clean_ministry(m):
    if not m:
        return m
    return re.sub(r"\s+and$", "", m.strip())


def parse_value(raw):
    try:
        return round(float(raw) * 1e7, 2)  # crore BDT -> BDT
    except (TypeError, ValueError):
        return None


def open_batch(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


class Dimension:
    """Name <-> small integer ID, so bulk records store an int, not a string."""

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

    ministries, divisions, entities = Dimension(), Dimension(), Dimension()

    batch_paths = sorted(glob.glob(os.path.join(raw_dir, "*.jsonl"))
                          + glob.glob(os.path.join(raw_dir, "*.jsonl.gz")))
    for path in batch_paths:
        with open_batch(path) as fh:
            for line in fh:
                rec = json.loads(line)
                key = (rec["tender_id"], rec["pkg_lot_id"])
                if key in seen_ids:
                    dupes += 1
                    continue
                seen_ids.add(key)

                d = parse_dmy(rec.get("contract_signing_date"))
                year = d.year if d else "unknown"
                by_year[year].append({
                    "tender_id": rec["tender_id"],
                    "pkg_lot_id": rec["pkg_lot_id"],
                    "package_ref": rec.get("package_ref"),
                    "ministry_id": ministries.id_of(clean_ministry(rec.get("ministry"))),
                    "division_id": divisions.id_of(rec.get("division")),
                    "procuring_entity_id": entities.id_of(rec.get("procuring_entity")),
                    "procurement_method": rec.get("procurement_method"),
                    "district": rec.get("district"),
                    "contract_signing_date": d.isoformat() if d else None,
                    "awarded_to": rec.get("awarded_to"),
                    "value_bdt": parse_value(rec.get("value_crore_bdt")),
                })

    for year, records in by_year.items():
        with open(os.path.join(out_dir, f"{year}.json"), "w") as fh:
            json.dump(records, fh, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(out_dir, "dimensions.json"), "w") as fh:
        json.dump({
            "ministries": ministries.names,
            "divisions": divisions.names,
            "procuring_entities": entities.names,
        }, fh, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in by_year.values())
    by_ministry = Counter()
    value_by_ministry = defaultdict(float)
    for records in by_year.values():
        for r in records:
            m = ministries.names[r["ministry_id"]] if r["ministry_id"] is not None else "Unknown"
            by_ministry[m] += 1
            if r["value_bdt"]:
                value_by_ministry[m] += r["value_bdt"]

    summary = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/SearchNOA.jsp",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": total,
            "duplicate_records_skipped": dupes,
            "years": sorted(str(y) for y in by_year),
        },
        "by_year_count": {str(y): len(v) for y, v in sorted(by_year.items(), key=lambda kv: str(kv[0]))},
        "by_ministry_count": dict(by_ministry.most_common(50)),
        "by_ministry_value_bdt": dict(sorted(value_by_ministry.items(), key=lambda kv: -kv[1])[:50]),
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)

    print(f"{total} contracts from {len(batch_paths)} raw batches, across {len(by_year)} year-buckets -> {out_dir}")
    print(f"dimensions: {len(ministries.names)} ministries, {len(divisions.names)} divisions, "
          f"{len(entities.names)} procuring entities")
    if dupes:
        print(f"skipped {dupes} duplicate (tender_id, pkg_lot_id) rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
