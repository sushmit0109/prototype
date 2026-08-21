#!/usr/bin/env python3
"""
Crawl the itemised Annual Procurement Plan -- the government's own
pre-tender cost estimate and planned procurement method, package by package.

This is the layer under scrape_app.py. That one gets the office/project
summary rows; this one follows each of them into
`/resources/common/StdSearch.jsp?officeId=..&bTypeId=..`, whose underlying
servlet is SearchAPPServlet with action=advSearch. (Note the path: the link
on SearchAPP.jsp is relative, so it resolves under /resources/common/ --
requesting /StdSearch.jsp at the site root returns an "Invalid Page" shell,
which is what made this look unreachable on a first pass.)

Why it's worth the crawl: every other source says what government *spent*.
This says what it *planned to spend, and how it planned to buy it* -- so
estimate-vs-award and planned-method-vs-actual-method become answerable,
which is the only way to see cost overruns or a package quietly moving from
open tendering to a limited one.

One request per (office, budget type); budget types are 1=Development,
2=Revenue, 3=Own Fund. ~10,200 offices x 3 = ~30,600 combos, most of them
empty, so this is resumable and ordered so a partial run is still useful.

    python3 scrape_app_items.py <raw/app_plans.jsonl> <out.jsonl> [--resume] [--limit N]
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import common
from htmlrows import ROW_RE, CELL_RE, clean, split_br_clean, total_pages

PAGE_SIZE = 200
BUDGET_TYPES = {"1": "Development Budget", "2": "Revenue Budget", "3": "Own Fund"}


def fetch_page(office_id, btype, page_no):
    body = common.post("/SearchAPPServlet", {
        "bTypeId": btype, "pageNo": page_no, "office": office_id,
        "action": "advSearch", "size": PAGE_SIZE, "keyWord": "null",
    })
    records = []
    for row in ROW_RE.findall(body):
        cells = CELL_RE.findall(row)
        if len(cells) < 6:
            continue
        _, app_id, app_code, nature_cell, package_cell, cost_cell = cells[:6]
        if "No Records Found" in clean(app_id):
            continue
        nature = split_br_clean(nature_cell)
        package = split_br_clean(package_cell)
        cost = split_br_clean(cost_cell)
        try:
            estimated = float(cost[0].replace(",", "")) if cost else None
        except ValueError:
            estimated = None
        records.append({
            "office_id": office_id,
            "budget_type": BUDGET_TYPES.get(btype, btype),
            "app_id": clean(app_id),
            "app_code": clean(app_code),
            "procurement_nature": nature[0] if nature else None,
            "project_name": nature[1] if len(nature) > 1 else None,
            "package_no": package[0] if package else None,
            "package_description": package[1] if len(package) > 1 else None,
            "estimated_cost_bdt": estimated,
            "planned_method": cost[1] if len(cost) > 1 else None,
        })
    return records, total_pages(body)


def crawl_combo(task):
    office_id, btype = task
    out = []
    try:
        first, pages = fetch_page(office_id, btype, 1)
        out.extend(first)
        for p in range(2, pages + 1):
            more, _ = fetch_page(office_id, btype, p)
            out.extend(more)
    except Exception as e:                      # one dead office must not kill the run
        print(f"  ! office {office_id} bType {btype}: {e}")
    return out


def already_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    done.add((r["office_id"], r["budget_type"]))
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


def main(app_path, out_path, resume=False, limit=None):
    # Order offices by how often they appear in the plan summary: the busiest
    # procuring offices first, so a truncated run still covers what matters.
    freq = {}
    with open(app_path) as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("office_id"):
                freq[r["office_id"]] = freq.get(r["office_id"], 0) + 1
    offices = sorted(freq, key=lambda o: -freq[o])
    if limit:
        offices = offices[:limit]

    skip = already_done(out_path) if resume else set()
    tasks = [(o, b) for o in offices for b in BUDGET_TYPES
             if (o, BUDGET_TYPES[b]) not in skip]
    print(f"{len(offices)} offices, {len(tasks)} (office, budget-type) combos to fetch")

    common.bootstrap()
    written = combos = 0
    with open(out_path, "a" if resume else "w") as fh:
        with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
            futures = [pool.submit(crawl_combo, t) for t in tasks]
            for fut in as_completed(futures):
                combos += 1
                for rec in fut.result():
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1
                fh.flush()
                if combos % 500 == 0:
                    print(f"  {combos}/{len(tasks)} combos, {written} line items so far")
    print(f"\nwrote {written} APP line items -> {out_path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    resume = "--resume" in sys.argv
    limit = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--limit=")), None)
    main(args[0], args[1], resume, limit)
