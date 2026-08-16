"""Extract country-wise remittance (Annex-III) from Bangladesh Bank reports.

Annex-III carries remittance by source country from FY 2016-17, with an annual
row per fiscal year and monthly rows beneath it. This takes the annual rows,
which is the depth the portal's remittance lens uses.

    python3 parse_bb_country.py pdfs/*.pdf   ->  remittance_country_fy.csv

Why coordinates rather than text layout
---------------------------------------
The country headers are stacked vertically and wrap across three lines
("UNITED / ARAB / EMIRATES (UAE)"), so column boundaries cannot be recovered
from `pdftotext -layout` character positions - clustering merged neighbouring
countries and silently shifted values. This reads real word coordinates with
`pdftotext -bbox-layout` and assigns each header word to the nearest value
column, then resolves the assembled words against a known country list.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NUM = re.compile(r"^-?[\d,]+\.\d+$")
FY = re.compile(r"^(\d{4})-(\d{2})$")
SKIP = {"FY", "FISCAL", "YEAR", "MONTH", "IN", "MILLION", "USD", "III",
        "ANNEX-III", "ANNEXURE-III", "COUNTRY", "WISE", "WORKERS", "INFLOWS", "TO",
        "REMITTANCE", "INFLOW"}
MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december")


def words(pdf: Path, page: int):
    out = subprocess.run(
        ["pdftotext", "-bbox-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True, text=True,
    ).stdout
    if "<word" not in out:
        return []
    root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", out))
    return [
        (float(w.get("xMin")), float(w.get("xMax")), float(w.get("yMin")), (w.text or "").strip())
        for w in root.iter("word") if (w.text or "").strip()
    ]


def n_pages(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def load_countries() -> list[str]:
    f = ROOT.parent / "site" / "data" / "dashboard.json"
    if f.exists():
        return [c["n"] for c in json.loads(f.read_text())["countries"]]
    return []


# Header words that mark a column as something other than a country.
NOT_A_COUNTRY = {"total", "grand"}


def resolve(tokens: list[str], known: list[str]) -> str:
    """Match assembled header words to a known country name by token overlap."""
    got = {t.lower().strip("().,") for t in tokens if t.lower() not in ("of", "the")}
    if not got:
        return ""
    # The final column is the row total, not a country. Counting it doubled
    # every fiscal year exactly; it is used as a check instead.
    if got & NOT_A_COUNTRY:
        return "__TOTAL__"
    best, score = "", 0.0
    for k in known:
        ks = {w.lower().strip("().,") for w in re.split(r"[\s,]+", k)}
        ks -= {"of", "the"}
        if not ks:
            continue
        inter = len(got & ks)
        if not inter:
            continue
        s = inter / max(len(got | ks), 1)
        if s > score:
            best, score = k, s
    if score >= 0.5:
        return best
    return " ".join(t.title() for t in tokens)   # keep BB's own label


def parse(pdf: Path, known: list[str], totals: dict) -> list[dict]:
    rows: list[dict] = []
    for p in range(1, n_pages(pdf) + 1):
        w = words(pdf, p)
        if not w:
            continue
        flat = " ".join(t for *_, t in w)
        if "Country" not in flat or "Annex" not in flat:
            continue

        by_y: dict[float, list] = {}
        for x0, x1, y, t in w:
            by_y.setdefault(round(y, 1), []).append((x0, x1, t))

        # annual rows: a fiscal-year label plus a full set of values
        # The first monthly row of each year repeats the fiscal-year label in
        # the leftmost column, so requiring only "has an FY label" counted July
        # as an annual total and doubled every yearly figure.
        annual_ys = [
            y for y in sorted(by_y)
            if any(FY.match(t) for _, _, t in by_y[y])
            and not any(t.lower() in MONTHS for _, _, t in by_y[y])
            and sum(1 for _, _, t in by_y[y] if NUM.match(t)) >= 5
        ]
        if not annual_ys:
            continue

        first = annual_ys[0]
        cols = sorted(((x0 + x1) / 2, t) for x0, x1, t in by_y[first] if NUM.match(t))
        centres = [c for c, _ in cols]

        # header words above the first data row, assigned to the nearest column
        buckets: dict[float, list] = {}
        for x0, x1, y, t in w:
            if y >= first - 2:
                continue
            if not re.match(r"^[A-Za-z][A-Za-z&'\.\(\),]*$", t) or t.upper() in SKIP:
                continue
            cx = (x0 + x1) / 2
            c = min(centres, key=lambda v: abs(v - cx))
            if abs(c - cx) < 26:
                buckets.setdefault(c, []).append((y, x0, t))

        names = {}
        for c in centres:
            toks = [t for _, _, t in sorted(buckets.get(c, []))]
            names[c] = resolve(toks, known) if toks else ""

        # Newer reports show only the previous fiscal year as an annual column
        # and the current one month by month, so a year is also accepted when
        # all twelve of its months are present.
        month_rows: dict[str, dict[str, dict[int, float]]] = {}
        cur_fy = None
        for y in sorted(by_y):
            line = sorted(by_y[y])
            lab = next((t for _, _, t in line if FY.match(t)), None)
            if lab:
                cur_fy = f"FY{lab}"
            mon = next((t for _, _, t in line if t.lower() in MONTHS), None)
            if not (cur_fy and mon):
                continue
            vals = sorted(((x0 + x1) / 2, t) for x0, x1, t in line if NUM.match(t))
            for cx, v in vals:
                c = min(centres, key=lambda k: abs(k - cx))
                if abs(c - cx) > 14 or not names.get(c) or names[c] == "__TOTAL__":
                    continue
                month_rows.setdefault(cur_fy, {}).setdefault(names[c], {})[
                    list(MONTHS).index(mon.lower())] = float(v.replace(",", ""))
        for fy, per in month_rows.items():
            for cname, mv in per.items():
                if len(mv) == 12:
                    rows.append({"country": cname, "fiscal_year": fy,
                                 "remittance_musd": round(sum(mv.values()), 1),
                                 "source_pdf": pdf.name + " (12 months)"})

        for y in annual_ys:
            line = sorted(by_y[y])
            fy = next((t for _, _, t in line if FY.match(t)), None)
            if not fy:
                continue
            vals = sorted(((x0 + x1) / 2, t) for x0, x1, t in line if NUM.match(t))
            for cx, v in vals:
                c = min(centres, key=lambda k: abs(k - cx))
                if abs(c - cx) > 14 or not names.get(c):
                    continue
                if names[c] == "__TOTAL__":
                    totals.setdefault(f"FY{fy}", float(v.replace(",", "")))
                    continue
                rows.append({
                    "country": names[c],
                    "fiscal_year": f"FY{fy}",
                    "remittance_musd": float(v.replace(",", "")),
                    "source_pdf": pdf.name,
                })
    return rows


def main() -> None:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print(__doc__)
        sys.exit(1)
    known = load_countries()
    totals: dict[str, float] = {}
    all_rows = []
    for p in paths:
        if not p.exists():
            continue
        r = parse(p, known, totals)
        if r:
            print(f"  {p.name:<34} {len(r):>5} country-year rows")
        all_rows += r

    seen = {}
    for r in all_rows:                     # later files win
        seen[(r["country"], r["fiscal_year"])] = r
    out = sorted(seen.values(), key=lambda r: (r["fiscal_year"], -r["remittance_musd"]))
    if not out:
        print("  nothing extracted")
        return
    with open(ROOT / "remittance_country_fy.csv", "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        wtr.writeheader()
        wtr.writerows(out)
    fys = sorted({r["fiscal_year"] for r in out})
    print(f"\n  remittance_country_fy.csv  {len(out):,} rows  "
          f"{len({r['country'] for r in out})} countries  {fys[0]}..{fys[-1]}")
    if totals:
        print("\n  check: summed countries vs the table's own Total column")
        for fy in fys:
            got = sum(r["remittance_musd"] for r in out if r["fiscal_year"] == fy)
            t = totals.get(fy)
            if t:
                print(f"    {fy}  {got:>9,.1f}  vs {t:>9,.1f}   {100*(got-t)/t:+6.2f}%")


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------
# Annexure-II: month-wise national inflows, FY 2014-15 onward. A plain grid,
# unlike the country table, so character layout is enough.

MONTH_ORDER = ["July", "August", "September", "October", "November", "December",
               "January", "February", "March", "April", "May", "June"]


def parse_national_monthly(pdf: Path) -> dict[str, dict[int, float]]:
    """Fiscal year -> {calendar month number: million USD}."""
    out: dict[str, dict[int, float]] = {}
    for p in range(1, n_pages(pdf) + 1):
        txt = subprocess.run(
            ["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"],
            capture_output=True, text=True).stdout
        titled = "Month-wise" in txt or "Month wise" in txt
        # The Jan-Jun half sits on a continuation page with no title, only the
        # month header and fiscal-year rows - the same trap as the district
        # table, and it cost half the series.
        cont = (sum(1 for m in MONTH_ORDER if m in txt) >= 3
                and (re.search(r"^\s*\d{4}-\d{2,4}\s+[\d,]+\.\d", txt, re.M)
                     or re.search(r"[\d,]+\.\d+\s+\d{4}-\d{2,4}\s*$", txt, re.M)))
        if not (titled or cont):
            continue
        header = next((l for l in txt.splitlines()
                       if sum(1 for m in MONTH_ORDER if m in l) >= 3), "")
        cols = [m for m in MONTH_ORDER if m in header]
        cols.sort(key=lambda m: header.index(m))
        if not cols:
            continue
        for line in txt.splitlines():
            # July-December rows lead with the fiscal year; the January-June
            # half puts it at the END, after a Total column. Handling only the
            # first layout silently halved the series.
            m = re.match(r"^\s*(\d{4})-(\d{4}|\d{2})\s+(.*)$", line)
            if m:
                body, fy = m.group(3), f"FY{m.group(1)}-{m.group(2)[-2:]}"
            else:
                m2 = re.match(r"^\s*(.*?)\s+(\d{4})-(\d{4}|\d{2})\s*$", line)
                if not m2:
                    continue
                body, fy = m2.group(1), f"FY{m2.group(2)}-{m2.group(3)[-2:]}"
            vals = [float(v.replace(",", "")) for v in re.findall(r"[\d,]+\.\d+", body)]
            if len(vals) < len(cols):
                continue
            for i, name in enumerate(cols):
                if i < len(vals):
                    out.setdefault(fy, {})[MONTH_ORDER.index(name)] = vals[i]
    return out


if __name__ == "__main__" and "--national" in sys.argv:
    import io
    pdfs = [Path(a) for a in sys.argv[1:] if a.endswith(".pdf")]
    merged: dict[str, dict[int, float]] = {}
    for f in pdfs:
        for fy, mv in parse_national_monthly(f).items():
            merged.setdefault(fy, {}).update(mv)
    rows = []
    for fy in sorted(merged):
        for oi, v in sorted(merged[fy].items()):
            name = MONTH_ORDER[oi]
            mn = ["January","February","March","April","May","June","July",
                  "August","September","October","November","December"].index(name) + 1
            yr = int(fy[2:6]) + (0 if mn >= 7 else 1)
            rows.append({"fiscal_year": fy, "year": yr, "month": mn,
                         "date": f"{yr}-{mn:02d}", "remittance_musd": v})
    rows.sort(key=lambda r: r["date"])
    with open(ROOT / "remittance_national_monthly.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  remittance_national_monthly.csv  {len(rows)} rows  "
          f"{rows[0]['date']}..{rows[-1]['date']}  {len(merged)} fiscal years")
