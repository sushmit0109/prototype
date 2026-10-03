#!/usr/bin/env python3
"""Assemble exact step ladders for every grade and era into one place.

Sources, in order of authority:
  nps_2026, nps_2015  the 17-Sep-2026 gazette prints BOTH ladders side by side,
                      step by step -> 06_structured/scale_2026_gazette.csv
  nps_2009 and before grades.csv carries explicit increment bands
                      ("7x490;11x540"), which expand to an exact ladder
  fallback            start/max with a step count -> geometric reconstruction,
                      marked `reconstructed` so downstream can discount it

Output: 06_structured/ladders.json  {era: {grade: {steps:[...], source:...}}}
"""
import csv, json, pathlib
from collections import defaultdict, Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTD = ROOT / "06_structured"
GAZ = OUTD / "scale_2026_gazette.csv"


def from_bands(start, bands):
    """'7x490;11x540' -> the full ladder from `start`."""
    steps = [start]
    cur = start
    for b in [x for x in (bands or "").split(";") if x]:
        try:
            n, inc = (int(v) for v in b.split("x"))
        except ValueError:
            return None
        for _ in range(n):
            cur += inc
            steps.append(cur)
    return steps if len(steps) > 1 else None


def geometric(start, mx, n):
    if not (start and mx and n and mx > start):
        return None
    r = (mx / start) ** (1 / n)
    return [start] + [round(start * r ** k, -1) and int(round(start * r ** k))
                      for k in range(1, n + 1)]


def anchors():
    """Validated start/max per (era, grade) from crosswalk.csv — those rows
    already passed the ladder-monotonicity and source-consensus checks, so they
    are the yardstick a candidate ladder has to agree with."""
    a = {}
    try:
        for r in csv.DictReader(open(OUTD / "crosswalk.csv")):
            if r.get("ladder_ok") == "True" and r.get("cadre") == "govt_civil":
                a[("nps_" + r["era_year"], int(r["grade"]))] = (
                    int(r["start_basic"]), int(r["max_basic"]))
    except FileNotFoundError:
        pass
    return a


