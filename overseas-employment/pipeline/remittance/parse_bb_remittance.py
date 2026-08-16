"""Extract district-wise remittance tables from Bangladesh Bank PDFs.

Bangladesh Bank publishes district-level workers' remittance, but never as a
downloadable series - only as tables inside PDFs, in two shapes:

  monthly    "Division and District wise Workers' Remittance Inflows" appears in
             every Monthly Report on Workers' Remittance Inflows. Each report
             shows the last ~6 months of the current fiscal year plus the FY
             total, so the December and June reports together cover a full FY.

  annual     "Annex-IV" in the same reports carries district x fiscal year from
             FY 2017-18 onward, which is the only long history that exists.

  snapshot   econdata/remittance/districtwise_remittance.pdf accumulates the
             current FY month by month and is overwritten, so historical
             versions exist only in the Wayback Machine.

    python3 parse_bb_remittance.py pdfs/*.pdf

Writes remittance_monthly.csv and remittance_annual_fy.csv next to this script.

Requires poppler's pdftotext on PATH.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}
# The snapshot table abbreviates: "July Aug Sep Oct Nov Dec".
ABBR = {m[:3].lower(): m for m in MONTHS} | {"sept": "September"}
MONTH_RE = r"\b(" + "|".join(MONTHS + [m[:3] for m in MONTHS] + ["Sept"]) + r")\b"

# Bangladesh Bank's district spellings differ from BMET's in a handful of
# places. Normalise to the BMET form so the two datasets join.
BB_TO_BMET = {
    "barishal": "Barisal",
    "bogura": "Bogura",
    "brahmanbaria": "Brahmanbaria",
    "chapai nawabganj": "Chapainawabganj",
    "chattogram": "Chattogram",
    "cox's bazar": "Coxsbazar",
    "coxs bazar": "Coxsbazar",
    "cumilla": "Comilla",
    "jashore": "Jashore",
    "moulvi bazar": "Moulvibazar",
    "moulvibazar": "Moulvibazar",
    "maulvi bazar": "Moulvibazar",
    "netrokona": "Netrokona",
    "netrakona": "Netrokona",
    "gazipur": "Gazipur",
    "jhalokati": "Jhalokati",
    "khagrachari": "Khagrachhari",
    "sunamganj": "Sunamganj",
    "shariatpur": "Shariatpur",
    # Bangladesh Bank's own typo, consistent across every report.
    "gaibandah": "Gaibandha",
    "gaibandha": "Gaibandha",
    # other spellings seen across report vintages
    "nawabganj": "Chapainawabganj",
    "chapai nababganj": "Chapainawabganj",
    "jessore": "Jashore",
    "bogra": "Bogura",
    "comilla": "Comilla",
    "barisal": "Barisal",
    "khagrachhari": "Khagrachhari",
    "coxsbazar": "Coxsbazar",
    "cox s bazar": "Coxsbazar",
}


# The 64 real districts, from the BMET reference. Whitelisting against them is
# what keeps Annexure-I's national series and the division subtotals out of the
# district tables - the same structural test that filtered BMET's junk rows.
CANON = {}


def load_canon() -> set:
    global CANON
    if CANON:
        return set(CANON.values())
    names = json.loads((ROOT / "districts_canonical.json").read_text())
    CANON = {n.lower(): n for n in names}
    for bb, bmet in BB_TO_BMET.items():
        CANON[bb] = bmet
    return set(CANON.values())


def norm_district(s: str) -> str:
    load_canon()
    k = re.sub(r"[^a-z' ]", "", re.sub(r"\s+", " ", s).strip().lower()).strip()
    return CANON.get(k, "")   # empty means "not one of the 64 districts"


def pdf_pages(path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    m = re.search(r"Pages:\s+(\d+)", out)
    return int(m.group(1)) if m else 0


def page_text(path: Path, page: int) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
        capture_output=True, text=True,
    ).stdout


NUM = re.compile(r"-?[\d,]+\.\d+|-?[\d,]+")


def parse_row(line: str):
    """Split a table line into a label and its numeric cells."""
    nums = NUM.findall(line)
    if not nums:
        return None, []
    first = line.index(nums[0])
    label = line[:first].strip()
    vals = []
    for n in nums:
        try:
            vals.append(float(n.replace(",", "")))
        except ValueError:
            pass
    return label, vals


def parse_monthly(path: Path) -> list[dict]:
    """District x month rows from a 'Division and District wise' table."""
    rows: list[dict] = []
    for p in range(1, pdf_pages(path) + 1):
        txt = page_text(path, p)
        if re.search(r"Annex", txt, re.I):
            continue   # the annual annexure is handled separately
        # Its continuation page carries no "Annex" marker but is still the
        # fiscal-year table; three or more FY tokens gives it away.
        if len(re.findall(r"FY\s*\d{4}-\d{2}", txt)) >= 3:
            continue
        titled = bool(re.search(r"District[-\s]wise\s+(Workers|Wage)", txt, re.I))
        # A long table continues onto the next page without repeating its
        # title, carrying only the Division/District header. Requiring the
        # title dropped those pages - and with them 24 of the 64 districts.
        continued = bool(re.search(r"^\s*Division\s+District", txt, re.M)) or (
            "District" in txt and sum(1 for m in MONTHS if re.search(rf"\b{m}\b", txt)) >= 2
        )
        if not (titled or continued):
            continue
        fy = re.search(r"FY\s*(\d{4})-(\d{2,4})", txt)
        if not fy:
            continue
        fy_label = f"FY{fy.group(1)}-{fy.group(2)[-2:]}"
        start_year = int(fy.group(1))

        # the header lists the month columns in order
        # The header ends with a cumulative range column ("July-October",
        # "July-June"). Strip ranges before reading the month names, or that
        # column is mistaken for a month and a whole fiscal year's total lands
        # on a single month.
        def months_of(line: str):
            cleaned = re.sub(r"\b[A-Z][a-z]+\s*[-–]\s*[A-Z][a-z]+\b", " ", line)
            out = []
            for m in re.finditer(MONTH_RE, cleaned):
                tok = m.group(1)
                out.append((m.start(), ABBR.get(tok.lower(), tok)))
            seen, ordered = set(), []
            for _, name in sorted(out):
                if name not in seen:
                    seen.add(name)
                    ordered.append(name)
            return ordered, cleaned

        header_months, n_extra = [], 0
        for line in txt.splitlines():
            got, cleaned = months_of(line)
            if len(got) >= 2:
                header_months = got
                # how many cumulative columns follow the months
                n_extra = len(re.findall(r"\b[A-Z][a-z]+\s*[-–]\s*[A-Z][a-z]+\b", line))
                break
        if not header_months:
            for line in txt.splitlines():
                got, _ = months_of(line)
                if len(got) == 1:
                    header_months = got
                    n_extra = len(re.findall(r"\b[A-Z][a-z]+\s*[-–]\s*[A-Z][a-z]+\b", line))
                    break
        if not header_months:
            continue
        n_month_cols = len(header_months)

        for line in txt.splitlines():
            label, vals = parse_row(line)
            if not label or not vals:
                continue
            low = label.lower()
            if "total" in low or "division" in low or "district" in low:
                continue
            d = norm_district(label)
            if not d:
                # a division name may sit in the same cell as the district
                d = norm_district(label.split("  ")[-1])
            if not d:
                continue
            # a row must supply exactly the month columns (plus any cumulative
            # ones); anything else is a wrapped or mis-read line
            if len(vals) < n_month_cols + n_extra:
                continue
            # Take the month block relative to the end of the row. Some layouts
            # lead with annual columns; counting from the left put a fiscal-year
            # figure into a month.
            take = vals[len(vals) - (n_month_cols + n_extra):] if n_extra else vals[len(vals) - n_month_cols:]
            for i, m in enumerate(header_months):
                if i >= len(take):
                    break
                mn = MONTH_NUM[m.lower()]
                # a fiscal year runs July..June, so Jan-Jun belong to year+1
                yr = start_year if mn >= 7 else start_year + 1
                rows.append({
                    "district": d, "fiscal_year": fy_label,
                    "year": yr, "month": mn,
                    "date": f"{yr}-{mn:02d}",
                    "remittance_musd": take[i],
                    "source_pdf": path.name,
                })
    return rows


def parse_annual(path: Path) -> list[dict]:
    """District x fiscal year rows from Annex-IV."""
    rows: list[dict] = []
    for p in range(1, pdf_pages(path) + 1):
        txt = page_text(path, p)
        if "Annex-IV" not in txt and "Annexure-IV" not in txt:
            continue
        # Take the column order from the header row only. The title line reads
        # "FY 2017-18 to FY 2025-26", and scanning the whole page put those two
        # first, silently shifting every district's values by several years.
        cols = []
        for line in txt.splitlines():
            if " to " in line and "Annex" not in line:
                continue                      # the title's range, not a header
            found = re.findall(r"FY\s*(\d{4})-(\d{2})", line)
            if len(found) >= 3:
                cols = [f"FY{a}-{b}" for a, b in found]
                break
        if len(cols) < 3:
            continue
        # a trailing partial-year column (the current FY's month) may follow
        n_cols = len(cols)
        for line in txt.splitlines():
            label, vals = parse_row(line)
            if not label or len(vals) < 3:
                continue
            low = label.lower()
            if "total" in low or "division" in low or "district" in low:
                continue
            d = norm_district(label)
            if not d:
                d = norm_district(label.split("  ")[-1])
            if not d:
                continue
            if len(vals) < n_cols:
                continue                      # a wrapped or partial row
            for i, fy in enumerate(cols):
                if i >= len(vals):
                    break
                rows.append({
                    "district": d, "fiscal_year": fy,
                    "remittance_musd": vals[i], "source_pdf": path.name,
                })
    return rows


def main() -> None:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print(__doc__)
        sys.exit(1)

    monthly, annual = [], []
    for p in paths:
        if not p.exists():
            print(f"  skip (missing): {p}")
            continue
        m = parse_monthly(p)
        a = parse_annual(p)
        print(f"  {p.name:<44} monthly rows {len(m):>5}   annual rows {len(a):>5}")
        monthly += m
        annual += a

    # later files win on a duplicate (district, month)
    seen = {}
    for r in monthly:
        seen[(r["district"], r["date"])] = r
    monthly = sorted(seen.values(), key=lambda r: (r["date"], r["district"]))

    seen_a = {}
    for r in annual:
        seen_a[(r["district"], r["fiscal_year"])] = r
    annual = sorted(seen_a.values(), key=lambda r: (r["fiscal_year"], r["district"]))

    if monthly:
        with open(ROOT / "remittance_monthly.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(monthly[0].keys()))
            w.writeheader()
            w.writerows(monthly)
        months = sorted({r["date"] for r in monthly})
        print(f"\n  remittance_monthly.csv   {len(monthly):,} rows  "
              f"{len({r['district'] for r in monthly})} districts  "
              f"{len(months)} months  {months[0]}..{months[-1]}")
    if annual:
        with open(ROOT / "remittance_annual_fy.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(annual[0].keys()))
            w.writeheader()
            w.writerows(annual)
        fys = sorted({r["fiscal_year"] for r in annual})
        print(f"  remittance_annual_fy.csv {len(annual):,} rows  "
              f"{len({r['district'] for r in annual})} districts  {fys[0]}..{fys[-1]}")


if __name__ == "__main__":
    main()
