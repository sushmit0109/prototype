#!/usr/bin/env python3
"""
Turn the raw debarment archive into the JSON the dashboard reads.

Two things happen here that the source itself doesn't give you. First, reason
records get tagged into a handful of categories by keyword -- there is no
category field in the source, "Reasons" is free text written by whichever
office filed the debarment. Second, each record gets a severity tier from the
combination of how broad its scope is (a Single Tender ban is not a
nationwide e-GP Portal ban), how long it runs, and whether the same company
has been debarred more than once. Not all debarments are equal; this is the
first pass at saying by how much.

    python3 build_site.py <raw/debarments.jsonl> <data/debarments.json>
"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from dates import parse_dmy
from entity import normalize_company

SCOPE_RANK = [
    ("e-GP Portal", 4, "Nationwide (e-GP Portal)"),
    ("Procuring Agency/Organization", 3, "Organization-wide"),
    ("Procuring Entity", 2, "Procuring Entity"),
    ("Project", 2, "Project"),
    ("Package", 1, "Package"),
    ("Single Tender", 1, "Single Tender"),
]

REASON_KEYWORDS = [
    ("collusion", ["collusive", "collusion", "cartel"]),
    ("forgery_false_document", ["forged", "forgery", "false document", "fake document", "fabricat"]),
    ("fraud", ["fraud", "fraudulent"]),
    ("corruption", ["corrupt", "bribe", "bribery"]),
    ("non_performance", ["fail to perform", "non-performance", "failed to complete", "abandon"]),
    ("misrepresentation", ["misrepresent", "false information", "false statement"]),
]

def scope_score(scope_text, debarred_by_text):
    hay = f"{scope_text} {debarred_by_text}".lower()
    for needle, score, label in SCOPE_RANK:
        if needle.lower() in hay:
            return score, label
    return 1, "Unspecified"


def tag_reason(reason_text):
    hay = (reason_text or "").lower()
    tags = [tag for tag, kws in REASON_KEYWORDS if any(kw in hay for kw in kws)]
    return tags or ["unspecified"]


def duration_days(start, end):
    s, e = parse_dmy(start), parse_dmy(end)
    if not s or not e:
        return None
    return (e - s).days


def severity_tier(scope_pts, duration, repeat_count):
    pts = scope_pts
    if duration and duration >= 730:
        pts += 2
    elif duration and duration >= 365:
        pts += 1
    if repeat_count > 1:
        pts += 2
    if pts >= 6:
        return "critical"
    if pts >= 4:
        return "high"
    if pts >= 2:
        return "medium"
    return "low"


def main(raw_path, out_path):
    with open(raw_path) as fh:
        records = [json.loads(line) for line in fh]

    counts = Counter(normalize_company(r["company"]) for r in records)

    for r in records:
        key = normalize_company(r["company"])
        pts, scope_label = scope_score(r.get("scope", ""), r.get("debarred_by", ""))
        dur = duration_days(r.get("debar_start"), r.get("debar_end"))
        r["company_key"] = key
        r["scope_label"] = scope_label
        r["reason_tags"] = tag_reason(r.get("reason"))
        r["duration_days"] = dur
        r["repeat_offender_count"] = counts[key]
        r["severity"] = severity_tier(pts, dur, counts[key])

    by_severity = Counter(r["severity"] for r in records)
    by_reason = Counter(tag for r in records for tag in r["reason_tags"])
    repeat_offenders = sorted({
        r["company_key"]: r["company"] for r in records if counts[r["company_key"]] > 1
    }.values())

    payload = {
        "meta": {
            "source": "https://www.eprocure.gov.bd/resources/common/DebarmentRpt.jsp",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
        },
        "summary": {
            "by_severity": dict(by_severity),
            "by_reason": dict(by_reason),
            "repeat_offenders": repeat_offenders,
        },
        "records": records,
    }

    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"{len(records)} records -> {out_path}")
    print(f"severity: {dict(by_severity)}")
    print(f"repeat offenders: {len(repeat_offenders)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
