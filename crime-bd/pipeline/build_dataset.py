#!/usr/bin/env python3
"""
Assemble every month into one dataset for the dashboard.

Two sources feed in:

  * a pre-compiled CSV covering Jan-2020 to May-2025, and
  * per-month JSON transcribed from the published sheets from Jun-2025 on,
    each one checked against the three totals the source prints.

The CSV was itself OCR'd by someone else and carries the marks of it -- capital
I read for the digit 1, a stray leading dot, a minus sign hallucinated onto a
count, two rows dropped entirely. Those are corrected here against the original
PDFs rather than papered over, and every correction is recorded in the output so
the dashboard can show its own workings.
"""
import csv
import json
import os
import re
import sys

from geography import resolve as resolve_units
from ocr_extract import CRIME_COLS, UNITS

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

HERE = os.path.dirname(os.path.abspath(__file__))

# Cells the compiled CSV got wrong, each re-read from the published PDF.
# key: (date, unit, column) -> (corrected value, note)
CELL_FIXES = {
    ("May-22", "Chittagong Range", "Burglary"):
        (31, "CSV held '. 31'; sheet prints 31"),
    ("Dec-24", "Sylhet Range", "Murder"):
        (16, "CSV held '16-'; sheet prints 16"),
    ("Aug-23", "Mymensingh Range", "Police Assault"):
        (1, "CSV blank; sheet prints 1"),
    # The scans carry speckles that the earlier OCR swallowed into the number --
    # a stray dot became a decimal point, a fleck became a minus sign. Each of
    # these rows was re-read and both its printed subtotals balance.
    ("Jan-21", "Chittagong Range", "Kidnapping"):
        (9, "CSV held '0.9'; sheet prints 9"),
    ("Apr-22", "Chittagong Range", "Dacoity"):
        (2, "CSV held '0.2'; sheet prints 2"),
    ("Apr-22", "Chittagong Range", "Woman & Child Repression"):
        (181, "CSV held '18.1'; sheet prints 181"),
    ("Jun-22", "Mymensingh Range", "Kidnapping"):
        (5, "CSV held '-5'; sheet prints 5"),
    ("Dec-22", "Mymensingh Range", "Other Cases"):
        (455, "CSV held '0.455'; sheet prints 455"),
    ("Jun-23", "Mymensingh Range", "Robbery"):
        (1, "CSV held '-1.0'; sheet prints 1"),
    ("Jun-23", "Mymensingh Range", "Kidnapping"):
        (1, "CSV held '-1'; sheet prints 1"),
}

# Whole rows the CSV dropped, re-read from the published PDF.
ROW_FIXES = {
    ("Nov-22", "Ralway Range"):
        ([0, 0, 2, 0, 0, 0, 0, 0, 0, 4, 9, 2, 0, 32, 5],
         "row absent from CSV; re-read from the 2022 annual sheet"),
    ("Dec-22", "Ralway Range"):
        ([0, 1, 2, 0, 0, 0, 0, 0, 0, 8, 9, 0, 0, 29, 1],
         "row absent from CSV; re-read from the 2022 annual sheet"),
}


