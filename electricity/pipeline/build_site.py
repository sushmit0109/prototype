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


REPAIRED_YEARS = []


def repair_report_year(d):
    """Put a report back in the year its listing says it belongs to.

    A handful of NLDC sheets carry a mistyped year on the report line — five
    days from late 2024 are dated 2028. The listing that published the file is
    reliable, and a report always describes the day or two before it, so where
    swapping in the listing's year lands the report next to its listing, that
    is the date. Where it does not, the record is set aside rather than filed
    under a year it cannot belong to: left alone it both loses a real day and
    invents a phantom one years away.
    """
    iso, listing = d.get("date"), d.get("listing_date")
    if not iso or not listing:
        return d
    try:
        rep, lst = date.fromisoformat(iso), date.fromisoformat(listing)
    except ValueError:
        return None
    if 0 <= (lst - rep).days <= 5:
        return d
    try:
        fixed = rep.replace(year=lst.year)
    except ValueError:                       # 29 Feb into a common year
        return None
    if 0 <= (lst - fixed).days <= 5:
        REPAIRED_YEARS.append({"was": iso, "now": fixed.isoformat(),
                               "listing": listing})
        d["date"] = fixed.isoformat()
        return d
    return None


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
        d = repair_report_year(d)
        if d is None:
            continue
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
    if REPAIRED_YEARS:
        ex = ", ".join(f"{x['was']}->{x['now']}" for x in REPAIRED_YEARS[:5])
        print(f"[build] moved {len(REPAIRED_YEARS)} report(s) to the year their "
              f"listing gives ({ex})")
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

    # Towns and city neighbourhoods that OpenStreetMap did not match, added so
    # the trend map can place them in a district. Positions are the locality,
    # not the switchyard.
    "patnitala": (25.050, 88.750), "juldah": (22.238, 91.800),
    "rahanpur": (24.820, 88.320), "bakulia": (22.340, 91.850),
    "bangabhaban": (23.710, 90.420), "kamrangirchar": (23.710, 90.370),
    "kazla": (24.370, 88.630), "keranigonj": (23.700, 90.360),
    "baroaulia": (22.630, 91.660), "khagrachori": (23.120, 91.980),
    "ruppur": (24.060, 89.050), "santhia": (24.100, 89.530),
    "satmasjid": (23.750, 90.370), "shitalakhya": (23.650, 90.520),
    "sholosohor": (22.360, 91.830), "shomvuganj": (24.770, 90.440),
    "chapai": (24.600, 88.280), "maijdee": (22.870, 91.100),
    "sreemongol": (24.310, 91.730), "srinagar": (23.500, 90.280),
    "mirsorai": (22.780, 91.570), "taraganj": (25.800, 89.100),
    "ullahpara": (24.300, 89.600), "ullon": (23.760, 90.420),
    "zigatola": (23.740, 90.370), "narshingdi": (23.920, 90.720),
    "gollamari": (22.800, 89.530), "netrakona": (24.880, 90.730),
    "halishahar": (22.320, 91.770), "hatirjheel": (23.750, 90.400),
    "borhanuddin": (22.500, 90.720), "bhulta": (23.790, 90.530),
    "coxsbazar": (21.440, 91.970), "bashundhara": (23.820, 90.430),

    # Large industrial consumers that take supply directly. Placed at the
    # company's known works, which is the only location the name gives.
    "aksml": (22.550, 91.720), "ksrm": (22.420, 91.790),
    "rahim": (22.400, 91.800), "rings": (22.360, 91.860),
    "shah": (23.550, 90.530), "cement": (23.550, 90.510),
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


def load_genend():
    """PGCB's generation-end hourly view, d_gen=1 on the same page.

    Kept apart from the sub-station view because the two are different
    measurements of the same hours, roughly six per cent apart. This one runs
    from 2015 but stops on 22 April 2026; the daily workbook carries the same
    measurement forward from there, and the two agree to within 0.02%.
    """
    out = []
    for f in sorted(PGCB.glob("genend_*.csv")):
        for x in read_csv(f):
            out.append({"date": x["date"], "hour": int(x["hour"]),
                        "demand": num(x.get("demand")),
                        "generation": num(x.get("generation")),
                        "loadshed": num(x.get("loadshed"))})
    return out


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


# Summer in Bangladesh runs April to September, not the three months an
# English calendar would call it. Defined once and shared: the gas comparison
# and the demand split are both statements about the same season, and if they
# were allowed to drift apart the page would appear to contradict itself.
SEASON_MONTHS = ("04", "05", "06", "07", "08", "09")
HOT_MONTHS = set(SEASON_MONTHS)
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


# Each station's fuel, taken from the Forecast sheet. The remarks column
# would be the obvious place to look for why a plant did not run, but it grew
# markedly more complete between the two summers, so counting on it would
# confuse better record-keeping with a worse shortage. The fuel does not move.
FLEET_LABELS = ("gas", "coal", "furnace oil", "import", "hydro",
                "diesel", "solar", "wind")
# Solar and diesel are reported but not shown: the evening peak falls after
# sunset, so solar is idle by arithmetic rather than by any decision, and the
# diesel fleet is a couple of hundred megawatts.
FLEET_SHOWN = ("gas", "coal", "furnace oil", "import", "hydro")
FLEET_MIN_MW = 60


def _fleet_of(fuel):
    v = (fuel or "").strip().lower()
    if "gas" in v:
        return "gas"
    if "coal" in v:
        return "coal"
    if "hfo" in v or "furnace" in v:
        return "furnace oil"
    if "hsd" in v or "diesel" in v:
        return "diesel"
    if "hydro" in v:
        return "hydro"
    if "solar" in v:
        return "solar"
    if "wind" in v:
        return "wind"
    if "import" in v:
        return "import"
    return "other"


# ── how much of demand growth is the weather ─────────────────────────────────
#
# Demand plainly moves with temperature; the disputed question is whether the
# decade-long climb is itself a weather story. Two things have to be kept
# apart, because they are routinely conflated: the response of demand to a
# given temperature, and the change in temperature itself. Both raise demand,
# and only the residual after both is left needing another explanation.
#
#   demand_d = year + month + day-of-week + Eid + f(temperature) + e
#
# f() is a set of bins rather than a slope: the response is flat below about
# 27C and steep above it, and a straight line would average the two regions
# into a single wrong number. The year effects are then growth at constant
# weather, and the weather term is the model evaluated at the actual
# temperature against that day's climatological normal.

TEMP_BINS = [-99, 18, 21, 24, 26, 28, 30, 32, 34, 99]
TEMP_MIN_DAYS = 800
TEMP_FULL_YEAR = 340        # days before a year counts as complete
# Typed-in errors reach five figures in the source (a peak of 156,050 MW
# appears in April 2023). They are dropped, not clipped: they are not extreme
# observations, they are wrong ones.
TEMP_DEMAND_LO, TEMP_DEMAND_HI = 2_000.0, 25_000.0


def _temp_bin_labels():
    out = []
    for i in range(len(TEMP_BINS) - 1):
        lo, hi = TEMP_BINS[i], TEMP_BINS[i + 1]
        out.append(f"<{hi}" if lo == -99 else
                   (f"{lo}+" if hi == 99 else f"{lo}-{hi}"))
    return out


def load_hourly_weather():
    """date -> daily max of the population-weighted temperature, per region."""
    day = defaultdict(lambda: defaultdict(list))
    for f in sorted((RAW / "weather").glob("temp_*.csv")):
        for row in read_csv(f):
            for k in ["national"] + ZONES:
                v = num(row.get(k))
                if v is not None:
                    day[row["date"]][k].append(v)
    return {d: {k: max(v) for k, v in cols.items() if len(v) >= 20}
            for d, cols in day.items()}


def _daily_demand_for_temp():
    """date -> daily peak of published demand, generation-end basis."""
    per = defaultdict(list)
    for f in sorted(PGCB.glob("genend_*.csv")):
        for row in read_csv(f):
            v = num(row.get("demand"))
            if v is not None and TEMP_DEMAND_LO <= v <= TEMP_DEMAND_HI:
                per[row["date"]].append(v)
    seen = set(per)
    for f in sorted(ERP_DIR.glob("hourly_*.csv")):
        for row in read_csv(f):
            if row["date"] in seen:
                continue
            v = num(row.get("demand"))
            if v is not None and TEMP_DEMAND_LO <= v <= TEMP_DEMAND_HI:
                per[row["date"]].append(v)
    return {d: {"peak": max(v), "mean": sum(v) / len(v)}
            for d, v in per.items() if len(v) >= 20}


