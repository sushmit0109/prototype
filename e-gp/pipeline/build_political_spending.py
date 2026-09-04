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
from district_divisions import division_of
from census_population import population_of

MIN_VOTERS_FOR_INCLUSION = 1000  # guards against a data-join sliver, not a real filter at district level
TREATMENTS = ["bnp_won", "bnp_vote_share", "bnp_seat_share"]

# The primary placebo split: post = this month onward, within the interim
# government's span. Two reasons this beats an even midpoint split:
# (1) it's the more targeted test of anticipatory favouritism -- if a
#     government due to lose office rewarded its expected base before an
#     election it saw coming, that would concentrate in the run-up to the
#     vote, not spread evenly across the whole interim period;
# (2) Bangladesh's fiscal year ends 30 June, and this portal shows a real,
#     large June spend spike every year (see Finding 01) -- the two-way
#     fixed effects give every calendar month its own dummy, so that spike
#     is absorbed for either split choice, but keeping it entirely on one
#     side (here, inside "pre") makes the comparison legible without
#     leaning on that argument at all. A November split does that; a
#     midpoint split (May) does not -- May-Feb includes the June 2025 spike
#     inside "post" instead. The midpoint version is kept below as a
#     secondary check, not the headline.
PLACEBO_SPLIT = "2025-11"

LEGACY_PRE_YEARS_MAIN = [str(y) for y in range(2015, 2026)]
LEGACY_PRE_YEARS_PLACEBO = [str(y) for y in range(2015, 2024)]


def asinh(x):
    return np.log(x + np.sqrt(x ** 2 + 1))


def district_category(e):
    """Swept out (BNP won zero of the district's seats), swept in (BNP won
    every seat), or split -- distinct from the continuous seat/vote share,
    since the hypothesis "shut out entirely" is not obviously the same
    claim as "won a below-average share"."""
    s = e["bnp_seat_share"]
    if s is None:
        return None
    if s == 0:
        return "none"
    if s == 1:
        return "all"
    return "some"


def treatment_values(e):
    cat = district_category(e)
    return {
        "bnp_won": 1 if (e["bnp_seat_share"] or 0) > 0.5 else 0,
        "bnp_vote_share": e["bnp_vote_share"],
        "bnp_seat_share": e["bnp_seat_share"],
        "bnp_some": 1 if cat == "some" else 0,
        "bnp_all": 1 if cat == "all" else 0,
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
                         "total_voters": e["total_voters"], "population": population_of(dist)})
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


