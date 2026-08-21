#!/usr/bin/env python3
"""
Crawl Annual Procurement Plans -- SearchAPP.jsp / SearchAPPServlet.

Unlike the other sources, this one is inherently sharded by financial year
(the form requires financialYear as a real value, not blank -- and, less
obviously, "no filter" for district/office/department is the literal string
"0", not an empty string; the site's dropdowns encode "-- Select --" that
way, and a blank string produces an empty 200 response with no error).

Each row here is a Ministry/Division/Organization/Project summary, not a
line-item budget -- the budget-type links (DB/RB/OF: Development Budget /
Revenue Budget / Own Fund) go one level deeper (StdSearch.jsp?officeId=...)
to the itemised plan, which this does not follow (that's a per-office,
per-budget-type crawl on top of this one; left for later if the summary
level proves not to be enough).

At size=1000 the whole 2010-2011..2027-2028 span is only ~90 pages total, so
this is cheap enough to re-crawl in full every run rather than incrementally.

    python3 scrape_app.py <out.jsonl>
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import common
from htmlrows import ROW_RE, CELL_RE, clean, total_pages

PAGE_SIZE = 1000
FINANCIAL_YEARS = [f"{y}-{y + 1}" for y in range(2010, 2028)]
OFFICE_ID_RE = re.compile(r"officeId=(\d+)")
BUDGET_TYPE_RE = re.compile(r'>([A-Z]{2})</a>')


def parse_row(cells_html, financial_year):
    if len(cells_html) < 5:
        return None
    ministry, division, organization, project, links_html = cells_html[:5]
    office_id_m = OFFICE_ID_RE.search(links_html)
    return {
        "financial_year": financial_year,
        "ministry": clean(ministry),
        "division": clean(division),
        "organization": clean(organization),
        "project": clean(project),
        "office_id": office_id_m.group(1) if office_id_m else None,
        "budget_types": BUDGET_TYPE_RE.findall(links_html),
    }


def fetch_page(financial_year, page_no):
    body = common.post("/SearchAPPServlet", {
        "stateId": "0", "financialYear": financial_year, "departmentid": "0",
        "pageNo": page_no, "officeId": "0", "action": "Search", "size": PAGE_SIZE,
    })
    records = []
    for row in ROW_RE.findall(body):
        rec = parse_row(CELL_RE.findall(row), financial_year)
        if rec:
            records.append(rec)
    return records, total_pages(body)


def crawl_year(financial_year):
    first, pages = fetch_page(financial_year, 1)
    records = list(first)
    for page_no in range(2, pages + 1):
        more, _ = fetch_page(financial_year, page_no)
        records.extend(more)
    return records


def main(out_path):
    common.bootstrap()
    total_written = 0
    with open(out_path, "w") as fh:
        with ThreadPoolExecutor(max_workers=max(1, common.MAX_CONCURRENCY // 2)) as pool:
            for fy, records in zip(FINANCIAL_YEARS, pool.map(crawl_year, FINANCIAL_YEARS)):
                print(f"{fy}: {len(records)} records")
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total_written += len(records)
    print(f"\nwrote {total_written} APP records -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