def _temp_design(dates, temps, years, months):
    import numpy as np
    cols = [np.ones(len(dates))]
    names = ["const"]
    for y in years[1:]:
        cols.append(np.array([1.0 if d[:4] == y else 0.0 for d in dates]))
        names.append(f"year_{y}")
    for m in months[1:]:
        cols.append(np.array([1.0 if d[5:7] == m else 0.0 for d in dates]))
        names.append(f"month_{m}")
    dows = [date.fromisoformat(d).weekday() for d in dates]
    for k in range(1, 7):
        cols.append(np.array([1.0 if w == k else 0.0 for w in dows]))
        names.append(f"dow_{k}")
    cols.append(np.array([1.0 if _is_eid(d) else 0.0 for d in dates]))
    names.append("eid")
    idx = np.digitize(temps, TEMP_BINS) - 1
    labels = _temp_bin_labels()
    for b in range(1, len(labels)):
        cols.append(np.array([1.0 if i == b else 0.0 for i in idx]))
        names.append(f"temp_{labels[b]}")
    return np.column_stack(cols), names, idx, labels


# Built on first use: EID_DATES is defined further down the module, and the
# festival closes industry for several days rather than one.
_EID_DAYS = None


def _is_eid(d):
    global _EID_DAYS
    if _EID_DAYS is None:
        _EID_DAYS = set()
        for _lst in EID_DATES.values():
            for _iso, _ in _lst:
                _b = date.fromisoformat(_iso)
                for _k in range(-1, 4):
                    _EID_DAYS.add((_b + timedelta(days=_k)).isoformat())
    return d in _EID_DAYS


def build_temperature():
    """What the weather explains, and what it does not."""
    try:
        import numpy as np
    except ImportError:
        print("[build] numpy missing; skipping the temperature model")
        return None
    wx = load_hourly_weather()
    dem = _daily_demand_for_temp()
    days = sorted(set(wx) & set(dem))
    days = [d for d in days if "national" in wx[d]]
    if len(days) < TEMP_MIN_DAYS:
        return None

    y = np.array([dem[d]["peak"] for d in days])
    t = np.array([wx[d]["national"] for d in days])
    years = sorted({d[:4] for d in days})
    months = sorted({d[5:7] for d in days})
    X, names, idx, labels = _temp_design(days, t, years, months)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(resid @ resid) / ss_tot if ss_tot else None
    keep = [i for i, n in enumerate(names) if not n.startswith("temp_")]
    b0, *_ = np.linalg.lstsq(X[:, keep], y, rcond=None)
    res0 = y - X[:, keep] @ b0
    share_daily = 1 - float(resid @ resid) / float(res0 @ res0)

    pos = {n: i for i, n in enumerate(names)}
    n_days = np.bincount(idx, minlength=len(labels))
    response = [{"bin": labels[b],
                 "lo": TEMP_BINS[b] if TEMP_BINS[b] != -99 else None,
                 "hi": TEMP_BINS[b + 1] if TEMP_BINS[b + 1] != 99 else None,
                 "mw": 0.0 if b == 0 else r(beta[pos[f"temp_{labels[b]}"]], 0),
                 "days": int(n_days[b])}
                for b in range(len(labels)) if n_days[b] > 0]

    # weather term: actual temperature against that day's climatological normal
    clim = defaultdict(list)
    for d, tt in zip(days, t):
        clim[d[5:]].append(tt)
    clim = {k: sum(v) / len(v) for k, v in clim.items()}
    Xn, *_ = _temp_design(days, np.array([clim[d[5:]] for d in days]),
                          years, months)
    weather = (X @ beta) - (Xn @ beta)

    byyear = defaultdict(list)
    for d, a, w, tt in zip(days, y, weather, t):
        byyear[d[:4]].append((a, w, tt))
    series = []
    for yr in sorted(byyear):
        v = byyear[yr]
        act = sum(x[0] for x in v) / len(v)
        wea = sum(x[1] for x in v) / len(v)
        series.append({"year": yr, "days": len(v), "actual": r(act),
                       "normalised": r(act - wea), "weather": r(wea, 1),
                       "temp": r(sum(x[2] for x in v) / len(v), 2)})
    full = [x for x in series if x["days"] >= TEMP_FULL_YEAR] or series
    a, b = full[0], full[-1]
    rise = b["actual"] - a["actual"]
    rise_norm = b["normalised"] - a["normalised"]

    return {
        "response": response, "series": series,
        "days": len(days), "from": days[0], "to": days[-1],
        "r2": r(r2, 3), "share_daily": r(100 * share_daily, 0),
        "compare": {
            "from": a["year"], "to": b["year"],
            "rise": r(rise), "rise_norm": r(rise_norm),
            "weather": r(rise - rise_norm, 1),
            "weather_pct": r(100 * (rise - rise_norm) / rise, 1) if rise else None,
            "rise_pct": r(100 * rise / a["actual"], 1),
            "temp_change": r(b["temp"] - a["temp"], 2),
        },
        "part_years": [x["year"] for x in series if x["days"] < TEMP_FULL_YEAR],
        "checks": _temp_checks(wx, dem),
        "zones": _temp_zones(wx, days),
    }


def _temp_checks(wx, dem_daily):
    """The same decomposition on two other samples.

    A result this consequential should not rest on one choice of dependent
    variable or one span. The daily mean is a different statistic from the
    peak, and 2016-2021 predates load-shedding of any size, so demand there
    is measured rather than reconstructed from the shortfall.
    """
    import numpy as np

    def run(days, values):
        if len(days) < TEMP_MIN_DAYS:
            return None
        t = np.array([wx[d]["national"] for d in days])
        y = np.array(values)
        yrs = sorted({d[:4] for d in days}); mos = sorted({d[5:7] for d in days})
        X, names, idx, labels = _temp_design(days, t, yrs, mos)
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        clim = defaultdict(list)
        for d, tt in zip(days, t):
            clim[d[5:]].append(tt)
        clim = {k: sum(v) / len(v) for k, v in clim.items()}
        Xn, *_ = _temp_design(days, np.array([clim[d[5:]] for d in days]),
                              yrs, mos)
        wea = (X @ beta) - (Xn @ beta)
        byy = defaultdict(list)
        for d, a, w in zip(days, y, wea):
            byy[d[:4]].append((a, w))
        rows = [(k, sum(x[0] for x in v) / len(v), sum(x[1] for x in v) / len(v),
                 len(v)) for k, v in sorted(byy.items())]
        full = [x for x in rows if x[3] >= TEMP_FULL_YEAR] or rows
        if len(full) < 2:
            return None
        a, b = full[0], full[-1]
        rise = b[1] - a[1]
        rise_n = (b[1] - b[2]) - (a[1] - a[2])
        return r(100 * (rise - rise_n) / rise, 1) if rise else None

    all_days = sorted(d for d in dem_daily if d in wx and "national" in wx[d])
    mean_pct = run(all_days, [dem_daily[d]["mean"] for d in all_days])
    early = [d for d in all_days if d <= "2021-12-31"]
    early_pct = run(early, [dem_daily[d]["peak"] for d in early])
    return {"mean_pct": mean_pct, "early_pct": early_pct}


def _temp_zones(wx, national_days):
    """Each zone's own response to its own temperature, as a share of its peak."""
    import numpy as np
    area = {}
    for f in sorted(AREA_DIR.glob("areawise*.json")):
        area.update(read_json(f, {}) or {})
    out = []
    for z in ZONES:
        ds, ys, ts = [], [], []
        for d, rec in sorted(area.items()):
            if rec.get("suspect") or d not in wx or z not in wx[d]:
                continue
            cell = (rec.get("zones") or {}).get(z)
            v = cell.get("demand") if isinstance(cell, dict) else (
                cell[0] if isinstance(cell, list) else cell)
            v = num(v)
            if v is None or not (50 <= v <= 12000):
                continue
            ds.append(d); ys.append(v); ts.append(wx[d][z])
        if len(ds) < TEMP_MIN_DAYS:
            continue
        yrs = sorted({d[:4] for d in ds}); mos = sorted({d[5:7] for d in ds})
        X, names, idx, labels = _temp_design(ds, np.array(ts), yrs, mos)
        beta, *_ = np.linalg.lstsq(X, np.array(ys), rcond=None)
        pos = {n: i for i, n in enumerate(names)}
        top = labels[-1]
        lift = beta[pos[f"temp_{top}"]] if f"temp_{top}" in pos else None
        mean = sum(ys) / len(ys)
        if lift is None:
            continue
        # the whole curve, not just its top: the shape differs between the dry
        # north-west and the coast, and that is the regional story
        counts = np.bincount(idx, minlength=len(labels))
        curve = [{"bin": labels[b],
                  "mw": 0.0 if b == 0 else r(beta[pos[f"temp_{labels[b]}"]], 0),
                  "pct": 0.0 if b == 0 else r(100 * beta[pos[f"temp_{labels[b]}"]]
                                              / mean, 1),
                  "days": int(counts[b])}
                 for b in range(len(labels)) if counts[b] >= 10]
        out.append({"zone": z, "mean_peak": r(mean), "lift_mw": r(lift),
                    "lift_pct": r(100 * lift / mean, 1), "days": len(ds),
                    "response": curve})
    out.sort(key=lambda x: -x["lift_pct"])
    return out


