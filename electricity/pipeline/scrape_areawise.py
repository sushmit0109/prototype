"""BPDB area-wise (zone-wise) demand and load-shed, one request per date.

Source: misc.bpdb.gov.bd/area-wise-demand?date=DD-MM-YYYY

Two quirks are handled here:
  * The page's own "Total" row is hard-coded to 0/0 — we sum the zones instead.
  * Before ~2016 the page echoes one value across all nine zones (e.g. every
    zone reporting 2380 MW / 311 MW). Those days are flagged suspect and are
    excluded from the site build rather than silently charted.

  python scrape_areawise.py                    # last 10 days
  python scrape_areawise.py --since 2016-01-01 # backfill
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from bs4 import BeautifulSoup

from common import RAW, ZONES, get, num, read_json, session, write_json, zone_key

URL = "https://misc.bpdb.gov.bd/area-wise-demand?date={}"
STORE_DIR = RAW / "area"


def load_store() -> dict:
    """All stored dates, merged from the per-year files."""
    store = {}
    for f in sorted(STORE_DIR.glob("areawise_*.json")):
        store.update(read_json(f, {}) or {})
    legacy = STORE_DIR / "areawise.json"          # pre-split layout
    if legacy.exists():
        store.update(read_json(legacy, {}) or {})
    return store


def save_store(store: dict):
    """Split per year so an incremental run rewrites only the current year."""
    by_year = {}
    for k, v in store.items():
        by_year.setdefault(k[:4], {})[k] = v
    for year, rows in by_year.items():
        write_json(STORE_DIR / f"areawise_{year}.json",
                   dict(sorted(rows.items())))
    legacy = STORE_DIR / "areawise.json"
    if legacy.exists():
        legacy.unlink()


def parse(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = {}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [" ".join(td.get_text(" ", strip=True).split())
                     for td in tr.find_all("td")]
            if len(cells) < 4:
                continue
            z = zone_key(cells[1])
            if not z:
                continue
            out[z] = {"demand": num(cells[2]), "loadshed": num(cells[3])}
    return out if len(out) >= 5 else None


def is_suspect(zones: dict) -> bool:
    """True when every zone carries the same numbers — a known upstream defect."""
    dem = [v["demand"] for v in zones.values() if v["demand"] is not None]
    if len(dem) < 5:
        return True
    return len(set(dem)) == 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true", help="re-fetch dates already stored")
    args = ap.parse_args()

    store = load_store()
    today = date.today()
    start = (date.fromisoformat(args.since) if args.since
             else today - timedelta(days=args.days))

    wanted = []
    d = start
    while d <= today:
        k = d.isoformat()
        # Always re-fetch the tail: same-day figures are revised upward later.
        if args.refresh or k not in store or (today - d).days <= 3:
            wanted.append(d)
        d += timedelta(days=1)

    print(f"[area] {len(wanted)} dates to fetch ({start} .. {today}); {len(store)} stored")
    if not wanted:
        return 0

    sess = session()

    def work(d: date):
        r = get(sess, URL.format(d.strftime("%d-%m-%Y")))
        return d.isoformat(), (parse(r.text) if r else None)

    got = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (k, zones) in enumerate(ex.map(work, wanted), 1):
            if zones:
                total_d = sum(v["demand"] or 0 for v in zones.values())
                total_l = sum(v["loadshed"] or 0 for v in zones.values())
                store[k] = {
                    "zones": {z: zones.get(z, {"demand": None, "loadshed": None})
                              for z in ZONES},
                    "total_demand": total_d,
                    "total_loadshed": total_l,
                    "suspect": is_suspect(zones),
                }
                got += 1
            if i % 250 == 0 or i == len(wanted):
                print(f"  {i}/{len(wanted)} ok={got}", flush=True)
                save_store(store)

    save_store(store)
    good = sum(1 for v in store.values() if not v["suspect"])
    print(f"[area] stored {len(store)} dates ({good} usable, "
          f"{len(store)-good} flagged suspect)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
