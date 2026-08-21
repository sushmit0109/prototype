#!/usr/bin/env python3
"""
Crawl the full debarment register (DebarmentRpt.jsp / InitDebarment).

The portal lists every debarred tenderer/consultant, ongoing and expired,
behind a single POST servlet -- no stable ID scheme, no direct per-record
URLs, just page N of a keyword-less search with statusTab=All. It's ~1,030
records as of writing (versus ~1.1M tenders), so this source is re-crawled in
full on every run rather than diffed incrementally.

    python3 scrape_debarment.py <out.jsonl>
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import common

PAGE_SIZE = 100

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
PERIOD_RE = re.compile(
    r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+to\s+(\d{1,2}-[A-Za-z]{3}-\d{4})\s*(?:\((.*)\))?\s*$",
    re.S,
)

SEARCH_DEFAULTS = {
    "searchFor": "company", "cmpName": "", "like": "",
    "firNameSearch": "", "lasNameSearch": "", "firName": "", "lastName": "",
    "dtFrom": "", "dtTo": "", "cntry": "", "state": "",
    "statusTab": "All", "departmentId": "", "officeId": "",
    "action": "getDebarListCommon",
}


def clean(html_fragment):
    text = TAG_RE.sub(" ", html_fragment)
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return WS_RE.sub(" ", text).strip()


def split_period(raw):
    """'12-Jul-2026 to 11-Jul-2027 (Stay Order ...)' -> (start, end, note)."""
    m = PERIOD_RE.match(raw.strip())
    if not m:
        return None, None, (raw or None)
    return m.group(1), m.group(2), m.group(3)


def fetch_page(page_no):
    body = common.post("/InitDebarment", {
        "pageNo": page_no, "size": PAGE_SIZE, **SEARCH_DEFAULTS,
    })
    total_pages_m = re.search(r'id="totalPages"\s+value="(\d+)"', body)
    total_pages = int(total_pages_m.group(1)) if total_pages_m else 1

    records = []
    for row in ROW_RE.findall(body):
        cells = [clean(c) for c in CELL_RE.findall(row)]
        if len(cells) < 8:
            continue
        _, company, country, address, debarred_by, period_raw, scope, reason = cells[:8]
        start, end, note = split_period(period_raw)
        records.append({
            "company": company,
            "country": country,
            "address": address,
            "debarred_by": debarred_by,
            "debar_start": start,
            "debar_end": end,
            "stay_order_note": note,
            "scope": scope,
            "reason": reason,
        })
    return records, total_pages


def main(out_path):
    common.bootstrap()
    first, total_pages = fetch_page(1)
    print(f"page 1/{total_pages}: {len(first)} records")

    pages = {1: first}
    remaining = range(2, total_pages + 1)
    with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
        for page_no, (recs, _) in zip(remaining, pool.map(fetch_page, remaining)):
            print(f"page {page_no}/{total_pages}: {len(recs)} records")
            pages[page_no] = recs

    records = [rec for page_no in sorted(pages) for rec in pages[page_no]]

    with open(out_path, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(records)} debarment records -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../raw/debarments.jsonl")
