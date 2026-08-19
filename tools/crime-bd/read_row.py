#!/usr/bin/env python3
"""
Read a single unit's row from a published sheet, and say whether to believe it.

Used to settle individual cells the compiled CSV mangled. A row is only worth
acting on if it proves itself: the sheet prints a Recovery subtotal and a grand
total on every row, so a correct reading satisfies both. If either fails, the
row is reported as unconfirmed rather than used.

    python3 read_row.py <pdf> <page> "<unit>"
"""
import sys

import numpy as np

from ocr_extract import (ALL_COLS, IDX_GRAND, IDX_OFFENCE, IDX_RC_TOTAL,
                         IDX_RECOVERY, UNITS, orient, read_cell, render_pages)


def read_row(pdf, page, unit, dpi=400):
    pages = render_pages(pdf, dpi)
    found = orient(pages[page - 1])
    if found is None:
        return None, "could not locate the table on this page"
    _s, im, _a, H, V, _f, _t = found
    iy = max(3, int(np.median(np.diff(H)) * 0.06))
    ix = max(3, int(np.median(np.diff(V)) * 0.06))
    ri = UNITS.index(unit)
    y0, y1 = H[ri] + iy, H[ri + 1] - iy
    vals = [read_cell(im.crop((V[c + 1] + ix, y0, V[c + 2] - ix, y1)))[0]
            for c in range(len(ALL_COLS))]
    if any(v is None for v in vals):
        return vals, "some cells unreadable"
    rc = sum(vals[i] for i in IDX_RECOVERY)
    grand = sum(vals[i] for i in IDX_OFFENCE) + vals[IDX_RC_TOTAL]
    if rc != vals[IDX_RC_TOTAL]:
        return vals, f"recovery subtotal {rc} != printed {vals[IDX_RC_TOTAL]}"
    if grand != vals[IDX_GRAND]:
        return vals, f"row total {grand} != printed {vals[IDX_GRAND]}"
    return vals, None


if __name__ == "__main__":
    pdf, page, unit = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    vals, err = read_row(pdf, page, unit)
    print(f"{unit} @ {pdf} p{page}")
    if vals:
        for c, v in zip(ALL_COLS, vals):
            print(f"   {c:26s} {v}")
    print("VERDICT:", err or "CONFIRMED - both printed subtotals balance")
