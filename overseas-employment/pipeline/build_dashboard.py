"""Build the static data files the dashboard reads.

Reads data/bmet.sqlite and writes site/data/*.json — small enough to serve from
GitHub Pages and to scan client-side on every filter change.

    python3 build_dashboard.py

Design notes
------------
The dashboard needs district x country x time slicing in the browser with no
server. A full daily cube is 347k rows; a monthly cube is 57k, which is small
enough to ship and fast enough to re-aggregate on every brush drag. Daily
resolution is kept only for the national trend line, where it is 1,051 numbers.

Geometry is fetched once and cached under data/geo/. District and country names
in the source do not match the geometry's names, so both mappings are explicit
and the build fails loudly if any district or any high-volume country is left
unmatched - a silently unmapped district would just vanish from the map.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

from bmet_crawler import DATA_START, MALE_ID as MALE, VOLATILE_DATES, connect, today

ROOT = Path(__file__).resolve().parent
# Overridable so this runs both from the analysis project (site/ next to it) and
# from a deployment checkout where the page lives somewhere else entirely.
SITE = Path(os.environ.get("BMET_SITE") or (ROOT / "site"))
SITE_DATA = SITE / "data"
GEO_CACHE = Path(os.environ.get("BMET_GEO_CACHE") or (ROOT / "data" / "geo"))

BD_ADM2_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/"
    "BGD/ADM2/geoBoundaries-BGD-ADM2_simplified.geojson"
)
WORLD_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"

# District population, 2022 census, from the UN OCHA Common Operational Dataset
# (UNFPA / BBS) on HDX. Needed for the per-100,000 view: absolute counts only
# say which districts are large, not where the propensity to emigrate is high.
POP_URL = (
    "https://data.humdata.org/dataset/fdf0606c-8a3b-421a-b3e8-903301e5b2ff/"
    "resource/43bfa9fd-f571-4973-9f31-91093e1e6142/download/bgd_admpop_adm2_2022.csv"
)

# BMET district spelling -> geoBoundaries shapeName. Only the ones that differ;
# the other 56 match exactly. Mostly the post-2018 romanisation updates.
DISTRICT_TO_GEO = {
    "Bogura": "Bogra",
    "Brahmanbaria": "Brahamanbaria",
    "Chattogram": "Chittagong",
    "Coxsbazar": "Cox's Bazar",
    "Jashore": "Jessore",
    "Moulvibazar": "Maulvibazar",
    "Chapainawabganj": "Nawabganj",
    "Netrokona": "Netrakona",
}

# BMET country label -> world-atlas country name, where they differ.
COUNTRY_TO_GEO = {
    "United Arab Emirates (UAE)": "United Arab Emirates",
    "United Kingdom (UK)": "United Kingdom",
    "United States of America (USA)": "United States of America",
    "Russian Federation": "Russia",
    "North Macedonia (formerly Macedonia)": "Macedonia",
    "Eswatini (formerly Swaziland)": "eSwatini",
    "Ivory Coast": "Côte d'Ivoire",
    "Cote d'Ivoire": "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia and Herz.",
    "Dominican Republic": "Dominican Rep.",
    "Equatorial Guinea": "Eq. Guinea",
    "South Sudan": "S. Sudan",
    "Solomon Islands": "Solomon Is.",
    "Czechia": "Czechia",
}

# The source lists Cote d'Ivoire twice, as "Ivory Coast" and "Cote d'Ivoire".
# They are one country; merge them so the map and the ranking are not split.
COUNTRY_MERGE = {"Ivory Coast": "Côte d'Ivoire", "Cote d'Ivoire": "Côte d'Ivoire"}

# Countries with no polygon at 110m resolution - mostly microstates, but note
# Singapore and Maldives are the 4th and 7th largest destinations. They are
# drawn as bubbles, so every destination appears on the map regardless.
EXTRA_CENTROIDS = {
    "Singapore": (103.82, 1.35),
    "Maldives": (73.51, 3.20),
    "Seychelles": (55.49, -4.68),
    "Mauritius": (57.55, -20.35),
    "Malta": (14.44, 35.90),
    "Hong Kong": (114.17, 22.32),
    "Macau": (113.54, 22.20),
    "Bahrain": (50.59, 26.07),
    "Palau": (134.58, 7.51),
    "Samoa": (-172.10, -13.76),
    "Andorra": (1.52, 42.51),
    "Micronesia": (158.21, 6.92),
    "Cook Islands": (-159.78, -21.24),
    "Liechtenstein": (9.55, 47.17),
    "Nauru": (166.93, -0.52),
    "Tonga": (-175.20, -21.18),
    "Bermuda": (-64.75, 32.32),
    "Turks & Caicos Islands": (-71.80, 21.72),
    "Barbados": (-59.54, 13.19),
}


def fetch_cached(url: str, name: str) -> dict:
    GEO_CACHE.mkdir(parents=True, exist_ok=True)
    p = GEO_CACHE / name
    if not p.exists():
        print(f"  downloading {name} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "bmet-dashboard-build"})
        with urllib.request.urlopen(req, timeout=180) as r:
            p.write_bytes(r.read())
    return json.loads(p.read_text())


# Working-age band. Emigration is overwhelmingly working-age, so a rate per
# 15-64 resident is the more faithful denominator; total population is kept as
# well because it is the figure most readers expect.
WORKING_AGE_COLS = [
    "T_15_19", "T_20_24", "T_25_29", "T_30_34", "T_35_39",
    "T_40_44", "T_45_49", "T_50_54", "T_55_59", "T_60_64",
]


def load_population() -> dict[str, dict]:
    """District -> {total, working-age 15-64} from the 2022 census."""
    GEO_CACHE.mkdir(parents=True, exist_ok=True)
    p = GEO_CACHE / "pop_adm2.csv"
    if not p.exists():
        print("  downloading pop_adm2.csv ...")
        req = urllib.request.Request(POP_URL, headers={"User-Agent": "bmet-dashboard-build"})
        with urllib.request.urlopen(req, timeout=180) as r:
            p.write_bytes(r.read())
    return {
        r["ADM2_NAME"].strip(): {
            "t": int(r["T_TL"]),
            "w": sum(int(r[c]) for c in WORKING_AGE_COLS),
        }
        for r in csv.DictReader(p.read_text(encoding="utf-8-sig").splitlines())
    }


def load_remittance() -> dict[str, dict[str, float]]:
    """District -> {fiscal year: million USD}, from the Bangladesh Bank extract.

    Optional: the dashboard hides the remittance lens when this is absent.
    Annual only - Bangladesh Bank's district figures exist as a fiscal-year
    series from FY 2017-18; the monthly tables start only in late 2024.
    """
    f = ROOT / "remittance" / "remittance_annual_fy.csv"
    if not f.exists():
        return {}
    out: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(f.read_text().splitlines()):
        out.setdefault(r["district"], {})[r["fiscal_year"]] = float(r["remittance_musd"])
    return out


# Bangladesh Bank's country labels, reassembled from stacked PDF headers,
# against the destination list. "Other countries" is a real aggregate row and
# stays out of the map on purpose.
REM_COUNTRY_ALIAS = {
    "China Of Hong Sar": "Hong Kong",
    "Of Korea, Republic": "South Korea",
    "Countries Other": "Other countries",
}


def load_migrant_stock() -> dict[str, int]:
    """Country -> Bangladeshi migrants living there (UN DESA, 2024).

    Remittance comes from everyone settled abroad, while a clearance is one new
    worker in a three-year window. Comparing those two directly is a flow
    against a stock; this is the denominator that makes the comparison fair.
    """
    f = ROOT / "remittance" / "migrant_stock_2024.csv"
    if not f.exists():
        return {}
    return {
        r["country"]: int(float(r["migrants"]))
        for r in csv.DictReader(f.read_text().splitlines())
        if r.get("matched") == "True" and float(r["migrants"]) > 0
    }


def load_country_remittance() -> dict[str, dict[str, float]]:
    """Country -> {fiscal year: million USD} (Bangladesh Bank Annex-III)."""
    f = ROOT / "remittance" / "remittance_country_fy.csv"
    if not f.exists():
        return {}
    out: dict[str, dict[str, float]] = {}
    for r in csv.DictReader(f.read_text().splitlines()):
        name = REM_COUNTRY_ALIAS.get(r["country"], r["country"])
        out.setdefault(name, {})[r["fiscal_year"]] = float(r["remittance_musd"])
    return out


def round_coords(obj, nd: int = 3):
    """Trim coordinate precision. 3dp is ~110m, far finer than a district map needs."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def polygon_centroid(geom) -> tuple[float, float]:
    """Area-weighted centroid of the largest ring, good enough to place a bubble."""
    rings = []
    if geom["type"] == "Polygon":
        rings = [geom["coordinates"][0]]
    elif geom["type"] == "MultiPolygon":
        rings = [p[0] for p in geom["coordinates"]]
    best, best_area = None, -1.0
    for ring in rings:
        a = 0.0
        cx = cy = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i][0], ring[i][1]
            x1, y1 = ring[i + 1][0], ring[i + 1][1]
            cr = x0 * y1 - x1 * y0
            a += cr
            cx += (x0 + x1) * cr
            cy += (y0 + y1) * cr
        if abs(a) < 1e-12:
            continue
        a *= 0.5
        if abs(a) > best_area:
            best_area = abs(a)
            best = (cx / (6 * a), cy / (6 * a))
    return best or (0.0, 0.0)


