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
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from common import (FUELS, RAW, SITE_DATA, ZONES, ZONE_BN, num, read_csv,
                    read_json, write_json)

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
        out.append({
            "month": m,
            "days": len(ds),
            "peak_demand": max(peaks) if peaks else None,
            "mean_peak_demand": r(sum(peaks) / len(peaks)) if peaks else None,
            "max_loadshed": max(sheds) if sheds else None,
            "energy_shed_mwh": r(sum(energy)) if energy else None,
            "mean_hours_shed": r(sum(hrs) / len(ds)) if ds else None,
        })
    return out


# ------------------------------------------------------------- BPDB daily

def load_bpdb():
    recs = {}
    for f in sorted(DAILYDIR.glob("*.json")):
        d = read_json(f)
        if not d or d.get("failed") or not d.get("date"):
            continue
        # keep the richest record if two listings resolve to the same report date
        cur = recs.get(d["date"])
        if cur is None or len(json.dumps(d)) > len(json.dumps(cur)):
            recs[d["date"]] = d
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


def build_plants(bpdb, geo):
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
        plants.append({
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


def build_substations(bpdb, geo):
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
        items.append({
            "name": s["name"], "load_mw": s["load_mw"], "hour": s.get("hour"),
            "lat": lat, "lon": lon, "geo": src,
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


# -------------------------------------------------------------- integrity

def build_integrity(hourly, area, bpdb, daily):
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
        "outliers": {
            "threshold_mw": PLAUSIBLE_MAX_MW,
            "count": len(OUTLIERS),
            "examples": sorted(OUTLIERS, key=lambda o: -o["value"])[:10],
        },
        "demand_identity": {
            "matches": ident, "mismatches": miss,
            "rate": r(ident / (ident + miss), 4) if (ident + miss) else None,
        },
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

    osm_plants = read_json(GEO / "plants.json", []) or []
    osm_subs = read_json(GEO / "substations.json", []) or []
    osm_places = read_json(GEO / "places.json", []) or []
    plants = build_plants(bpdb, Geocoder([("osm", osm_plants),
                                          ("place", osm_places)]))
    subs = build_substations(bpdb, Geocoder([("osm", osm_subs),
                                             ("place", osm_places)]))
    if plants:
        write_json(SITE_DATA / "plants.json", plants)
        print(f"[build] plants {len(plants['plants'])} geo={plants['geo_counts']}")
    if subs:
        write_json(SITE_DATA / "substations.json", subs)
        print(f"[build] substations {len(subs['substations'])} geo={subs['geo_counts']}")

    write_json(SITE_DATA / "reasons.json", build_reason_history(bpdb))
    write_json(SITE_DATA / "fuelmix.json", {
        "fuels": FUELS,
        "daily": build_fuelmix(bpdb),
        "zone_latest": build_zone_fuel_latest(bpdb),
    })
    write_json(SITE_DATA / "zones.json", build_zones(area, bpdb))

    integrity = build_integrity(hourly, area, bpdb, daily)
    write_json(SITE_DATA / "integrity.json", integrity)
    write_json(SITE_DATA / "latest.json", build_latest(hourly, daily, bpdb, area))

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