def main():
    out = defaultdict(dict)
    ANCH = anchors()

    # 1. the gazette's own side-by-side ladders (authoritative for 2015 & 2026)
    if GAZ.exists():
        g = defaultdict(lambda: defaultdict(list))
        for r in csv.DictReader(open(GAZ)):
            if r["ok"] == "True":
                g[r["era"]][int(r["grade"])].append((int(r["step_index"]),
                                                     int(r["amount"])))
        for era, grades in g.items():
            for gr, pairs in grades.items():
                steps = [v for _, v in sorted(pairs)]
                # grade 1 is a single fixed amount, not a ladder -- still the
                # gazette's own figure, so it must not fall through to the
                # geometric fallback
                if steps:
                    out[era][gr] = {
                        "steps": steps,
                        "source": "gazette_2026_table" if len(steps) > 1
                                  else "gazette_2026_table_fixed",
                        "n_steps": len(steps)}

    # 2. explicit increment bands from the earlier corpus.
    # grades.csv holds several rows per (era, grade): the defining gazette plus
    # the same scale restated as the "existing scale" column of the NEXT
    # commission. Those prior-era columns carry the OLD numbers, so including
    # them silently relabels e.g. 1977 figures as 1985. Filter them out, then
    # take the candidate the most documents agree on.
    # Before 2009 the national scale was one table reprinted in each service's
    # chapter, so when the civil chapter's own rows are contaminated these
    # siblings carry the same scale uncontaminated and settle it. They are kept
    # in a separate pool and consulted only when the civil rows are all rejected.
    # The uniformed, judicial and parliamentary chapters are excluded: those
    # genuinely map different scales onto the same grade number.
    SIBLINGS = {"police", "banks_financial_institutions",
                "autonomous_public_bodies"}
    cand, sib = defaultdict(list), defaultdict(list)
    for r in csv.DictReader(open(OUTD / "grades.csv")):
        if r.get("valid") != "True" or not r["grade"].isdigit():
            continue
        cadre = r.get("cadre")
        if cadre != "govt_civil" and cadre not in SIBLINGS:
            continue
        if r.get("is_prior_column") == "True":
            continue
        gr, era = int(r["grade"]), r["era"]
        if not (1 <= gr <= 20) or gr in out[era]:
            continue
        start, mx = int(r["start"] or 0), int(r["max"] or 0)
        n = int(r["n_steps"] or 0)
        # A fixed scale (grade 1) has no bands to expand, and a step-list scale
        # has a start and a ceiling but no bands either. Both still have to go
        # through the same contamination checks as a banded row, or they bypass
        # them -- which is how 1985's ৳6,000 stayed on 1991's grade 1.
        steps = from_bands(start, r.get("bands"))
        if not steps and start > 0:
            steps = [start] if start == mx else (geometric(start, mx, n) if n else None)
        if steps:
            # a row sourced from the gazette that DEFINES this era outranks the
            # same era restated inside a later gazette, which is where stray
            # next-commission figures leak in
            own = r.get("report_id", "").startswith(era)
            anc = ANCH.get((era, gr))
            # a candidate whose start disagrees with the validated crosswalk
            # start is almost always another era's scale wearing this era's label
            agrees = (anc is None) or (steps[0] == anc[0])
            tier = (0 if agrees else 2) + (0 if own else 1)
            (cand if cadre == "govt_civil" else sib)[(era, gr)].append((tier, steps))
    # A new pay scale never restates the previous scale's exact starting figure
    # for the same grade, so a candidate that does is the "existing scale" column
    # of a side-by-side table that the prior-column detector missed. Eras are
    # resolved oldest first so the previous era is already settled when its
    # successor is checked. This is what put 1985's ৳6,000 under 1991's grade 1.
    ORDER = ["nps_1973", "nps_1977", "nps_1985", "nps_1991", "nps_1997",
             "nps_2005", "nps_2009", "nps_2015", "nps_2026"]
    for (era, gr), options in sorted(
            cand.items(), key=lambda kv: (ORDER.index(kv[0][0])
                                          if kv[0][0] in ORDER else 99, kv[0][1])):
        i = ORDER.index(era) if era in ORDER else 0
        prev = out.get(ORDER[i - 1], {}).get(gr) if i else None
        src = "increment_bands"
        if prev:
            def fresh(opts):
                return [(t, s) for t, s in opts if s[0] != prev["steps"][0]]
            kept = fresh(options)
            if not kept:
                # every civil row for this grade repeats the previous scale;
                # fall back to the same scale as printed in a sibling chapter
                kept = fresh(sib.get((era, gr), []))
                if kept:
                    src = "sibling_chapter"
            if kept:
                options = kept
        top = min(t for t, _ in options)
        elig = [tuple(s) for t, s in options if t == top]
        counts = Counter(elig)
        best, _ = max(counts.items(), key=lambda kv: (kv[1], -kv[0][0]))
        anc = ANCH.get((era, gr))
        # When no candidate matches the validated start, the label is wrong on
        # every one of them -- typically a neighbouring era's scale carried over
        # in a later gazette's "existing scale" column. Grade 1 of 1991 came
        # through as 1985's ৳6,000 and grade 1 of 2009 as grade 4's ৳25,750 this
        # way, which would have put a false ratio in the hierarchy column. Prefer
        # the anchor and reconstruct, rather than publish a mislabelled ladder.
        # The anchor comes from the same corpus, so where it repeats the previous
        # scale it carries the same contamination and cannot arbitrate -- without
        # this guard it reinstates the very figures the sibling chapter corrected.
        if anc and prev and anc[0] == prev["steps"][0]:
            anc = None
        if anc and best[0] != anc[0]:
            s, m = anc
            if s == m:
                out[era][gr] = {"steps": [s], "source": "anchor_fixed", "n_steps": 1}
            else:
                n = len(best) - 1 or 18
                out[era][gr] = {"steps": geometric(s, m, n),
                                "source": "anchor_geometric", "n_steps": n + 1,
                                "rejected_start": best[0]}
            continue
        out[era][gr] = {"steps": list(best), "source": src,
                        "n_steps": len(best), "n_sources": len(options),
                        "consensus": counts[best],
                        "from_defining_gazette": top == 0}

    # 3. geometric fallback, clearly marked
    for r in csv.DictReader(open(OUTD / "grades.csv")):
        if r.get("valid") != "True" or not r["grade"].isdigit():
            continue
        if r.get("cadre") != "govt_civil":
            continue
        if r.get("is_prior_column") == "True":
            continue
        gr, era = int(r["grade"]), r["era"]
        if not (1 <= gr <= 20) or gr in out[era]:
            continue
        n = int(r["n_steps"] or 0)
        steps = geometric(int(r["start"]), int(r["max"]), n) if n else None
        if steps:
            out[era][gr] = {"steps": steps, "source": "reconstructed_geometric",
                            "n_steps": len(steps)}
        elif r["start"] == r["max"]:
            out[era][gr] = {"steps": [int(r["start"])], "source": "fixed",
                            "n_steps": 1}

    data = {e: {str(k): v for k, v in sorted(gs.items())} for e, gs in out.items()}
    (OUTD / "ladders.json").write_text(json.dumps(data, indent=1))
    print("ladders.json written")
    for e in sorted(data):
        srcs = {}
        for v in data[e].values():
            srcs[v["source"]] = srcs.get(v["source"], 0) + 1
        print(f"  {e:10} {len(data[e]):>2} grades  {srcs}")


if __name__ == "__main__":
    main()
