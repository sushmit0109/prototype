"""Download and parse the NLDC daily PDF reports listed in the archive index.

The archive's page_1 / page_2 / page_3 / summary slots do NOT hold a fixed form:
which NLDC form lands in which slot varies by day. So every PDF is downloaded,
identified by its own form title, and routed to the matching parser:

  QF-LDC-08 Sheet-1  "System Summary Report"
      peak generation & demand, energy generated / demanded / unserved,
      gas supplied, production cost, zone x fuel energy matrix,
      zone-wise load-shed & demand at evening peak, interconnector flows
  QF-LDC-08 Sheet-2  "Evening peak generation and day long energy data of
                      power stations" -- per-plant capacity, output, and the
      free-text Remarks that say *why* a plant produced nothing
  QF-LDC-09          "Maximum load served by different grid sub-stations"
      ~200 named grid substations with peak load MW and the hour it occurred

The report's own "Date :" line is authoritative; the archive listing date is
the publication date and is normally one day later.

  python parse_bpdb_pdf.py --recent 30
  python parse_bpdb_pdf.py --all
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

import pdfplumber

from common import (FUELS, RAW, get, halve_runs, is_doubled, num, read_json,
                    session, undouble, write_json, zone_key)

# A miss newer than this is treated as retryable rather than permanent.
RETRY_WINDOW_DAYS = 10

INDEX = RAW / "bpdb" / "archive_index.json"
DAILY = RAW / "bpdb" / "daily"

# --------------------------------------------------------------- sheet 1

SCALARS = [
    ("day_peak_generation",     r"Day\s+Peak\s+Generation\s+([\d.,]+)"),
    ("day_peak_demand",         r"Day\s+Peak\s+Demand\s+([\d.,]+)"),
    ("evening_peak_generation", r"Evening\s+Peak\s+Generation\s+([\d.,]+)"),
    ("evening_peak_demand",     r"Evening\s+Peak\s+Demand\s+([\d.,]+)"),
    ("min_generation",          r"Minimum\s+Generation\s+of\s+the\s+Day\s+([\d.,]+)"),
    ("max_generation",          r"Maximum\s+Generation\s+of\s+the\s+Day\s+([\d.,]+)"),
    ("energy_generated",        r"Energy\s+Generated\s+([\d.,]+)"),
    # BPDB's own typo "Unserverd" appears in most editions
    ("energy_unserved",         r"Energy\s+Unserve?r?d\s+([\d.,]+)"),
    ("energy_demand",           r"Energy\s+Demand\s+([\d.,]+)"),
    ("max_temperature",         r"Maximum\s+Temperature\s+([\d.,]+)"),
    ("gas_supplied",            r"Total\s+Gas\s+Supplied\s+([\d.,]+)"),
    ("cost_per_kwh",            r"Production\s+Cost\s+per\s+KWHr\.?\s+([\d.,]+)"),
]

PEAK_HOURS = [
    ("day_peak_hour",     r"Day\s+Peak\s+Generation\s+[\d.,]+\s*MW\s+(\d{1,2}):"),
    ("evening_peak_hour", r"Evening\s+Peak\s+Generation\s+[\d.,]+\s*MW\s+(\d{1,2}):"),
]

FUEL_COST_RE = re.compile(
    r"\b(Gas|Coal|HFO|HSD|Hydro|Solar|Import|Wind)\s+([\d.,]+)", re.I)


def parse_sheet1(text: str) -> dict:
    out: dict = {}

    m = re.search(r"Date\s*:\s*(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if m:
        dd, mm, yyyy = m.groups()
        out["date"] = f"{yyyy}-{int(mm):02d}-{int(dd):02d}"

    for key, pat in SCALARS:
        mm_ = re.search(pat, text, re.I)
        if mm_:
            out[key] = num(mm_.group(1))
    for key, pat in PEAK_HOURS:
        mm_ = re.search(pat, text, re.I)
        if mm_:
            out[key] = int(mm_.group(1))

    # ---- zone x fuel energy matrix (MKWHr) -----------------------------
    zf = {}
    for line in text.splitlines():
        zm = re.match(r"\s*([A-Za-z]+)\s+Zone\s+(.+)$", line)
        if not zm:
            continue
        z = zone_key(zm.group(1))
        if not z:
            continue
        vals = [num(v) for v in re.findall(r"-?[\d.,]+", zm.group(2))]
        # 8 fuels + total; tolerate editions that omit trailing columns
        if len(vals) >= 8:
            zf[z] = {f: (vals[i] if i < len(vals) else None)
                     for i, f in enumerate(FUELS[:4] + ["hydro", "solar", "import", "wind"])}
            # column order on the sheet is Gas Coal HFO HSD Hydro Solar Import Wind
            order = ["gas", "coal", "hfo", "hsd", "hydro", "solar", "import", "wind"]
            zf[z] = {f: vals[i] for i, f in enumerate(order) if i < len(vals)}
            zf[z]["total"] = vals[8] if len(vals) > 8 else sum(
                v for v in vals[:8] if v is not None)
    if zf:
        out["zone_fuel_energy"] = zf

    # ---- production cost by fuel ---------------------------------------
    cm = re.search(r"Production\s+Cost\s*\(Tk\.?\)(.*?)(?:Total\s*:|$)",
                   text, re.I | re.S)
    if cm:
        costs = {}
        for fuel, val in FUEL_COST_RE.findall(cm.group(1)):
            v = num(val)
            if v is not None:
                costs[fuel.lower()] = v
        if costs:
            out["fuel_cost_tk"] = costs
    tm = re.search(r"Total\s*:\s*([\d,]+)\s*Tk", text, re.I)
    if tm:
        out["total_cost_tk"] = num(tm.group(1))

    # ---- zone-wise load-shed & demand at evening peak -------------------
    lm = re.search(
        r"Zone-?wise\s+Load-?shed\s+and\s+Demand.*?(?:Zone\s+Load-?Shed\s+Demand)(.*?)"
        r"(?:Total\s+[\d.,]+\s+[\d.,]+|Status\s+of|$)", text, re.I | re.S)
    if lm:
        zl = {}
        for line in lm.group(1).splitlines():
            pm = re.match(r"\s*([A-Za-z]+)\s+([\d.,]+)\s+([\d.,]+)\s*$", line)
            if not pm:
                continue
            z = zone_key(pm.group(1))
            if z:
                zl[z] = {"loadshed": num(pm.group(2)), "demand": num(pm.group(3))}
        if zl:
            out["zone_peak"] = zl
    tl = re.search(r"Zone-?wise\s+Load-?shed.*?Total\s+([\d.,]+)\s+([\d.,]+)",
                   text, re.I | re.S)
    if tl:
        out["peak_loadshed_total"] = num(tl.group(1))
        out["peak_demand_total"] = num(tl.group(2))

    # ---- cross-border imports ------------------------------------------
    im = re.search(r"Total\s+Import\s+through\s+C/B\s+Interconnector\s*:?\s*"
                   r"MKWHr\s*:?\s*([\d.,]+)", text, re.I)
    if im:
        out["import_energy"] = num(im.group(1))

    return out


# --------------------------------------------------------------- sheet 2

SKIP_ROW = re.compile(
    r"^(sl\.?|name of the power|unit no|area total|eastern grid|western grid|"
    r"national grid|total|grand total)", re.I)


PLANT_HEADER = re.compile(r"name\s+of\s+the\s+power\s+station", re.I)


def parse_sheet2(pdf) -> list:
    """Per-power-station rows across every page of sheet 2.

    Only tables that actually carry the power-station header are read; the same
    PDF may also contain unrelated tables.
    """
    plants = []
    zone_totals = {}
    pending = []  # rows seen since the last "<Area> Area Total" line
    for page in pdf.pages:
        for table in page.extract_tables() or []:
            flat = " ".join((c or "") for c in (table[0] if table else []))
            if not PLANT_HEADER.search(flat):
                continue
            for row in table:
                cells = [(c or "").replace("\n", " ").strip() for c in row]
                if len(cells) < 7:
                    continue
                # If this row's text layer was drawn twice, every field in it is
                # doubled — collapse the whole row before reading any number.
                # Doubling does not always hit every cell of a row — some rows
                # keep a clean station name while units, capacity and remarks
                # are doubled. So any cell that is detectably doubled condemns
                # the whole row, and every cell is then halved: a numeric cell
                # can never be judged on its own, since a genuine "22" and a
                # doubled "2" are the same string.
                if any(is_doubled(c) for c in cells):
                    cells = [halve_runs(c) for c in cells]
                name = cells[1].strip()
                # Subtotal rows carry their label in the Sl. column, not the
                # name column, so look at both.
                label = cells[0].strip() or name

                # "<Area> Area Total" closes the block of plants above it, so the
                # zone is only known once the subtotal row is reached.
                am = re.match(r"(.+?)\s+Area\s+Total", label, re.I)
                if am:
                    z = zone_key(am.group(1))
                    for p in pending:
                        p["zone"] = z
                    plants.extend(pending)
                    pending = []
                    if z:
                        zone_totals[z] = {
                            "capacity_mw": num(cells[4]),
                            "peak_mw": num(cells[5]),
                            "energy_kwh": num(cells[6]),
                        }
                    continue
                if re.search(r"Grid\s+Total", label, re.I):
                    plants.extend(pending)
                    pending = []
                    continue
                if not name or SKIP_ROW.match(name):
                    continue

                installed = num(cells[4])
                peak = num(cells[5])
                energy = num(cells[6])
                if installed is None and peak is None and energy is None:
                    continue

                pending.append({
                    "name": " ".join(name.split()),
                    "producer": " ".join(cells[2].split()) or None,
                    "units": " ".join(cells[3].split()) or None,
                    "capacity_mw": installed,
                    "peak_mw": peak,
                    "energy_kwh": energy,
                    "remarks": " ".join(cells[7].split()) if len(cells) > 7 else "",
                    "zone": None,
                })
    plants.extend(pending)  # trailing rows with no subtotal row after them
    return plants, zone_totals


# ------------------------------------------- BPDB daily generation report
#
# A third form, published in the archive's "summary" slot: BPDB's own Daily
# Electricity Generation Report. It carries three things no other sheet does —
# the shortfall attributed to a cause in MW, a next-day forecast including the
# load-shedding BPDB expects, and fuel cost alongside energy by fuel, which
# together give a cost per unit for each fuel. Its zone table is measured at
# the sub-station end and prints Demand, Supply and Load Shed, which is what
# establishes that "Demand" in these reports already includes the shed portion.

ZONE_ROW = re.compile(
    r"\b([A-Z][a-z]+)\s+(\d[\d,]*)\s+(\d[\d,]*)\s+(\d[\d,]*)\b")

CAUSES = [
    ("gas_lf",      r"Gas\s*/\s*LF\s+limitation\s*:?\s*([\d.,]+)\s*MW"),
    ("kaptai",      r"Low\s+water\s+level\s+in\s+Kaptai[^:]*:?\s*([\d.,]+)\s*MW"),
    ("maintenance", r"Plants?\s+under\s+shut\s*down\s*/?\s*maintenance\s*:?\s*([\d.,]+)\s*MW"),
    ("coal",        r"Coal\s+supply\s+Limitation\s*:?\s*([\d.,]+)\s*MW"),
]
ENERGY = [("gas", r"By\s+Gas\s*=\s*([\d.,]+)"), ("oil", r"By\s+Oil\s*=\s*([\d.,]+)"),
          ("coal", r"By\s+Coal\s*=\s*([\d.,]+)"),
          ("hydro_wind", r"By\s+Hydro\s*&\s*Wind\s*=\s*([\d.,]+)"),
          ("solar", r"By\s+Solar\s*=\s*([\d.,]+)"),
          ("import", r"Imported\s*=\s*([\d.,]+)")]
COST = [("gas", r"\(a\)\s*Gas\s*=\s*([\d.,]+)\s*Taka"),
        ("oil", r"\(b\)\s*Oil\s*=\s*([\d.,]+)\s*Taka"),
        ("coal", r"\(c\)\s*Coal\s*=\s*([\d.,]+)\s*Taka"),
        ("renewable", r"\(d\)\s*Renewable\s*=?\s*([\d.,]+)\s*Taka"),
        ("import", r"\(e\)\s*Import\s*=\s*([\d.,]+)\s*Taka")]
PEAKS = [("eve_peak_demand_gen_end", r"Max\.?\s*Demand\s+at\s+eve\.?\s*peak[^:]*:\s*([\d.,]+)\s*MW"),
         ("eve_peak_generation", r"Evening-?peak\s+Generation[^:]*:\s*([\d.,]+)\s*MW"),
         ("highest_generation", r"Highest\s+Generation[^:]*:\s*([\d.,]+)\s*MW"),
         ("day_peak_demand", r"Day\s+Peak\s+Demand\s*:\s*([\d.,]+)\s*MW"),
         ("day_peak_generation", r"Day-?peak\s+Generation[^:]*:\s*([\d.,]+)\s*MW"),
         ("min_generation", r"Minimum\s+Generation[^:]*:\s*([\d.,]+)\s*MW")]
FORECAST = [("f_day_peak_demand", r"Probable\s+Maximum\s+Demand\s+at\s+Day\s+Peak\s*:\s*([\d.,]+)"),
            ("f_eve_peak_demand", r"Probable\s+Maximum\s+Demand\s+at\s+Evening\s+Peak\s*:\s*([\d.,]+)"),
            ("f_eve_peak_generation", r"Probable\s+Maximum\s+Generation\s+at\s+Evening\s+Peak\s*:\s*([\d.,]+)"),
            ("f_loadshed", r"Probable\s+Load\s*Shed\s*:\s*([\d.,]+)"),
            ("f_energy", r"Probable\s+Total\s+Energy\s+Generation\s*:\s*([\d.,]+)"),
            ("f_max_temp", r"Probable\s+Maximum\s+Temperature\s*:\s*([\d.,]+)")]


def parse_genreport(text: str) -> dict:
    """Parse BPDB's Daily Electricity Generation Report.

    The date needs care. Through 2026 the "Actual data of DD.MM.YY" line
    carries a stale year — a report headed "Date : 10-08-2026" describes its
    previous day as "09.08.25". Left alone, a year of 2026 reports lands on
    2025 dates and overwrites the real ones. The four-digit report date is
    reliable, so the day and month come from the actual-data line and the year
    is taken from the report, with a sanity check against the report date.
    """
    out = {}
    rep = re.search(r"Date\s*:\s*(\d{1,2})-(\d{1,2})-(\d{4})", text)
    report_date = None
    if rep:
        rd, rm, ry = (int(x) for x in rep.groups())
        try:
            report_date = date(ry, rm, rd)
        except ValueError:
            report_date = None

    m = re.search(r"Actual\s+data\s+of\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", text)
    data_date = None
    if m and report_date:
        dd, mm = int(m.group(1)), int(m.group(2))
        # a December reading reported in January belongs to the year before
        year = report_date.year - 1 if mm > report_date.month else report_date.year
        try:
            cand = date(year, mm, dd)
        except ValueError:
            cand = None
        if cand and 0 <= (report_date - cand).days <= 5:
            data_date = cand
    if data_date is None and report_date:
        data_date = report_date - timedelta(days=1)   # the report's own convention
    elif data_date is None and m:
        dd, mm, yy = m.groups()
        yr = int(yy) + 2000 if len(yy) == 2 else int(yy)
        try:
            data_date = date(yr, int(mm), int(dd))
        except ValueError:
            data_date = None
    if data_date:
        out["data_date"] = data_date.isoformat()
    fm = re.search(r"Forecast\s+of\s*(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if fm:
        dd, mm, yy = fm.groups()
        out["forecast_date"] = f"{yy}-{int(mm):02d}-{int(dd):02d}"

    for key, pat in CAUSES + PEAKS + FORECAST:
        r_ = re.search(pat, text, re.I)
        if r_:
            out[key] = num(r_.group(1))
    e = {}
    for key, pat in ENERGY:
        r_ = re.search(pat, text, re.I)
        if r_:
            e[key] = num(r_.group(1))
    if e:
        out["energy_by_fuel"] = e
    c = {}
    for key, pat in COST:
        r_ = re.search(pat, text, re.I)
        if r_:
            c[key] = num(r_.group(1))
    if c:
        out["cost_by_fuel"] = c
    r_ = re.search(r"Total\s*Energy\s*\(Generation\s*\+\s*Import\)\s*:\s*([\d.,]+)", text, re.I)
    if r_:
        out["total_energy"] = num(r_.group(1))
    r_ = re.search(r"Total\s+Gas\s+Supplied\s*:\s*([\d.,]+)", text, re.I)
    if r_:
        out["gas_supplied"] = num(r_.group(1))

    zt = {}
    i = text.find("Zone wise Demand")
    if i > 0:
        for line in text[i:i + 1200].splitlines():
            for zn, d_, s_, l_ in ZONE_ROW.findall(line):
                z = zone_key(zn)
                if z:
                    zt[z] = {"demand": num(d_), "supply": num(s_), "loadshed": num(l_)}
    if zt:
        out["zone_substation"] = zt
    return out


# --------------------------------------------------------------- QF-LDC-09

SUBSTATION_HEADER = re.compile(r"sub-?station", re.I)


def parse_substations(pdf) -> list:
    """Grid substations with their maximum load served and the hour it peaked.

    The sheet packs three (Sl, Sub-station, Load, Time) column groups across the
    page width, so each row is unpacked into up to three records.
    """
    out = []
    for page in pdf.pages:
        for table in page.extract_tables() or []:
            if not table:
                continue
            header = [(c or "").strip().lower() for c in table[0]]
            if not any(SUBSTATION_HEADER.search(h) for h in header):
                continue
            # locate each repeating "Sub-station" column
            starts = [i for i, h in enumerate(header) if SUBSTATION_HEADER.search(h)]
            for row in table[1:]:
                cells = [(c or "").replace("\n", " ").strip() for c in row]
                if any(is_doubled(c) for c in cells if len(c) > 6):
                    cells = [halve_runs(c) for c in cells]
                for s in starts:
                    if s + 2 >= len(cells):
                        continue
                    name = " ".join(cells[s].split())
                    load = num(cells[s + 1])
                    if not name or load is None:
                        continue
                    t = cells[s + 2].strip()
                    tm = re.match(r"(\d{1,2}):(\d{2})", t)
                    out.append({
                        "name": name,
                        "load_mw": load,
                        "hour": int(tm.group(1)) % 24 if tm else None,
                    })
    return out


def parse_zone_totals(text: str) -> dict:
    """'Zone Total Scenario at Evening Peak Hour' block on QF-LDC-09."""
    out = {}
    for m in re.finditer(r"(?:i+v?|v?i{0,3})\)\s*([A-Za-z]+)\s+area\s+([\d.,]+)\s*MW",
                         text, re.I):
        z = zone_key(m.group(1))
        if z:
            out[z] = num(m.group(2))
    return out


# --------------------------------------------------------------- driver

FORMS = {
    "summary":     re.compile(r"System\s+Summary\s+Report", re.I),
    "plants":      re.compile(r"EVENING\s+PEAK\s+GENERATION\s+AND\s+DAY\s+LONG", re.I),
    "substations": re.compile(r"MAXIMUM\s+LOAD\s+SERVED\s+BY\s+DIFFERENT\s+GRID", re.I),
    "genreport": re.compile(r"DAILY\s+ELECTRICITY\s+GENERATION\s+REPORT", re.I),
}


def classify(text: str):
    for kind, pat in FORMS.items():
        if pat.search(text or ""):
            return kind
    return None


def pdf_text(sess, url: str):
    r = get(sess, url, tries=3, timeout=90)
    if not r or not r.content[:5].startswith(b"%PDF"):
        return None, None
    try:
        pdf = pdfplumber.open(io.BytesIO(r.content))
    except Exception:  # noqa: BLE001 - corrupt upstream file
        return None, None
    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    # a wholly doubled page shows up line by line
    lines = text.split("\n")
    if lines and sum(1 for ln in lines if is_doubled(ln.strip())) > len(lines) / 3:
        text = "\n".join(undouble(ln) for ln in lines)
    return pdf, text


DATE_RE = re.compile(r"Date\s*:\s*(\d{1,2})-(\d{1,2})-(\d{4})")


def process(sess, listing_date: str, links: dict):
    rec = {"listing_date": listing_date, "sources": {}}
    seen_urls = set()

    for slot in ("page_1", "page_2", "page_3", "summary"):
        url = links.get(slot)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        pdf, text = pdf_text(sess, url)
        if not pdf:
            continue
        with pdf:
            kind = classify(text)
            if kind and kind not in rec["sources"]:
                dm = DATE_RE.search(text or "")
                if dm:
                    dd, mm, yyyy = dm.groups()
                    rec.setdefault("date", f"{yyyy}-{int(mm):02d}-{int(dd):02d}")

                if kind == "summary":
                    rec.update(parse_sheet1(text))
                    rec["sources"]["summary"] = url
                elif kind == "plants":
                    plants, zone_totals = parse_sheet2(pdf)
                    if plants:
                        rec["plants"] = plants
                        rec["sources"]["plants"] = url
                    if zone_totals:
                        rec["zone_generation"] = zone_totals
                elif kind == "genreport":
                    g = parse_genreport(text)
                    if g:
                        rec["genreport"] = g
                        rec["sources"]["genreport"] = url
                        rec.setdefault("date", g.get("data_date"))
                elif kind == "substations":
                    subs = parse_substations(pdf)
                    if subs:
                        rec["substations"] = subs
                        rec["sources"]["substations"] = url
                    zt = parse_zone_totals(text)
                    if zt:
                        rec["zone_peak_load"] = zt

    if "date" not in rec:
        return None
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--recent", type=int, default=14)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    index = read_json(INDEX, {}) or {}
    if not index:
        print("[bpdb-pdf] no archive index yet — run scrape_bpdb_index.py first")
        return 1

    dates = sorted(index, reverse=True)
    if not args.all:
        dates = dates[: args.recent]

    DAILY.mkdir(parents=True, exist_ok=True)
    todo = [d for d in dates
            if args.force or not (DAILY / f"{d}.json").exists()]
    print(f"[bpdb-pdf] {len(todo)} of {len(dates)} listing dates to parse")
    if not todo:
        return 0

    sess = session()
    ok = fail = 0

    def work(d):
        try:
            return d, process(sess, d, index[d])
        except Exception as e:  # noqa: BLE001 - keep the batch alive
            print(f"  ! {d}: {type(e).__name__}: {e}")
            return d, None

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (d, rec) in enumerate(ex.map(work, todo), 1):
            if rec:
                write_json(DAILY / f"{d}.json", rec)
                ok += 1
            else:
                # Remember a miss so --all does not retry it forever — but only
                # once the date is old enough that the file is genuinely absent
                # upstream. A recent date is far more likely to be a transient
                # network error, or a report not published yet, so leave it
                # unmarked and let the next run try again.
                age = (date.today() - date.fromisoformat(d)).days
                if age > RETRY_WINDOW_DAYS:
                    write_json(DAILY / f"{d}.json", {"listing_date": d, "failed": True})
                fail += 1
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} ok={ok} fail={fail}", flush=True)

    print(f"[bpdb-pdf] done ok={ok} fail={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