def norm_cell(raw):
    """Turn one CSV cell into an integer, or None if it cannot be trusted.

    Handles the compiled CSV's OCR residue: a capital I standing in for 1, and
    stray punctuation picked up from the scan ('. 31', '16-').
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None, None
    if re.fullmatch(r"[Il|]+", s):                 # I, l, | -> 1, 11, ...
        return int("1" * len(s)), f"read {s!r} as {'1' * len(s)}"

    # Try the value as written first. These are counts, so a clean decimal can
    # only be pandas' float formatting -- "2.0" means 2. Stripping punctuation
    # before parsing would read it as 20 and inflate the column tenfold.
    try:
        f = float(s)
        if f.is_integer():
            return (int(f), None) if f >= 0 else (
                None, f"negative count {s!r} rejected")
    except ValueError:
        pass

    # Not a clean number: the scan speckled a dot or a dash into it. The digits
    # are what the sheet actually prints, so keep those and drop the rest.
    cleaned = re.sub(r"[^0-9]", "", s)
    if cleaned == "":
        return None, None
    if s.lstrip().startswith("-"):
        return None, f"negative count {s!r} rejected"
    return int(cleaned), f"read {s!r} as {int(cleaned)}"


def load_csv(path):
    """Rows of the compiled CSV as {(date, unit): [15 values]} plus notes."""
    data, notes = {}, []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            date, unit = row["Date"].strip(), row["Names of Unit"].strip()
            vals = []
            for c in CRIME_COLS:
                v, note = norm_cell(row.get(c))
                if note:
                    notes.append({"date": date, "unit": unit, "column": c,
                                  "note": note})
                vals.append(v)
            data[(date, unit)] = vals
    return data, notes


def apply_fixes(data, notes):
    for (date, unit), (vals, why) in ROW_FIXES.items():
        data[(date, unit)] = list(vals)
        notes.append({"date": date, "unit": unit, "column": "(whole row)",
                      "note": why})
    for (date, unit, col), (val, why) in CELL_FIXES.items():
        if (date, unit) in data:
            data[(date, unit)][CRIME_COLS.index(col)] = val
            notes.append({"date": date, "unit": unit, "column": col,
                          "note": why})
    return data, notes


def load_transcripts(dirpath):
    """The verified per-month sheets, keyed YYYY-MM."""
    out = {}
    for fn in sorted(os.listdir(dirpath)):
        if not fn.endswith(".json"):
            continue
        key = fn[:-5]
        if not re.fullmatch(r"\d{4}-\d{2}", key):
            continue
        sheet = json.load(open(os.path.join(dirpath, fn)))
        # keep only the fifteen offence columns; the two subtotals were
        # checking columns, not data
        out[key] = {u: sheet[u][:15] for u in UNITS if u in sheet}
    return out


def profile_anomalies(months, values, tol=6.0):
    """Flag months whose offence mix does not look like anybody else's.

    January 2025 arrived in the compiled CSV with its columns rotated -- an
    extra zero pushed into the middle of every row, shifting the rest one place
    right. Nothing about that month looked wrong cell by cell, but it turned
    Woman & Child Repression into a near-zero column and invented a correlation
    of 0.83 between two unrelated offences across the whole dataset.

    The tell is the shape of the month, not any single number: each offence
    holds a fairly stable share of the national total, so a month where a share
    jumps by a large multiple is either a real shock or a scrambled row. Either
    way it is worth a human look before it is published.
    """
    shares = []
    for row in values:
        tot = sum(sum(r) for r in row) or 1
        shares.append([sum(r[c] for r in row) / tot for c in range(len(CRIME_COLS))])

    out = []
    for c in range(len(CRIME_COLS)):
        col = sorted(s[c] for s in shares)
        med = col[len(col) // 2]
        # Only worth testing columns that carry real weight. Riot and Explosive
        # Act sit near a tenth of a percent, where a genuine event -- riots
        # during the 2024 uprising -- multiplies the share many times over and
        # would bury the signal we actually want in false alarms.
        if med < 0.01:
            continue
        for mi, s in enumerate(shares):
            ratio = s[c] / med
            if ratio > tol or ratio < 1 / tol:
                out.append({"month": months[mi], "column": CRIME_COLS[c],
                            "share": round(s[c], 5), "typical_share": round(med, 5)})
    return out


def ym(date):
    mon, yy = date.split("-")
    return f"20{yy}-{MONTHS.index(mon[:3].title()) + 1:02d}"


def main(csv_path, truth_dir, out_path):
    csv_data, notes = apply_fixes(*load_csv(csv_path))
    sheets = load_transcripts(truth_dir)

    by_month = {}
    for (date, unit), vals in csv_data.items():
        by_month.setdefault(ym(date), {})[unit] = vals
    superseded = sorted(set(by_month) & set(sheets))
    by_month.update(sheets)                    # transcripts win where both exist

    months = sorted(by_month)
    unit_meta = resolve_units()

    values, holes = [], []
    for m in months:
        rows = []
        for u in UNITS:
            row = by_month[m].get(u)
            if row is None:
                row = [None] * len(CRIME_COLS)
            for ci, v in enumerate(row):
                if v is None:
                    holes.append({"month": m, "unit": u,
                                  "column": CRIME_COLS[ci]})
            rows.append(row)
        values.append(rows)

    anomalies = profile_anomalies(months, values)

    out = {
        "meta": {
            "source": "Bangladesh Police, monthly Crime Statistics",
            "source_url": "https://www.police.gov.bd/en/crime_statistic_home",
            "months": len(months),
            "first_month": months[0],
            "last_month": months[-1],
            "units": len(UNITS),
            "crimes": len(CRIME_COLS),
            "verified_from_source": sorted(sheets),
            "superseded_by_transcript": superseded,
            "corrections": notes,
            "unresolved_cells": holes,
            "profile_anomalies": anomalies,
        },
        "months": months,
        "units": [unit_meta[u] for u in UNITS],
        "crimes": CRIME_COLS,
        "values": values,
    }
    json.dump(out, open(out_path, "w"), separators=(",", ":"))

    print(f"months     : {len(months)}  ({months[0]} .. {months[-1]})")
    print(f"corrections: {len(notes)}")
    print(f"holes      : {len(holes)}")
    print(f"anomalies  : {len(anomalies)}")
    for a in anomalies:
        print(f"   ! {a['month']} {a['column']}: share {a['share']} vs typical {a['typical_share']}")
    print(f"bytes      : {os.path.getsize(out_path):,}")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
