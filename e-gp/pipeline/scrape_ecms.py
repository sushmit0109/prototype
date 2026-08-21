#!/usr/bin/env python3
"""
Crawl eExperience -- SearcheCMS.jsp / AdvSearcheCMSServlet, statusTab=All.

This is the one source with a real per-company identifier in the row itself
(the "Company Unique ID" / tendererId column) rather than a bare name string
-- useful on its own (grouping one company's completed/ongoing work by ID,
not name), though the debarment register doesn't expose the same ID, so it
doesn't yet let the flagging pipeline drop name-matching (that would need
the ID to appear on both sides).

~186K records at size=1000 (186 pages), small enough to re-crawl in full.

    python3 scrape_ecms.py <out.jsonl>
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import common
from htmlrows import ROW_RE, CELL_RE, clean, split_br_clean, total_pages

PAGE_SIZE = 1000
TENDER_LINK_RE = re.compile(
    r"^(\d+),\s*APP ID\s*:\s*(\S+)\s*(?:<br\s*/?>)?\s*"
    r"<a href='/resources/common/VieweCmsDetails\.jsp\?wcs=([a-zA-Z]+)&Id=(\d+)'[^>]*>(.*)$",
    re.S,
)
# Manual-source rows (no eTenders link): "<tender_id>, <ref/title text>"
PLAIN_ID_RE = re.compile(r"^(\d+),\s*(.*)$", re.S)

SEARCH_DEFAULTS = {
    "action": "geteCMSList", "keyword": "", "expCertNo": "", "officeId": "",
    "contractAwardTo": "", "contractStartDtFrom": "", "contractStartDtTo": "",
    "contractEndDtFrom": "", "contractEndDtTo": "", "departmentId": "",
    "tenderId": "", "contractAmount": "", "procurementMethod": "",
    "procurementNature": "", "contAwrdSearchOpt": "", "exCertSearchOpt": "",
    "exCertificateNo": "", "tendererId": "", "procType": "", "statusTab": "All",
    "workStatus": "All",
}


def parse_tender_cell(html_fragment):
    m = TENDER_LINK_RE.match(html_fragment.strip())
    if m:
        tender_id, app_id, wcs, detail_id, title = m.groups()
        return {"tender_id": tender_id, "app_id": app_id, "work_status_code": wcs,
                "detail_id": detail_id, "title": clean(title)}
    # Manual-source records carry no eTenders link, just "<id>, <ref/title>".
    text = clean(html_fragment)
    m2 = PLAIN_ID_RE.match(text)
    if m2:
        return {"tender_id": m2.group(1), "app_id": None, "work_status_code": None,
                "detail_id": None, "title": m2.group(2)}
    return {"tender_id": None, "app_id": None, "work_status_code": None,
            "detail_id": None, "title": text}


def parse_row(cells_html):
    if len(cells_html) < 10:
        return None
    _, pe_cell, method_cell, tender_cell, awarded_to, company_id, cert_no, amount, dates_cell, work_status = cells_html[:10]

    pe_parts = split_br_clean(pe_cell)
    method_parts = split_br_clean(method_cell)
    date_parts = split_br_clean(dates_cell)
    tender = parse_tender_cell(tender_cell)

    return {
        "division": pe_parts[0] if pe_parts else None,
        "organization": pe_parts[1] if len(pe_parts) > 1 else None,
        "procuring_entity": pe_parts[-1] if pe_parts else None,
        "procurement_nature": method_parts[0] if method_parts else None,
        "procurement_type": method_parts[1] if len(method_parts) > 1 else None,
        "procurement_method": method_parts[2] if len(method_parts) > 2 else None,
        "tender_id": tender["tender_id"],
        "app_id": tender["app_id"],
        "title": tender["title"],
        "awarded_to": clean(awarded_to),
        "company_unique_id": clean(company_id) or None,
        "experience_certificate_no": clean(cert_no),
        "contract_amount": clean(amount),
        "contract_start_date": date_parts[0] if date_parts else None,
        "contract_end_date": date_parts[1] if len(date_parts) > 1 else None,
        "work_status": clean(work_status),
    }


def fetch_page(page_no):
    body = common.post("/AdvSearcheCMSServlet", {
        "pageNo": page_no, "size": PAGE_SIZE, **SEARCH_DEFAULTS,
    })
    records = []
    for row in ROW_RE.findall(body):
        rec = parse_row(CELL_RE.findall(row))
        if rec:
            records.append(rec)
    return records, total_pages(body)


def main(out_path, max_pages=None):
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
    print(f"\nwrote {total_written} eExperience records -> {out_path}")


if __name__ == "__main__":
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(sys.argv[1], max_pages)
