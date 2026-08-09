"""PGCB hourly demand / supply / load-shed.

Source: erp.powergrid.gov.bd — one paginated Bengali table, 50 rows/page,
~2,020 pages covering 2015-04-19 to today. Each row is one hour.

  python scrape_pgcb.py            # incremental: first 4 pages
  python scrape_pgcb.py --full     # full backfill of every page
  python scrape_pgcb.py --pages 60 # first N pages

Output: raw/pgcb/hourly_<YYYY>.csv, columns
        datetime,date,hour,demand,supply,loadshed,peak
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from common import RAW, bn2en, get, num, read_csv, session, write_csv

BASE = ("https://erp.powergrid.gov.bd/web/generations/"
        "view_demand_supply_loadshed_bn?page={}")

OUT = RAW / "pgcb"

# The "মন্তব্য" (remarks) column only ever carries a peak marker.
PEAK_MAP = {"day peak": "day", "evening peak": "evening"}


# A handful of rows carry a mistyped year ("05-08-0008"). They are upstream
# data-entry errors, not a parsing problem, so they are counted and set aside.
MIN_YEAR, MAX_YEAR = 2010, 2035
REJECTS = []


def parse_page(html: str):
    """Return list of row dicts from one paginated table page."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []
    rows = []
    for tr in table.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split())
                 for td in tr.find_all(["td", "th"])]
        if len(cells) < 5:
            continue
        d = bn2en(cells[0]).strip()
        m = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", d)
        if not m:
            continue  # header row
        dd, mm, yyyy = m.groups()
        if not (MIN_YEAR <= int(yyyy) <= MAX_YEAR):
            REJECTS.append(cells[:5])
            continue
        date = f"{yyyy}-{int(mm):02d}-{int(dd):02d}"

        t = bn2en(cells[1]).strip()
        tm = re.match(r"(\d{1,2}):(\d{2})", t)
        if not tm:
            continue
        hour = int(tm.group(1)) % 24

        peak = PEAK_MAP.get(cells[5].strip().lower(), "") if len(cells) > 5 else ""

        rows.append({
            "datetime": f"{date}T{hour:02d}:00",
            "date": date,
            "hour": hour,
            "demand": num(cells[2]),
            "supply": num(cells[3]),
            "loadshed": num(cells[4]),
            "peak": peak,
        })
    return rows


def total_pages(sess) -> int:
    r = get(sess, BASE.format(1))
    if not r:
        return 0
    pages = [int(x) for x in re.findall(r"page=(\d+)", r.text)]
    return max(pages) if pages else 1


def load_existing() -> dict:
    """Existing rows keyed by datetime, so a re-run merges instead of clobbering."""
    store = {}
    for f in sorted(OUT.glob("hourly_*.csv")):
        for r in read_csv(f):
            for k in ("demand", "supply", "loadshed"):
                r[k] = num(r[k])
            r["hour"] = int(r["hour"])
            store[r["datetime"]] = r
    return store


def save(store: dict):
    # Bucketed per month, not per year: an hourly job rewrites only the current
    # bucket, so the committed diff stays small instead of rewriting a whole
    # year's file every run.
    by_year = defaultdict(list)
    for dt, r in store.items():
        by_year[dt[:7]].append(r)
    for year, rows in by_year.items():
        rows.sort(key=lambda r: r["datetime"])
        write_csv(
            OUT / f"hourly_{year}.csv",
            [[r["datetime"], r["date"], r["hour"], r["demand"] if r["demand"] is not None else "",
              r["supply"] if r["supply"] is not None else "",
              r["loadshed"] if r["loadshed"] is not None else "", r["peak"]] for r in rows],
            ["datetime", "date", "hour", "demand", "supply", "loadshed", "peak"],
        )
    return sum(len(v) for v in by_year.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    sess = session()
    store = load_existing()
    print(f"[pgcb] existing rows: {len(store)}")

    last = total_pages(sess) if args.full else args.pages
    if not last:
        print("[pgcb] could not reach source")
        return 1
    print(f"[pgcb] fetching pages 1..{last}")

    def work(p):
        r = get(sess, BASE.format(p))
        return p, (parse_page(r.text) if r else [])

    added = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (p, rows) in enumerate(ex.map(work, range(1, last + 1)), 1):
            for row in rows:
                # Later pages are older; never let a re-fetch blank out a good value.
                prev = store.get(row["datetime"])
                if prev is None:
                    added += 1
                    store[row["datetime"]] = row
                else:
                    for k in ("demand", "supply", "loadshed"):
                        if prev.get(k) is None and row.get(k) is not None:
                            prev[k] = row[k]
                    if row["peak"]:
                        prev["peak"] = row["peak"]
            if i % 100 == 0 or i == last:
                print(f"  page {i}/{last}  rows={len(store)}", flush=True)
                if args.full and i % 400 == 0:
                    save(store)  # checkpoint a long backfill

    n = save(store)

    # Retire buckets from older layouts: implausible years from upstream typos,
    # and the whole-year files this script used to write before monthly buckets.
    for f in OUT.glob("hourly_*.csv"):
        key = f.stem.split("_", 1)[1]
        if len(key) == 4:
            print(f"[pgcb] removing superseded year file {f.name}")
            f.unlink()
        elif not (key[:4].isdigit() and MIN_YEAR <= int(key[:4]) <= MAX_YEAR):
            print(f"[pgcb] removing implausible bucket {f.name}")
            f.unlink()

    print(f"[pgcb] done: {n} rows total (+{added} new)")
    if REJECTS:
        print(f"[pgcb] {len(REJECTS)} rows rejected for an implausible year, "
              f"e.g. {REJECTS[0]}")
    if store:
        ks = sorted(store)
        print(f"[pgcb] range {ks[0]} .. {ks[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
