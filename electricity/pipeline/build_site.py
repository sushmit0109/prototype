"""Turn the scraped raw data into the compact JSON the dashboard loads.

Everything the page reads is produced here, so the front-end never parses a
government page itself. Files land in prototype/electricity/data/.

  meta.json         build time, coverage, per-source record counts
  latest.json       headline numbers for the hero panel
  daily.json        one row per day, 2015 -> today (PGCB)
  monthly.json      monthly rollup for the long view
  hourly/<year>.json  hourly series, split per year to keep requests small
  zones.json        per-zone latest + daily history (BPDB area-wise)
  fuelmix.json      national and zone fuel mix (BPDB PDFs)
  plants.json       latest per-plant status, geocoded
  substations.json  latest per-substation peak load, geocoded
  integrity.json    cross-source agreement checks

  python build_site.py
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from common import (FUELS, RAW, SITE_DATA, ZONES, ZONE_BN, num, read_csv,
                    read_json, write_json)
from population import (CENSUS_YEAR, SOURCE_BN as POP_SOURCE_BN,
                        SOURCE_EN as POP_SOURCE_EN, zone_population)

PGCB = RAW / "pgcb"
DAILYDIR = RAW / "bpdb" / "daily"
AREA_DIR = RAW / "area"
GEO = RAW / "geo"


def r(x, n=1):
    """Round, preserving None."""
    return None if x is None else round(x, n)


# National installed capacity is ~29 GW and the all-time peak demand is under
# 20 GW, so any hourly figure above this ceiling is a data-entry error, not a
# reading. They are quarantined and counted rather than charted.
PLAUSIBLE_MAX_MW = 20000

# PGCB's archive carries rows back to 2015, but demand/supply are blank before
# 2026 and load-shed is recorded as 0 for ~99.9% of hours before this year.
# Those zeros mean "nothing was published", not "nothing was shed", so the site
# must not draw them as a flat zero line.
REPORTING_START = "2022-01-01"


# ------------------------------------------------------------------ PGCB

OUTLIERS = []


def load_hourly():
    rows = []
    for f in sorted(PGCB.glob("hourly_*.csv")):
        year = f.stem.split("_", 1)[1][:4]
        if not (year.isdigit() and 2010 <= int(year) <= 2035):
            continue  # implausible bucket from an upstream typo
        for x in read_csv(f):
            rec = {
                "dt": x["datetime"],
                "date": x["date"],
                "hour": int(x["hour"]),
                "demand": num(x["demand"]),
                "supply": num(x["supply"]),
                "loadshed": num(x["loadshed"]),
                "peak": x.get("peak") or "",
            }
            for k in ("demand", "supply", "loadshed"):
                v = rec[k]
                if v is not None and v > PLAUSIBLE_MAX_MW:
                    OUTLIERS.append({"datetime": rec["dt"], "field": k, "value": v})
                    rec[k] = None
            rows.append(rec)
    rows.sort(key=lambda z: z["dt"])
    return rows


def build_hourly_files(rows):
    """One file per month. The hourly job then rewrites only the current
    month, keeping each commit small; older months never change again."""
    by_month = defaultdict(list)
    for x in rows:
        by_month[x["date"][:7]].append(x)
    months = []
    for m, rs in sorted(by_month.items()):
        write_json(SITE_DATA / "hourly" / f"{m}.json", {
            "month": m,
            "cols": ["datetime", "demand", "supply", "loadshed"],
            "rows": [[x["dt"], x["demand"], x["supply"], x["loadshed"]] for x in rs],
        })
        months.append(m)

    # remove per-year files written by the previous layout
    for f in (SITE_DATA / "hourly").glob("*.json"):
        if len(f.stem) == 4:
            f.unlink()
    return months


def build_daily(rows):
    by_day = defaultdict(list)
    for x in rows:
        by_day[x["date"]].append(x)

    out = []
    for d, rs in sorted(by_day.items()):
        dem = [x["demand"] for x in rs if x["demand"] is not None]
        sup = [x["supply"] for x in rs if x["supply"] is not None]
        shed = [x["loadshed"] for x in rs if x["loadshed"] is not None]
        ev = next((x for x in rs if x["peak"] == "evening"), None)
        # A day counts as reported if anything non-zero was ever published for
        # it. Before 2022 almost every hour reads 0, which is an absence of
        # publication rather than an absence of load-shedding.
        reported = bool(dem or sup or any(v > 0 for v in shed))
        out.append({
            "date": d,
            "n": len(rs),
            "reported": reported,
            "peak_demand": max(dem) if dem else None,
            "peak_supply": max(sup) if sup else None,
            "max_loadshed": max(shed) if shed else None,
            "mean_loadshed": r(sum(shed) / len(shed)) if shed else None,
            # one hourly reading of X MW held for an hour is X MWh not served
            "energy_shed_mwh": r(sum(shed)) if shed else None,
            "hours_shed": sum(1 for v in shed if v > 0),
            "evening_loadshed": ev["loadshed"] if ev else None,
        })
    return out


def pctile(values, q):
    """Nearest-rank percentile; used instead of a maximum, which is an
    extremum of one observation and grows with sample size."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return v[min(len(v) - 1, int(q * (len(v) - 1)))]


def build_monthly(daily):
    by_m = defaultdict(list)
    for d in daily:
        by_m[d["date"][:7]].append(d)
    out = []
    for m, ds in sorted(by_m.items()):
        peaks = [d["peak_demand"] for d in ds if d["peak_demand"]]
        sheds = [d["max_loadshed"] for d in ds if d["max_loadshed"] is not None]
        energy = [d["energy_shed_mwh"] for d in ds if d["energy_shed_mwh"] is not None]
        hrs = [d["hours_shed"] for d in ds]
        # Several measures of the same month, because they disagree and the
        # choice of one is itself an editorial act. A maximum is the most
        # fragile: a single mis-keyed hour can put a quiet month above a
        # catastrophic one, so the 95th percentile is carried beside it.
        out.append({
            "month": m,
            "days": len(ds),
            "reported_days": len(energy),
            "peak_demand": max(peaks) if peaks else None,
            "mean_peak_demand": r(sum(peaks) / len(peaks)) if peaks else None,
            "max_loadshed": max(sheds) if sheds else None,
            "p95_loadshed": pctile(sheds, 0.95),
            "energy_shed_mwh": r(sum(energy)) if energy else None,
            "mean_energy_shed_mwh": r(sum(energy) / len(energy)) if energy else None,
            "median_energy_shed_mwh": r(pctile(energy, 0.5)) if energy else None,
            "mean_hours_shed": r(sum(hrs) / len(ds)) if ds else None,
        })
    return out


# ------------------------------------------------------------- BPDB daily

# Some editions print the whole energy sheet a thousand times too large — the
# columns are still headed "MKWHr." but hold kWh-scale numbers (e.g. energy
# generated 219,337.66 for a day that actually produced 219.3 MkWh). National
# daily generation has never been outside roughly 100-500 MkWh, so anything an
# order of magnitude beyond that is a unit slip, and the whole record is scaled
# together to keep it internally consistent.
ENERGY_SANITY_MAX = 5000
# Daily national generation has never been below this in MkWh; a total under it
# means the sheet's energy block is printed in a smaller unit.
ENERGY_UNIT_FLOOR = 50
ENERGY_FIELDS = ("energy_generated", "energy_unserved", "energy_demand",
                 "import_energy")


# No single generating unit in Bangladesh exceeds about 1,500 MW (the largest
# import block is ~1,496 MW; Payra and Rampal are 1,320 MW). A per-station row
# above this ceiling means the report's text layer defeated the parser, so the
# row is dropped and counted rather than charted.
PLANT_MAX_MW = 2000
DROPPED_PLANT_ROWS = []


def drop_implausible_plants(rec: dict) -> dict:
    ps = rec.get("plants")
    if not ps:
        return rec
    keep = []
    for p in ps:
        if (p.get("capacity_mw") or 0) > PLANT_MAX_MW:
            DROPPED_PLANT_ROWS.append({"date": rec.get("date"), "name": p.get("name"),
                                       "capacity_mw": p.get("capacity_mw")})
        else:
            keep.append(p)
    rec["plants"] = keep
    return rec


def normalise_units(rec: dict) -> dict:
    gen = rec.get("energy_generated")
    if gen is None or gen <= ENERGY_SANITY_MAX:
        return rec
    rec["unit_rescaled"] = True
    for k in ENERGY_FIELDS:
        if rec.get(k) is not None:
            rec[k] = r(rec[k] / 1000, 5)
    zf = rec.get("zone_fuel_energy")
    if zf:
        for zone, vals in zf.items():
            for fuel, v in list(vals.items()):
                if v is not None:
                    vals[fuel] = r(v / 1000, 3)
    return rec


GENREPORTS = {}


def load_bpdb():
    """Daily records keyed by report date.

    Generation reports are gathered separately, keyed by the date they
    themselves describe: several archive listings can resolve to the same
    NLDC sheet-1 date while carrying generation reports for different days,
    so deduplicating on sheet-1's date would silently discard them.
    """
    recs = {}
    rescaled = 0
    for f in sorted(DAILYDIR.glob("*.json")):
        d = read_json(f)
        if not d or d.get("failed") or not d.get("date"):
            continue
        d = drop_implausible_plants(normalise_units(d))
        rescaled += 1 if d.get("unit_rescaled") else 0
        g = d.get("genreport")
        # A report describes the day or two before the listing that published
        # it. Anything further away means its date line was misread — through
        # 2026 the source prints a stale year there — and such a record would
        # otherwise overwrite the real report for the date it lands on.
        listing = d.get("listing_date")
        dd_ = g.get("data_date") if g else None
        near = False
        if dd_ and listing:
            try:
                near = 0 <= (date.fromisoformat(listing)
                             - date.fromisoformat(dd_)).days <= 5
            except ValueError:
                near = False
        if g and dd_ and near and (
                "2024-01-01" <= dd_ <= date.today().isoformat()):
            cur = GENREPORTS.get(g["data_date"])
            if cur is None or len(json.dumps(g)) > len(json.dumps(cur)):
                GENREPORTS[g["data_date"]] = g
        # keep the richest record if two listings resolve to the same report date
        cur = recs.get(d["date"])
        if cur is None or len(json.dumps(d)) > len(json.dumps(cur)):
            recs[d["date"]] = d
    if rescaled:
        print(f"[build] rescaled {rescaled} day(s) whose energy sheet was "
              f"published in kWh under an MKWHr heading")
    if DROPPED_PLANT_ROWS:
        print(f"[build] dropped {len(DROPPED_PLANT_ROWS)} per-station row(s) above "
              f"{PLANT_MAX_MW} MW as unparseable")
    return recs


