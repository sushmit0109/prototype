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
other terms are known -- so the constraint names the correct value. Repair runs
in two stages:

  1. Deduction. Any cell a constraint determines outright is filled in. This is
     always safe and is kept whatever happens next.
  2. Search. While the sheet still does not balance, change the single
     low-confidence cell that most reduces the total residual, and repeat.

Stage 2 is a guess, so it is all-or-nothing: unless the guesses take the
residual to zero, they are discarded and the sheet is reported as unreconciled.
Two errors inside one constraint can otherwise lead the search to a wrong local
minimum, where it "fixes" the wrong cell and still does not balance -- and a
plausible-looking wrong number is far worse than a sheet held back for review.
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


def _residual(grid):
    """Total absolute imbalance across every fully-known constraint."""
    total = 0
    for members, tot in constraints():
        cells = members + [tot]
        if any(grid[p] is None for p in cells):
            continue
        total += abs(sum(grid[p] for p in members) - grid[tot])
    return total


def _implied_values(grid, cell):
    """What each constraint containing `cell` says its value should be."""
    out = set()
    for members, tot in constraints():
        cells = members + [tot]
        if cell not in cells:
            continue
        others = [p for p in cells if p != cell]
        if any(grid[p] is None for p in others):
            continue
        if cell == tot:
            out.add(sum(grid[p] for p in members))
        else:
            out.add(grid[tot] - sum(grid[p] for p in members if p != cell))
    return out


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

    # Fill whatever the constraints determine outright first. That is pure
    # deduction and always safe to keep.
    while _solve_pass(grid):
        pass
    deduced = grid.copy()

    for _ in range(max_rounds):
        while _solve_pass(grid):
            pass
        bad = violations(grid)
        if not bad:
            break
        # A broken constraint means one of its cells was misread. Requiring the
        # replacement to satisfy every constraint it touches is too strict once
        # more than one cell is wrong: each repair is blocked by the others.
        # Instead, minimise the total residual across all constraints, taking
        # whichever single change reduces it most. Only cells OCR was unsure
        # about are candidates, so a confidently-read figure is never rewritten.
        progressed = False
        best = None
        for members, total, _got, _want in bad:
            for p in members + [total]:
                if p in dropped or conf[p] >= CONF_TRUSTED:
                    continue
                for cand in _implied_values(grid, p):
                    if cand < 0 or cand == grid[p]:
                        continue
                    before = _residual(grid)
                    keep = grid[p]
                    grid[p] = cand
                    after = _residual(grid)
                    grid[p] = keep
                    if after < before and (best is None or after < best[0]):
                        best = (after, p, cand)
        if best is not None:
            _, p, cand = best
            grid[p] = cand
            dropped.append(p)
            progressed = True
        if not progressed:
            break

    while _solve_pass(grid):
        pass

    # Overwriting a cell is a guess, justified only if it makes the whole sheet
    # add up. Two errors inside one constraint can lead the search to a wrong
    # local minimum -- it "fixes" the wrong cell and still does not balance. So
    # unless the guesses reach zero residual, throw them all away and report the
    # sheet as unreconciled rather than publish a plausible-looking edit.
    if _residual(grid) != 0:
        grid = deduced
        dropped = []

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