# ── which stations promised, and which delivered ─────────────────────────────
#
# The daily Forecast sheet names every station and states how much it expects
# to have available at tomorrow's evening peak. The next day's sheet reports
# what each actually produced. Lining the two up is the only per-station
# accountability the published record allows, and it is the difference between
# "capacity exists" and "capacity turned up".
#
# The two figures sit in the same row but describe different days: the sheet
# dated d carries the forecast for d and the outturn for d-1. Comparing them
# in place would be an off-by-one, so the outturn is filed under the day it
# describes before the two are matched.
FORECAST_MIN_MW = 20        # ignore trivial declarations
FORECAST_MIN_DAYS = 60      # a station needs a season before it is named
FORECAST_FAIL = 0.02        # produced under 2% of what was declared


# ── what the sub-station record says about peak load ─────────────────────────
#
# Every grid sub-station reports its own daily maximum and the hour it fell.
# Two things follow that nothing else in the published record can give.
#
# First, sub-stations do not peak together. Summing each one's own maximum
# gives a non-coincident peak; the system only ever meets the coincident one.
# The ratio is the coincidence factor, and the gap is the headroom that would
# be needed if the whole country ever peaked at the same moment.
#
# Both sides of that ratio must be the same quantity. A sub-station can only
# register electricity it actually delivered, so it is compared against
# coincident SERVED load -- the zone table's demand column already contains
# the shed portion, and using it would inflate the numerator in exactly the
# years when shedding is worst.
#
# Second, the hour of each sub-station's peak is a signature of what it feeds:
# evening for households, working hours for industry.
SUBPEAK_MIN_STATIONS = 150      # a day must cover most of the fleet
SUBPEAK_MIN_DAYS = 200          # a station must be present for a season
SUBPEAK_MAX_MW = 1500           # above this is a typed-in error


def _peak_band(hour):
    if 9 <= hour <= 16:
        return "day"
    if 17 <= hour <= 22:
        return "evening"
    return "night"


def build_substation_peak():
    """Coincidence of sub-station peaks, and when each one falls."""
    by_day, by_station = defaultdict(dict), defaultdict(list)
    for f in sorted(ERP_DIR.glob("substations_*.csv")):
        for row in read_csv(f):
            v = num(row.get("load_mw"))
            if v is None or not (0 < v <= SUBPEAK_MAX_MW):
                continue
            by_day[row["date"]][row["substation"]] = v
            t = row.get("time") or ""
            if len(t) >= 4 and t[:2].isdigit():
                by_station[row["substation"]].append((row["date"], v, int(t[:2])))
    if not by_day:
        return None

    zones = read_json(SITE_DATA / "zones.json", {}) or {}
    zk = zones.get("zones") or ZONES
    served = {}
    for x in zones.get("nldc_evening_peak", []):
        dem = x.get("total_demand")
        if not dem:
            continue
        shed = sum((x[k][1] or 0) for k in zk if isinstance(x.get(k), list))
        served[x["date"]] = dem - shed

    pairs = [(d, sum(m.values()), served[d])
             for d, m in by_day.items()
             if d in served and len(m) >= SUBPEAK_MIN_STATIONS]
    if len(pairs) < 100:
        return None
    nc = sorted(x[1] for x in pairs)
    co = sorted(x[2] for x in pairs)
    cf = sorted(x[2] / x[1] for x in pairs)
    med_cf = statistics.median(cf)

    # is the coincidence drifting? summer against summer, so the seasonal mix
    # cannot masquerade as a trend
    summers = defaultdict(list)
    for d, n, c in pairs:
        if d[5:7] in ("06", "07", "08"):
            summers[d[:4]].append(c / n)
    trend = [{"year": y, "coincidence": r(statistics.median(v), 3), "days": len(v)}
             for y, v in sorted(summers.items()) if len(v) >= 40]

    bands = defaultdict(lambda: {"stations": 0, "mw": 0.0})
    for st_name, recs in by_station.items():
        if len(recs) < SUBPEAK_MIN_DAYS:
            continue
        c = Counter(_peak_band(h) for _, _, h in recs)
        b = bands[c.most_common(1)[0][0]]
        b["stations"] += 1
        b["mw"] += statistics.median(v for _, v, _ in recs)
    total_mw = sum(b["mw"] for b in bands.values()) or 1
    band_rows = [{"band": k, "stations": v["stations"], "mw": r(v["mw"]),
                  "pct": r(100 * v["mw"] / total_mw, 1)}
                 for k, v in sorted(bands.items(), key=lambda x: -x[1]["mw"])]

    return {
        "days": len(pairs), "stations": len([s for s, v in by_station.items()
                                             if len(v) >= SUBPEAK_MIN_DAYS]),
        "from": min(x[0] for x in pairs), "to": max(x[0] for x in pairs),
        "non_coincident_median": r(statistics.median(nc)),
        "non_coincident_max": r(nc[-1]),
        "coincident_median": r(statistics.median(co)),
        "coincident_max": r(co[-1]),
        "coincidence": r(med_cf, 3),
        "diversity": r(1 / med_cf, 3),
        "headroom_pct": r(100 * (1 / med_cf - 1), 1),
        "trend": trend,
        "bands": band_rows,
    }


# ── can suppressed demand be located station by station? ─────────────────────
#
# A sub-station that once carried X MW proves at least X MW of demand sits
# behind it, so the natural idea is to map each station's shortfall against
# its own record and call the difference suppression. That inference does not
# survive contact with the data, and this function is what tests it.
#
# Three tests, none of which finds a per-station signal:
#
#   level     the fleet's recent maximum against the sum of all-time records.
#             If load had been driven off the network the sum would have
#             fallen. It has not.
#   response  each station's daily peak regressed on its zone's shed rate,
#             holding that zone's temperature constant. If shedding held a
#             station back the coefficient would be negative everywhere.
#   pinning   how often a station sits within 5% of its own record. Rationing
#             against a fixed ceiling would clip the top of the distribution.
#
# The reason they all come back empty is that rotational load-shedding is
# executed by the distribution utilities on 11 kV feeders *below* these
# transmission sub-stations, and rotated between feeders. The station carries
# on at close to its allowed load while the curtailment moves around beneath
# it, so the shed energy never appears at any station and nothing in this
# table records which station it would have flowed through. Suppression is
# real, but it is only measurable in the aggregate — see build_substation_peak.
#
# A record is a record: the raw maximum stands unless the reading is
# impossible. An earlier version compared each maximum against the station's
# own 99th percentile and rejected thirteen of them, which threw away real
# records -- Kalurghat's 134 MW against a second-highest of 130, Matarbari's
# 132 against 127. Those are ordinary peaks at stations that are usually
# quiet, not typos.
#
# A reading is discarded only when it fails both halves of a physical test:
# it stands more than three times clear of the same station's second-highest
# reading ever, AND it exceeds the largest load any credible station in the
# country has carried. Exactly one reading in the archive qualifies --
# HaripurSBU at 1,110 MW on 2026-06-29, which is 5.6x its own second-highest
# (197 MW) and 3.1x the biggest sub-station in Bangladesh (Kodda, 356 MW).
# It is replaced by that station's second-highest reading, not by a
# percentile, so what survives is still an observed peak.
SUPPRESS_ISOLATION = 3.0        # max must clear its own runner-up by this much
SUPPRESS_MIN_READINGS = 60
SUPPRESS_RECENT = 40            # days needed in the recent window
SUPPRESS_MIN_MW = 5             # below this the percentages are noise
SUPPRESS_PIN = 0.95             # "at its ceiling" means within 5% of record