def two_way_fe_did(rows, treatment_key="bnp_won", division_lookup=None, denom_key="total_voters"):
    """OLS with district + period fixed effects (explicit dummies) plus a
    treatment x post interaction, cluster-robust (by district) SEs.

    If division_lookup is given (district -> division name), also adds a
    division x period fixed effect for every division -- a control for a
    region rolling out on its own time-varying trend (a coastal-embankment
    programme, a char-land scheme) for reasons that have nothing to do
    with the election, which plain district + period fixed effects cannot
    tell apart from a real district-level political effect. This is the
    single most important robustness check when a treatment group is
    itself geographically clustered (see build_political_spending.py's
    module docstring on the "some vs none" result).

    denom_key picks what "per capita" means: "total_voters" (the election
    data's registered-voter count, the default so far) or "population"
    (BBS's 2022 census count, from census_population.py). Voter rolls are
    an imperfect population proxy -- registration drives, out-migration,
    and how recently a roll was updated all move it for reasons that have
    nothing to do with development need. Running the same regression on
    both is a check that the result isn't an artifact of which denominator
    was chosen. Rows without a value for denom_key are dropped rather than
    silently zero-filled."""
    rows = [r for r in rows if r.get(denom_key)]
    districts = sorted({r["district"] for r in rows})
    periods = sorted({r["period"] for r in rows})
    dist_idx = {d: i for i, d in enumerate(districts)}
    per_idx = {p: i for i, p in enumerate(periods)}

    divisions = sorted({division_lookup(d) for d in districts}) if division_lookup else []
    div_idx = {dv: i for i, dv in enumerate(divisions)}
    n_div_period = (len(divisions) - 1) * (len(periods) - 1) if divisions else 0

    n = len(rows)
    k = 1 + (len(districts) - 1) + (len(periods) - 1) + n_div_period + 1
    X = np.zeros((n, k))
    y = np.zeros(n)
    cluster = np.zeros(n, dtype=int)

    div_period_col0 = 1 + (len(districts) - 1) + (len(periods) - 1)
    for i, r in enumerate(rows):
        X[i, 0] = 1.0
        di = dist_idx[r["district"]]
        if di > 0:
            X[i, 1 + di - 1] = 1.0
        pi = per_idx[r["period"]]
        if pi > 0:
            X[i, 1 + (len(districts) - 1) + pi - 1] = 1.0
        if divisions:
            dvi = div_idx[division_lookup(r["district"])]
            if dvi > 0 and pi > 0:
                X[i, div_period_col0 + (dvi - 1) * (len(periods) - 1) + (pi - 1)] = 1.0
        X[i, -1] = (r[treatment_key] or 0) * r["post"]
        per_capita = r["value_bdt"] / r[denom_key]
        y[i] = asinh(per_capita)
        cluster[i] = di

    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XtX_inv = np.linalg.pinv(X.T @ X)
    rank_deficient = rank < min(X.shape)

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
        "division_controlled": bool(divisions),
        "n_divisions": len(divisions) if divisions else None,
        "rank_deficient": bool(rank_deficient),
        "denominator": denom_key,
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


def all_treatments(rows, denom_key="total_voters"):
    return {t: two_way_fe_did(rows, treatment_key=t, denom_key=denom_key) for t in TREATMENTS}


def category_comparisons(geo_districts, election_by_district, months, post_months):
    """Two separate binary comparisons against the same reference group
    (districts BNP won zero seats in) rather than one three-level
    regression -- "some vs none" and "all vs none" use naturally different
    subsamples (the "all" group is tiny, 3 districts; a shared design would
    obscure that rather than surface it)."""
    none_or_some = {d: e for d, e in election_by_district.items() if district_category(e) in ("none", "some")}
    none_or_all = {d: e for d, e in election_by_district.items() if district_category(e) in ("none", "all")}

    some_rows = build_monthly_panel(geo_districts, none_or_some, months, post_months)
    all_rows = build_monthly_panel(geo_districts, none_or_all, months, post_months)

    def simple_binary_means(rows, key):
        cells = defaultdict(list)
        for r in rows:
            cells[(r[key], r["post"])].append(r["value_bdt"] / r["total_voters"])
        try:
            did = ((np.mean(cells[(1, 1)]) - np.mean(cells[(1, 0)])) - (np.mean(cells[(0, 1)]) - np.mean(cells[(0, 0)])))
        except KeyError:
            did = None
        return round(float(did), 2) if did is not None else None

    return {
        "some_vs_none": {
            "n_districts": len(none_or_some), "n_some": sum(1 for e in none_or_some.values() if district_category(e) == "some"),
            "regression": two_way_fe_did(some_rows, treatment_key="bnp_some"),
            "regression_division_controlled": two_way_fe_did(some_rows, treatment_key="bnp_some", division_lookup=division_of),
            "regression_population_denominator": two_way_fe_did(some_rows, treatment_key="bnp_some", denom_key="population"),
            "simple_did_bdt_per_voter": simple_binary_means(some_rows, "bnp_some"),
        },
        "all_vs_none": {
            "n_districts": len(none_or_all), "n_all": sum(1 for e in none_or_all.values() if district_category(e) == "all"),
            "regression": two_way_fe_did(all_rows, treatment_key="bnp_all"),
            "regression_division_controlled": two_way_fe_did(all_rows, treatment_key="bnp_all", division_lookup=division_of),
            "regression_population_denominator": two_way_fe_did(all_rows, treatment_key="bnp_all", denom_key="population"),
            "simple_did_bdt_per_voter": simple_binary_means(all_rows, "bnp_all"),
        },
    }


