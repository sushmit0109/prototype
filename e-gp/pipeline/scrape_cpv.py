#!/usr/bin/env python3
"""
Tender counts by CPV (Common Procurement Vocabulary) category -- the
standardised international commodity/service classification this portal
uses internally, exposed via the "Category" tree-picker on the tender
search form (backed by GetCpvTree) and accepted as a filter on
TenderDetailsServlet's own cpvCategory parameter.

Nothing else in this pipeline captures *what kind of thing* a tender is for
beyond the three-way Works/Goods/Services split in procurement_nature. CPV
is the only source with real topical granularity -- "Construction work" vs
"Computer and related services" vs "Health and social work services", and
58 more -- which is what an actual infrastructure-vs-ICT (or any sector)
comparison needs.

The tender list servlet always returns full result rows, but at size=1 its
totalPages field IS the exact matching record count (ceil(n/1) == n) -- so
a full topic breakdown costs one lightweight request per category rather
than a real crawl of the underlying tenders. cpvCategory takes the category
NAME (not its numeric CPV code); passing the code returns nothing.

Categories are the 61 top-level CPV divisions from GetCpvTree (id=0); each
has its own subtree for finer granularity, not fetched here. A year-by-year
trend per category was attempted (pubDtFrm/pubDtTo) but the servlet returns
an empty response the moment either date field is set, regardless of
format tried -- so this is an all-time snapshot, not a trend, until that's
figured out.

    python3 scrape_cpv.py <out.json>
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import common

SEARCH_DEFAULTS = {
    "funName": "AllTenders", "viewType": "AllTenders",
    "departmentId": "", "office": "", "procNature": "", "procType": "",
    "procMethod": "", "tenderId": "", "refNo": "", "pubDtFrm": "", "pubDtTo": "",
    "closeDtFrm": "", "closeDtTo": "", "isFrame": "", "h": "t",
}
TOTAL_PAGES_RE = re.compile(r'id="totalPages"\s+value="(\d+)"')


def fetch_categories():
    body = common.get("/GetCpvTree?searchBy=&action=&keyword=&id=0")
    return [{"cpvcode": d["attr"]["cpvcode"], "name": d["attr"]["cpvname"]} for d in json.loads(body)]


def count_for(cpv_name):
    body = common.post("/TenderDetailsServlet", {
        **SEARCH_DEFAULTS, "cpvCategory": cpv_name, "pageNo": 1, "size": 1,
    })
    m = TOTAL_PAGES_RE.search(body)
    return int(m.group(1)) if m else 0


def main(out_path):
    common.bootstrap()
    categories = fetch_categories()
    print(f"{len(categories)} top-level CPV categories")

    with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
        futures = {pool.submit(count_for, c["name"]): c for c in categories}
        for fut in as_completed(futures):
            futures[fut]["count"] = fut.result()

    categories.sort(key=lambda c: -c["count"])
    # A tender can carry more than one CPV category, so per-category counts
    # overlap and don't sum to a unique total -- take the real, unfiltered
    # count as its own request rather than summing the categorised ones.
    all_tenders = count_for("")
    for c in categories[:15]:
        print(f"  {c['count']:>7,}  ({100*c['count']/all_tenders:4.1f}%)  {c['name']}")

    payload = {
        "source": "https://www.eprocure.gov.bd/resources/common/AllTenders.jsp (Category tree)",
        "all_tenders": all_tenders,
        "categories": categories,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {len(categories)} categories, {all_tenders:,} tenders overall -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