def _ols3(rows):
    """Least squares for y ~ a + b*x1 + c*x2. Returns (c, t) or None."""
    n = len(rows)
    X = [(1.0, x1, x2) for x1, x2, _ in rows]
    y = [v for _, _, v in rows]
    xtx = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(3)]
           for i in range(3)]
    xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(3)]
    # Gauss-Jordan on the augmented normal equations, carrying the inverse
    # so the standard error of the shed term comes out with the fit.
    a = [xtx[i][:] + [1.0 if i == j else 0.0 for j in range(3)] + [xty[i]]
         for i in range(3)]
    for i in range(3):
        piv = max(range(i, 3), key=lambda k: abs(a[k][i]))
        if abs(a[piv][i]) < 1e-9:
            return None
        a[i], a[piv] = a[piv], a[i]
        d = a[i][i]
        a[i] = [v / d for v in a[i]]
        for k in range(3):
            if k != i and a[k][i]:
                f = a[k][i]
                a[k] = [v - f * w for v, w in zip(a[k], a[i])]
    beta = [a[i][6] for i in range(3)]
    inv = [[a[i][3 + j] for j in range(3)] for i in range(3)]
    rss = sum((y[k] - sum(beta[i] * X[k][i] for i in range(3))) ** 2
              for k in range(n))
    dof = n - 3
    if dof <= 0 or inv[2][2] <= 0:
        return None
    se = math.sqrt(rss / dof * inv[2][2])
    return (beta[2], beta[2] / se) if se > 0 else None


_PEAK_CACHE = None


def _station_daily_peaks():
    global _PEAK_CACHE
    if _PEAK_CACHE is not None:
        return _PEAK_CACHE
    per = defaultdict(dict)
    for f in sorted(ERP_DIR.glob("substations_*.csv")):
        for row in read_csv(f):
            v = num(row.get("load_mw"))
            if v is None or not (0 < v <= SUBPEAK_MAX_MW):
                continue
            d = row["date"]
            per[row["substation"]][d] = max(v, per[row["substation"]].get(d, 0))
    _PEAK_CACHE = per
    return per


def _zone_daily_tmax():
    out = defaultdict(dict)
    for f in sorted((RAW / "weather").glob("temp_*.csv")):
        for row in read_csv(f):
            for z in ZONES:
                v = num(row.get(z))
                if v is None:
                    continue
                d = row["date"]
                if v > out[z].get(d, -99):
                    out[z][d] = v
    return out


def build_suppression(area, subs):
    """Test whether suppressed demand can be pinned to individual stations."""
    per = _station_daily_peaks()
    if not per or not subs:
        return None
    latest = max(d for v in per.values() for d in v)
    cutoff = (date.fromisoformat(latest) - timedelta(days=90)).isoformat()

    rec, rejected = _station_records()
    stations = {}
    raw_sum = robust_sum = recent_sum = matched_sum = 0.0
    pins = []
    for name, record in rec.items():
        dd = per[name]
        raw_sum += max(dd.values())
        robust_sum += record
        recent = [min(v, record) for d, v in dd.items() if d >= cutoff]
        if len(recent) < SUPPRESS_RECENT or record < SUPPRESS_MIN_MW:
            continue
        # like for like: only stations that have a recent window count
        # on both sides of the level test.
        matched_sum += record
        recent_sum += min(max(recent), record)
        pins.append(100 * sum(1 for v in recent if v >= SUPPRESS_PIN * record)
                    / len(recent))
        stations[name] = r(record, 1)

    # response test: does a station give way when its zone is short?
    tmax = _zone_daily_tmax()
    shed = {}
    for d, arow in sorted(area.items()):
        if arow.get("suspect"):
            continue
        for z in ZONES:
            zz = arow["zones"].get(z) or {}
            if zz.get("demand"):
                shed.setdefault(z, {})[d] = 100 * zz["loadshed"] / zz["demand"]
    zone_of = {s["name"]: s["zone"] for s in subs["substations"] if s.get("zone")}
    recent_shed = {z: statistics.mean(
        [v[d] for d in sorted(v)[-90:]]) for z, v in shed.items() if v}

    tested = neg = sig = 0
    supp_mw = 0.0
    for name, dd in per.items():
        z = zone_of.get(name)
        if not z or z not in shed:
            continue
        obs = [(tmax[z][d], shed[z][d], v) for d, v in dd.items()
               if d[5:7] in SEASON_MONTHS and d[:4] >= "2025"
               and d in tmax.get(z, {}) and d in shed[z] and v > 0]
        if len(obs) < 80:
            continue
        fit = _ols3(obs)
        if not fit:
            continue
        c, t = fit
        tested += 1
        if c < 0:
            neg += 1
            if t < -1.96:
                sig += 1
                supp_mw += -c * recent_shed.get(z, 0)

    return {
        "stations": stations, "n": len(stations),
        "spikes_capped": len(rejected), "rejected": sorted(rejected),
        "window_from": cutoff, "window_to": latest,
        "raw_sum": r(raw_sum), "robust_sum": r(robust_sum),
        "level_gap_pct": r(100 * (1 - recent_sum / matched_sum), 1),
        "level_records": r(matched_sum), "level_recent": r(recent_sum),
        "response": {"tested": tested, "negative": neg, "significant": sig,
                     "mw": r(supp_mw)},
        "pinned_median_pct": r(statistics.median(pins), 1) if pins else None,
        "pinned_max_pct": r(max(pins), 1) if pins else None,
        "verdict": "not-localisable",
    }


# ── the whole network's demonstrated ceiling, day by day ─────────────────────
#
# Every sub-station's own all-time peak is a fact the network has already
# proved: that much load did flow through that point. Adding them up gives a
# non-coincident ceiling for the country -- what the grid would have to carry
# if every sub-station hit its own record on the same day. Nothing is ever
# asked to do that (see build_substation_peak for the coincidence factor), so
# the figure is a reference line, not a forecast.
#
# What it is good for is a denominator. Each day's non-coincident sum against
# that ceiling says how much of the network's demonstrated capability was
# actually used, and the load-shedding of the same day says how much of the
# shortfall was rationing rather than quiet demand.
#
# The shed figure is a coincident national number and the served figure is a
# non-coincident sum, so the two do not add to a true non-coincident demand.
# Their sum is a floor for it, and is labelled as one.
SUM_MIN_COVERAGE = 0.9          # days where too few stations reported are out


def _station_records():
    """Each station's all-time peak, keeping every reading that could be real.

    Returns {name: record} plus the set of names whose top reading failed the
    physical test above and fell back to their runner-up.
    """
    tops = {}
    for name, dd in _station_daily_peaks().items():
        if len(dd) < SUPPRESS_MIN_READINGS:
            continue
        vals = sorted(dd.values())
        tops[name] = (vals[-1], vals[-2] if len(vals) > 1 else vals[-1])

    isolated = {n for n, (a, b) in tops.items()
                if b > 0 and a > SUPPRESS_ISOLATION * b}
    # the largest load any station not under suspicion has ever carried
    credible = max((a for n, (a, _) in tops.items() if n not in isolated),
                   default=0.0)
    rejected = {n for n in isolated if tops[n][0] > credible}
    return ({n: (tops[n][1] if n in rejected else tops[n][0]) for n in tops},
            rejected)


def build_theoretical(subs):
    """The summed peak ceiling, and how much of it each day actually used."""
    per = _station_daily_peaks()
    rec, rejected = _station_records()
    if not rec:
        return None
    ceiling = sum(rec.values())

    served, count = defaultdict(float), Counter()
    for name, record in rec.items():
        for d, v in per[name].items():
            served[d] += min(v, record)      # a spike cannot exceed the record
            count[d] += 1
    need = SUM_MIN_COVERAGE * len(rec)
    days = sorted(d for d in served if count[d] >= need)
    if not days:
        return None

    shed = {}
    for row in read_json(SITE_DATA / "daily.json", {}).get("rows", []):
        if row.get("max_loadshed") is not None:
            shed[row["date"]] = row["max_loadshed"]
    days = [d for d in days if d in shed]
    if not days:
        return None

    latest = days[-1]
    busiest = max(days, key=lambda d: served[d])
    util = [100 * served[d] / ceiling for d in days]

    # the latest day, station by station
    bands = [(0, 50), (50, 70), (70, 85), (85, 101)]
    band_rows = [{"lo": lo, "hi": hi, "stations": 0, "record": 0.0, "unused": 0.0}
                 for lo, hi in bands]
    zone_of = {x["name"]: x["zone"] for x in (subs or {}).get("substations", [])}
    zrec, zserved = Counter(), Counter()
    station_util, reporting_rec, reporting_used = {}, 0.0, 0.0
    for name, record in rec.items():
        v = per[name].get(latest)
        if v is None or record < SUPPRESS_MIN_MW:
            continue
        v = min(v, record)
        pct = 100 * v / record
        station_util[name] = r(pct, 1)
        reporting_rec += record
        reporting_used += v
        for row, (lo, hi) in zip(band_rows, bands):
            if lo <= pct < hi:
                row["stations"] += 1
                row["record"] += record
                row["unused"] += record - v
                break
        z = zone_of.get(name)
        if z:
            zrec[z] += record
            zserved[z] += v

    return {
        "ceiling": r(ceiling), "stations": len(rec),
        "rejected": sorted(rejected),
        "from": days[0], "to": latest, "days": days,
        "served": [r(served[d]) for d in days],
        "shed": [r(shed[d]) for d in days],
        "median_util": r(statistics.median(util), 1),
        "latest_util": r(100 * served[latest] / ceiling, 1),
        "latest_record": r(reporting_rec), "latest_unused": r(reporting_rec - reporting_used),
        "latest_shed": r(shed[latest]),
        "busiest": {"date": busiest, "served": r(served[busiest]),
                    "util": r(100 * served[busiest] / ceiling, 1),
                    "unused": r(ceiling - served[busiest]),
                    "shed": r(shed[busiest])},
        "bands": [{**x, "record": r(x["record"]), "unused": r(x["unused"])}
                  for x in band_rows],
        "zones": [{"zone": z, "record": r(zrec[z]), "served": r(zserved[z]),
                   "util": r(100 * zserved[z] / zrec[z], 1)}
                  for z in ZONES if zrec[z]],
        "station_util": station_util,
    }


