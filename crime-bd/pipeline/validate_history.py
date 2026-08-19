#!/usr/bin/env python3
"""
Audit the pre-compiled 2020-2025 CSV against the source sheets.

The CSV holds only the seventeen unit rows -- whoever compiled it dropped the
printed Total row, and with it the only way to tell whether the numbers are
right. So we go back to the published PDFs and read just that Total row for
each month, then check it against the CSV's own column sums.

Reading one row instead of a whole sheet makes auditing 65 months affordable,
and the Total row checks itself twice over (its Recovery subtotal and its grand
total), so a bad OCR of the audit row shows up as a bad audit rather than a
false accusation against the CSV.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from ocr_extract import (ALL_COLS, IDX_GRAND, IDX_OFFENCE, IDX_RC_TOTAL,
                         IDX_RECOVERY, N_ROWS, orient, read_cell)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def source_for(year, month, pdf_dir):
    """Where a given month lives: annual books hold one month per page, and
    from 2025 the PHQ switched to publishing each month on its own."""
    annual = os.path.join(pdf_dir, f"year{year}.pdf")
    if os.path.exists(annual):
        return annual, month           # page N is month N
    return os.path.join(pdf_dir, f"{year}-{month:02d}.pdf"), 1


_PAGE_CACHE = {}


def _pages(pdf):
    """Rasterise a PDF once. The annual books hold twelve months each, so
    rendering per month would redo the same work a dozen times over."""
    if pdf not in _PAGE_CACHE:
        from ocr_extract import render_pages
        _PAGE_CACHE.clear()          # one book at a time; these are large
        _PAGE_CACHE[pdf] = render_pages(pdf, 400)
    return _PAGE_CACHE[pdf]


def read_total_row(pdf, page):
    """OCR just the Total row of one sheet."""
    pages = _pages(pdf)
    if page > len(pages):
        return None, f"page {page} missing (pdf has {len(pages)})"
    found = orient(pages[page - 1])
    if found is None:
        return None, "no table grid found"
    _s, im, _ang, H, V, _frac, _turn = found
    iy = max(3, int(np.median(np.diff(H)) * 0.06))
    ix = max(3, int(np.median(np.diff(V)) * 0.06))
    ri = N_ROWS - 1                     # Total is the last row
    y0, y1 = H[ri] + iy, H[ri + 1] - iy
    vals = []
    for ci in range(len(ALL_COLS)):
        x0, x1 = V[ci + 1] + ix, V[ci + 2] - ix
        v, _c = read_cell(im.crop((x0, y0, x1, y1)))
        vals.append(v)
    return vals, None


def self_consistent(row):
    """The Total row must satisfy the same two arithmetic rules as any row."""
    if any(v is None for v in row):
        return False
    if sum(row[i] for i in IDX_RECOVERY) != row[IDX_RC_TOTAL]:
        return False
    return sum(row[i] for i in IDX_OFFENCE) + row[IDX_RC_TOTAL] == row[IDX_GRAND]


def main(csv_path, pdf_dir, out_path):
    df = pd.read_csv(csv_path)
    cols = ALL_COLS[:15]                # the CSV carries only the 15 offences
    report = {}
    for date, g in df.groupby("Date", sort=False):
        mon, yy = date.split("-")
        year = 2000 + int(yy)
        month = MONTHS.index(mon[:3].title()) + 1
        pdf, page = source_for(year, month, pdf_dir)
        if not os.path.exists(pdf):
            report[date] = {"status": "no source pdf"}
            continue
        total, err = read_total_row(pdf, page)
        if err:
            report[date] = {"status": err}
            continue
        entry = {"status": "ok", "audit_row_self_consistent": self_consistent(total)}
        diffs = {}
        for i, c in enumerate(cols):
            csv_sum = pd.to_numeric(g[c], errors="coerce").sum()
            if total[i] is None or pd.isna(csv_sum):
                diffs[c] = {"csv": None if pd.isna(csv_sum) else int(csv_sum),
                            "printed": total[i]}
            elif int(csv_sum) != total[i]:
                diffs[c] = {"csv": int(csv_sum), "printed": total[i],
                            "delta": int(csv_sum) - total[i]}
        entry["mismatches"] = diffs
        entry["clean"] = not diffs and entry["audit_row_self_consistent"]
        report[date] = entry
        flag = "OK " if entry["clean"] else "DIFF"
        print(f"{flag} {date:8s} {len(diffs)} column(s) differ", flush=True)

    json.dump(report, open(out_path, "w"), indent=1)
    clean = sum(1 for v in report.values() if v.get("clean"))
    print(f"\n{clean}/{len(report)} months reconcile with the printed totals")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