def category_descriptive(geo_districts, election_by_district):
    """Plain description, no fixed effects: for each of the three groups
    (shut out / split / swept), how many districts, and what interim vs.
    elected spending per voter looks like on average."""
    groups = defaultdict(list)
    for dist, e in election_by_district.items():
        cat = district_category(e)
        g = geo_districts.get(dist)
        if not cat or not g or e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        interim = g["by_era"].get("Interim Government (2024–2026)", {"value_bdt": 0, "count": 0})
        elected = g["by_era"].get("Elected Government (2026–)", {"value_bdt": 0, "count": 0})
        groups[cat].append({
            "district": dist,
            "interim_value_per_voter_bdt": interim["value_bdt"] / e["total_voters"],
            "elected_value_per_voter_bdt": elected["value_bdt"] / e["total_voters"],
        })

    out = {}
    for cat in ["none", "some", "all"]:
        rows = groups.get(cat, [])
        if not rows:
            continue
        interim_avg = float(np.mean([r["interim_value_per_voter_bdt"] for r in rows]))
        elected_avg = float(np.mean([r["elected_value_per_voter_bdt"] for r in rows]))
        out[cat] = {
            "n_districts": len(rows), "districts": sorted(r["district"] for r in rows),
            "avg_interim_value_per_voter_bdt": round(interim_avg, 2),
            "avg_elected_value_per_voter_bdt": round(elected_avg, 2),
            "avg_change_bdt_per_voter": round(elected_avg - interim_avg, 2),
        }
    return out


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

    # Primary placebo: split the interim government's own span at
    # PLACEBO_SPLIT (2025-11) -- see the comment on that constant for why
    # this beats an even midpoint split.
    placebo_post_months = [m for m in interim_months if m >= PLACEBO_SPLIT]
    placebo_rows = build_monthly_panel(geo["districts"], election_by_district, interim_months, placebo_post_months)

    # Secondary placebo, kept for robustness rather than as the headline:
    # the same interim-only span split at its even midpoint instead.
    mid = len(interim_months) // 2
    placebo_mid_post_months = interim_months[mid:]
    placebo_mid_rows = build_monthly_panel(geo["districts"], election_by_district, interim_months, placebo_mid_post_months)

    main_results = all_treatments(main_rows)
    placebo_results = all_treatments(placebo_rows)
    placebo_midpoint_results = all_treatments(placebo_mid_rows)
    main_simple = simple_group_means(main_rows)
    placebo_simple = simple_group_means(placebo_rows)
    placebo_midpoint_simple = simple_group_means(placebo_mid_rows)

    # Robustness check: same regressions, spending scaled by 2022 census
    # population instead of registered voters (see census_population.py's
    # docstring for why the two denominators can disagree).
    main_results_population = all_treatments(main_rows, denom_key="population")
    placebo_results_population = all_treatments(placebo_rows, denom_key="population")

    # Shut out entirely vs. swept entirely vs. split -- is "some" the same
    # story as "all", or does collapsing to a share hide something the
    # extremes don't?
    category_descriptive_stats = category_descriptive(geo["districts"], election_by_district)
    category_main = category_comparisons(geo["districts"], election_by_district, stable_months, elected_months)
    category_placebo = category_comparisons(geo["districts"], election_by_district, interim_months, placebo_post_months)
    category_placebo_midpoint = category_comparisons(geo["districts"], election_by_district, interim_months, placebo_mid_post_months)

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
            "placebo_split_month": PLACEBO_SPLIT,
            "placebo_midpoint_split_month": interim_months[mid] if interim_months else None,
        },
        "main": main_results, "main_simple": main_simple,
        "placebo": placebo_results, "placebo_simple": placebo_simple,
        "placebo_midpoint": placebo_midpoint_results, "placebo_midpoint_simple": placebo_midpoint_simple,
        "robustness": {
            "note": "Same regressions with two independent checks a real district-level "
                    "political effect should survive: (1) scaling spending by 2022 census "
                    "population instead of registered voters (census_population.py); "
                    "(2) adding a division x period fixed effect so a region rolling out its "
                    "own unrelated programme on its own schedule isn't mistaken for a "
                    "district-level political effect (district_divisions.py). Population-scaled "
                    "results sit here as main_population/placebo_population; the division-controlled "
                    "regression sits alongside each category result as regression_division_controlled.",
            "main_population": main_results_population,
            "placebo_population": placebo_results_population,
        },
        "by_category": {
            "descriptive": category_descriptive_stats,
            "main": category_main, "placebo": category_placebo, "placebo_midpoint": category_placebo_midpoint,
        },
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
    print(f"placebo split (primary, run-up to election): {PLACEBO_SPLIT}; "
          f"placebo split (secondary, midpoint): {interim_months[mid]}")
    for t in TREATMENTS:
        m, p, pm = main_results[t], placebo_results[t], placebo_midpoint_results[t]
        print(f"  {t:16s} main b={m['coefficient']:>8.4f} p={m['p_value']:.4f}   "
              f"placebo b={p['coefficient']:>8.4f} p={p['p_value']:.4f}   "
              f"placebo(midpoint) b={pm['coefficient']:>8.4f} p={pm['p_value']:.4f}")
    print(f"  simple DiD (Tk/voter): main={main_simple['did_bdt_per_voter']} "
          f"placebo={placebo_simple['did_bdt_per_voter']} placebo(midpoint)={placebo_midpoint_simple['did_bdt_per_voter']}")
    print(f"legacy (coverage-confounded) design, kept for transparency: main b={legacy_main_did['coefficient']} "
          f"p={legacy_main_did['p_value']}; placebo b={legacy_placebo_did['coefficient']} p={legacy_placebo_did['p_value']}")

    print("\nrobustness -- census population denominator instead of registered voters:")
    for t in TREATMENTS:
        mp, pp = main_results_population[t], placebo_results_population[t]
        print(f"  {t:16s} main b={mp['coefficient']:>8.4f} p={mp['p_value']:.4f}   "
              f"placebo b={pp['coefficient']:>8.4f} p={pp['p_value']:.4f}")

    print("\nby category (shut out / split / swept):")
    for cat, stats_ in category_descriptive_stats.items():
        print(f"  {cat:5s} n={stats_['n_districts']:3d}  interim=Tk{stats_['avg_interim_value_per_voter_bdt']:>9,.0f}/voter  "
              f"elected=Tk{stats_['avg_elected_value_per_voter_bdt']:>9,.0f}/voter  change=Tk{stats_['avg_change_bdt_per_voter']:>9,.0f}/voter")
    for label, cat_result in [("real", category_main), ("placebo", category_placebo), ("placebo(midpoint)", category_placebo_midpoint)]:
        sv, av = cat_result["some_vs_none"], cat_result["all_vs_none"]
        print(f"  {label:18s} some-vs-none: b={sv['regression']['coefficient']:>8.4f} p={sv['regression']['p_value']:.4f} "
              f"(n={sv['n_districts']}, {sv['n_some']} 'some')   "
              f"all-vs-none: b={av['regression']['coefficient']:>8.4f} p={av['regression']['p_value']:.4f} "
              f"(n={av['n_districts']}, {av['n_all']} 'all' -- tiny sample)")
        svd, avd = sv["regression_division_controlled"], av["regression_division_controlled"]
        print(f"  {'  +division FE':18s} some-vs-none: b={svd['coefficient']:>8.4f} p={svd['p_value']:.4f} "
              f"(rank_deficient={svd['rank_deficient']})   "
              f"all-vs-none: b={avd['coefficient']:>8.4f} p={avd['p_value']:.4f} (rank_deficient={avd['rank_deficient']})")
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