def build_fuelmix(bpdb):
    days = []
    for d, rec in sorted(bpdb.items()):
        zf = rec.get("zone_fuel_energy")
        if not zf:
            continue
        nat = {f: 0.0 for f in FUELS}
        for z, vals in zf.items():
            for f in FUELS:
                v = vals.get(f)
                if v:
                    nat[f] += v
        total = sum(nat.values())
        if total <= 0:
            continue
        days.append({
            "date": d,
            "total": r(total, 2),
            **{f: r(nat[f], 2) for f in FUELS},
            "cost_per_kwh": rec.get("cost_per_kwh"),
            "total_cost_tk": rec.get("total_cost_tk"),
        })
    return days


# Fuels are grouped as a reader thinks of them: the two oils together, the
# three renewables together. Eight separate bands would not survive a stacked
# monthly chart legibly, and the small ones carry no story on their own.
FUEL_GROUPS = [
    ("gas", ["gas"]),
    ("coal", ["coal"]),
    ("import", ["import"]),
    ("oil", ["hfo", "hsd"]),
    ("renewable", ["solar", "wind", "hydro"]),
]


def build_fuel_monthly(days):
    """Generation by fuel per month, as a daily average.

    A daily average rather than a monthly total, so a short month or an
    incomplete one cannot masquerade as a fall in generation.
    """
    by_month = defaultdict(list)
    for d in days:
        by_month[d["date"][:7]].append(d)

    out = []
    for m, ds in sorted(by_month.items()):
        row = {"month": m, "days": len(ds)}
        total = 0.0
        for name, parts in FUEL_GROUPS:
            v = sum(sum(d.get(p) or 0 for p in parts) for d in ds) / len(ds)
            row[name] = r(v, 2)
            total += v
        row["total"] = r(total, 2)
        costs = [d["cost_per_kwh"] for d in ds if d.get("cost_per_kwh")]
        row["cost_per_kwh"] = r(sum(costs) / len(costs), 3) if costs else None
        out.append(row)

    # The same month a year apart — matched on the day range, not just the
    # month. The current month is usually incomplete, and generation builds
    # through August, so weighing eleven days against a full thirty-one
    # understates the change.
    compare = None
    if out:
        cur_month = out[-1]["month"]
        y, mo = cur_month.split("-")
        cur_days = sorted(int(d["date"][8:10]) for d in by_month.get(cur_month, []))
        prev_month = f"{int(y) - 1}-{mo}"
        prev_all = by_month.get(prev_month, [])
        if cur_days and len(prev_all) >= 10:
            cutoff = max(cur_days)
            prev_days = [d for d in prev_all if int(d["date"][8:10]) <= cutoff]
            if len(prev_days) >= max(5, len(cur_days) // 2):
                def profile(ds):
                    row = {"days": len(ds)}
                    tot = 0.0
                    for name, parts in FUEL_GROUPS:
                        v = sum(sum(d.get(p) or 0 for p in parts) for d in ds) / len(ds)
                        row[name] = r(v, 2)
                        tot += v
                    row["total"] = r(tot, 2)
                    return row

                now_p = profile(by_month[cur_month])
                before_p = profile(prev_days)
                now_p["month"], before_p["month"] = cur_month, prev_month
                compare = {
                    "month": mo, "day_range": [min(cur_days), cutoff],
                    "now": now_p, "before": before_p,
                    "changes": {k: (r(100 * (now_p[k] - before_p[k]) / before_p[k], 1)
                                    if before_p.get(k) else None)
                                for k in ("total", "gas", "coal", "oil",
                                          "import", "renewable")},
                }
    return {"monthly": out, "same_month": compare}


def build_zone_fuel_latest(bpdb):
    for d in sorted(bpdb, reverse=True):
        zf = bpdb[d].get("zone_fuel_energy")
        if zf:
            return {"date": d, "zones": zf}
    return None


# --------------------------------------------------------------- geocoding

STOP = {
    "power", "plant", "station", "pp", "ps", "ccpp", "tpp", "gtpp", "hfo", "hsd",
    "mw", "unit", "units", "ltd", "limited", "ipp", "pdb", "egcb", "rpcl", "bpdb",
    "co", "company", "energy", "electric", "generation", "plc", "bd", "bangladesh",
    "the", "and", "of", "phase", "no", "block", "project", "simple", "cycle",
    "combined", "dual", "fuel", "engine", "barge", "mounted", "new", "old",
    "solar", "wind", "park", "npp", "gt", "st", "i", "ii", "iii", "iv", "v",
}


def toks(name: str):
    t = re.sub(r"\(.*?\)", " ", name or "")
    # NLDC writes some substations without spaces ("DhakaUniversity",
    # "HaripurSBU"); split on the camel-case boundary so they tokenise.
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    t = re.sub(r"[^A-Za-z\s]", " ", t).lower()
    return [w for w in t.split() if w not in STOP and len(w) > 2]


# Town-level positions for major stations that OpenStreetMap does not carry as
# a named power=plant. These are the *town*, not the plot: good enough to show
# where output sits on the grid, and flagged as approximate on the map.
CURATED = {
    "payra": (21.982, 90.253), "rampal": (22.556, 89.596),
    "maitree": (22.556, 89.596), "matarbari": (21.723, 91.930),
    "barapukuria": (25.533, 88.940), "ashuganj": (24.045, 91.000),
    "ghorasal": (23.978, 90.637), "ghorashal": (23.978, 90.637),
    "siddhirgonj": (23.681, 90.512), "siddhirganj": (23.681, 90.512),
    "haripur": (23.678, 90.533), "meghnaghat": (23.611, 90.593),
    "bibiyana": (24.420, 91.551), "sirajganj": (24.417, 89.720),
    "bheramara": (24.052, 88.982), "kaptai": (22.495, 92.220),
    "shahjibazar": (24.303, 91.452), "fenchugonj": (24.700, 91.930),
    "fenchuganj": (24.700, 91.930), "baghabari": (24.133, 89.593),
    "saidpur": (25.778, 88.893), "rooppur": (24.062, 89.048),
    "khulna": (22.820, 89.550), "chandpur": (23.220, 90.650),
    "rangpur": (25.750, 89.240), "kodda": (23.985, 90.380),
    "madanganj": (23.620, 90.510), "gagnagar": (23.630, 90.520),
    "sutiakhali": (24.680, 90.420), "teesta": (25.350, 89.550),
    "thakurgaon": (26.033, 88.470), "manikganj": (23.861, 90.003),
    "nababganj": (23.600, 90.000), "kamalaghat": (23.470, 91.180),
    "bhairob": (24.050, 90.980), "tangail": (24.250, 89.917),
    "moulvibazar": (24.483, 91.783), "pabna": (24.000, 89.233),
    "natore": (24.410, 89.000), "gopalganj": (23.005, 89.826),
    "faridpur": (23.606, 89.842), "jamalpur": (24.917, 89.937),
    "mymensingh": (24.757, 90.400), "sylhet": (24.900, 91.870),
    "barishal": (22.700, 90.370), "bogura": (24.850, 89.371),
    "cumilla": (23.460, 91.180), "feni": (23.017, 91.397),
    "chattogram": (22.335, 91.834), "julda": (22.238, 91.800),
    "raozan": (22.533, 91.933), "dohazari": (22.170, 92.070),
    "hathazari": (22.492, 91.806), "shikalbaha": (22.283, 91.850),
    "anwara": (22.190, 91.900), "patenga": (22.240, 91.800),
    "keraniganj": (23.700, 90.360), "amnura": (24.650, 88.300),
    "katakhali": (24.350, 88.680), "gazipur": (23.999, 90.421),
}

# Zone fallback centroids, used only when nothing else matches.
ZONE_CENTROID = {
    "dhaka": (23.85, 90.30), "chattogram": (22.35, 91.90),
    "cumilla": (23.35, 91.10), "mymensingh": (24.80, 90.30),
    "sylhet": (24.75, 91.70), "khulna": (22.90, 89.30),
    "barishal": (22.50, 90.30), "rajshahi": (24.45, 89.00),
    "rangpur": (25.75, 89.10),
}


class Geocoder:
    """Match a report's station/substation name to a coordinate.

    Tiers are tried in order and the winning tier is always recorded, so the
    map can be honest about how precise each dot is:
      osm       matched a named OpenStreetMap power feature
      place     matched an OpenStreetMap town/city of the same name
      curated   matched a known town in the table above
      zone      fell back to the centroid of the reporting zone
      none      not placed; shown in the table but not on the map
    """

    def __init__(self, tiers):
        # tiers: list of (tag, items)
        self.tiers = [(tag, [(set(toks(it["name"])), it) for it in items
                             if toks(it["name"])])
                      for tag, items in tiers]

    @staticmethod
    def _best(t, index):
        best, score = None, 0.0
        for otoks, it in index:
            inter = len(t & otoks)
            if not inter:
                continue
            s = inter / len(t | otoks)
            if (t & otoks) & set(CURATED):
                s += 0.15  # a place-name token agreeing is strong evidence
            if s > score:
                best, score = it, s
        return best, score

    def match(self, name, zone=None):
        t = set(toks(name))
        if t:
            for tag, index in self.tiers:
                best, score = self._best(t, index)
                if best and score >= 0.34:
                    return best["lat"], best["lon"], tag, r(score, 2)
        for w in toks(name):
            if w in CURATED:
                lat, lon = CURATED[w]
                return lat, lon, "curated", None
        if zone and zone in ZONE_CENTROID:
            lat, lon = ZONE_CENTROID[zone]
            return lat, lon, "zone", None
        return None, None, "none", None


# ------------------------------------------------ district point-in-polygon

def _in_ring(lon, lat, ring) -> bool:
    """Ray casting against one closed ring of [lon, lat] pairs."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_at = (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
            if lon < x_at:
                inside = not inside
        j = i
    return inside


class DistrictIndex:
    """Which district a coordinate falls in, with a bounding-box prefilter."""

    def __init__(self, geojson):
        self.items = []
        for f in (geojson or {}).get("features", []):
            props = f["properties"]
            for poly in f["geometry"]["coordinates"]:
                ring = poly[0]
                lons = [p[0] for p in ring]
                lats = [p[1] for p in ring]
                self.items.append((min(lons), min(lats), max(lons), max(lats),
                                   ring, props))

    def find(self, lat, lon):
        if lat is None or lon is None:
            return None, None
        for x0, y0, x1, y1, ring, props in self.items:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _in_ring(lon, lat, ring):
                return props["name_en"], props["zone"]
        return None, None


# ------------------------------------------------------------- gazetteer

def build_places(districts: "DistrictIndex", geojson):
    """Everywhere a person might type, mapped to the district it sits in.

    The published figures only go down to nine grid zones, but nobody thinks of
    themselves as living in "Dhaka zone" — they live in Ramna, or Savar, or
    Bhaluka. This gazetteer lets the page accept the name people actually use
    and resolve it upwards to the area the data is published for.

    Sources: district boundaries, upazila/thana boundaries (admin level 6), and
    named settlements — all from OpenStreetMap.
    """
    seen, out = set(), []
    # OSM's Bengali names often already carry the administrative word
    # ("ঢাকা জেলা"); the UI adds its own kind label, so strip it here.
    strip_bn = re.compile(r"\s*(জেলা|উপজেলা|থানা|সিটি কর্পোরেশন)\s*$")
    dist_bn = {f["properties"]["name_en"]: strip_bn.sub("", f["properties"].get("name_bn") or "")
               for f in (geojson or {}).get("features", [])}

    def add(name_en, name_bn, kind, district, zone, lat=None, lon=None):
        key = (kind, (name_en or "").lower(), district)
        if not name_en or key in seen:
            return
        seen.add(key)
        clean_bn = strip_bn.sub("", name_bn or "").strip()
        rec = {"n": name_en, "k": kind, "d": district, "z": zone}
        if clean_bn and clean_bn != name_en:
            rec["b"] = clean_bn
        if district and dist_bn.get(district):
            rec["db"] = dist_bn[district]
        if lat is not None:
            rec["lat"], rec["lon"] = round(lat, 4), round(lon, 4)
        out.append(rec)

    for f in (geojson or {}).get("features", []):
        p = f["properties"]
        add(p["name_en"], p.get("name_bn"), "district", p["name_en"], p["zone"])

    for kind, fname in (("upazila", "upazilas.json"), ("place", "places.json")):
        for it in read_json(GEO / fname, []) or []:
            name = re.sub(r"\s+(Sadar\s+)?(Upazila|Sub-?district|Thana|Paurashava|"
                          r"City\s+Corporation|District)$", "", it["name"],
                          flags=re.I).strip()
            dist, zone = districts.find(it.get("lat"), it.get("lon"))
            if not dist:
                continue          # outside the country outline, or unplaceable
            if name.lower() == dist.lower():
                continue          # the district itself, already listed
            add(name, it.get("name_bn"), kind, dist, zone, it.get("lat"), it.get("lon"))

    by_kind = Counter(x["k"] for x in out)
    return {"places": out, "counts": dict(by_kind)}


# --------------------------------------------------------- reason grouping

REASON_RULES = [
    (r"gas\s*(shortage|short|crisis)|low\s*gas|gas\s*pressure|gas\s*\(rms\)|"
     r"no\s*gas|gas\s*supply", "gas_shortage"),
    (r"liquid\s*fuel|fuel\s*shortage|hfo\s*shortage|no\s*fuel|oil\s*shortage",
     "fuel_shortage"),
    (r"overhaul|maintenance|outage|repair|inspection|shutdown|s/d|servicing",
     "maintenance"),
    (r"fault|trip|problem|damage|defect|breakdown|failure|leak", "fault"),
    (r"contract\s*expire|expired|decommission|retire|not\s*in\s*operation",
     "contract_ended"),
    (r"reserve|standby|stand\s*by|backing\s*down|low\s*demand|shut\s*down\s*for\s*low",
     "not_needed"),
]

REASON_BN = {
    "gas_shortage": "গ্যাস সংকট",
    "fuel_shortage": "জ্বালানি তেলের সংকট",
    "maintenance": "রক্ষণাবেক্ষণ",
    "fault": "যান্ত্রিক ত্রুটি",
    "contract_ended": "চুক্তি শেষ",
    "not_needed": "চাহিদা কম / রিজার্ভ",
    "other": "অন্যান্য",
    "none": "কারণ উল্লেখ নেই",
}
REASON_EN = {
    "gas_shortage": "Gas shortage",
    "fuel_shortage": "Liquid fuel shortage",
    "maintenance": "Maintenance / overhaul",
    "fault": "Mechanical fault",
    "contract_ended": "Contract ended",
    "not_needed": "Low demand / reserve",
    "other": "Other",
    "none": "No reason stated",
}


def classify_reason(remark: str) -> str:
    t = (remark or "").strip().lower()
    if not t or t in ("-", "--", "n/a"):
        return "none"
    for pat, key in REASON_RULES:
        if re.search(pat, t):
            return key
    return "other"


def build_plants(bpdb, geo, districts):
    latest = None
    for d in sorted(bpdb, reverse=True):
        if bpdb[d].get("plants"):
            latest = d
            break
    if not latest:
        return None

    plants = []
    for p in bpdb[latest]["plants"]:
        lat, lon, src, score = geo.match(p["name"], p.get("zone"))
        cap = p.get("capacity_mw") or 0
        peak = p.get("peak_mw") or 0
        reason = classify_reason(p.get("remarks"))
        dist, dzone = districts.find(lat, lon)
        plants.append({
            "district": dist,
            "name": p["name"],
            "zone": p.get("zone"),
            "producer": p.get("producer"),
            "capacity_mw": p.get("capacity_mw"),
            "peak_mw": p.get("peak_mw"),
            "energy_kwh": p.get("energy_kwh"),
            "idle_mw": r(max(cap - peak, 0)),
            "utilisation": r(peak / cap, 3) if cap else None,
            "remarks": p.get("remarks") or "",
            "reason": reason,
            "lat": lat, "lon": lon, "geo": src, "geo_score": score,
        })

    # how much capacity sat idle, grouped by the stated reason
    by_reason = defaultdict(lambda: {"idle_mw": 0.0, "plants": 0})
    for p in plants:
        if (p["peak_mw"] or 0) <= 0 and (p["capacity_mw"] or 0) > 0:
            g = by_reason[p["reason"]]
            g["idle_mw"] += p["capacity_mw"]
            g["plants"] += 1
    reasons = [{"reason": k, "idle_mw": r(v["idle_mw"]), "plants": v["plants"]}
               for k, v in sorted(by_reason.items(),
                                  key=lambda kv: -kv[1]["idle_mw"])]

    return {
        "date": latest,
        "plants": plants,
        "idle_by_reason": reasons,
        "total_capacity_mw": r(sum(p["capacity_mw"] or 0 for p in plants)),
        "total_peak_mw": r(sum(p["peak_mw"] or 0 for p in plants)),
        "geo_counts": dict(Counter(p["geo"] for p in plants)),
    }


def build_reason_history(bpdb):
    """Idle capacity by stated reason, per day — the 'why' time series."""
    out = []
    for d in sorted(bpdb):
        ps = bpdb[d].get("plants")
        if not ps:
            continue
        agg = defaultdict(float)
        for p in ps:
            cap = p.get("capacity_mw") or 0
            peak = p.get("peak_mw") or 0
            if cap > 0 and peak <= 0:
                agg[classify_reason(p.get("remarks"))] += cap
        if agg:
            out.append({"date": d, **{k: r(v) for k, v in agg.items()}})
    return out


def build_substations(bpdb, geo, districts):
    latest = None
    for d in sorted(bpdb, reverse=True):
        if bpdb[d].get("substations"):
            latest = d
            break
    if not latest:
        return None
    items = []
    for s in bpdb[latest]["substations"]:
        lat, lon, src, score = geo.match(s["name"])
        dist, dzone = districts.find(lat, lon)
        items.append({
            "name": s["name"], "load_mw": s["load_mw"], "hour": s.get("hour"),
            "lat": lat, "lon": lon, "geo": src,
            "district": dist, "zone": dzone,
        })
    return {
        "date": latest,
        "substations": items,
        "total_mw": r(sum(s["load_mw"] or 0 for s in items)),
        "geo_counts": dict(Counter(s["geo"] for s in items)),
    }


# ------------------------------------------------------------------ zones

def build_zones(area, bpdb):
    days = []
    for d, rec in sorted(area.items()):
        if rec.get("suspect"):
            continue
        z = rec["zones"]
        days.append({
            "date": d,
            **{k: [z[k]["demand"], z[k]["loadshed"]] for k in ZONES},
            "total_demand": rec["total_demand"],
            "total_loadshed": rec["total_loadshed"],
        })

    peak = []
    for d, rec in sorted(bpdb.items()):
        zp = rec.get("zone_peak")
        if not zp:
            continue
        peak.append({
            "date": d,
            **{k: [zp.get(k, {}).get("demand"), zp.get(k, {}).get("loadshed")]
               for k in ZONES},
            "total_demand": rec.get("peak_demand_total"),
            "total_loadshed": rec.get("peak_loadshed_total"),
        })

    return {"cols": ["demand", "loadshed"], "zones": ZONES,
            "areawise_daily": days, "nldc_evening_peak": peak}


# ------------------------------------------------- BPDB generation report

def build_official(bpdb):  # noqa: C901
    """Three things only BPDB's Daily Electricity Generation Report carries.

    causes      the evening-peak shortfall attributed to a cause, in MW, by
                BPDB itself — rather than inferred from per-plant remarks
    forecast    the load-shedding BPDB expected for the next day, set beside
                what actually happened, so the forecast can be scored
    unit_cost   cost per kWh for each fuel, from cost and energy on the same
                sheet: the price of running the grid on liquid fuel
    """
    causes, unit_cost = [], []
    forecast_for, actual_for = {}, {}

    for dd, g in sorted(GENREPORTS.items()):
        rec = bpdb.get(dd, {})

        cs = {k: g.get(k) for k in ("gas_lf", "kaptai", "maintenance", "coal")}
        if any(v is not None for v in cs.values()):
            causes.append({"date": dd,
                           **{k: (v or 0) for k, v in cs.items()},
                           "total": sum(v or 0 for v in cs.values())})

        e, c = g.get("energy_by_fuel") or {}, g.get("cost_by_fuel") or {}
        # Some editions print the per-fuel energy in a scale that does not
        # match the sheet's own total; a unit cost from those would be wrong by
        # orders of magnitude, so the row is only kept when the parts add up.
        tot_e, stated = sum(v or 0 for v in e.values()), g.get("total_energy")
        reconciles = (stated and tot_e and abs(tot_e - stated) / stated < 0.15)
        # Some editions print the whole energy block a thousand times small, so
        # the parts still agree with the stated total while the scale is wrong.
        # National daily generation sits near 100-500 MkWh, which identifies
        # those days and lets them be rescaled rather than discarded.
        scale = 1000.0 if (tot_e and tot_e < ENERGY_UNIT_FLOOR) else 1.0
        if e and c and reconciles:
            row = {"date": dd}
            # A fuel that barely ran gives a meaningless unit cost: the
            # denominator approaches zero and the ratio explodes. Below a
            # megawatt-hour-scale floor the day is simply not priced.
            floor = 1e6                       # 1 MkWh generated by that fuel
            for fuel, ekey in (("gas", "gas"), ("oil", "oil"), ("coal", "coal"),
                               ("import", "import")):
                kwh = (e.get(ekey) or 0) * 1e6 * scale
                if kwh > floor and c.get(fuel):
                    row[fuel] = r(c[fuel] / kwh, 2)
            ren_kwh = ((e.get("solar") or 0) + (e.get("hydro_wind") or 0)) * 1e6 * scale
            if ren_kwh > floor and c.get("renewable"):
                row["renewable"] = r(c["renewable"] / ren_kwh, 2)
            if len(row) > 1:
                unit_cost.append(row)

        if g.get("forecast_date") is not None and g.get("f_loadshed") is not None:
            forecast_for[g["forecast_date"]] = {
                "loadshed": g["f_loadshed"],
                "demand": g.get("f_eve_peak_demand"),
            }
        zs = g.get("zone_substation") or {}
        if zs:
            actual_for[dd] = {
                "loadshed": sum((v.get("loadshed") or 0) for v in zs.values()),
                "demand": sum((v.get("demand") or 0) for v in zs.values()),
            }
        elif rec.get("peak_loadshed_total") is not None:
            actual_for[dd] = {"loadshed": rec["peak_loadshed_total"],
                              "demand": rec.get("peak_demand_total")}

    forecast = []
    for d in sorted(set(forecast_for) & set(actual_for)):
        f, a = forecast_for[d], actual_for[d]
        forecast.append({"date": d,
                         "forecast_loadshed": f["loadshed"],
                         "actual_loadshed": a["loadshed"],
                         "forecast_demand": f["demand"],
                         "actual_demand": a["demand"]})

    def score(rows):
        zero = [x for x in rows if (x["forecast_loadshed"] or 0) == 0]
        miss = [x for x in zero if (x["actual_loadshed"] or 0) > 0]
        return {
            "days": len(rows),
            "forecast_zero": len(zero),
            "forecast_zero_but_shed": len(miss),
            "mean_shed_on_those_days": r(
                sum(x["actual_loadshed"] for x in miss) / len(miss)) if miss else None,
            "mean_forecast": r(
                sum(x["forecast_loadshed"] or 0 for x in rows) / len(rows)) if rows else None,
            "worst": max(miss, key=lambda x: x["actual_loadshed"]) if miss else None,
        }

    by_year = {}
    for row in forecast:
        by_year.setdefault(row["date"][:4], []).append(row)

    zero_fc = [x for x in forecast if (x["forecast_loadshed"] or 0) == 0]
    missed = [x for x in zero_fc if (x["actual_loadshed"] or 0) > 0]
    return {
        "causes": causes,
        "unit_cost": unit_cost,
        "forecast": forecast,
        "forecast_summary": {
            "days": len(forecast),
            "forecast_zero": len(zero_fc),
            "forecast_zero_but_shed": len(missed),
            "mean_shed_on_those_days": r(
                sum(x["actual_loadshed"] for x in missed) / len(missed)) if missed else None,
            "worst": max(missed, key=lambda x: x["actual_loadshed"]) if missed else None,
            # The practice changed: 2025 forecast zero almost daily, 2026 far
            # less often but misses by more, so the years are scored apart.
            "by_year": {y: score(rows) for y, rows in sorted(by_year.items())},
        },
    }


# --------------------------------------------------------------- seasonal

SEASONAL_SMOOTH = 7          # days in the centred rolling mean
COMPARE_WINDOW = 30          # days in the "now vs a year ago" comparison


# ── PGCB's own workbooks ─────────────────────────────────────────────────────
#
# erp.powergrid.gov.bd publishes each day's NLDC reports as a spreadsheet as
# well as a PDF. The spreadsheet carries two things the PDFs do not: the
# generation mix at half-hourly resolution, and the shortage alongside it. It
# is also the better witness for everything the two share, never having been
# through a PDF text layer, so it is preferred where it exists (2025 onward).

ERP_DIR = RAW / "erp"

# En-Curve's fourteen columns onto the eight fuels used across the site. The
# public/private split is an ownership distinction, not a fuel one, and the
# four import columns are separate interconnectors.
ERP_FUEL_MAP = {
    "gas_public": "gas", "gas_pvt": "gas",
    "coal": "coal",
    "hfo_public": "hfo", "hfo_pvt": "hfo",
    "hsd_public": "hsd", "hsd_pvt": "hsd",
    "hydro": "hydro", "solar": "solar", "wind": "wind",
    "hvdc": "import", "nepal": "import", "tripura": "import",
    "adani": "import",
}

DAYCURVE_WINDOW = 30            # days averaged into the profile
DAYCURVE_MIN_SLOTS = 40         # a day missing more than a few slots is skipped


def load_erp_halfhourly():
    """date -> {time -> {fuel -> MW, 'shortage': MW, 'total': MW}}."""
    out = {}
    for f in sorted(ERP_DIR.glob("halfhourly_*.csv")):
        for r in read_csv(f):
            slot = out.setdefault(r["date"], {}).setdefault(r["time"], {})
            for col, fuel in ERP_FUEL_MAP.items():
                v = num(r.get(col))
                if v is not None:
                    slot[fuel] = slot.get(fuel, 0.0) + v
            for k in ("shortage", "total"):
                v = num(r.get(k))
                if v is not None:
                    slot[k] = v
    return out


def load_erp_hourly():
    """date -> [{time, generation, loadshed, demand}], from the workbook P4."""
    out = {}
    for f in sorted(ERP_DIR.glob("hourly_*.csv")):
        for r in read_csv(f):
            out.setdefault(r["date"], []).append({
                "time": r["time"], "generation": num(r.get("generation")),
                "loadshed": num(r.get("loadshed")), "demand": num(r.get("demand"))})
    return out


def build_daycurve(hh):
    """The generation mix and the shortage through an average day.

    Averaged over a window of recent days rather than shown for one day: a
    single day is weather and outages, whereas the shape that repeats is the
    thing worth explaining — which fuels carry the base load, which are
    started only for the evening peak, and when the shortage actually falls.

    The same window one and two years earlier is included so the change in
    shape is visible, not just the level.
    """
    if not hh:
        return None
    days = sorted(hh)
    slots = sorted({t for d in days for t in hh[d]})
    if not slots:
        return None

    def profile(window):
        """Mean MW per slot across the given days, and the days that counted."""
        used = [d for d in window if len(hh[d]) >= DAYCURVE_MIN_SLOTS]
        if not used:
            return None, []
        rows = []
        for t in slots:
            vals = [hh[d][t] for d in used if t in hh[d]]
            if not vals:
                continue
            rec = {"time": t, "n": len(vals)}
            for fuel in FUELS:
                got = [v[fuel] for v in vals if v.get(fuel) is not None]
                rec[fuel] = round(sum(got) / len(got), 1) if got else 0.0
            # A handful of bad nights drag the mean shortage well above what a
            # normal night looks like, so the median leads and the mean is
            # carried beside it rather than instead of it.
            short = [v["shortage"] for v in vals if v.get("shortage") is not None]
            rec["shortage"] = round(statistics.median(short), 1) if short else None
            rec["shortage_mean"] = round(sum(short) / len(short), 1) if short else None
            rows.append(rec)
        return rows, used

    latest = days[-1]
    window = days[-DAYCURVE_WINDOW:]
    now, used = profile(window)
    if not now:
        return None

    # the same calendar window in earlier years, so like is compared with like
    prior = []
    for back in (1, 2):
        try:
            lo = date.fromisoformat(window[0]).replace(
                year=date.fromisoformat(window[0]).year - back).isoformat()
            hi = date.fromisoformat(latest).replace(
                year=date.fromisoformat(latest).year - back).isoformat()
        except ValueError:                       # 29 Feb
            continue
        earlier = [d for d in days if lo <= d <= hi]
        rows, used_p = profile(earlier)
        if rows and len(used_p) >= 7:
            prior.append({"year": lo[:4], "rows": rows, "days": len(used_p),
                          "from": min(used_p), "to": max(used_p)})

    # What the shape says, computed rather than asserted. The swing of each
    # fuel across the day is the point: if one fuel carries nearly all of it,
    # that fuel sets the cost of every extra unit at the peak.
    swing = {}
    for fuel in FUELS:
        vals = [r[fuel] for r in now]
        swing[fuel] = round(max(vals) - min(vals), 1)
    oil_vals = [r["hfo"] + r["hsd"] for r in now]
    swing["oil"] = round(max(oil_vals) - min(oil_vals), 1)
    total_vals = [sum(r[f] for f in FUELS) for r in now]
    swing["total"] = round(max(total_vals) - min(total_vals), 1)

    peak = max(now, key=lambda r: sum(r[f] for f in FUELS))
    trough = min(now, key=lambda r: sum(r[f] for f in FUELS))
    oil_peak = max(now, key=lambda r: r["hfo"] + r["hsd"])
    worst_short = max((r for r in now if r["shortage"] is not None),
                      key=lambda r: r["shortage"], default=None)
    worst_short_mean = max((r for r in now if r["shortage_mean"] is not None),
                           key=lambda r: r["shortage_mean"], default=None)
    oil_swing = round((oil_peak["hfo"] + oil_peak["hsd"])
                      - (trough["hfo"] + trough["hsd"]), 1)

    return {
        "slots": [r["time"] for r in now],
        "fuels": FUELS,
        "now": now,
        "prior": prior,
        "days": len(used),
        "from": min(used), "to": max(used),
        "peak_time": peak["time"],
        "trough_time": trough["time"],
        "oil_peak_time": oil_peak["time"],
        "oil_peak_mw": round(oil_peak["hfo"] + oil_peak["hsd"], 1),
        "oil_trough_mw": round(trough["hfo"] + trough["hsd"], 1),
        "oil_swing_mw": oil_swing,
        "swing": swing,
        "oil_share_of_swing": (round(100 * swing["oil"] / swing["total"], 1)
                               if swing["total"] else None),
        "shortage_peak_time": worst_short["time"] if worst_short else None,
        "shortage_peak_mw": worst_short["shortage"] if worst_short else None,
        "shortage_mean_peak_time": (worst_short_mean["time"]
                                    if worst_short_mean else None),
        "shortage_mean_peak_mw": (worst_short_mean["shortage_mean"]
                                  if worst_short_mean else None),
    }


def load_erp_summary():
    """date -> the workbook's system summary."""
    out = {}
    for f in sorted(ERP_DIR.glob("summary_*.json")):
        out.update(read_json(f, {}) or {})
    return out


# PGCB prints the day's blended production cost as well as the taka spent on
# each fuel and the energy each produced, so the parts can be checked against
# the whole. A day whose parts do not reproduce the published blended figure
# is set aside rather than guessed at: the energy column has been published in
# two different units at different times, and a silent factor of a thousand
# would put a fuel's cost per unit out by the same factor.
COST_RECONCILE_TOL = 0.05


def build_fuelcost(summary):
    """What each fuel contributes, and what each fuel costs.

    A fuel's share of the electricity and its share of the bill are different
    numbers, and the gap between them is the whole argument about the fuel mix.
    """
    agg_e, agg_c, used, rejected = {}, {}, [], 0
    for d, rec in sorted(summary.items()):
        cost = rec.get("cost_by_fuel_tk") or {}
        zone = (rec.get("zone_generation") or {}).get("total") or {}
        unit = rec.get("unit_cost")
        energy = sum(v for k, v in zone.items() if k != "total" and v)
        total_cost = sum(v for v in cost.values() if v)
        if not (energy and total_cost and unit):
            continue
        if abs(total_cost / (energy * 1e6) - unit) / unit > COST_RECONCILE_TOL:
            rejected += 1
            continue
        used.append(d)
        for fuel in FUELS:
            agg_e[fuel] = agg_e.get(fuel, 0.0) + (zone.get(fuel) or 0.0)
            agg_c[fuel] = agg_c.get(fuel, 0.0) + (cost.get(fuel) or 0.0)
    if len(used) < 60:
        return None
    tot_e, tot_c = sum(agg_e.values()), sum(agg_c.values())
    if not (tot_e and tot_c):
        return None
    rows = []
    for fuel in FUELS:
        e, c = agg_e[fuel], agg_c[fuel]
        if e <= 0 and c <= 0:
            continue
        rows.append({
            "fuel": fuel,
            "energy_share": r(100 * e / tot_e, 2),
            "cost_share": r(100 * c / tot_c, 2),
            "tk_per_kwh": r(c / (e * 1e6), 2) if e else None,
            "energy_mkwh": r(e, 1), "cost_tk": r(c, 0),
        })
    rows.sort(key=lambda x: -x["cost_share"])
    oil_e = agg_e["hfo"] + agg_e["hsd"]
    oil_c = agg_c["hfo"] + agg_c["hsd"]
    return {
        "rows": rows,
        "days": len(used), "from": min(used), "to": max(used),
        "days_rejected": rejected,
        "blended_tk_per_kwh": r(tot_c / (tot_e * 1e6), 2),
        "total_cost_crore": r(tot_c / 1e7, 0),
        "oil": {
            "energy_share": r(100 * oil_e / tot_e, 1),
            "cost_share": r(100 * oil_c / tot_c, 1),
            "tk_per_kwh": r(oil_c / (oil_e * 1e6), 2) if oil_e else None,
            "gas_tk_per_kwh": (r(agg_c["gas"] / (agg_e["gas"] * 1e6), 2)
                               if agg_e["gas"] else None),
        },
    }


# Gas supply and load-shedding both follow the season, so a correlation over
# the whole year mostly measures the calendar. The hot months are where the
# system is actually tight, and that is where the question is asked.
HOT_MONTHS = {"04", "05", "06", "07", "08", "09"}
COOL_MONTHS = {"11", "12", "01", "02"}


def _pearson(pairs):
    n = len(pairs)
    if n < 10:
        return None
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    cov = sum((a - mx) * (b - my) for a, b in pairs)
    sx = math.sqrt(sum((a - mx) ** 2 for a, _ in pairs))
    sy = math.sqrt(sum((b - my) ** 2 for _, b in pairs))
    return r(cov / (sx * sy), 3) if sx and sy else None


def build_gas(summary):
    """Gas supplied to the power stations, against what went unserved.

    The comparison that matters holds the weather still: sorting the hot
    months by how much gas arrived, and reading off the load-shedding at each
    level, answers whether the shortfall follows the fuel or merely the
    temperature.
    """
    have = [d for d, x in summary.items()
            if x.get("gas_supplied") and x.get("energy_unserved") is not None]
    if len(have) < 120:
        return None
    have.sort()

    monthly = {}
    for d in have:
        monthly.setdefault(d[:7], []).append(d)
    months = []
    for m, ds in sorted(monthly.items()):
        if len(ds) < 5:
            continue
        temps = [summary[d]["max_temperature"] for d in ds
                 if summary[d].get("max_temperature")]
        months.append({
            "month": m, "days": len(ds),
            "gas_mmcfd": r(statistics.median(summary[d]["gas_supplied"] for d in ds), 0),
            "unserved_mkwh": r(statistics.median(summary[d]["energy_unserved"]
                                                 for d in ds), 2),
            "generated_mkwh": r(statistics.median(
                summary[d]["energy_generated"] for d in ds
                if summary[d].get("energy_generated")), 1),
            "max_temp": r(statistics.median(temps), 1) if temps else None,
        })

    hot = [d for d in have if d[5:7] in HOT_MONTHS
           and summary[d].get("max_temperature")]
    cool = [d for d in have if d[5:7] in COOL_MONTHS]
    bands = []
    if len(hot) >= 60:
        gases = sorted(summary[d]["gas_supplied"] for d in hot)
        lo, hi = gases[len(gases) // 3], gases[2 * len(gases) // 3]
        for key, ds in (("low", [d for d in hot if summary[d]["gas_supplied"] <= lo]),
                        ("mid", [d for d in hot
                                 if lo < summary[d]["gas_supplied"] < hi]),
                        ("high", [d for d in hot if summary[d]["gas_supplied"] >= hi])):
            if not ds:
                continue
            bands.append({
                "band": key, "days": len(ds),
                "gas_mmcfd": r(statistics.median(summary[d]["gas_supplied"]
                                                 for d in ds), 0),
                "unserved_mkwh": r(statistics.median(summary[d]["energy_unserved"]
                                                     for d in ds), 2),
                "max_temp": r(statistics.median(summary[d]["max_temperature"]
                                                for d in ds), 1),
            })

    return {
        "months": months,
        "bands": bands,
        "r_hot": _pearson([(summary[d]["gas_supplied"],
                            summary[d]["energy_unserved"]) for d in hot]),
        "r_cool": _pearson([(summary[d]["gas_supplied"],
                             summary[d]["energy_unserved"]) for d in cool]),
        "hot_days": len(hot), "cool_days": len(cool),
        "from": min(have), "to": max(have),
    }


def build_identity(erp_hourly):
    """Test whether published demand is measured or arithmetic.

    PGCB's workbook gives generation, load-shed and demand for every hour. If
    demand were an independent measurement the three would not close exactly.
    They do: demand is generation plus load-shed grossed up by a fixed factor,
    which is the transmission and distribution loss the shed load would itself
    have incurred. Reporting the factor found in the data, rather than one
    assumed, is what makes the claim checkable.
    """
    ratios, months = [], {}
    for d, rows in erp_hourly.items():
        for r in rows:
            g, s, dem = r["generation"], r["loadshed"], r["demand"]
            if None in (g, s, dem) or s <= 0:
                continue
            ratios.append((dem - g) / s)
            months.setdefault(d[:7], []).append((dem - g) / s)
    if len(ratios) < 100:
        return None
    med = statistics.median(ratios)
    within = sum(1 for x in ratios if abs(x - med) <= 0.002)
    by_month = sorted((m, round(statistics.median(v), 4), len(v))
                      for m, v in months.items() if len(v) >= 24)
    return {
        "hours": len(ratios),
        "factor": round(med, 4),
        "share_within": round(100 * within / len(ratios), 1),
        "months": len(by_month),
        "months_at_factor": sum(1 for _, f, _ in by_month
                                if abs(f - med) <= 0.002),
        "by_month": [{"month": m, "factor": f, "hours": n}
                     for m, f, n in by_month],
    }


def _doy(iso: str) -> int:
    """Day of year, with 29 Feb folded onto 28 Feb so years align."""
    d = date.fromisoformat(iso)
    n = d.timetuple().tm_yday
    leap = (d.year % 4 == 0 and d.year % 100 != 0) or d.year % 400 == 0
    if leap and n > 59:
        n -= 1
    return n


def build_seasonal(daily):
    """Year-on-year comparison of the same time of year.

    Load-shedding is strongly seasonal, so comparing today with a year ago only
    means anything against the same point in the calendar. Years before
    load-shedding was actually published are left out entirely rather than
    drawn as an improvement from zero.
    """
    start_year = int(REPORTING_START[:4])
    by_year = defaultdict(dict)
    for d in daily:
        y = int(d["date"][:4])
        if y < start_year or not d.get("reported"):
            continue
        by_year[y][_doy(d["date"])] = {
            "energy": d.get("energy_shed_mwh"),
            "hours": d.get("hours_shed"),
            "peak": d.get("max_loadshed"),
        }

    def smooth(vals):
        out, half = [], SEASONAL_SMOOTH // 2
        for i in range(len(vals)):
            win = [v for v in vals[max(0, i - half): i + half + 1] if v is not None]
            out.append(r(sum(win) / len(win)) if win else None)
        return out

    series = {}
    for y, days in sorted(by_year.items()):
        raw = [days.get(n, {}).get("energy") for n in range(1, 366)]
        # trim the tail of a year still in progress so the line simply stops
        last = max((i for i, v in enumerate(raw) if v is not None), default=-1)
        if last < 0:
            continue
        series[str(y)] = smooth(raw[: last + 1])

    # ---- like-for-like window comparison -------------------------------
    dmap = {d["date"]: d for d in daily}
    end = date.fromisoformat(daily[-1]["date"])
    compare = []
    for back in range(0, 5):
        try:
            w_end = end.replace(year=end.year - back)
        except ValueError:                      # 29 Feb in a non-leap year
            w_end = end.replace(year=end.year - back, day=28)
        rows = []
        for k in range(COMPARE_WINDOW):
            day = (w_end - timedelta(days=k)).isoformat()
            rec = dmap.get(day)
            if rec and rec.get("reported"):
                rows.append(rec)
        if not rows:
            continue
        energies = [x["energy_shed_mwh"] for x in rows if x["energy_shed_mwh"] is not None]
        peaks = [x["max_loadshed"] for x in rows if x["max_loadshed"] is not None]
        compare.append({
            "year": w_end.year,
            "to": w_end.isoformat(),
            "days": len(rows),
            "mean_energy_shed_mwh": r(sum(energies) / len(energies)) if energies else None,
            "mean_hours_shed": r(sum(x["hours_shed"] for x in rows) / len(rows), 1),
            "peak_loadshed": max(peaks) if peaks else None,
        })

    return {
        "metric": "energy_shed_mwh",
        "smooth_days": SEASONAL_SMOOTH,
        "reporting_start": REPORTING_START,
        "series": series,
        "compare_window": COMPARE_WINDOW,
        "compare": compare,
    }


# ---------------------------------------------------------------- demand

# Bangladesh's all-time evening peak is under 18 GW, so a daily figure above
# this ceiling is a data-entry error. A handful of days read above 22,000 MW.
DEMAND_MAX_MW = 20000
DEMAND_MIN_MW = 3000
DEMAND_MIN_DAYS = 200          # a year needs real coverage to be comparable
# Five years, matching the load-shedding chart. Legibility is handled by
# letting the reader isolate a year from the legend, not by dropping years:
# showing fewer would invite exactly the suspicion of a chosen window that the
# rest of the page is built to avoid.
DEMAND_OVERLAY_YEARS = 5

# Eid as observed in Bangladesh. Static reference data, not scraped. Industry
# shuts for several days and national demand falls sharply, which is why the
# series has a deep trough that moves earlier through the Gregorian calendar
# each year. Every one of these is checked against the data before being drawn.
EID_DATES = {
    "2022": [("2022-05-03", "Eid al-Fitr"), ("2022-07-10", "Eid al-Adha")],
    "2023": [("2023-04-22", "Eid al-Fitr"), ("2023-06-29", "Eid al-Adha")],
    "2024": [("2024-04-11", "Eid al-Fitr"), ("2024-06-17", "Eid al-Adha")],
    "2025": [("2025-03-31", "Eid al-Fitr"), ("2025-06-07", "Eid al-Adha")],
    "2026": [("2026-03-20", "Eid al-Fitr"), ("2026-05-27", "Eid al-Adha")],
}
EID_MIN_DROP = 0.05            # only label a festival the data actually shows


def build_demand(area):
    """Evening-peak demand, year by year.

    This is demand as published: served load plus load-shed, at the
    sub-station end. Because the shed portion is itself the authorities'
    estimate, the series is a floor on true demand rather than a measurement
    of it — a mill that stopped asking for power it knew would not arrive is
    not counted here.
    """
    clean, dropped = defaultdict(dict), 0
    for d, rec in sorted(area.items()):
        if rec.get("suspect"):
            continue
        v = rec.get("total_demand")
        if not v:
            continue
        if not (DEMAND_MIN_MW <= v <= DEMAND_MAX_MW):
            dropped += 1
            continue
        clean[d[:4]][_doy(d)] = v

    years = [y for y, days in sorted(clean.items()) if len(days) >= DEMAND_MIN_DAYS]
    if not years:
        return None

    def smooth(days, win=7):
        last = max(days)
        raw = [days.get(n) for n in range(1, last + 1)]
        half, out = win // 2, []
        for i in range(len(raw)):
            w = [x for x in raw[max(0, i - half): i + half + 1] if x is not None]
            out.append(r(sum(w) / len(w)) if w else None)
        return out

    overlay = years[-DEMAND_OVERLAY_YEARS:]
    series = {y: smooth(clean[y]) for y in overlay}

    # Label a festival only where the demand drop is actually present.
    holidays = []
    for y in overlay:
        days = clean.get(y, {})
        for iso, name in EID_DATES.get(y, []):
            e = date.fromisoformat(iso)
            win = [(e + timedelta(days=k)) for k in range(-1, 4)]
            vals = [(k, days.get(_doy(k.isoformat()))) for k in win
                    if days.get(_doy(k.isoformat()))]
            base = [days[_doy((e - timedelta(days=k)).isoformat())]
                    for k in range(8, 29)
                    if days.get(_doy((e - timedelta(days=k)).isoformat()))]
            if not vals or len(base) < 8:
                continue
            lo = min(vals, key=lambda t: t[1])
            nb = sorted(base)[len(base) // 2]
            drop = 1 - lo[1] / nb
            if drop >= EID_MIN_DROP:
                holidays.append({"year": y, "label": name,
                                 "date": lo[0].isoformat(),
                                 "doy": _doy(lo[0].isoformat()),
                                 "demand": r(lo[1]), "normal": r(nb),
                                 "drop_pct": r(100 * drop, 1)})

    annual = []
    for y in years:
        v = sorted(clean[y].values())
        annual.append({
            "year": y, "days": len(v),
            "median": r(v[len(v) // 2]),
            "p95": r(v[int(0.95 * (len(v) - 1))]),
            "min": r(v[0]),
        })

    first, last = annual[0], annual[-1]
    span = int(last["year"]) - int(first["year"])
    growth = {
        "from": first["year"], "to": last["year"],
        "median_from": first["median"], "median_to": last["median"],
        "total_pct": r(100 * (last["median"] / first["median"] - 1), 1),
        "cagr_pct": r(100 * ((last["median"] / first["median"]) ** (1 / span) - 1), 2)
        if span else None,
    }
    return {"by_year": series, "annual": annual, "growth": growth,
            "holidays": holidays, "dropped_implausible": dropped}


# ------------------------------------------------------------------ cost

def build_cost(fuel_daily, official, bpdb):
    """What a day of electricity costs, and why that changes.

    Built primarily from BPDB's generation report, which prints the cost and
    the energy of each fuel on the same sheet and runs back to July 2024. The
    NLDC summary carries the same totals but only from December 2024, so using
    it as the base would throw away five months and leave no third year to
    compare against. It is kept as a fallback for days the generation report
    is missing.
    """
    GROUPS = {"gas": ["gas"], "coal": ["coal"], "oil": ["oil"],
              "import": ["import"], "renewable": ["solar", "hydro_wind"]}
    s1_groups = {"gas": ["gas"], "coal": ["coal"], "oil": ["hfo", "hsd"],
                 "import": ["import"], "renewable": ["solar", "wind", "hydro"]}
    s1 = {d["date"]: d for d in fuel_daily}

    rows = []
    for dd in sorted(set(GENREPORTS) | set(s1)):
        g = GENREPORTS.get(dd) or {}
        e, c = g.get("energy_by_fuel") or {}, g.get("cost_by_fuel") or {}
        tot_e = sum(v or 0 for v in e.values())
        stated = g.get("total_energy")
        # the same unit slip the per-fuel costs guard against
        scale = 1000.0 if (tot_e and tot_e < ENERGY_UNIT_FLOOR) else 1.0
        total_cost = sum(v or 0 for v in c.values()) or None
        energy_mkwh = (tot_e * scale) or None
        shares, prices = {}, {}
        if e and c and tot_e:
            for grp, parts in GROUPS.items():
                ge = sum(e.get(x) or 0 for x in parts)
                shares[grp] = ge / tot_e
                kwh = ge * 1e6 * scale
                gc = sum(c.get(x) or 0 for x in ([grp] if grp in c else parts))
                if kwh > 1e6 and gc:
                    prices[grp] = gc / kwh

        rec = bpdb.get(dd) or {}
        if not total_cost and rec.get("total_cost_tk"):
            total_cost = rec["total_cost_tk"]
        if not energy_mkwh and rec.get("energy_generated"):
            energy_mkwh = rec["energy_generated"]
        if not shares and dd in s1:
            row = s1[dd]
            t = sum(sum(row.get(x) or 0 for x in parts) for parts in s1_groups.values())
            if t:
                shares = {g_: sum(row.get(x) or 0 for x in parts) / t
                          for g_, parts in s1_groups.items()}
        if not total_cost or not energy_mkwh:
            continue

        cpk = rec.get("cost_per_kwh") or r(total_cost / (energy_mkwh * 1e6), 3)
        rows.append({"date": dd, "total_cost_tk": total_cost,
                     "energy_mkwh": r(energy_mkwh, 2), "cost_per_kwh": cpk,
                     "shares": shares, "prices": prices})

    if not rows:
        return None

    series_cost, series_unit = defaultdict(dict), defaultdict(dict)
    for d in rows:
        n = _doy(d["date"])
        series_cost[d["date"][:4]][n] = r(d["total_cost_tk"] / 1e7, 2)   # crore Tk
        series_unit[d["date"][:4]][n] = d["cost_per_kwh"]

    def to_list(store, smooth=7):
        out = {}
        for y, days in sorted(store.items()):
            last = max(days)
            raw = [days.get(n) for n in range(1, last + 1)]
            half, sm = smooth // 2, []
            for i in range(len(raw)):
                w = [v for v in raw[max(0, i - half): i + half + 1] if v is not None]
                sm.append(r(sum(w) / len(w), 2) if w else None)
            out[y] = sm
        return out

    monthly = defaultdict(list)
    for d in rows:
        monthly[d["date"][:7]].append(d)
    months = [{
        "month": m, "days": len(ds),
        "total_cost_crore": r(sum(x["total_cost_tk"] for x in ds) / 1e7 / len(ds), 1),
        "cost_per_kwh": r(sum(x["cost_per_kwh"] for x in ds) / len(ds), 3),
    } for m, ds in sorted(monthly.items())]

    # ---- why the unit cost moved: mix against price --------------------
    def profile(ds):
        sh, pr = {}, {}
        for g_ in GROUPS:
            v = [d["shares"][g_] for d in ds if d["shares"].get(g_) is not None]
            if v:
                sh[g_] = sum(v) / len(v)
            q = [d["prices"][g_] for d in ds if d["prices"].get(g_) is not None]
            if q:
                pr[g_] = sum(q) / len(q)
        return sh, pr

    decomp = None
    if months:
        cur = months[-1]["month"]
        y, mo = cur.split("-")
        prev = f"{int(y) - 1}-{mo}"
        now_d, old_d = monthly.get(cur, []), monthly.get(prev, [])
        if len(old_d) >= 10 and len(now_d) >= 5:
            s0, p0 = profile(old_d)
            s1_, p1 = profile(now_d)
            common = [g_ for g_ in GROUPS
                      if g_ in s0 and g_ in s1_ and g_ in p0 and g_ in p1]
            if common:
                base = sum(s0[g_] * p0[g_] for g_ in common)
                after = sum(s1_[g_] * p1[g_] for g_ in common)
                mix_only = sum(s1_[g_] * p0[g_] for g_ in common)
                decomp = {
                    "from": prev, "to": cur,
                    "cost_before": r(base, 2), "cost_after": r(after, 2),
                    "change": r(after - base, 2),
                    "mix_effect": r(mix_only - base, 2),
                    "price_effect": r(after - mix_only, 2),
                    "shares_before": {g_: r(s0[g_], 4) for g_ in common},
                    "shares_after": {g_: r(s1_[g_], 4) for g_ in common},
                    "prices_before": {g_: r(p0[g_], 2) for g_ in common},
                    "prices_after": {g_: r(p1[g_], 2) for g_ in common},
                }

    latest = rows[-1]
    return {
        "unit_by_year": to_list(series_unit),
        "crore_by_year": to_list(series_cost),
        "monthly": months,
        "decomposition": decomp,
        "coverage": {"days": len(rows), "from": rows[0]["date"], "to": rows[-1]["date"]},
        "latest": {"date": latest["date"],
                   "total_cost_crore": r(latest["total_cost_tk"] / 1e7, 1),
                   "cost_per_kwh": latest["cost_per_kwh"]},
    }


# ----------------------------------------------------------------- equity

# In the NLDC zone table, "Demand" is TOTAL demand and already contains the
# shed portion. Confirmed against BPDB's Daily Electricity Generation Report,
# whose section 10 prints the same zone figures with a Supply column as well:
# Demand = Supply + Load Shed, exactly (e.g. Dhaka 4,812 = 4,780 + 32 on
# 14-04-2025), and its Demand column matches this table value for value.
#
# An earlier reading of this compared the summed zone demand against
# generation-end output and concluded demand was the served load. That was
# wrong: the zone table is measured at the sub-station end, after auxiliary
# use and transmission loss, so the two are not comparable. The share of a
# zone's demand that went unserved is therefore load-shed / demand.
EQUITY_WINDOWS = [30, 90, 365, None]


def build_equity(bpdb):
    """Who actually carries the shortfall.

    Three different questions, because they can disagree:
      shed_rate      what share of a zone's own demand went unserved
      watts_person   how much shortfall per resident
      burden         a zone's share of national load-shedding divided by its
                     share of national demand (1.0 = proportionate)
    """
    pops = zone_population()

    days = [(d, rec["zone_peak"]) for d, rec in sorted(bpdb.items())
            if rec.get("zone_peak")]
    if not days:
        return None

    def window(n):
        sel = days[-n:] if n else days
        agg = {z: {"shed": 0.0, "demand": 0.0, "days": 0, "shed_days": 0}
               for z in ZONES}
        for _, zp in sel:
            for z in ZONES:
                v = zp.get(z)
                if not v:
                    continue
                shed = v.get("loadshed") or 0
                dem = v.get("demand") or 0
                a = agg[z]
                a["shed"] += shed
                a["demand"] += dem
                a["days"] += 1
                if shed > 0:
                    a["shed_days"] += 1

        nat_shed = sum(a["shed"] for a in agg.values())
        nat_total = sum(a["demand"] for a in agg.values())

        rows = []
        for z in ZONES:
            a = agg[z]
            if not a["days"]:
                continue
            pop = pops.get(z) or 0
            total = a["demand"]          # already inclusive of the shed portion
            mean_shed = a["shed"] / a["days"]
            share_shed = a["shed"] / nat_shed if nat_shed else None
            share_dem = total / nat_total if nat_total else None
            rows.append({
                "zone": z,
                "population": pop,
                "days": a["days"],
                "shed_days": a["shed_days"],
                "mean_loadshed": r(mean_shed),
                "mean_demand": r(a["demand"] / a["days"]),
                "mean_served": r((a["demand"] - a["shed"]) / a["days"]),
                # share of this zone's own demand that went unserved
                "shed_rate": r(a["shed"] / total, 4) if total else None,
                # watts of shortfall per resident at the evening peak
                "watts_per_person": r(mean_shed * 1e6 / pop, 2) if pop else None,
                "share_shed": r(share_shed, 4) if share_shed is not None else None,
                "share_demand": r(share_dem, 4) if share_dem is not None else None,
                "burden": (r(share_shed / share_dem, 3)
                           if share_shed is not None and share_dem else None),
            })
        rows.sort(key=lambda x: -(x["shed_rate"] or 0))
        return {
            "days": len(sel),
            "from": sel[0][0], "to": sel[-1][0],
            "national_shed_rate": r(nat_shed / nat_total, 4) if nat_total else None,
            "national_watts_per_person": (
                r((nat_shed / len(sel)) * 1e6 / sum(pops.values()), 2) if sel else None),
            "zones": rows,
        }

    return {
        "population_source": {"en": POP_SOURCE_EN, "bn": POP_SOURCE_BN,
                              "year": CENSUS_YEAR,
                              "national_population": sum(pops.values())},
        "windows": {(str(n) if n else "all"): window(n) for n in EQUITY_WINDOWS},
    }


# -------------------------------------------------------------- integrity

def build_integrity(hourly, area, bpdb, daily, identity=None):
    """Cross-source agreement checks.

    The point is not to accuse anyone of anything: it is to show, from the
    authorities' own published numbers, where two official sources describing
    the same day disagree, and to make explicit which figures are measurements
    and which are arithmetic.
    """
    # 1. Is PGCB "demand" ever anything other than supply + load-shed?
    ident = miss = 0
    for x in hourly:
        if x["demand"] is None or x["supply"] is None or x["loadshed"] is None:
            continue
        if abs(x["demand"] - (x["supply"] + x["loadshed"])) < 0.5:
            ident += 1
        else:
            miss += 1

    # 2. Same for the BPDB energy identity.
    e_ident = e_miss = 0
    for rec in bpdb.values():
        g, u, dm = (rec.get("energy_generated"), rec.get("energy_unserved"),
                    rec.get("energy_demand"))
        if None in (g, u, dm):
            continue
        if abs(dm - (g + u)) < 0.01:
            e_ident += 1
        else:
            e_miss += 1

    # 3. Area-wise page vs the NLDC report, on the same day.
    pairs = []
    for d, rec in sorted(bpdb.items()):
        tot = rec.get("peak_loadshed_total")
        a = area.get(d)
        if tot is None or not a or a.get("suspect"):
            continue
        pairs.append({
            "date": d,
            "nldc_peak_loadshed": tot,
            "areawise_loadshed": a["total_loadshed"],
            "nldc_peak_demand": rec.get("peak_demand_total"),
            "areawise_demand": a["total_demand"],
        })

    zero_days = sum(1 for p in pairs
                    if p["areawise_loadshed"] == 0 and p["nldc_peak_loadshed"] > 0)
    hidden = sum(p["nldc_peak_loadshed"] for p in pairs
                 if p["areawise_loadshed"] == 0 and p["nldc_peak_loadshed"] > 0)

    # 4. PGCB evening-peak load-shed vs the NLDC report for the same date.
    dmap = {d["date"]: d for d in daily}
    trio = []
    for d, rec in sorted(bpdb.items()):
        tot = rec.get("peak_loadshed_total")
        dd = dmap.get(d)
        if tot is None or not dd:
            continue
        trio.append({
            "date": d,
            "pgcb_max": dd["max_loadshed"],
            "pgcb_evening": dd["evening_loadshed"],
            "nldc_peak": tot,
        })

    # 5. How much of the archive is actually populated, year by year.
    by_year = defaultdict(lambda: {"rows": 0, "with_demand": 0,
                                   "with_supply": 0, "nonzero_loadshed": 0})
    for x in hourly:
        y = x["date"][:4]
        b = by_year[y]
        b["rows"] += 1
        if x["demand"] is not None:
            b["with_demand"] += 1
        if x["supply"] is not None:
            b["with_supply"] += 1
        if x["loadshed"]:
            b["nonzero_loadshed"] += 1
    completeness = [{"year": y, **v} for y, v in sorted(by_year.items())]

    return {
        "reporting_start": REPORTING_START,
        "completeness": completeness,
        "plant_rows_dropped": {
            "threshold_mw": PLANT_MAX_MW,
            "count": len(DROPPED_PLANT_ROWS),
            "examples": DROPPED_PLANT_ROWS[:5],
        },
        "outliers": {
            "threshold_mw": PLAUSIBLE_MAX_MW,
            "count": len(OUTLIERS),
            "examples": sorted(OUTLIERS, key=lambda o: -o["value"])[:10],
        },
        "demand_identity": {
            "matches": ident, "mismatches": miss,
            "rate": r(ident / (ident + miss), 4) if (ident + miss) else None,
        },
        # The website's hourly table rounds, so the identity there only holds
        # approximately. PGCB's workbook carries full precision and closes it
        # exactly, including the loss factor applied to the shed load — that
        # is the stronger statement, so it is published alongside.
        "demand_formula": identity,
        "energy_identity": {
            "matches": e_ident, "mismatches": e_miss,
            "rate": r(e_ident / (e_ident + e_miss), 4) if (e_ident + e_miss) else None,
        },
        "areawise_vs_nldc": pairs,
        "areawise_zero_days": zero_days,
        "areawise_days_compared": len(pairs),
        "hidden_peak_mw_sum": r(hidden),
        "pgcb_vs_nldc": trio,
    }


# ----------------------------------------------------------------- latest

def build_latest(hourly, daily, bpdb, area):
    live = next((x for x in reversed(hourly)
                 if x["supply"] is not None or x["loadshed"] is not None), None)
    today = daily[-1] if daily else None
    prev = daily[-2] if len(daily) > 1 else None

    last_bpdb_date = max(bpdb) if bpdb else None
    rec = bpdb.get(last_bpdb_date, {}) if last_bpdb_date else {}

    # worst zone on the most recent NLDC report
    worst = None
    zp = rec.get("zone_peak") or {}
    if zp:
        k, v = max(zp.items(), key=lambda kv: kv[1].get("loadshed") or 0)
        worst = {"zone": k, "zone_bn": ZONE_BN.get(k), **v}

    return {
        "observed_at": live["dt"] if live else None,
        "demand": live["demand"] if live else None,
        "supply": live["supply"] if live else None,
        "loadshed": live["loadshed"] if live else None,
        "today": today,
        "yesterday": prev,
        "nldc": {
            "date": rec.get("date"),
            "evening_peak_generation": rec.get("evening_peak_generation"),
            "evening_peak_demand": rec.get("evening_peak_demand"),
            "energy_generated": rec.get("energy_generated"),
            "energy_unserved": rec.get("energy_unserved"),
            "cost_per_kwh": rec.get("cost_per_kwh"),
            "gas_supplied": rec.get("gas_supplied"),
            "max_temperature": rec.get("max_temperature"),
            "peak_loadshed_total": rec.get("peak_loadshed_total"),
            "peak_demand_total": rec.get("peak_demand_total"),
            "worst_zone": worst,
        },
    }


# ------------------------------------------------------------------- main

def stamp_assets():
    """Rewrite index.html so app.js and styles.css carry a content hash."""
    import hashlib
    root = SITE_DATA.parent
    index = root / "index.html"
    if not index.exists():
        return
    html = index.read_text(encoding="utf-8")
    for asset in ("app.js", "styles.css"):
        f = root / asset
        if not f.exists():
            continue
        digest = hashlib.sha1(f.read_bytes()).hexdigest()[:8]
        html = re.sub(rf'(["\'])({re.escape(asset)})(\?v=[0-9a-f]+)?\1',
                      rf'\g<1>{asset}?v={digest}\g<1>', html)
    index.write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    hourly = load_hourly()
    if not hourly:
        print("[build] no PGCB data — run scrape_pgcb.py first")
        return 1
    bpdb = load_bpdb()
    area = {}
    for f in sorted(AREA_DIR.glob("areawise*.json")):
        area.update(read_json(f, {}) or {})
    print(f"[build] hourly={len(hourly)} bpdb_days={len(bpdb)} area_days={len(area)}")

    daily = build_daily(hourly)
    months = build_hourly_files(hourly)

    # The newest day is still accumulating hours. Publishing it inside the
    # aggregate files would rewrite them every hour for a row that is not final
    # yet; the hero panel reads today's partial figures from latest.json.
    settled = daily[:-1] if len(daily) > 1 else daily
    monthly = build_monthly(settled)

    write_json(SITE_DATA / "daily.json", {"cols": list(settled[0].keys()),
                                          "rows": settled})
    write_json(SITE_DATA / "monthly.json", monthly)

    official = build_official(bpdb)
    write_json(SITE_DATA / "official.json", official)
    fs = official["forecast_summary"]
    if fs["days"]:
        print(f"[build] BPDB forecast: {fs['forecast_zero']}/{fs['days']} days "
              f"forecast zero load-shedding; {fs['forecast_zero_but_shed']} of those "
              f"then shed (mean {fs['mean_shed_on_those_days']} MW)")

    erp_hh = load_erp_halfhourly()
    erp_hourly = load_erp_hourly()
    if erp_hh:
        print(f"[build] PGCB workbooks: {len(erp_hh)} days half-hourly "
              f"({min(erp_hh)} to {max(erp_hh)})")
    daycurve = build_daycurve(erp_hh)
    if daycurve:
        write_json(SITE_DATA / "daycurve.json", daycurve)
        print(f"[build] day curve over {daycurve['days']} days: oil peaks "
              f"{daycurve['oil_peak_mw']:,.0f} MW at {daycurve['oil_peak_time']} "
              f"against {daycurve['oil_trough_mw']:,.0f} MW at its lowest "
              f"(swing {daycurve['oil_swing_mw']:,.0f} MW); shortage peaks "
              f"{daycurve['shortage_peak_mw']:,.0f} MW at "
              f"{daycurve['shortage_peak_time']} on the median, "
              f"{daycurve['shortage_mean_peak_mw']:,.0f} MW at "
              f"{daycurve['shortage_mean_peak_time']} on the mean")
    erp_summary = load_erp_summary()
    fuelcost = build_fuelcost(erp_summary)
    if fuelcost:
        write_json(SITE_DATA / "fuelcost.json", fuelcost)
        o = fuelcost["oil"]
        print(f"[build] fuel cost over {fuelcost['days']} days "
              f"({fuelcost['days_rejected']} set aside as unreconciled): oil is "
              f"{o['energy_share']}% of the electricity and {o['cost_share']}% of "
              f"the bill, {o['tk_per_kwh']} Tk/kWh against {o['gas_tk_per_kwh']} "
              f"for gas; blended {fuelcost['blended_tk_per_kwh']} Tk/kWh")
    gas = build_gas(erp_summary)
    if gas:
        write_json(SITE_DATA / "gas.json", gas)
        b = {x["band"]: x for x in gas["bands"]}
        if "low" in b and "high" in b:
            print(f"[build] gas vs load-shedding: r={gas['r_hot']} in the hot "
                  f"months ({gas['hot_days']} days), r={gas['r_cool']} in the cool "
                  f"ones; at {b['low']['max_temp']}C vs {b['high']['max_temp']}C, "
                  f"low-gas days go unserved {b['low']['unserved_mkwh']} MkWh "
                  f"against {b['high']['unserved_mkwh']}")
    identity = build_identity(erp_hourly)
    if identity:
        print(f"[build] demand identity: demand = generation + load-shed x "
              f"{identity['factor']} on {identity['share_within']}% of "
              f"{identity['hours']:,} hours; that factor is the monthly median "
              f"in {identity['months_at_factor']}/{identity['months']} months")

    seasonal = build_seasonal(settled)
    write_json(SITE_DATA / "seasonal.json", seasonal)
    if seasonal["compare"]:
        c = seasonal["compare"]
        print("[build] last %dd vs prior years (mean MWh/day not supplied): %s"
              % (seasonal["compare_window"],
                 ", ".join(f"{x['year']}={x['mean_energy_shed_mwh']}" for x in c)))

    osm_plants = read_json(GEO / "plants.json", []) or []
    osm_subs = read_json(GEO / "substations.json", []) or []
    osm_places = read_json(GEO / "places.json", []) or []
    dgeo = read_json(SITE_DATA / "geo" / "districts.json")
    districts = DistrictIndex(dgeo)
    places = build_places(districts, dgeo)
    write_json(SITE_DATA / "places.json", places)
    print(f"[build] gazetteer: {len(places['places'])} searchable places "
          f"{places['counts']}")
    plants = build_plants(bpdb, Geocoder([("osm", osm_plants),
                                          ("place", osm_places)]), districts)
    subs = build_substations(bpdb, Geocoder([("osm", osm_subs),
                                             ("place", osm_places)]), districts)
    if plants:
        write_json(SITE_DATA / "plants.json", plants)
        print(f"[build] plants {len(plants['plants'])} geo={plants['geo_counts']}")
    if subs:
        write_json(SITE_DATA / "substations.json", subs)
        print(f"[build] substations {len(subs['substations'])} geo={subs['geo_counts']}")

    write_json(SITE_DATA / "reasons.json", build_reason_history(bpdb))
    _fuel_daily = build_fuelmix(bpdb)
    _fuel_monthly = build_fuel_monthly(_fuel_daily)
    if _fuel_monthly["same_month"]:
        ch = _fuel_monthly["same_month"]["changes"]
        print(f"[build] fuel, same month a year apart: total {ch['total']:+.1f}%  "
              f"gas {ch['gas']:+.1f}%  coal {ch['coal']:+.1f}%  oil {ch['oil']:+.1f}%")
    write_json(SITE_DATA / "fuelmix.json", {
        "fuels": FUELS,
        "groups": [g[0] for g in FUEL_GROUPS],
        "monthly": _fuel_monthly["monthly"],
        "same_month": _fuel_monthly["same_month"],
        "daily": _fuel_daily,
        "zone_latest": build_zone_fuel_latest(bpdb),
    })
    write_json(SITE_DATA / "zones.json", build_zones(area, bpdb))

    demand = build_demand(area)
    if demand:
        write_json(SITE_DATA / "demand.json", demand)
        g = demand["growth"]
        print(f"[build] peak demand {g['from']}->{g['to']}: {g['median_from']:,.0f} -> "
              f"{g['median_to']:,.0f} MW ({g['total_pct']:+.0f}%, {g['cagr_pct']}%/yr); "
              f"{demand['dropped_implausible']} implausible days dropped")

    cost = build_cost(_fuel_daily, official, bpdb)
    if cost:
        write_json(SITE_DATA / "cost.json", cost)
        dc = cost["decomposition"]
        if dc:
            print(f"[build] unit cost {dc['from']}->{dc['to']}: {dc['cost_before']} -> "
                  f"{dc['cost_after']} Tk/kWh  (mix {dc['mix_effect']:+.2f}, "
                  f"price {dc['price_effect']:+.2f})")

    equity = build_equity(bpdb)
    if equity:
        write_json(SITE_DATA / "equity.json", equity)
        w = equity["windows"]["90"]
        top = w["zones"][0]
        print(f"[build] equity 90d: national shed rate {w['national_shed_rate']}, "
              f"worst {top['zone']} {top['shed_rate']} "
              f"({top['watts_per_person']} W/person)")

    integrity = build_integrity(hourly, area, bpdb, daily, identity)
    write_json(SITE_DATA / "integrity.json", integrity)
    write_json(SITE_DATA / "latest.json", build_latest(hourly, daily, bpdb, area))

    # Cache-busting: the browser revalidates data on every load, but would
    # otherwise hold app.js and styles.css indefinitely, so fresh figures could
    # be rendered by stale code. Stamp both with a hash of their contents.
    stamp_assets()

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "coverage": {
            "hourly": {"from": hourly[0]["dt"], "to": hourly[-1]["dt"],
                       "rows": len(hourly), "months": months},
            "daily": {"from": daily[0]["date"], "to": daily[-1]["date"],
                      "days": len(daily)},
            "bpdb": {"days": len(bpdb),
                     "from": min(bpdb) if bpdb else None,
                     "to": max(bpdb) if bpdb else None},
            "areawise": {"days": len(area),
                         "usable": sum(1 for v in area.values() if not v.get("suspect")),
                         "suspect": sum(1 for v in area.values() if v.get("suspect"))},
        },
        "sources": [
            {"id": "pgcb", "name_en": "PGCB / NLDC hourly demand-supply-loadshed",
             "name_bn": "পিজিসিবি / এনএলডিসি ঘণ্টাভিত্তিক চাহিদা-সরবরাহ-লোডশেড",
             "url": "https://erp.powergrid.gov.bd/web/generations/view_demand_supply_loadshed_bn"},
            {"id": "bpdb_archive", "name_en": "BPDB daily generation archive (NLDC PDF reports)",
             "name_bn": "বিপিডিবি দৈনিক উৎপাদন আর্কাইভ (এনএলডিসি পিডিএফ প্রতিবেদন)",
             "url": "https://misc.bpdb.gov.bd/daily-generation-archive"},
            {"id": "bpdb_area", "name_en": "BPDB area-wise demand",
             "name_bn": "বিপিডিবি এলাকাভিত্তিক চাহিদা",
             "url": "https://misc.bpdb.gov.bd/area-wise-demand"},
            {"id": "osm", "name_en": "OpenStreetMap (plant & substation locations, district boundaries)",
             "name_bn": "ওপেনস্ট্রিটম্যাপ (কেন্দ্র ও উপকেন্দ্রের অবস্থান, জেলা সীমানা)",
             "url": "https://www.openstreetmap.org/copyright"},
        ],
        "integrity_summary": {
            "demand_identity_rate": integrity["demand_identity"]["rate"],
            "energy_identity_rate": integrity["energy_identity"]["rate"],
            "areawise_zero_days": integrity["areawise_zero_days"],
            "areawise_days_compared": integrity["areawise_days_compared"],
        },
    }
    write_json(SITE_DATA / "meta.json", meta, indent=1)

    print(f"[build] demand identity  {integrity['demand_identity']}")
    print(f"[build] energy identity  {integrity['energy_identity']}")
    print(f"[build] area-wise zero-loadshed days vs NLDC>0: "
          f"{integrity['areawise_zero_days']}/{integrity['areawise_days_compared']}")
    total = sum(f.stat().st_size for f in SITE_DATA.rglob("*.json"))
    print(f"[build] wrote {total/1e6:.2f} MB to {SITE_DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
