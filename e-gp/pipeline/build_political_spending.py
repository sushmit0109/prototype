#!/usr/bin/env python3
"""
Did winning a district's seats in the February 2026 election change how
much e-GP contract money that district gets? The hypothesis under test:
districts that did NOT elect BNP-led-alliance MPs are underrepresented in
development spending -- and, per the brief, mere correlation isn't enough.

WHY THIS IS A PANEL DIFFERENCE-IN-DIFFERENCES, NOT A CORRELATION

A raw comparison of "BNP districts spend more" would be confounded by
everything that makes a district likely to elect BNP AND likely to receive
money for unrelated reasons. Two-way fixed effects absorb both: a DISTRICT
fixed effect absorbs everything time-invariant about a district, and a
PERIOD fixed effect absorbs whatever moved every district together in a
given period. What's left to identify the effect is only the interaction --
does a district's spending move differently from its own baseline,
specifically in the period it went BNP, relative to districts that didn't.
Only valid if parallel trends hold -- which the placebo test below checks
rather than assumes.

A CONFOUND THIS FILE GOT WRONG ONCE, AND THE FIX

The first version of this analysis used 2015-2025 as the pre-period for
every test. That's wrong, for a reason specific to this portal: e-GP use
was HYBRID before the interim government took office -- offices could
still run tenders outside the platform, and the platform itself did not
support every tender type -- and the interim government made e-GP usage
obligatory. National contract counts confirm the shape (roughly 16K in
2015 climbing past 97K by 2023-2025): that is coverage of the same
underlying government activity expanding over a decade, not a decade of
actual spending growing 6x. Comparing a decade-long average spanning that
expansion against ANY short recent period will show a "gap" for reasons
that have nothing to do with which party won anything, and if that
coverage expansion happened even slightly unevenly across districts --
which offices had the IT capacity to digitise first, say -- it can produce
exactly the kind of spurious, non-causal correlation with vote share this
whole file exists to rule out. (It did, in the first version: see
`LEGACY_*` below, kept and clearly labelled rather than deleted.)

The fix: confine the panel to periods where e-GP coverage is already
stable -- interim government onward, monthly resolution, never touching
the pre-mandate hybrid era at all. The placebo then can't reuse "years
before the interim government" either, since that's the exact regime this
fix is trying to get away from; instead it splits the interim government's
own span in half and asks whether a fake jump appears between two halves
of a period where coverage was constant throughout and no election
happened at all.

TREATMENT IS A DISTRICT-LEVEL AGGREGATE OF SEAT-LEVEL OUTCOMES

A district is not one election result -- it is several constituencies,
and BNP's seat record within a district ranges from losing all of them to
winning all of them (see the scatter on the dashboard). bnp_won (binary,
seat majority) is one summary of that; bnp_vote_share (district-wide vote
share) and bnp_seat_share (fraction of the district's own seats BNP won)
are two continuous alternatives that don't collapse that heterogeneity to
a single threshold, and both are tested, on both the real and placebo
panels, not just whichever looks better.

DESIGN

  - Unit: district (64 -- the finest geography e-GP contracts carry).
  - Treatment: bnp_won / bnp_vote_share / bnp_seat_share, each fixed at its
    real 2026 value regardless of which period is being tested.
  - Outcome: contract value per registered voter, asinh-transformed (not
    log, so a zero-spend district-month doesn't need to be dropped or
    padded with an arbitrary epsilon).
  - PRIMARY panel: monthly, confined to the interim and elected governments
    (2024-08 through the latest crawled month) -- every month is its own
    period with its own fixed effect; post=1 for elected-government months.
  - PLACEBO panel: the interim government's own span split at its midpoint
    (post=1 for the second half) -- same district set, same treatment
    values, no real election anywhere in it.
  - LEGACY panel (kept for transparency, not used as the headline result):
    the original 2015-2025 vs. lumped-era design, which the coverage
    confound above invalidates as a causal test.
  - Inference: OLS via numpy, standard errors clustered by district,
    t-test against t(63).

    python3 build_political_spending.py <data/geo.json> <data/election_2026.json> <out.json>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

from districts import display_name
from eras import era_of

MIN_VOTERS_FOR_INCLUSION = 1000  # guards against a data-join sliver, not a real filter at district level
TREATMENTS = ["bnp_won", "bnp_vote_share", "bnp_seat_share"]

LEGACY_PRE_YEARS_MAIN = [str(y) for y in range(2015, 2026)]
LEGACY_PRE_YEARS_PLACEBO = [str(y) for y in range(2015, 2024)]


def asinh(x):
    return np.log(x + np.sqrt(x ** 2 + 1))


def treatment_values(e):
    return {
        "bnp_won": 1 if (e["bnp_seat_share"] or 0) > 0.5 else 0,
        "bnp_vote_share": e["bnp_vote_share"],
        "bnp_seat_share": e["bnp_seat_share"],
    }


def month_era(month_key):
    """Which era holds this calendar month -- classified by its 15th, the
    same representative-day convention build_growth.py uses for a month
    that might straddle an era boundary."""
    return era_of(f"{month_key}-15")


def build_monthly_panel(geo_districts, election_by_district, months, post_months):
    """One row per (district, month), confined to `months` (all from the
    stable-coverage regime). post=1 for months in `post_months`."""
    post_set = set(post_months)
    rows = []
    for dist, e in election_by_district.items():
        g = geo_districts.get(dist)
        if not g or e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        tv = treatment_values(e)
        for m in months:
            mb = g["by_month"].get(m, {"value_bdt": 0.0, "count": 0})
            rows.append({"district": dist, "period": m, "post": 1 if m in post_set else 0,
                         **tv, "value_bdt": mb["value_bdt"], "count": mb["count"],
                         "total_voters": e["total_voters"]})
    return rows


def build_legacy_panel(geo_districts, election_by_district, pre_years, post_label, post_era_name):
    rows = []
    for dist, e in election_by_district.items():
        g = geo_districts.get(dist)
        if not g or e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        tv = treatment_values(e)
        for y in pre_years:
            yb = g["by_year"].get(y, {"value_bdt": 0.0, "count": 0})
            rows.append({"district": dist, "period": y, "post": 0, **tv,
                         "value_bdt": yb["value_bdt"], "count": yb["count"], "total_voters": e["total_voters"]})
        pb = g["by_era"].get(post_era_name, {"value_bdt": 0.0, "count": 0})
        rows.append({"district": dist, "period": post_label, "post": 1, **tv,
                     "value_bdt": pb["value_bdt"], "count": pb["count"], "total_voters": e["total_voters"]})
    return rows


def two_way_fe_did(rows, treatment_key="bnp_won"):
    """OLS with district + period fixed effects (explicit dummies) plus a
    treatment x post interaction, cluster-robust (by district) SEs."""
    districts = sorted({r["district"] for r in rows})
    periods = sorted({r["period"] for r in rows})
    dist_idx = {d: i for i, d in enumerate(districts)}
    per_idx = {p: i for i, p in enumerate(periods)}

    n = len(rows)
    k = 1 + (len(districts) - 1) + (len(periods) - 1) + 1
    X = np.zeros((n, k))
    y = np.zeros(n)
    cluster = np.zeros(n, dtype=int)

    for i, r in enumerate(rows):
        X[i, 0] = 1.0
        di = dist_idx[r["district"]]
        if di > 0:
            X[i, 1 + di - 1] = 1.0
        pi = per_idx[r["period"]]
        if pi > 0:
            X[i, 1 + (len(districts) - 1) + pi - 1] = 1.0
        X[i, -1] = (r[treatment_key] or 0) * r["post"]
        per_voter = r["value_bdt"] / r["total_voters"]
        y[i] = asinh(per_voter)
        cluster[i] = di

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XtX_inv = np.linalg.pinv(X.T @ X)

    G = len(districts)
    meat = np.zeros((k, k))
    for g in range(G):
        mask = cluster == g
        Xg = X[mask]
        ug = resid[mask]
        score = Xg.T @ ug
        meat += np.outer(score, score)
    correction = (G / (G - 1)) * ((n - 1) / (n - k))
    vcov = correction * XtX_inv @ meat @ XtX_inv

    b = beta[-1]
    se = np.sqrt(vcov[-1, -1])
    df = G - 1
    t = b / se if se > 0 else 0.0
    p = 2 * (1 - stats.t.cdf(abs(t), df)) if se > 0 else 1.0

    return {
        "coefficient": round(float(b), 4), "std_error": round(float(se), 4),
        "t_stat": round(float(t), 3), "p_value": round(float(p), 4),
        "df": df, "n_obs": n, "n_districts": G, "n_periods": len(periods),
        "approx_proportional_effect": round(float(np.exp(b) - 1), 4),
    }


def simple_group_means(rows):
    cells = defaultdict(list)
    for r in rows:
        per_voter = r["value_bdt"] / r["total_voters"]
        cells[(r["bnp_won"], r["post"])].append(per_voter)
    means = {f"bnp_won={k[0]}_post={k[1]}": round(float(np.mean(v)), 2) for k, v in cells.items()}
    try:
        did = ((np.mean(cells[(1, 1)]) - np.mean(cells[(1, 0)]))
               - (np.mean(cells[(0, 1)]) - np.mean(cells[(0, 0)])))
    except KeyError:
        did = None
    return {"cell_means_bdt_per_voter": means, "did_bdt_per_voter": round(float(did), 2) if did is not None else None}


def all_treatments(rows):
    return {t: two_way_fe_did(rows, treatment_key=t) for t in TREATMENTS}


def main(geo_path, election_path, out_path):
    geo = json.load(open(geo_path))
    election = json.load(open(election_path))

    election_by_district = {display_name(d["district"]): d for d in election["districts"]}
    common_districts = sorted(set(election_by_district) & set(geo["districts"]))

    # Every month across every district, classified by era -- restrict to
    # the stable-coverage regime (interim onward) for the primary test.
    all_months = sorted({m for d in geo["districts"].values() for m in d["by_month"]})
    interim_months = [m for m in all_months if month_era(m) == "Interim Government (2024–2026)"]
    elected_months = [m for m in all_months if month_era(m) == "Elected Government (2026–)"]
    stable_months = sorted(interim_months + elected_months)

    main_rows = build_monthly_panel(geo["districts"], election_by_district, stable_months, elected_months)

    # Placebo: split the interim government's own span at its midpoint.
    mid = len(interim_months) // 2
    placebo_post_months = interim_months[mid:]
    placebo_rows = build_monthly_panel(geo["districts"], election_by_district, interim_months, placebo_post_months)

    main_results = all_treatments(main_rows)
    placebo_results = all_treatments(placebo_rows)
    main_simple = simple_group_means(main_rows)
    placebo_simple = simple_group_means(placebo_rows)

    # Legacy panel -- kept and clearly labelled, not used as the headline.
    legacy_main_rows = build_legacy_panel(geo["districts"], election_by_district, LEGACY_PRE_YEARS_MAIN,
                                           "elected", "Elected Government (2026–)")
    legacy_placebo_rows = build_legacy_panel(geo["districts"], election_by_district, LEGACY_PRE_YEARS_PLACEBO,
                                              "interim", "Interim Government (2024–2026)")
    legacy_main_did = two_way_fe_did(legacy_main_rows)
    legacy_placebo_did = two_way_fe_did(legacy_placebo_rows)
    legacy_main_simple = simple_group_means(legacy_main_rows)
    legacy_placebo_simple = simple_group_means(legacy_placebo_rows)

    scatter = []
    for dist in common_districts:
        e = election_by_district[dist]
        g = geo["districts"][dist]
        if e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        interim = g["by_era"].get("Interim Government (2024–2026)", {"value_bdt": 0, "count": 0})
        elected = g["by_era"].get("Elected Government (2026–)", {"value_bdt": 0, "count": 0})
        scatter.append({
            "district": dist, "bnp_vote_share": e["bnp_vote_share"], "bnp_seat_share": e["bnp_seat_share"],
            "bnp_won": 1 if (e["bnp_seat_share"] or 0) > 0.5 else 0,
            "interim_value_per_voter_bdt": round(interim["value_bdt"] / e["total_voters"], 2),
            "elected_value_per_voter_bdt": round(elected["value_bdt"] / e["total_voters"], 2),
            "total_voters": e["total_voters"],
        })

    payload = {
        "meta": {
            "hypothesis": "Districts that did not elect a BNP-led-alliance seat majority in "
                          "the Feb 2026 election are underrepresented in e-GP development spending.",
            "method": "Two-way fixed effects (district + month) panel difference-in-differences, "
                      "confined to the interim-and-later period so e-GP's own coverage expansion "
                      "isn't mistaken for a spending effect; asinh(value per registered voter); "
                      "cluster-robust SEs by district.",
            "districts_matched": len(common_districts),
            "stable_months": stable_months, "interim_months": interim_months, "elected_months": elected_months,
            "placebo_split_month": interim_months[mid] if interim_months else None,
        },
        "main": main_results, "main_simple": main_simple,
        "placebo": placebo_results, "placebo_simple": placebo_simple,
        "legacy": {
            "note": "The original design: 2015-2025 (or 2015-2023 for the placebo) averaged as the "
                    "pre-period. Confounded by e-GP's own decade-long coverage expansion (hybrid, "
                    "partial platform support before the interim government mandated its use) -- "
                    "kept here for transparency about the correction, not as evidence for anything.",
            "main_did": legacy_main_did, "main_did_simple": legacy_main_simple,
            "placebo_did": legacy_placebo_did, "placebo_did_simple": legacy_placebo_simple,
        },
        "district_scatter": scatter,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{len(common_districts)} districts matched; {len(interim_months)} interim months, "
          f"{len(elected_months)} elected months in the stable-coverage panel")
    for t in TREATMENTS:
        m, p = main_results[t], placebo_results[t]
        print(f"  {t:16s} main b={m['coefficient']:>8.4f} p={m['p_value']:.4f}   "
              f"placebo b={p['coefficient']:>8.4f} p={p['p_value']:.4f}")
    print(f"  simple DiD (Tk/voter): main={main_simple['did_bdt_per_voter']} placebo={placebo_simple['did_bdt_per_voter']}")
    print(f"legacy (coverage-confounded) design, kept for transparency: main b={legacy_main_did['coefficient']} "
          f"p={legacy_main_did['p_value']}; placebo b={legacy_placebo_did['coefficient']} p={legacy_placebo_did['p_value']}")
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
