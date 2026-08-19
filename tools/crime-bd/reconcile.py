#!/usr/bin/env python3
"""
Validate and repair an OCR'd crime-statistics sheet against its own arithmetic.

The published sheet over-determines itself. Each row prints a Recovery subtotal
and a grand total; the bottom row totals every column. That gives 3 families of
linear constraints over the same cells:

    RC Total    = Arms + Explosive + Narcotics + Smuggling
    Total Cases = (eleven offence columns) + RC Total
    Total row   = sum of the seventeen unit rows

A cell that OCR missed, or misread, almost always sits in a constraint whose
other terms are known -- so the constraint names the correct value. We apply
that repeatedly: solve what is determined, then treat the least-confident cell
in each still-broken constraint as suspect, drop it, and solve again.

Whatever cannot be reconciled is reported, never guessed.
"""
from ocr_extract import (ALL_COLS, IDX_GRAND, IDX_OFFENCE, IDX_RC_TOTAL,
                         IDX_RECOVERY, N_ROWS, UNITS)

N_UNITS = len(UNITS)
TOTAL_RI = N_UNITS  # the Total row sits last


def constraints():
    """Yield (member_cells, total_cell) pairs; each total equals its members."""
    for r in range(N_ROWS):
        yield [(r, c) for c in IDX_RECOVERY], (r, IDX_RC_TOTAL)
        yield [(r, c) for c in IDX_OFFENCE] + [(r, IDX_RC_TOTAL)], (r, IDX_GRAND)
    for c in range(len(ALL_COLS)):
        yield [(r, c) for r in range(N_UNITS)], (TOTAL_RI, c)


def _solve_pass(grid):
    """Fill any cell that a constraint uniquely determines.

    Only ever fills a hole -- an existing reading is never overwritten here --
    and refuses a solution that is not a valid count, since these are offence
    tallies and cannot be negative. Returns the number of cells filled.
    """
    filled = 0
    for members, total in constraints():
        cells = members + [total]
        unknown = [p for p in cells if grid[p] is None]
        if len(unknown) != 1:
            continue
        u = unknown[0]
        known_members = sum(grid[p] for p in members if p != u)
        if u == total:
            val = known_members
        elif grid[total] is None:
            continue
        else:
            val = grid[total] - known_members
        if val < 0:
            continue          # the constraint is inconsistent, not this cell
        grid[u] = val
        filled += 1
    return filled


# A cell all four page-segmentation modes agreed on is taken as read.
CONF_TRUSTED = 1.0


def _cell_consistent(grid, cell):
    """True if every fully-known constraint containing `cell` balances."""
    for members, total in constraints():
        cells = members + [total]
        if cell not in cells or any(grid[p] is None for p in cells):
            continue
        if sum(grid[p] for p in members) != grid[total]:
            return False
    return True


def violations(grid):
    """Constraints whose terms are all known but do not balance."""
    bad = []
    for members, total in constraints():
        cells = members + [total]
        if any(grid[p] is None for p in cells):
            continue
        s = sum(grid[p] for p in members)
        if s != grid[total]:
            bad.append((members, total, s, grid[total]))
    return bad


def reconcile(grid, conf, max_rounds=12):
    """Repair the grid against its checksums.

    Returns (grid, report). The report records every cell we changed and every
    constraint still broken at the end.
    """
    grid = grid.copy()
    original = grid.copy()
    repaired, dropped = [], []

    for _ in range(max_rounds):
        while _solve_pass(grid):
            pass
        bad = violations(grid)
        if not bad:
            break
        # A broken constraint means one of its cells was misread. Only a cell
        # OCR was already unsure about is a candidate, and we accept the repair
        # only if the replacement satisfies *every* constraint that cell sits
        # in -- one checksum could be coincidence, two agreeing is not.
        progressed = False
        for members, total, _got, _want in bad:
            cells = [p for p in members + [total]
                     if p not in dropped and conf[p] < CONF_TRUSTED]
            for p in sorted(cells, key=lambda q: conf[q]):
                trial = grid.copy()
                trial[p] = None
                while _solve_pass(trial):
                    pass
                if trial[p] is None or not _cell_consistent(trial, p):
                    continue
                grid, dropped, progressed = trial, dropped + [p], True
                break
            if progressed:
                break
        if not progressed:
            break

    while _solve_pass(grid):
        pass

    for r in range(N_ROWS):
        for c in range(len(ALL_COLS)):
            if original[r, c] != grid[r, c]:
                repaired.append({
                    "row": (UNITS + ["Total"])[r], "col": ALL_COLS[c],
                    "ocr": original[r, c], "fixed": grid[r, c],
                    "confidence": round(float(conf[r, c]), 2),
                })

    unresolved = [
        {"row": (UNITS + ["Total"])[t[0]], "col": ALL_COLS[t[1]],
         "members_sum": s, "printed_total": w}
        for (_m, t, s, w) in violations(grid)
    ]
    missing = [{"row": (UNITS + ["Total"])[r], "col": ALL_COLS[c]}
               for r in range(N_ROWS) for c in range(len(ALL_COLS))
               if grid[r, c] is None]

    return grid, {
        "repaired": repaired,
        "unresolved": unresolved,
        "missing": missing,
        "clean": not unresolved and not missing,
    }