def topo_to_geo(topo: dict, obj_name: str) -> dict:
    """Minimal TopoJSON -> GeoJSON decoder (avoids a JS dependency at build time)."""
    tr = topo.get("transform")
    sx, sy = (tr["scale"] if tr else (1, 1))
    tx, ty = (tr["translate"] if tr else (0, 0))

    def decode_arc(arc):
        out, x, y = [], 0, 0
        for dx, dy in arc:
            if tr:
                x += dx
                y += dy
                out.append([x * sx + tx, y * sy + ty])
            else:
                out.append([dx, dy])
        return out

    arcs = [decode_arc(a) for a in topo["arcs"]]

    def ring(idxs):
        pts = []
        for i in idxs:
            a = arcs[~i][::-1] if i < 0 else arcs[i]
            pts.extend(a[1:] if pts else a)
        return pts

    feats = []
    for g in topo["objects"][obj_name]["geometries"]:
        if g["type"] == "Polygon":
            coords = [ring(r) for r in g["arcs"]]
        elif g["type"] == "MultiPolygon":
            coords = [[ring(r) for r in poly] for poly in g["arcs"]]
        else:
            continue
        feats.append(
            {
                "type": "Feature",
                "id": g.get("id"),
                "properties": g.get("properties", {}),
                "geometry": {"type": g["type"], "coordinates": coords},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def main() -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    con = connect()
    print("[build] reading database ...")

    districts = con.execute(
        "SELECT d.name, v.name FROM district d JOIN division v ON v.division_id = d.division_id"
        " WHERE d.is_valid = 1 ORDER BY d.name"
    ).fetchall()
    dnames = [d for d, _ in districts]
    ddiv = {d: v for d, v in districts}

    # ---- geometry -------------------------------------------------------
    print("[build] geometry ...")
    bd = fetch_cached(BD_ADM2_URL, "bd_adm2.geojson")
    world_topo = fetch_cached(WORLD_URL, "world-110m.json")
    world = topo_to_geo(world_topo, "countries")

    geo_by_name = {f["properties"].get("shapeName"): f for f in bd["features"]}
    bd_out = {"type": "FeatureCollection", "features": []}
    unmatched_d = []
    for d in dnames:
        key = DISTRICT_TO_GEO.get(d, d)
        f = geo_by_name.get(key)
        if not f:
            unmatched_d.append(d)
            continue
        bd_out["features"].append(
            {
                "type": "Feature",
                "properties": {"name": d, "division": ddiv[d]},
                "geometry": {
                    "type": f["geometry"]["type"],
                    "coordinates": round_coords(f["geometry"]["coordinates"]),
                },
            }
        )
    if unmatched_d:
        sys.exit(f"FATAL: districts with no geometry: {unmatched_d}")
    dcentroid = {
        f["properties"]["name"]: polygon_centroid(f["geometry"])
        for f in bd_out["features"]
    }

    # Population, on the same eight spelling variants as the boundary file.
    pop_raw = load_population()
    dpop = {d: pop_raw.get(DISTRICT_TO_GEO.get(d, d)) for d in dnames}
    missing_pop = [d for d, v in dpop.items() if not v or not v["t"] or not v["w"]]
    if missing_pop:
        sys.exit(f"FATAL: districts with no population: {missing_pop}")
    tot_t = sum(v["t"] for v in dpop.values())
    tot_w = sum(v["w"] for v in dpop.values())
    rem = load_remittance()
    crem = load_country_remittance()
    stock = load_migrant_stock()
    if rem:
        fys = sorted({fy for v in rem.values() for fy in v})
        miss = [d for d in dnames if d not in rem]
        print(f"  remittance mapped              : {len(rem)}/64 districts, "
              f"{len(fys)} fiscal years {fys[0]}..{fys[-1]}"
              + (f"  MISSING {miss}" if miss else ""))
    print(f"  population mapped              : {len(dpop)}/64  "
          f"(total {tot_t:,}; working age 15-64 {tot_w:,} = {100*tot_w/tot_t:.1f}%)")
    print(f"  districts mapped to geometry : {len(bd_out['features'])}/64")

    # ---- countries ------------------------------------------------------
    rows = con.execute(
        "SELECT country_id, name, total_records FROM country WHERE has_data = 1"
    ).fetchall()
    world_by_name = {f["properties"].get("name"): f for f in world["features"]}

    # merge duplicate source entries into one display country
    merged: dict[str, dict] = {}
    id_to_key: dict[int, str] = {}
    for cid, name, tot in rows:
        key = COUNTRY_MERGE.get(name, name)
        m = merged.setdefault(key, {"name": key, "ids": [], "total": 0})
        m["ids"].append(cid)
        m["total"] += tot or 0
        id_to_key[cid] = key

    centroids: dict[str, tuple[float, float]] = {}
    geo_names: dict[str, str] = {}
    for key, m in merged.items():
        gname = COUNTRY_TO_GEO.get(key, key)
        # a merged key may map through either source label
        if gname not in world_by_name:
            for src in rows:
                if COUNTRY_MERGE.get(src[1], src[1]) == key:
                    cand = COUNTRY_TO_GEO.get(src[1], src[1])
                    if cand in world_by_name:
                        gname = cand
                        break
        if gname in world_by_name:
            geo_names[key] = gname
            centroids[key] = polygon_centroid(world_by_name[gname]["geometry"])
        elif key in EXTRA_CENTROIDS:
            centroids[key] = EXTRA_CENTROIDS[key]
        else:
            centroids[key] = (0.0, 0.0)

    no_geo = [k for k in merged if k not in geo_names and k not in EXTRA_CENTROIDS]
    big_no_geo = [k for k in no_geo if merged[k]["total"] > 500]
    print(f"  countries: {len(merged)}  with polygon: {len(geo_names)}  "
          f"bubble-only: {len(merged)-len(geo_names)}  unplaced: {len(no_geo)}")
    if big_no_geo:
        sys.exit(f"FATAL: high-volume countries with no position: {big_no_geo}")
    if no_geo:
        print(f"  unplaced (low volume, omitted from map, kept in tables): {no_geo}")

    # ---- the cube -------------------------------------------------------
    print("[build] aggregating ...")
    didx = {d: i for i, d in enumerate(dnames)}
    ckeys = sorted(merged, key=lambda k: -merged[k]["total"])
    cidx = {k: i for i, k in enumerate(ckeys)}

    if stock:
        sm = sum(1 for k in ckeys if k in stock)
        print(f"  migrant stock (UN DESA 2024)   : {sm} countries, "
              f"{sum(stock.values()):,} Bangladeshis abroad")
    if crem:
        matched = sum(1 for k in ckeys if k in crem)
        unmatched = sorted(set(crem) - set(ckeys))
        cfys = sorted({fy for v in crem.values() for fy in v})
        print(f"  country remittance             : {matched}/{len(crem)} joined to the "
              f"country list, {len(cfys)} fiscal years {cfys[0]}..{cfys[-1]}")
        if unmatched:
            print(f"    not on the destination list  : {unmatched}")

    # One cube per crawled gender, plus male derived by subtraction. The source's
    # three gender buckets sum exactly to the unfiltered total, so male is exact
    # and never had to be crawled.
    cubes: dict[int, dict[tuple[int, int, int], int]] = {}
    months: dict[str, int] = {}
    for date, cid, gid, district, cnt in con.execute(
        "SELECT date, country_id, gender_id, district, count FROM daily_country"
    ):
        if date in VOLATILE_DATES:
            continue  # a catch-all bucket, not a day - see bmet_crawler
        di = didx.get(district)
        if di is None:
            continue  # Unknown/Unknown and the one junk pair
        key = id_to_key.get(cid)
        if key is None:
            continue
        ym = date[:7]
        mi = months.setdefault(ym, len(months))
        k = (mi, di, cidx[key])
        c = cubes.setdefault(gid, {})
        c[k] = c.get(k, 0) + cnt

    mlist = sorted(months, key=lambda m: m)
    remap = {months[m]: i for i, m in enumerate(mlist)}

    have_gender = 2 in cubes
    if have_gender:
        male = dict(cubes[0])
        for gid in (2, 3):
            for k, v in cubes.get(gid, {}).items():
                male[k] = male.get(k, 0) - v

        # The three slices cannot be crawled atomically - each is a separate
        # pass over ~75k requests - and BMET keeps entering records while they
        # run. A cell whose female count was captured after its all count can
        # therefore exceed it, giving a small negative male value. Clamp those
        # to zero and report the magnitude; fail only if it is large enough to
        # matter, which would mean a genuinely incomplete crawl rather than
        # ordinary drift.
        neg = {k: v for k, v in male.items() if v < 0}
        neg_records = -sum(neg.values())
        total_all = sum(cubes[0].values())
        if neg:
            share = 100 * neg_records / max(total_all, 1)
            print(f"  gender drift: {len(neg)} cells negative by {neg_records} records "
                  f"({share:.4f}% of all) - clamped to zero")
            if share > 0.01:
                sys.exit(
                    f"FATAL: {neg_records:,} records of negative male ({share:.3f}%) - "
                    "the gender crawl looks incomplete, not merely stale"
                )
        cubes[MALE] = {k: max(v, 0) for k, v in male.items() if v > 0}

    def pack(cube):
        e = sorted(((remap[m], d, c, v) for (m, d, c), v in cube.items()))
        return {"m": [x[0] for x in e], "d": [x[1] for x in e],
                "c": [x[2] for x in e], "v": [x[3] for x in e]}

    entries = sorted(((remap[m], d, c, v) for (m, d, c), v in cubes[0].items()))
    for gid, cube in sorted(cubes.items()):
        print(f"  cube gender {gid:<2} rows: {len(cube):>7,}  "
              f"records {sum(cube.values()):>10,}")
    print(f"  months: {len(mlist)}")

    # national daily series, for the fine-grained trend
    daily = [
        (d, v)
        for d, v in con.execute(
            "SELECT date, SUM(count) FROM daily_all GROUP BY date ORDER BY date"
        )
        if d not in VOLATILE_DATES
    ]

    total = sum(v for *_, v in entries)
    payload = {
        "meta": {
            "generated": today().isoformat(),
            "source": "BMET / OEP geo-clearance report, oep.gov.bd",
            "popSource": "District population: 2022 census, UN OCHA COD-PS (UNFPA/BBS)",
            "remSource": ("District remittance: Bangladesh Bank, Monthly Report on Workers' "
                          "Remittance Inflows (Annex-IV), million USD by fiscal year"),
            "stockSource": "Migrant stock: UN DESA International Migrant Stock 2024",
            "dateStart": DATA_START.isoformat(),
            "dateEnd": max(d for d, _ in daily),
            "total": total,
            "volatileDates": sorted(VOLATILE_DATES),
            "note": (
                "Counts are overseas employment clearances by district of origin. "
                "2023-06-19 is a catch-all bucket, not a day, and is excluded."
            ),
        },
        # District centroid, so the connection arcs leave from the real place
        # rather than a single national point.
        "districts": [
            {"n": d, "v": ddiv[d], "c": [round(x, 2) for x in dcentroid[d]],
             "p": dpop[d]["t"], "pw": dpop[d]["w"],
             "r": rem.get(d) or None}
            for d in dnames
        ],
        "countries": [
            {"n": k, "g": geo_names.get(k), "c": [round(x, 2) for x in centroids[k]],
             "r": crem.get(k) or None, "s": stock.get(k) or None}
            for k in ckeys
        ],
        "months": mlist,
        # parallel arrays compress far better than an array of objects
        "cube": pack(cubes[0]),
        # keyed by gender: 1 male, 2 female. Absent when the gender crawl has
        # not run, and the page hides its toggle in that case.
        "cubesByGender": {
            str(g): pack(cubes[g]) for g in (MALE, 2) if g in cubes
        },
        "daily": {"dates": [d for d, _ in daily], "values": [v for _, v in daily]},
    }

    def write(name: str, obj) -> None:
        p = SITE_DATA / name
        p.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        print(f"  {name:<24} {p.stat().st_size/1024:8.0f} KB")

    print("[build] writing site/data ...")
    write("dashboard.json", payload)
    write("bd-districts.geo.json", bd_out)
    world_min = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": f["properties"].get("name")},
                "geometry": {
                    "type": f["geometry"]["type"],
                    "coordinates": round_coords(f["geometry"]["coordinates"], 2),
                },
            }
            for f in world["features"]
        ],
    }
    write("world.geo.json", world_min)
    print(f"[build] done — {total:,} clearances across "
          f"{len(dnames)} districts and {len(ckeys)} countries")
    con.close()


if __name__ == "__main__":
    main()
