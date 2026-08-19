#!/usr/bin/env python3
"""Check a transcribed sheet against the three checksums the source prints.

Usage: python3 verify.py truth/2025-07.json [...]

Exits non-zero if any sheet fails, so it can gate the build.
"""
import json
import sys

import numpy as np

from ocr_extract import ALL_COLS, UNITS
from reconcile import constraints

ROWS = UNITS + ["Total"]


def check(path):
    data = json.load(open(path))
    missing = [u for u in ROWS if u not in data]
    if missing:
        print(f"{path}: MISSING ROWS {missing}")
        return False
    grid = np.array([data[u] for u in ROWS], dtype=object)
    if grid.shape != (len(ROWS), len(ALL_COLS)):
        print(f"{path}: shape {grid.shape}, expected {(len(ROWS), len(ALL_COLS))}")
        return False

    bad = []
    for members, total in constraints():
        s = sum(grid[p] for p in members)
        if s != grid[total]:
            bad.append(f"    {ROWS[total[0]]:>18s} / {ALL_COLS[total[1]]:<26s} "
                       f"members={s} printed={grid[total]} (diff {s - grid[total]:+d})")
    neg = [f"    {ROWS[i]} / {ALL_COLS[j]} = {grid[i, j]}"
           for i in range(grid.shape[0]) for j in range(grid.shape[1])
           if grid[i, j] < 0]

    if bad or neg:
        print(f"{path}: FAIL ({len(bad)} checksum, {len(neg)} negative)")
        for line in bad + neg:
            print(line)
        return False
    print(f"{path}: OK  all {sum(1 for _ in constraints())} checksums balance")
    return True


if __name__ == "__main__":
    ok = all([check(p) for p in sys.argv[1:]])
    sys.exit(0 if ok else 1)
