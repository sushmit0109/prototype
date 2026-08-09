"""Enumerate the BPDB daily-generation archive into a date -> PDF-URL index.

Source: misc.bpdb.gov.bd/daily-generation-archive?page=N  (~684 pages x 10 days)

Each archive row links up to five artefacts for one publication date:
  page_1 / page_2 : NLDC "System Summary Report"  (sheet 1)
  page_3          : "Evening peak generation and day long energy data of
                     power stations" (sheet 2) -- plant-level
  summary         : occasional extra summary sheet
  energy / load   : GIF charts (not parsed)

The listing date is the *publication* date; the report inside is normally for
the previous day. The true date is taken from the PDF text at parse time, so
this index only needs to be a complete set of URLs.

  python scrape_bpdb_index.py --full
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from common import RAW, get, read_json, session, write_json

URL = "https://misc.bpdb.gov.bd/daily-generation-archive?page={}"
STORE = RAW / "bpdb" / "archive_index.json"

KINDS = ("page_1", "page_2", "page_3", "summary", "energy", "load")


def parse_page(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", tds[1].get_text(strip=True))
        if not m:
            continue
        dd, mm, yyyy = m.groups()
        listing_date = f"{yyyy}-{mm}-{dd}"
        links = {}
        for a in tr.find_all("a", href=True):
            href = a["href"]
            fn = href.rsplit("/", 1)[-1]
            for k in KINDS:
                if fn.startswith(k + "_"):
                    links[k] = href
                    break
        if links:
            out[listing_date] = links
    return out


def total_pages(sess) -> int:
    r = get(sess, URL.format(1))
    if not r:
        return 0
    pages = [int(x) for x in re.findall(r"page=(\d+)", r.text)]
    return max(pages) if pages else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    sess = session()
    store = read_json(STORE, {}) or {}
    last = total_pages(sess) if args.full else args.pages
    if not last:
        print("[bpdb-index] source unreachable")
        return 1
    print(f"[bpdb-index] {len(store)} known; scanning pages 1..{last}")

    def work(p):
        r = get(sess, URL.format(p))
        return parse_page(r.text) if r else {}

    new = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, batch in enumerate(ex.map(work, range(1, last + 1)), 1):
            for k, v in batch.items():
                if k not in store:
                    new += 1
                store.setdefault(k, {}).update(v)
            if i % 100 == 0 or i == last:
                print(f"  page {i}/{last} dates={len(store)}", flush=True)
                write_json(STORE, store)

    write_json(STORE, store)
    ks = sorted(store)
    print(f"[bpdb-index] {len(store)} dates (+{new}); {ks[0]} .. {ks[-1]}")
    for k in ("page_1", "page_3"):
        print(f"  with {k}: {sum(1 for v in store.values() if k in v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