# ── every sub-station's own trend, and where the growth actually is ──────────
#
# The natural suspicion about a demand surge is that a handful of places
# caused it -- a district that electrified its rickshaw charging, an area that
# went over to induction cooking, a belt of new industry. That is a testable
# claim: if it were true, the increase would sit in a few sub-stations and the
# rest of the fleet would be flat.
#
# Two things have to be separated before the per-station numbers mean
# anything. New sub-stations are energised to relieve existing ones, so their
# whole load reads as growth while the neighbour they took it from reads as
# collapse -- Daganbhuiyan appears with 37 MW while Chowmuhani drops 48, and
# Sylhet_(South) appears with 69 MW while Sylhet-132 falls. Each station's
# change is therefore reported next to its district's net change, and stations
# with no baseline season are marked rather than ranked as the fastest
# growing.
#
# Seasons are compared May-August, the months fully covered in both years, so
# the comparison is not an artefact of when collection started or stopped.
TREND_SEASON = ("05", "06", "07", "08")
TREND_MIN_DAYS = 40             # days needed in a season for it to count


def build_station_trend():
    """Each station's monthly trend and its share of the fleet's change."""
    per = _station_daily_peaks()
    rec, _ = _station_records()
    if not per:
        return None
    subs = read_json(SITE_DATA / "substations.json", {}) or {}
    meta = {x["name"]: x for x in subs.get("substations", [])}

    monthly = defaultdict(lambda: defaultdict(list))
    season = defaultdict(lambda: defaultdict(list))
    for name, dd in per.items():
        cap = rec.get(name)
        for d, v in dd.items():
            if cap:
                v = min(v, cap)
            monthly[name][d[:7]].append(v)
            if d[5:7] in TREND_SEASON:
                season[name][d[:4]].append(v)
    months = sorted({m for v in monthly.values() for m in v})
    years = sorted({y for v in season.values() for y in v})
    if len(years) < 2 or len(months) < 6:
        return None
    y0, y1 = years[-2], years[-1]

    stations, dist = [], defaultdict(lambda: [0.0, 0.0, 0])
    for name in sorted(monthly):
        a = season[name].get(y0, [])
        b = season[name].get(y1, [])
        if len(b) < TREND_MIN_DAYS:
            continue                       # no current season, nothing to say
        fresh = len(a) < TREND_MIN_DAYS
        am = 0.0 if fresh else statistics.mean(a)
        bm = statistics.mean(b)
        m = meta.get(name) or {}
        d = m.get("district") or "-"
        dist[d][0] += am
        dist[d][1] += bm
        dist[d][2] += 1
        stations.append({
            "name": name, "zone": m.get("zone"), "district": m.get("district"),
            "series": [r(statistics.mean(monthly[name][mo]), 1)
                       if monthly[name].get(mo) else None for mo in months],
            "a": r(am, 1), "b": r(bm, 1), "delta": r(bm - am, 1),
            "pct": None if fresh or am < SUPPRESS_MIN_MW else r(100 * (bm / am - 1), 1),
            "new": fresh,
        })
    if not stations:
        return None

    comp = [x for x in stations if not x["new"]]
    fresh = [x for x in stations if x["new"]]
    A = sum(x["a"] for x in comp)
    B = sum(x["b"] for x in comp)
    ups = [x for x in comp if x["delta"] > 0]
    dns = [x for x in comp if x["delta"] < 0]
    gross_up = sum(x["delta"] for x in ups)
    top10 = sum(sorted((x["delta"] for x in ups), reverse=True)[:10])
    pcts = sorted(x["pct"] for x in comp if x["pct"] is not None)
    for x in stations:
        # Stations whose location could not be matched are pooled under "-";
        # that pool is not a district, so it must not be quoted as one.
        d = dist.get(x["district"]) if x["district"] else None
        x["district_delta"] = r(d[1] - d[0], 1) if d else None

    return {
        "months": months, "y0": y0, "y1": y1,
        "season": "-".join((TREND_SEASON[0], TREND_SEASON[-1])),
        "fleet": {
            "comparable": len(comp), "a": r(A), "b": r(B),
            "pct": r(100 * (B / A - 1), 1) if A else None,
            "new_stations": len(fresh), "new_mw": r(sum(x["b"] for x in fresh)),
            "rose": len(ups), "fell": len(dns),
            "gross_up": r(gross_up), "gross_down": r(sum(x["delta"] for x in dns)),
            "net": r(B - A),
            "median_pct": r(statistics.median(pcts), 1) if pcts else None,
            "q1_pct": r(pcts[len(pcts) // 4], 1) if pcts else None,
            "q3_pct": r(pcts[3 * len(pcts) // 4], 1) if pcts else None,
            "top10_gross_pct": r(100 * top10 / gross_up, 0) if gross_up else None,
        },
        # New stations are listed after the comparable ones: their whole load
        # reads as growth, so ranking them as the fastest-growing would say
        # the opposite of what the numbers mean.
        "stations": sorted(stations, key=lambda x: (x["new"], -x["delta"])),
        "districts": sorted(
            [{"district": k, "a": r(v[0], 1), "b": r(v[1], 1),
              "delta": r(v[1] - v[0], 1), "stations": v[2]}
             for k, v in dist.items() if k != "-"],
            key=lambda x: -x["delta"]),
    }


# ── what the generating fleet has proved it can do ───────────────────────────
#
# The sub-station side of this dashboard asks how much load the network has
# demonstrated it can carry. The same question can be put to the other end:
# what has each power station actually produced, as opposed to what its
# nameplate says? A plant's highest recorded output is the strongest evidence
# of its real capability, because it happened.
#
# The NLDC per-plant table cannot be used raw. On a large minority of days the
# PDF's columns come out shifted, so capacity and output land in each other's
# fields -- Payra reads "capacity 2 MW, output 1,244 MW", Adani reads 1,496 MW
# against a 748 MW nameplate. The corruption is wholesale rather than
# scattered: on a good day almost no row reports more output than the plant's
# own nameplate, and on a bad day three quarters of them do. That split is
# what DAY_BAD_SHARE tests, and it throws out about 174 of 789 days.
#
# Two independent checks say the surviving days are sound. Across the days
# where PGCB's own hourly generation series overlaps, the plant table sums to
# 1.03-1.05x the coincident peak -- the small excess a non-coincident sum
# should carry. And the largest simultaneous plant-sum in the clean data lands
# on 17,201 MW, which is the record generation the rest of the dashboard
# derives from an entirely different source.
DAY_BAD_SHARE = 0.02            # share of impossible rows that condemns a day
DAY_MIN_PLANTS = 50
PLANT_OVER_CAP = 1.15           # output above this multiple of nameplate is a
                                # parse error, not a record
PLANT_MIN_DAYS = 60
PLANT_SEASON_DAYS = 30


def _clean_plant_days():
    """Daily per-plant rows from the days whose table parsed correctly."""
    out = []
    for f in sorted(DAILYDIR.glob("*.json")):
        d = read_json(f, {}) or {}
        dt, plants = d.get("date"), d.get("plants") or []
        if not dt or len(plants) < DAY_MIN_PLANTS:
            continue
        if not ("2024-01-01" <= dt <= date.today().isoformat()):
            continue
        bad = sum(1 for p in plants
                  if p.get("capacity_mw") and p.get("peak_mw") is not None
                  and p["peak_mw"] > PLANT_OVER_CAP * p["capacity_mw"])
        if bad / len(plants) <= DAY_BAD_SHARE:
            out.append((dt, plants))
    return out


def build_plant_capability(demand_ceiling=None):
    """Each station's demonstrated output, and whether it is rising."""
    clean = _clean_plant_days()
    total_days = sum(1 for _ in DAILYDIR.glob("*.json"))
    if len(clean) < 100:
        return None

    peak = defaultdict(dict)
    caps, reasons, zone_of = defaultdict(list), defaultdict(Counter), {}
    for dt, plants in clean:
        for p in plants:
            name = (p.get("name") or "").strip()
            mw = p.get("peak_mw")
            if not name or mw is None:
                continue
            if p.get("capacity_mw"):
                caps[name].append(p["capacity_mw"])
            zone_of[name] = p.get("zone")
            peak[name][dt] = max(mw, peak[name].get(dt, 0))
            if mw <= 0 and (p.get("remarks") or "").strip() not in ("", "-"):
                reasons[name][p["remarks"].strip()] += 1
    # nameplate drifts between reports, so take the value stated most often
    cap = {n: Counter(v).most_common(1)[0][0] for n, v in caps.items()}
    proven = {n: max(v.values()) for n, v in peak.items()
              if len(v) >= PLANT_MIN_DAYS}
    if not proven:
        return None

    nameplate = sum(cap.get(n, 0) for n in proven)
    total_proven = sum(proven.values())
    sim = defaultdict(float)
    for n in proven:
        for d, v in peak[n].items():
            sim[d] += v
    best = max(sim, key=sim.get)

    never = [(cap[n] - proven[n], n) for n in proven
             if cap.get(n) and cap[n] - proven[n] > 0]
    never.sort(reverse=True)

    # capability season on season: the maximum, not the mean. A plant that was
    # not called is not a plant that cannot run, so the mean would measure
    # dispatch rather than capability.
    def season(n, y):
        return [v for d, v in peak[n].items()
                if d[:4] == y and d[5:7] in TREND_SEASON]
    years = sorted({d[:4] for v in peak.values() for d in v})
    if len(years) < 2:
        return None
    y0, y1 = years[-2], years[-1]
    rows = []
    for n in proven:
        a, b = season(n, y0), season(n, y1)
        if len(a) < PLANT_SEASON_DAYS or len(b) < PLANT_SEASON_DAYS:
            continue
        am, bm = max(a), max(b)
        top = reasons[n].most_common(1)
        rows.append({"name": n, "a": r(am, 1), "b": r(bm, 1),
                     "delta": r(bm - am, 1),
                     "pct": r(100 * (bm / am - 1), 1) if am > 0 else None,
                     "cap": cap.get(n), "zone": zone_of.get(n),
                     "reason": top[0][0] if top else None})
    if not rows:
        return None
    A = sum(x["a"] for x in rows)
    B = sum(x["b"] for x in rows)
    up = [x for x in rows if x["delta"] > 0]
    dn = [x for x in rows if x["delta"] < 0]

    allr = Counter()
    for c in reasons.values():
        allr.update(c)

    ladder = [{"k": "nameplate", "mw": r(nameplate)},
              {"k": "proven", "mw": r(total_proven)}]
    if demand_ceiling:
        ladder.append({"k": "demand", "mw": r(demand_ceiling)})
    ladder.append({"k": "simultaneous", "mw": r(sim[best])})

    return {
        "days": len(clean), "dropped_days": total_days - len(clean),
        "from": clean[0][0], "to": clean[-1][0], "plants": len(proven),
        "nameplate": r(nameplate), "proven": r(total_proven),
        "proven_pct": r(100 * total_proven / nameplate, 1) if nameplate else None,
        "best_mw": r(sim[best]), "best_date": best,
        "never_mw": r(sum(x for x, _ in never)), "never_plants": len(never),
        "never_top": [{"name": n, "cap": cap[n], "best": r(proven[n], 1)}
                      for _, n in never[:10]],
        "season": {"y0": y0, "y1": y1, "a": r(A), "b": r(B),
                   "pct": r(100 * (B / A - 1), 1) if A else None,
                   "rose": len(up), "rose_mw": r(sum(x["delta"] for x in up)),
                   "fell": len(dn), "fell_mw": r(sum(x["delta"] for x in dn))},
        "declines": sorted(rows, key=lambda x: x["delta"])[:12],
        "gains": sorted(rows, key=lambda x: -x["delta"])[:8],
        "reasons": [{"reason": k, "plant_days": v} for k, v in allr.most_common(8)],
        "ladder": ladder,
    }


def build_forecast_plants(year=None):
    """Per-station forecast availability against what actually ran."""
    fc, ac, rem = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for f in sorted(ERP_DIR.glob("forecast_*.csv")):
        for row in read_csv(f):
            d, plant = row["date"], row["plant"]
            v = num(row.get("forecast_evening"))
            if v is not None:
                fc[d][plant] = v
            a = num(row.get("actual_evening"))
            if a is not None:
                prev = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
                ac[prev][plant] = a
            rem[d][plant] = (row.get("remarks") or "").strip()
    if not fc:
        return None
    year = year or max(fc)[:4]

    per = defaultdict(lambda: {"days": 0, "failed": 0, "declared": 0.0,
                               "undelivered": 0.0, "reasons": Counter()})
    declared = undelivered = 0.0
    for d in sorted(fc):
        if d[:4] != year or d not in ac:
            continue
        for plant, want in fc[d].items():
            got = ac[d].get(plant)
            if got is None or want < FORECAST_MIN_MW:
                continue
            b = per[plant]
            b["days"] += 1
            b["declared"] += want
            declared += want
            if got < FORECAST_FAIL * want:
                b["failed"] += 1
                b["undelivered"] += want
                undelivered += want
                b["reasons"][rem.get(d, {}).get(plant) or "—"] += 1
    if not declared:
        return None

    rows = []
    for plant, b in per.items():
        if b["days"] < FORECAST_MIN_DAYS or not b["failed"]:
            continue
        why, n = b["reasons"].most_common(1)[0]
        rows.append({
            "plant": plant, "days": b["days"], "failed": b["failed"],
            "fail_pct": r(100 * b["failed"] / b["days"], 0),
            "undelivered_mwd": r(b["undelivered"], 0),
            "reason": why, "reason_share": r(100 * n / b["failed"], 0),
        })
    rows.sort(key=lambda x: -x["undelivered_mwd"])

    why_all = Counter()
    for b in per.values():
        why_all.update(b["reasons"])
    total_fail = sum(why_all.values()) or 1
    reasons = [{"reason": k, "pct": r(100 * v / total_fail, 1)}
               for k, v in why_all.most_common(6)]
    return {"year": year, "plants": rows[:12], "n_plants": len(rows),
            "undelivered_pct": r(100 * undelivered / declared, 1),
            "reasons": reasons,
            "days": len({d for d in fc if d[:4] == year and d in ac})}


def build_idle_fleet():
    """How much of each fleet produced nothing at the evening peak.

    Quoting the gas fleet on its own invites the obvious retort — is not
    everything idle? — so every fleet is measured on the same days. The answer
    is that coal, imports and hydro run when called and gas does not.
    """
    fuel = {}
    for f in sorted(ERP_DIR.glob("forecast_*.csv")):
        for rec in read_csv(f):
            if rec.get("fuel"):
                fuel[rec["plant"]] = rec["fuel"]
    rows = defaultdict(list)
    for f in sorted(ERP_DIR.glob("plants_*.csv")):
        for rec in read_csv(f):
            rows[rec["date"]].append(rec)
    if not rows:
        return None

    newest = max(rows)
    cutoff = max(d[5:] for d in rows if d[:4] == newest[:4]
                 and d[5:7] in SEASON_MONTHS) if any(
                     d[5:7] in SEASON_MONTHS for d in rows) else None
    if not cutoff:
        return None
    years = sorted({d[:4] for d in rows if d[5:7] in SEASON_MONTHS
                    and d[5:] <= cutoff})[-2:]
    if len(years) < 2:
        return None

    out = {}
    for y in years:
        days = sorted(d for d in rows if d[:4] == y
                      and d[5:7] in SEASON_MONTHS and d[5:] <= cutoff)
        if len(days) < 30:
            continue
        idle, fleet, daily_total = defaultdict(list), defaultdict(list), []
        for d in days:
            ai, ac = defaultdict(float), defaultdict(float)
            for rec in rows[d]:
                cap = num(rec.get("present_mw"))
                peak = num(rec.get("peak_mw")) or 0.0
                if not cap:
                    continue
                g = _fleet_of(fuel.get(rec["plant"]))
                ac[g] += cap
                if peak < 0.02 * cap:
                    ai[g] += cap
            daily_total.append(sum(ai.values()))
            for k in set(list(ai) + list(ac) + list(idle)):
                idle[k].append(ai.get(k, 0.0))
                fleet[k].append(ac.get(k, 0.0))
        # The total is the median of each day's total, not the sum of the
        # per-fleet medians: those are different numbers, and only the first
        # is "what an ordinary day looks like".
        out[y] = {"days": len(days),
                  "total_idle_mw": r(statistics.median(daily_total), 0),
                  "fleets": {
            k: {"idle_mw": r(statistics.median(idle[k]), 1),
                "fleet_mw": r(statistics.median(fleet[k]), 1)}
            for k in idle}}
    if len(out) < 2:
        return None

    ys = sorted(out)
    fleets = []
    for k in FLEET_SHOWN:
        a = out[ys[0]]["fleets"].get(k)
        b = out[ys[-1]]["fleets"].get(k)
        if not a or not b or max(a["fleet_mw"], b["fleet_mw"]) < FLEET_MIN_MW:
            continue
        fleets.append({
            "fleet": k,
            "prev_pct": r(100 * a["idle_mw"] / a["fleet_mw"], 1) if a["fleet_mw"] else None,
            "pct": r(100 * b["idle_mw"] / b["fleet_mw"], 1) if b["fleet_mw"] else None,
            "prev_idle_mw": a["idle_mw"], "idle_mw": b["idle_mw"],
            "prev_fleet_mw": a["fleet_mw"], "fleet_mw": b["fleet_mw"]})
    fleets.sort(key=lambda x: -(x["pct"] or 0))

    return {"years": ys, "window_from": f"{SEASON_MONTHS[0]}-01",
            "window_to": cutoff, "fleets": fleets,
            "days": {y: out[y]["days"] for y in ys},
            "total_idle": {y: out[y]["total_idle_mw"] for y in ys},
            "excluded": ["solar", "diesel"]}


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


# A month needs this many shed hours before its median factor means anything.
IDENT_MIN_HOURS = 20
IDENT_STEP = 0.005          # a change this large is a revision, not rounding


def identity_regimes(genend):
    """When the gross-up factor was changed, and to what.

    The factor is not a constant of the system. It is an administrative
    assumption about transmission loss, and PGCB has revised it: reading the
    monthly medians end to end shows the steps and when they happened.
    """
    bym = defaultdict(list)
    for x in genend:
        d, g, l = x["demand"], x["generation"], x["loadshed"]
        if None in (d, g, l) or not l or l <= 0:
            continue
        bym[x["date"][:7]].append((d - g) / l)
    months = [(m, statistics.median(v)) for m, v in sorted(bym.items())
              if len(v) >= IDENT_MIN_HOURS]
    if not months:
        return []
    regimes, cur = [], None
    for m, f in months:
        if cur is None or abs(f - cur["factor"]) > IDENT_STEP:
            cur = {"from": m, "to": m, "factor": r(f, 4), "months": 1,
                   "_vals": [f]}
            regimes.append(cur)
        else:
            cur["to"] = m
            cur["months"] += 1
            cur["_vals"].append(f)
    for x in regimes:
        x["factor"] = r(statistics.median(x.pop("_vals")), 4)
        x["loss_pct"] = r(100 * (1 - 1 / x["factor"]), 1)
    return regimes


def build_identity(erp_hourly, genend=None):
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
        "regimes": identity_regimes(genend or []),
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
            "holidays": holidays, "dropped_implausible": dropped,
            "split": build_demand_split(area),
            "surge": build_demand_surge(area)}


# The published demand line has pulled away from every earlier year, and the
# obvious suspicion is that something changed in the reporting rather than on
# the grid. Month against the same month a year earlier, separating what was
# delivered from what was shed, settles it: if a reporting change were behind
# it the break would sit on the month the change was made, and the delivered
# line would jump with the demand line. Neither happens.
SURGE_MONTHS = 14
SURGE_MIN_DAYS = 12


def build_demand_surge(area):
    """Month-on-month growth, split into delivered load and load-shedding."""
    dem, shed = defaultdict(list), defaultdict(list)
    for d, rec in area.items():
        if rec.get("suspect") or not rec.get("total_demand"):
            continue
        v = rec["total_demand"]
        if not (DEMAND_MIN_MW <= v <= DEMAND_MAX_MW):
            continue
        dem[d[:7]].append(v)
        shed[d[:7]].append(rec.get("total_loadshed") or 0)
    months = sorted(m for m in dem if len(dem[m]) >= SURGE_MIN_DAYS)
    rows = []
    for m in months[-SURGE_MONTHS:]:
        prev = f"{int(m[:4]) - 1}{m[4:]}"
        if prev not in dem or len(dem[prev]) < SURGE_MIN_DAYS:
            continue
        served = [a - b for a, b in zip(dem[m], shed[m])]
        served0 = [a - b for a, b in zip(dem[prev], shed[prev])]
        d1, d0 = statistics.median(dem[m]), statistics.median(dem[prev])
        s1, s0 = statistics.median(served), statistics.median(served0)
        rows.append({"month": m, "demand": r(d1), "served": r(s1),
                     "shed": r(statistics.median(shed[m])),
                     "demand_yoy": r(100 * (d1 / d0 - 1), 1) if d0 else None,
                     "served_yoy": r(100 * (s1 / s0 - 1), 1) if s0 else None})
    if len(rows) < 6:
        return None
    hot = [x for x in rows if x["demand_yoy"] is not None
           and x["demand_yoy"] >= 6 and x["shed"] >= 100]
    recent = [x for x in rows if x["served_yoy"] is not None][-3:]
    return {
        "rows": rows,
        "basis_switch": "2026-04",
        "surge_from": hot[0]["month"] if hot else None,
        "served_recent": r(statistics.median(x["served_yoy"] for x in recent), 1)
        if recent else None,
        "demand_recent": r(statistics.median(x["demand_yoy"] for x in recent), 1)
        if recent else None,
    }


# The published demand curve is served load plus load-shedding, so a year in
# which more was shed shows higher demand even if no extra electricity was
# wanted. Splitting the summer peak into the two parts says how much of the
# rise is appetite and how much is failure to meet it.
DEMAND_SPLIT_MONTHS = SEASON_MONTHS
DEMAND_SPLIT_FROM = "2022"


def build_demand_split(area):
    """Summer evening peak, split into what was delivered and what was cut.

    Matched on the day range, not the month: the current year stops partway
    through August, and August is the heaviest part of the window, so running
    a part-year against three full months would understate it.
    """
    rows = defaultdict(list)
    for d, rec in area.items():
        if rec.get("suspect") or not rec.get("total_demand"):
            continue
        if d[5:7] not in DEMAND_SPLIT_MONTHS or d[:4] < DEMAND_SPLIT_FROM:
            continue
        dem = rec["total_demand"]
        if not (DEMAND_MIN_MW <= dem <= DEMAND_MAX_MW):
            continue
        rows[d[:4]].append((d[5:], dem, rec.get("total_loadshed") or 0))
    if len(rows) < 2:
        return None
    newest = max(rows)
    cutoff = max(md for md, _, _ in rows[newest])

    out = []
    for y in sorted(rows):
        days = [x for x in rows[y] if x[0] <= cutoff]
        if len(days) < 20:
            continue
        dem = sum(x[1] for x in days) / len(days)
        shed = sum(x[2] for x in days) / len(days)
        out.append({"year": y, "days": len(days),
                    "demand": r(dem), "served": r(dem - shed), "shed": r(shed)})
    if len(out) < 2:
        return None

    last, prev = out[-1], out[-2]
    d_rise = last["demand"] - prev["demand"]
    v_rise = last["served"] - prev["served"]
    s_rise = last["shed"] - prev["shed"]
    return {
        "rows": out, "window_to": cutoff,
        "window_from": f"{DEMAND_SPLIT_MONTHS[0]}-01",
        "months": list(DEMAND_SPLIT_MONTHS),
        "compare": {
            "from": prev["year"], "to": last["year"],
            "demand_pct": r(100 * (last["demand"] / prev["demand"] - 1), 1),
            "served_pct": r(100 * (last["served"] / prev["served"] - 1), 1),
            "demand_rise": r(d_rise), "served_rise": r(v_rise),
            "shed_rise": r(s_rise),
            "shed_share_of_rise": r(100 * s_rise / d_rise, 0) if d_rise > 0 else None,
        },
    }


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
    #
    # PGCB publishes the same hours twice: the default view is measured at the
    # sub-station end and leaves demand and supply blank before 2026, while
    # the generation-end view (d_gen=1) fills them back to 2015 but stopped
    # updating in April 2026. Counting only the first would say the archive is
    # empty when the figures are in fact published, one click away.
    by_year = defaultdict(lambda: {"rows": 0, "with_demand": 0,
                                   "with_supply": 0, "nonzero_loadshed": 0,
                                   "genend_rows": 0, "genend_with_demand": 0})
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
    for x in load_genend():
        b = by_year[x["date"][:4]]
        b["genend_rows"] += 1
        if x["demand"] is not None and x["generation"] is not None:
            b["genend_with_demand"] += 1
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
    temp = build_temperature()
    if temp:
        write_json(SITE_DATA / "temperature.json", temp)
        c = temp["compare"]
        print(f"[build] temperature model: {temp['days']:,} days, R2={temp['r2']}; "
              f"hottest bin {temp['response'][-1]['mw']:,.0f} MW above a mild day; "
              f"explains {temp['share_daily']:.0f}% of day-to-day variation")
        print(f"[build]   {c['from']}->{c['to']}: demand {c['rise']:+,.0f} MW "
              f"({c['rise_pct']:+.1f}%), of which weather {c['weather']:+,.0f} MW "
              f"({c['weather_pct']:.1f}%); temperature moved {c['temp_change']:+.2f}C")
    subpeak = build_substation_peak()
    if subpeak:
        write_json(SITE_DATA / "substationpeak.json", subpeak)
        tr = " -> ".join(f"{x['year']} {x['coincidence']}" for x in subpeak["trend"])
        print(f"[build] sub-station peaks: non-coincident "
              f"{subpeak['non_coincident_median']:,.0f} MW against coincident served "
              f"{subpeak['coincident_median']:,.0f}; coincidence "
              f"{subpeak['coincidence']} (summer {tr}); "
              + ", ".join(f"{b['band']} {b['pct']}%" for b in subpeak["bands"]))
    fcplants = build_forecast_plants()
    if fcplants:
        write_json(SITE_DATA / "forecastplants.json", fcplants)
        print(f"[build] forecast vs outturn {fcplants['year']}: "
              f"{fcplants['undelivered_pct']}% of declared evening-peak capacity "
              f"produced nothing; {fcplants['n_plants']} stations failed on at "
              f"least one day of {fcplants['days']}")
    idlefleet = build_idle_fleet()
    if idlefleet:
        write_json(SITE_DATA / "idlefleet.json", idlefleet)
        ys = idlefleet["years"]
        bits = ", ".join(f"{f['fleet']} {f['prev_pct']:.0f}->{f['pct']:.0f}%"
                         for f in idlefleet["fleets"])
        print(f"[build] idle at the evening peak, {idlefleet['window_from']} to "
              f"{idlefleet['window_to']}, {ys[0]} vs {ys[-1]}: {bits}; total "
              f"{idlefleet['total_idle'][ys[0]]:,.0f} -> "
              f"{idlefleet['total_idle'][ys[-1]]:,.0f} MW")
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
    identity = build_identity(erp_hourly, load_genend())
    if identity:
        print(f"[build] demand identity: demand = generation + load-shed x "
              f"{identity['factor']} on {identity['share_within']}% of "
              f"{identity['hours']:,} hours; that factor is the monthly median "
              f"in {identity['months_at_factor']}/{identity['months']} months")
        for reg in identity.get("regimes", []):
            print(f"[build]   factor {reg['factor']} ({reg['loss_pct']}% loss) "
                  f"from {reg['from']} to {reg['to']}, {reg['months']} months")

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
        trend = build_station_trend()
        if trend:
            write_json(SITE_DATA / "stationtrend.json", trend)
            fl = trend["fleet"]
            print(f"[build] station trend {trend['y0']}->{trend['y1']}: "
                  f"{fl['comparable']} comparable stations {fl['a']:,.0f} -> "
                  f"{fl['b']:,.0f} MW ({fl['pct']:+.1f}%), median station "
                  f"{fl['median_pct']:+.1f}%; {fl['rose']} up / {fl['fell']} down; "
                  f"top ten = {fl['top10_gross_pct']}% of gross rises; "
                  f"{fl['new_stations']} new stations add {fl['new_mw']:,.0f} MW")
        theo = build_theoretical(subs)
        if theo:
            write_json(SITE_DATA / "theoretical.json", theo)
            b = theo["busiest"]
            print(f"[build] theoretical ceiling: {theo['ceiling']:,.0f} MW over "
                  f"{theo['stations']} stations; busiest day {b['date']} used "
                  f"{b['util']}% ({b['unused']:,.0f} MW unused); median day "
                  f"{theo['median_util']}%; latest {theo['latest_util']}% with "
                  f"{theo['latest_unused']:,.0f} MW unused against "
                  f"{theo['latest_shed']:,.0f} MW shed")
        pcap = build_plant_capability(theo["ceiling"] if theo else None)
        if pcap:
            write_json(SITE_DATA / "plantcapability.json", pcap)
            se = pcap["season"]
            print(f"[build] plant capability: {pcap['plants']} plants over "
                  f"{pcap['days']} clean days ({pcap['dropped_days']} dropped); "
                  f"proven {pcap['proven']:,.0f} MW = {pcap['proven_pct']}% of "
                  f"{pcap['nameplate']:,.0f} nameplate; best simultaneous "
                  f"{pcap['best_mw']:,.0f} on {pcap['best_date']}; "
                  f"{pcap['never_mw']:,.0f} MW never demonstrated across "
                  f"{pcap['never_plants']} plants; season {se['a']:,.0f} -> "
                  f"{se['b']:,.0f} MW ({se['pct']:+.1f}%), {se['rose']} up / "
                  f"{se['fell']} down")
        suppress = build_suppression(area, subs)
        if suppress:
            write_json(SITE_DATA / "suppression.json", suppress)
            rs = suppress["response"]
            print(f"[build] suppression: {suppress['n']} stations, records sum "
                  f"{suppress['robust_sum']:,.0f} MW ({suppress['spikes_capped']} "
                  f"spikes capped from {suppress['raw_sum']:,.0f}); level gap "
                  f"{suppress['level_gap_pct']}%, {rs['negative']}/{rs['tested']} "
                  f"respond to shedding ({rs['significant']} significantly, "
                  f"{rs['mw']:,.0f} MW), pinned at ceiling "
                  f"{suppress['pinned_median_pct']}% of days -> "
                  f"{suppress['verdict']}")
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
        sp = demand.get("split")
        if sp and sp.get("compare"):
            c = sp["compare"]
            print(f"[build] summer evening peak {c['from']}->{c['to']} "
                  f"({sp['window_from']} to {sp['window_to']}): published demand "
                  f"{c['demand_pct']:+.1f}%, electricity actually delivered "
                  f"{c['served_pct']:+.1f}%; {c['shed_share_of_rise']:.0f}% of the "
                  f"rise is load-shedding counted as demand")
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
        # Each source carries the newest day it actually holds. One "updated"
        # stamp for the whole page would say everything is current whenever
        # the build ran, which is wrong the moment a single publisher stops
        # posting — and they do, without notice.
        "sources": [
            {"id": "pgcb", "name_en": "PGCB / NLDC hourly demand-supply-loadshed",
             "name_bn": "পিজিসিবি / এনএলডিসি ঘণ্টাভিত্তিক চাহিদা-সরবরাহ-লোডশেড",
             "url": "https://erp.powergrid.gov.bd/web/generations/view_demand_supply_loadshed_bn",
             "latest": max((x["date"] for x in hourly), default=None)},
            {"id": "bpdb_archive", "name_en": "BPDB daily generation archive (NLDC PDF reports)",
             "name_bn": "বিপিডিবি দৈনিক উৎপাদন আর্কাইভ (এনএলডিসি পিডিএফ প্রতিবেদন)",
             "url": "https://misc.bpdb.gov.bd/daily-generation-archive",
             "latest": max(bpdb, default=None)},
            {"id": "bpdb_area", "name_en": "BPDB area-wise demand",
             "name_bn": "বিপিডিবি এলাকাভিত্তিক চাহিদা",
             "url": "https://misc.bpdb.gov.bd/area-wise-demand",
             "latest": max(area, default=None)},
            {"id": "pgcb_erp", "name_en": "PGCB daily workbook (NLDC reports, digitised)",
             "name_bn": "পিজিসিবির দৈনিক ওয়ার্কবুক (এনএলডিসি প্রতিবেদন, ডিজিটাইজড)",
             "url": "https://erp.powergrid.gov.bd/",
             "latest": max(erp_summary, default=None)},
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
