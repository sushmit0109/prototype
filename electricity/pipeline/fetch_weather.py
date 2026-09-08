"""Hourly temperature for every district, from the ERA5 reanalysis.

Bangladesh's own hourly weather is not published in a form this project can
read; PGCB prints one national daily maximum and only since January 2025,
which is far too thin to say anything about eleven years of demand. ERA5 is
the standard reanalysis for this kind of work: a physical model reconciled
against observations, gridded, hourly, and free of the station gaps that make
raw observations awkward to use across a whole country.

  Source: https://open-meteo.com/en/docs/historical-weather-api  (ERA5)

One point per district centroid, then two weighted aggregates:

  national  population-weighted mean over all 64 districts
  zone      population-weighted mean within each of the nine NLDC zones

Weighting by population rather than by area is the point. Electricity demand
follows people, so the temperature that matters for the grid is the
temperature where the load is -- an area-weighted mean would give the
Sundarbans the same say as Dhaka.

Only the aggregates are stored. The per-district series is 64 x ~100,000
hours, which is neither small enough to keep in the repository nor needed
again once the weights are applied.

  python fetch_weather.py                 # fill in whatever is missing
  python fetch_weather.py --from 2015-04-17 --to 2026-09-08
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from common import RAW, SITE_DATA, get, num, read_csv, session, write_csv

try:
    from population import DISTRICT_POPULATION as POP
except ImportError:                                     # pragma: no cover
    POP = {}

OUT = RAW / "weather"
ARCHIVE = "https://archive-api.open-meteo.com/v1/era5"

# Each district's series is cached outside the repository. Sixty-four long
# requests is enough to trip the archive's daily quota, and without a cache a
# refetch throws away every district that did succeed -- which is how an
# entire zone came to be missing from one run of this script. With a cache,
# repeated runs fill the gaps instead of starting again.
CACHE = Path(os.environ.get("WEATHER_CACHE",
                            Path(tempfile.gettempdir()) / "bd-weather-cache"))

# ERA5 lags real time by about five days; asking for later dates returns
# nulls rather than an error, so the window is clipped instead.
ERA5_LAG_DAYS = 6
FIRST = "2015-04-17"          # the first hour the demand archive covers

ZONES = ["dhaka", "chattogram", "cumilla", "mymensingh", "sylhet",
         "khulna", "barishal", "rajshahi", "rangpur"]


def district_points():
    """Centroid and population for each district, from the built geography."""
    geo = json.loads((SITE_DATA / "geo" / "districts.json").read_text())

    def centroid(geom):
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        best, best_area = None, 0.0
        for poly in polys:
            ring = poly[0]
            area = abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
                           for i in range(len(ring) - 1)) / 2)
            if area > best_area:
                best, best_area = ring, area
        n = len(best) - 1
        return (round(sum(p[1] for p in best[:n]) / n, 4),
                round(sum(p[0] for p in best[:n]) / n, 4))

    # The geography and the census spell several districts differently
    # (Barisal/Barishal, Jessore/Jashore). A prefix match handles most of it,
    # but "barisal" and "barishal" differ at the fifth character, so the
    # transliteration variants are normalised first.
    def key(name):
        k = re.sub(r"\s+", "", re.sub(r"\s+hill$", "",
                   name.lower().replace("'", "").replace(".", "").strip()))
        k = k.replace("sh", "s").replace("chh", "ch")
        if k in POP:
            return k
        for cand in POP:
            c = cand.replace("sh", "s").replace("chh", "ch")
            if c == k or c.startswith(k[:6]) or k.startswith(c[:6]):
                return cand
        return k

    out = []
    for f in geo["features"]:
        lat, lon = centroid(f["geometry"])
        p = f["properties"]
        out.append({"district": p["name_en"], "zone": p.get("zone"),
                    "lat": lat, "lon": lon,
                    "pop": POP.get(key(p["name_en"]))})
    return out


def fetch_point(sess, lat, lon, start, end, tries=4):
    """Hourly 2 m temperature for one point, local time.

    Retried with a widening pause: a burst of sixty-odd long requests trips
    the archive's rate limit, and a district dropped silently would bias the
    population weighting rather than announce itself.
    """
    for attempt in range(tries):
        r = get(sess, ARCHIVE, timeout=180, params={
            "latitude": lat, "longitude": lon,
            "start_date": start, "end_date": end,
            "hourly": "temperature_2m", "timezone": "Asia/Dhaka"})
        if r is not None:
            try:
                h = r.json()["hourly"]
                if h.get("time"):
                    return dict(zip(h["time"], h["temperature_2m"]))
            except Exception:                           # noqa: BLE001
                pass
        time.sleep(2 * (attempt + 1))
    return None


def existing_hours():
    have = set()
    for f in OUT.glob("temp_*.csv"):
        for row in read_csv(f):
            have.add(row["datetime"])
    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=FIRST)
    ap.add_argument("--to", dest="end", default=None)
    ap.add_argument("--force", action="store_true",
                    help="rebuild the aggregates from the cache")
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the cache and pull every district again")
    args = ap.parse_args()

    end = args.end or (dt.date.today()
                       - dt.timedelta(days=ERA5_LAG_DAYS)).isoformat()
    if args.start > end:
        print(f"[weather] nothing to do: {args.start} is after {end}")
        return 0

    pts = district_points()
    missing_pop = [p["district"] for p in pts if not p["pop"]]
    if missing_pop:
        print(f"[weather] no population for {len(missing_pop)} district(s): "
              f"{', '.join(missing_pop[:5])}", file=sys.stderr)
    total_pop = sum(p["pop"] or 0 for p in pts)
    if not total_pop:
        print("[weather] no population weights available", file=sys.stderr)
        return 1

    have = set() if args.force else existing_hours()
    print(f"[weather] {len(pts)} districts, {args.start} to {end}; "
          f"{len(have):,} hours already stored")

    OUT.mkdir(parents=True, exist_ok=True)
    sess = session()

    # Accumulate weighted sums hour by hour rather than holding 64 full
    # series in memory at once.
    nat_num, nat_den = defaultdict(float), defaultdict(float)
    zone_num = {z: defaultdict(float) for z in ZONES}
    zone_den = {z: defaultdict(float) for z in ZONES}
    fetched = 0

    CACHE.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(pts, 1):
        if not p["pop"]:
            continue
        cf = CACHE / (re.sub(r"[^a-z0-9]+", "_", p["district"].lower()) + ".csv")
        series = None
        if cf.exists() and not args.refetch:
            series = {}
            with cf.open(encoding="utf-8") as fh:
                for line in fh:
                    ts, _, v = line.partition(",")
                    if v.strip():
                        series[ts] = float(v)
            if len(series) < 1000:
                series = None
        if series is None:
            series = fetch_point(sess, p["lat"], p["lon"], args.start, end)
            if series:
                cf.write_text("".join(f"{k},{v}\n" for k, v in series.items()
                                      if v is not None), encoding="utf-8")
            time.sleep(0.5)                 # only pause on a real request
        if not series:
            print(f"[weather] {p['district']}: no data", file=sys.stderr)
            continue
        fetched += 1
        w = float(p["pop"])
        z = p["zone"] if p["zone"] in zone_num else None
        for ts, t in series.items():
            if t is None:
                continue
            nat_num[ts] += t * w
            nat_den[ts] += w
            if z:
                zone_num[z][ts] += t * w
                zone_den[z][ts] += w
        if i % 10 == 0 or i == len(pts):
            print(f"  {i}/{len(pts)} districts", flush=True)

    if not nat_den:
        print("[weather] nothing fetched", file=sys.stderr)
        return 1

    header = ["datetime", "date", "hour", "national"] + ZONES
    by_year = defaultdict(list)
    for ts in sorted(nat_den):
        date, hh = ts.split("T")
        row = [ts, date, int(hh[:2]),
               round(nat_num[ts] / nat_den[ts], 2)]
        for z in ZONES:
            d = zone_den[z].get(ts)
            row.append(round(zone_num[z][ts] / d, 2) if d else "")
        by_year[date[:4]].append(row)

    kept = 0
    for year, rows in sorted(by_year.items()):
        # merge with anything already on disk for that year
        path = OUT / f"temp_{year}.csv"
        merged = {r[0]: r for r in rows}
        if path.exists() and not args.force:
            for old in read_csv(path):
                merged.setdefault(old["datetime"], [
                    old["datetime"], old["date"], int(old["hour"]),
                    num(old["national"])] + [num(old[z]) for z in ZONES])
        out = [merged[k] for k in sorted(merged)]
        write_csv(path, out, header)
        kept += len(out)

    if fetched < sum(1 for p in pts if p["pop"]):
        print(f"[weather] WARNING: {sum(1 for p in pts if p['pop']) - fetched} "
              f"district(s) missing from the weighting", file=sys.stderr)
    print(f"[weather] {fetched} districts fetched; {kept:,} hours stored "
          f"({min(by_year)}..{max(by_year)}), population-weighted "
          f"across {total_pop:,} people")
    return 0


if __name__ == "__main__":
    sys.exit(main())
