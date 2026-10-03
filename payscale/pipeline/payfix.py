#!/usr/bin/env python3
"""The 2026 pay-fixation engine — Article 5 of চাকরি (বেতন ও ভাতাদি) আদেশ, ২০২৬.

Verbatim rule from the gazette (p.25199):

  ৫(ক)  an employee drawing pay at the STARTING step of the current scale is
        fixed at the starting step of the 2026 corresponding scale;
  ৫(খ)  otherwise: take the difference between the employee's basic and the
        lowest step of the current scale, add that difference to the lowest
        step of the 2026 corresponding scale, and then —
        (অ) if the sum equals a step of the new scale, fix there;
        (আ) if it equals no step, fix at the NEXT HIGHER step.

Everything the portal reports — the raises, the compression, the step demotion
— falls out of this one rule, so it is implemented once, here, and reused.

Also implements the phased release (Article 1(3)):
  phase 1  1 Jul 2026 – 31 Dec 2026   40% of the rise (grades 1–9), 50% (10–20)
  phase 2  1 Jan 2027 – 30 Jun 2027   70% (grades 1–9), 75% (10–20)
  full     from 1 Jul 2027            100%
"""
from bisect import bisect_left


def fix(old_basic, old_ladder, new_ladder):
    """Apply Article 5. Returns a dict describing the whole derivation."""
    if not old_ladder or not new_ladder:
        return None
    old_start, new_start = old_ladder[0], new_ladder[0]

    if old_basic <= old_start:                      # 5(ক)
        return {"rule": "5(ka)", "diff": 0, "target": new_start,
                "new_basic": new_start, "exact": True,
                "old_step": 0, "new_step": 0}

    diff = old_basic - old_start                    # 5(খ)
    target = new_start + diff
    i = bisect_left(new_ladder, target)
    if i < len(new_ladder) and new_ladder[i] == target:
        new_basic, exact = target, True             # 5(খ)(অ)
    elif i < len(new_ladder):
        new_basic, exact = new_ladder[i], False     # 5(খ)(আ) next higher step
    else:
        new_basic, exact = new_ladder[-1], False    # beyond the ceiling
    old_step = old_ladder.index(old_basic) if old_basic in old_ladder else None
    return {"rule": "5(kha)", "diff": diff, "target": target,
            "new_basic": new_basic, "exact": exact,
            "old_step": old_step, "new_step": new_ladder.index(new_basic)}


def phase_pay(old_basic, new_basic, grade, phase):
    """Basic actually drawn during the phased rollout."""
    rise = new_basic - old_basic
    if phase == "full":
        return new_basic, 1.0
    pct = {"p1": 0.40 if grade <= 9 else 0.50,
           "p2": 0.70 if grade <= 9 else 0.75}[phase]
    return round(old_basic + rise * pct), pct


def grade_table(grade, l15, l26):
    """Fix every 2015 step of a grade and return the full comparison."""
    rows = []
    for i, ob in enumerate(l15):
        r = fix(ob, l15, l26)
        nb = r["new_basic"]
        rows.append({
            "grade": grade, "old_step": i + 1, "old_basic": ob,
            "new_basic": nb, "new_step": r["new_step"] + 1,
            "raise_pct": round((nb / ob - 1) * 100, 2),
            "step_shift": (r["new_step"] + 1) - (i + 1),
            "exact": r["exact"], "diff": r["diff"], "target": r["target"],
        })
    return rows


def anomalies(rows):
    """Compression (several old steps -> one new step) and step demotion."""
    from collections import Counter
    byn = Counter(r["new_basic"] for r in rows)
    collided = {k: v for k, v in byn.items() if v > 1}
    demoted = [r for r in rows if r["step_shift"] < 0]
    return {
        "n_old_steps": len(rows),
        "n_distinct_new": len(byn),
        "collapsed_steps": len(rows) - len(byn),
        "collisions": collided,
        "n_demoted": len(demoted),
        "max_demotion": min((r["step_shift"] for r in rows), default=0),
        "raise_top": rows[0]["raise_pct"] if rows else None,
        "raise_bottom": rows[-1]["raise_pct"] if rows else None,
    }


if __name__ == "__main__":
    # grade 6, verified against both the gazette table and the source chat
    l15 = [35500, 37280, 39150, 41110, 43170, 45330, 47600, 49980,
           52480, 55110, 57870, 60770, 63810, 67010]
    l26 = [71000, 74600, 78300, 82200, 86400, 90700, 95200, 100000,
           104900, 110200, 115700, 121500, 127600, 134000]
    rows = grade_table(6, l15, l26)
    print(f"{'old#':>4} {'old basic':>10} {'diff':>7} {'target':>8} "
          f"{'new basic':>10} {'new#':>5} {'shift':>6} {'raise%':>8}")
    print("-" * 66)
    for r in rows:
        print(f"{r['old_step']:>4} {r['old_basic']:>10,} {r['diff']:>7,} "
              f"{r['target']:>8,} {r['new_basic']:>10,} {r['new_step']:>5} "
              f"{r['step_shift']:>+6} {r['raise_pct']:>7.2f}%")
    a = anomalies(rows)
    print(f"\n{a['n_old_steps']} old steps -> {a['n_distinct_new']} distinct new "
          f"({a['collapsed_steps']} collapsed)")
    print(f"demoted: {a['n_demoted']}  worst: {a['max_demotion']} steps")
    print(f"raise at step 1: {a['raise_top']}%   at top step: {a['raise_bottom']}%")
