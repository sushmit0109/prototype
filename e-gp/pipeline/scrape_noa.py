#!/usr/bin/env python3
"""
Crawl the eContracts (awarded contracts) list -- SearchNOA.jsp / SearchNoaServlet.

Unlike the debarment register, this list carries real per-record IDs
(tenderid, pkgLotId) and is sorted newest-first by contract signing date, so
it supports both a full backfill and a cheap incremental update: crawl from
page 1 and stop once a page's records are all already known.

The one search page (blank keyword, size=1000) turns out to carry everything
this pipeline's flagging step needs -- tender ID, ministry, procuring entity,
district, contract signing date, awardee, value -- directly in the row. The
full ~872K-record history is ~872 requests at size=1000, a couple of minutes,
not the per-record detail-page crawl (ViewAwardedContracts.jsp) originally
assumed necessary. Detail pages add beneficial-ownership and project-code
fields the list doesn't have; those are fetched separately, and only for
records that matter (see scrape_noa_detail.py), not all 872K.

    python3 scrape_noa.py <out.jsonl> [--pages N] [--stop-known <ids-file>]

--pages N caps how many pages to fetch (testing / incremental early stop).
--stop-known <ids-file> stops once a full page's tender_ids are all present
in that file (one id per line) -- the incremental-update mode.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import common

PAGE_SIZE = 1000

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
LINK_RE = re.compile(
    r'href="/resources/common/ViewAwardedContracts\.jsp\?pkgLotId=(\d+)&(?:amp;)?tenderid=(\d+)"'
    r'[^>]*>([^<]*)</a>\s*(?:<br\s*/?>)?\s*<span class="more">\s*(.*?)\s*</span>\s*(.*)$',
    re.S,
)


def clean(html_fragment):
    text = TAG_RE.sub(" ", html_fragment)
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return WS_RE.sub(" ", text).strip()


def split_br(html_fragment):
    parts = re.split(r"<br\s*/?>", html_fragment, flags=re.I)
    return [clean(p) for p in parts if clean(p)]


def parse_row(cells_html):
    if len(cells_html) < 8:
        return None
    _, ministry_html, tender_html, pe_html, district, signing_date, awarded_to, value = cells_html[:8]

    ministry_parts = split_br(ministry_html)
    ministry = ministry_parts[0] if ministry_parts else None
    division = ministry_parts[1] if len(ministry_parts) > 1 else None

    pe_parts = split_br(pe_html)
    procuring_entity = pe_parts[0] if pe_parts else None
    procurement_method = pe_parts[1] if len(pe_parts) > 1 else None

    m = LINK_RE.search(tender_html)
    if not m:
        return None
    pkg_lot_id, tender_id, link_text, description, trailing = m.groups()
    link_text = clean(link_text)
    tender_id_display, _, package_ref = link_text.partition(", ")

    return {
        "tender_id": tender_id,
        "pkg_lot_id": pkg_lot_id,
        "package_ref": package_ref or link_text,
        "description": clean(description),
        "advertisement_raw": clean(trailing),
        "ministry": ministry,
        "division": division,
        "procuring_entity": procuring_entity,
        "procurement_method": procurement_method,
        "district": clean(district),
        "contract_signing_date": clean(signing_date),
        "awarded_to": clean(awarded_to),
        "value_crore_bdt": clean(value),
    }


def fetch_page(page_no):
    body = common.post("/SearchNoaServlet", {
        "keyword": "", "pageNo": page_no, "size": PAGE_SIZE,
    })
    total_pages_m = re.search(r'id="totalPages"\s+value="(\d+)"', body)
    total_pages = int(total_pages_m.group(1)) if total_pages_m else 1

    records = []
    for row in ROW_RE.findall(body):
        cells = CELL_RE.findall(row)
        rec = parse_row(cells)
        if rec:
            records.append(rec)
    return records, total_pages


def crawl_incremental(out_path, known_ids):
    """Sequential, page by page, stopping at the first already-known record.

    The list is newest-first, so once we hit one known tender_id, every
    record after it (rest of this page, and every later page) must already
    be known too. Runs one page at a time rather than the full crawl's
    thread pool -- an incremental run is a handful of pages at most, and
    knowing where to stop before fetching is the entire point.
    """
    common.bootstrap()
    page_no = 1
    total_written = 0
    with open(out_path, "w") as fh:
        while True:
            records, total_pages = fetch_page(page_no)
            new_records = []
            hit_known = False
            for rec in records:
                if rec["tender_id"] in known_ids:
                    hit_known = True
                    break
                new_records.append(rec)

            for rec in new_records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total_written += len(new_records)
            print(f"page {page_no}/{total_pages}: {len(new_records)} new"
                  + (" (hit known record, stopping)" if hit_known else ""))

            if hit_known or page_no >= total_pages:
                break
            page_no += 1

    print(f"\nwrote {total_written} new contract records -> {out_path}")


def crawl_full(out_path, max_pages=None):
    common.bootstrap()
    first, total_pages = fetch_page(1)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    print(f"page 1/{total_pages}: {len(first)} records")

    with open(out_path, "w") as fh:
        def write(records):
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        write(first)
        remaining = range(2, total_pages + 1)
        total_written = len(first)
        with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
            for page_no, (recs, _) in zip(remaining, pool.map(fetch_page, remaining)):
                print(f"page {page_no}/{total_pages}: {len(recs)} records")
                write(recs)
                total_written += len(recs)

    print(f"\nwrote {total_written} contract records -> {out_path}")


def main(out_path, max_pages=None, stop_known_path=None):
    if stop_known_path:
        try:
            with open(stop_known_path) as fh:
                known_ids = {line.strip() for line in fh if line.strip()}
        except FileNotFoundError:
            known_ids = set()
        crawl_incremental(out_path, known_ids)
    else:
        crawl_full(out_path, max_pages)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--pages=")), None)
    stop_known = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--stop-known=")), None)
    main(args[0], pages, stop_known)
