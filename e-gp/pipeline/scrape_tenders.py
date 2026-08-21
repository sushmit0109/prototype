#!/usr/bin/env python3
"""
Crawl the master tender list -- AllTenders.jsp's underlying servlet,
/TenderDetailsServlet (funName=AllTenders).

This is the source SearchNOA can't give you: SearchNOA only lists tenders
that have already been AWARDED. This lists every tender regardless of
outcome -- Live (open for bids), Archive (closed), Cancel -- so it's what
lets the dashboard show the full funnel (invited -> processing -> awarded),
not just the awarded end of it. viewType=AllTenders is the one that returns
the complete set; Live/Archive/Cancel individually are subsets of it.

    python3 scrape_tenders.py <out.jsonl> [--pages N] [--stop-known <ids-file>]
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import common
from htmlrows import ROW_RE, CELL_RE, split_br_clean, total_pages

PAGE_SIZE = 1000

SEARCH_DEFAULTS = {
    "funName": "AllTenders", "viewType": "AllTenders",
    "departmentId": "", "office": "", "procNature": "", "procType": "",
    "procMethod": "", "tenderId": "", "refNo": "", "pubDtFrm": "", "pubDtTo": "",
    "closeDtFrm": "", "closeDtTo": "", "cpvCategory": "", "isFrame": "", "h": "t",
}


def parse_row(cells_html):
    if len(cells_html) < 6:
        return None
    _, id_cell, nature_cell, org_cell, method_cell, date_cell = cells_html[:6]

    id_parts = split_br_clean(id_cell)
    tender_id = id_parts[0] if id_parts else None
    package_ref = id_parts[1] if len(id_parts) > 1 else None
    status = id_parts[2] if len(id_parts) > 2 else None

    nature_parts = split_br_clean(nature_cell)
    procurement_nature = nature_parts[0] if nature_parts else None
    description = nature_parts[1] if len(nature_parts) > 1 else None

    org_parts = split_br_clean(org_cell)
    ministry = org_parts[0] if org_parts else None
    division = org_parts[1] if len(org_parts) > 1 else None
    organization = org_parts[2] if len(org_parts) > 2 else None
    procuring_entity = org_parts[3] if len(org_parts) > 3 else (org_parts[-1] if org_parts else None)

    method_parts = split_br_clean(method_cell)
    procurement_type = method_parts[0] if method_parts else None
    procurement_method = method_parts[1] if len(method_parts) > 1 else None

    date_parts = split_br_clean(date_cell)
    publish_date = date_parts[0] if date_parts else None
    close_date = date_parts[1] if len(date_parts) > 1 else None

    if not tender_id:
        return None
    return {
        "tender_id": tender_id,
        "package_ref": package_ref,
        "status": status,
        "procurement_nature": procurement_nature,
        "description": description,
        "ministry": ministry,
        "division": division,
        "organization": organization,
        "procuring_entity": procuring_entity,
        "procurement_type": procurement_type,
        "procurement_method": procurement_method,
        "publish_date": publish_date,
        "close_date": close_date,
    }


def fetch_page(page_no):
    body = common.post("/TenderDetailsServlet", {
        "pageNo": page_no, "size": PAGE_SIZE, **SEARCH_DEFAULTS,
    })
    records = []
    for row in ROW_RE.findall(body):
        rec = parse_row(CELL_RE.findall(row))
        if rec:
            records.append(rec)
    return records, total_pages(body)


def crawl_incremental(out_path, known_ids):
    common.bootstrap()
    page_no = 1
    total_written = 0
    with open(out_path, "w") as fh:
        while True:
            records, pages = fetch_page(page_no)
            new_records, hit_known = [], False
            for rec in records:
                if rec["tender_id"] in known_ids:
                    hit_known = True
                    break
                new_records.append(rec)
            for rec in new_records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total_written += len(new_records)
            print(f"page {page_no}/{pages}: {len(new_records)} new"
                  + (" (hit known record, stopping)" if hit_known else ""))
            if hit_known or page_no >= pages:
                break
            page_no += 1
    print(f"\nwrote {total_written} new tender records -> {out_path}")


def crawl_full(out_path, max_pages=None):
    common.bootstrap()
    first, pages = fetch_page(1)
    if max_pages:
        pages = min(pages, max_pages)
    print(f"page 1/{pages}: {len(first)} records")

    with open(out_path, "w") as fh:
        def write(records):
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        write(first)
        remaining = range(2, pages + 1)
        total_written = len(first)
        with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
            for page_no, (recs, _) in zip(remaining, pool.map(fetch_page, remaining)):
                print(f"page {page_no}/{pages}: {len(recs)} records")
                write(recs)
                total_written += len(recs)
    print(f"\nwrote {total_written} tender records -> {out_path}")


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
