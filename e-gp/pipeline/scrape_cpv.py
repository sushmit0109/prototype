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
has its own subtree for finer granularity, not fetched here.

Each category is also fetched per political era (see eras.py), using
pubDtFrm/pubDtTo -- which took real trial and error to unlock. Every other
date field on this portal (contract signing, debarment start/end, ...)
uses DD-Mon-YYYY ("07-Aug-2024"); this one silently returns an empty
response for that format, and for ISO (2024-08-07), and doesn't error --
it just gives nothing back, which looks identical to "zero matching
tenders" unless you already know to be suspicious. The format it actually
wants is DD/MM/YYYY ("07/08/2024").

Counts alone can't answer "which sector gets the most money" -- the tender
list carries no value field. For the top TOP_N_FOR_VALUE categories (by
count), this also pages through the full tender_id list (size=1000, same
row shape as scrape_tenders.py) so build_cpv.py can join those IDs against
data/contracts and sum actual awarded value per category. This is the
expensive part of the crawl -- Construction work alone is ~340 pages -- so
it's deliberately capped to the categories that will actually be shown,
not all 61.

    python3 scrape_cpv.py <out.json>
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import common
from eras import ERAS
from htmlrows import ROW_RE, CELL_RE, split_br_clean, total_pages

SEARCH_DEFAULTS = {
    "funName": "AllTenders", "viewType": "AllTenders",
    "departmentId": "", "office": "", "procNature": "", "procType": "",
    "procMethod": "", "tenderId": "", "refNo": "",
    "closeDtFrm": "", "closeDtTo": "", "isFrame": "", "h": "t",
}
TOTAL_PAGES_RE = re.compile(r'id="totalPages"\s+value="(\d+)"')
TOP_N_FOR_VALUE = 25


def fetch_categories():
    body = common.get("/GetCpvTree?searchBy=&action=&keyword=&id=0")
    return [{"cpvcode": d["attr"]["cpvcode"], "name": d["attr"]["cpvname"]} for d in json.loads(body)]


def iso_to_ddmmyyyy(iso):
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def count_for(cpv_name, pub_from="", pub_to=""):
    body = common.post("/TenderDetailsServlet", {
        **SEARCH_DEFAULTS, "cpvCategory": cpv_name,
        "pubDtFrm": pub_from, "pubDtTo": pub_to,
        "pageNo": 1, "size": 1,
    })
    m = TOTAL_PAGES_RE.search(body)
    return int(m.group(1)) if m else 0


def fetch_id_page(cpv_name, page_no):
    body = common.post("/TenderDetailsServlet", {
        **SEARCH_DEFAULTS, "cpvCategory": cpv_name, "pubDtFrm": "", "pubDtTo": "",
        "pageNo": page_no, "size": 1000,
    })
    ids = []
    for row in ROW_RE.findall(body):
        cells = CELL_RE.findall(row)
        if len(cells) < 2:
            continue
        id_parts = split_br_clean(cells[1])
        if id_parts:
            ids.append(id_parts[0])
    return ids, total_pages(body)


def fetch_all_tender_ids(cpv_name):
    first_ids, pages = fetch_id_page(cpv_name, 1)
    all_ids = list(first_ids)
    if pages > 1:
        with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
            futures = [pool.submit(fetch_id_page, cpv_name, p) for p in range(2, pages + 1)]
            for fut in as_completed(futures):
                ids, _ = fut.result()
                all_ids.extend(ids)
    return all_ids


def main(out_path):
    common.bootstrap()
    categories = fetch_categories()
    print(f"{len(categories)} top-level CPV categories")

    # Era boundaries clamp to the portal's actual span (pre-2009 data isn't
    # meaningfully queryable and 9999 isn't a valid input); blank means "no
    # lower/upper bound" to the servlet, so this doesn't lose the tails.
    era_bounds = [(name, "" if start.startswith("0000") else iso_to_ddmmyyyy(start),
                   "" if end.startswith("9999") else iso_to_ddmmyyyy(end))
                  for name, start, end in ERAS]

    tasks = [(c, None, "", "") for c in categories]
    tasks += [(c, era_name, frm, to) for c in categories for era_name, frm, to in era_bounds]

    def run(task):
        c, era_name, frm, to = task
        return c, era_name, count_for(c["name"], frm, to)

    with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
        futures = [pool.submit(run, t) for t in tasks]
        for fut in as_completed(futures):
            c, era_name, n = fut.result()
            if era_name is None:
                c["count"] = n
            else:
                c.setdefault("by_era", {})[era_name] = n

    categories.sort(key=lambda c: -c["count"])
    # A tender can carry more than one CPV category, so per-category counts
    # overlap and don't sum to a unique total -- take the real, unfiltered
    # count as its own request rather than summing the categorised ones.
    all_tenders = count_for("")
    all_tenders_by_era = {name: count_for("", frm, to) for name, frm, to in era_bounds}
    for c in categories[:15]:
        print(f"  {c['count']:>7,}  ({100*c['count']/all_tenders:4.1f}%)  {c['name']}")

    print(f"\nfetching full tender-id lists for the top {TOP_N_FOR_VALUE} categories (for the value join)")
    for i, c in enumerate(categories[:TOP_N_FOR_VALUE], 1):
        ids = fetch_all_tender_ids(c["name"])
        c["tender_ids"] = ids
        print(f"  {i}/{TOP_N_FOR_VALUE}  {len(ids):>7,} ids  {c['name']}")

    payload = {
        "source": "https://www.eprocure.gov.bd/resources/common/AllTenders.jsp (Category tree)",
        "all_tenders": all_tenders,
        "all_tenders_by_era": all_tenders_by_era,
        "categories": categories,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {len(categories)} categories, {all_tenders:,} tenders overall -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
