#!/usr/bin/env python3
"""
Did winning a district's seats in the February 2026 election change how
much e-GP contract money that district gets? The hypothesis under test:
districts that did NOT elect BNP-led-alliance MPs are underrepresented in
development spending -- and, per the brief, mere correlation isn't enough.

WHY THIS IS A PANEL DIFFERENCE-IN-DIFFERENCES, NOT A CORRELATION

A raw comparison of "BNP districts spend more" would be confounded by
everything that makes a district likely to elect BNP AND likely to receive
money for unrelated historical reasons (population, urbanisation, existing
infrastructure, which of the old regime's patronage networks it sat in).
Two-way fixed effects absorb both: a DISTRICT fixed effect absorbs
everything time-invariant about a district (size, geography, its whole
pre-2026 history) and a PERIOD fixed effect absorbs whatever moved every
district together in a given period (e-GP's own year-on-year adoption
curve, national budget cycles). What's left to identify the effect is only
the interaction -- does a district's spending move differently from its
OWN historical average, in the SAME period that every other district also
experienced, specifically because IT went BNP and others didn't. That is
the standard applied-econometrics way to get a causal-shaped estimate out
of observational panel data; it is not an experiment, and it is only valid
if the parallel-trends assumption holds -- which is exactly what the
placebo test below checks rather than assumes.

THE PLACEBO TEST IS THE MOST IMPORTANT PART OF THIS FILE

Run the identical regression, identical treatment classification (which
districts elected BNP in 2026), but pretend the "treatment" happened at
the START of the interim government (2024-08-08) instead of the real
election (2026-02-17) -- a period when the election hadn't happened yet
and nobody's seats were "won". If a spending gap between future-BNP and
future-non-BNP districts already opens up in this fake pre-period, the
post-election estimate cannot be trusted as caused by the election: it
would just mean these two groups of districts were already diverging for
some other reason, and 2026 happened to fall on one side of it. Both
numbers are reported side by side, not just the one that supports the
hypothesis.

DESIGN

  - Unit: district (64 -- the finest geography e-GP contracts carry).
  - Treatment: bnp_won = the district elected a BNP-led-alliance MP
    majority (seats_won), fixed at its actual 2026 value regardless of
    which period is being tested -- a real district characteristic, not
    something that changes across the placebo/real comparison.
  - Outcome: contract value per registered voter (total_voters from the
    election data is a real population denominator, better than raw value
    which just tracks district size), inverse-hyperbolic-sine transformed
    (asinh, not log) so district-years with zero recorded spending don't
    have to be dropped or padded with an arbitrary epsilon.
  - Panel: 11 yearly pre-periods (2015-2025 for the real test, 2015-2023
    for the placebo, so neither pre-period window contains any part of the
    period being tested) plus one lumped post-period built from eras.py's
    own era boundaries (not a partial calendar year), regressed with
    district and period fixed effects plus the bnp_won x post interaction.
  - Inference: OLS via numpy, standard errors clustered by district (the
    standard correction for serial correlation within a unit over time),
    t-test against a t(63) reference distribution -- 64 clusters, 1 fewer
    degree of freedom for the interaction term.

    python3 build_political_spending.py <data/geo.json> <data/election_2026.json> <out.json>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

from districts import display_name
from eras import era_of

PRE_YEARS_MAIN = [str(y) for y in range(2015, 2026)]     # 2015-2025, strictly before the election
POST_LABEL_MAIN = "elected"
PRE_YEARS_PLACEBO = [str(y) for y in range(2015, 2024)]  # 2015-2023, strictly before the interim government
POST_LABEL_PLACEBO = "interim"

MIN_VOTERS_FOR_INCLUSION = 1000  # guards against a data-join sliver, not a real filter at district level


def asinh(x):
    return np.log(x + np.sqrt(x ** 2 + 1))


def build_panel(geo_districts, election_by_district, pre_years, post_label, post_era_name):
    """One row per (district, period). period is either a calendar year
    (pre) or post_label (the lumped post-period, built from eras.py's own
    by_era bucket -- not a slice of a straddled calendar year)."""
    rows = []
    for dist, e in election_by_district.items():
        g = geo_districts.get(dist)
        if not g or e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        bnp_won = 1 if (e["bnp_seat_share"] or 0) > 0.5 else 0
        for y in pre_years:
            yb = g["by_year"].get(y, {"value_bdt": 0.0, "count": 0})
            rows.append({"district": dist, "period": y, "post": 0, "bnp_won": bnp_won,
                         "bnp_vote_share": e["bnp_vote_share"],
                         "value_bdt": yb["value_bdt"], "count": yb["count"],
                         "total_voters": e["total_voters"]})
        pb = g["by_era"].get(post_era_name, {"value_bdt": 0.0, "count": 0})
        rows.append({"district": dist, "period": post_label, "post": 1, "bnp_won": bnp_won,
                     "bnp_vote_share": e["bnp_vote_share"],
                     "value_bdt": pb["value_bdt"], "count": pb["count"],
                     "total_voters": e["total_voters"]})
    return rows


def two_way_fe_did(rows, treatment_key="bnp_won"):
    """OLS with district + period fixed effects (explicit dummies) plus a
    treatment x post interaction, cluster-robust (by district) SEs.
    Outcome: asinh(value per voter). Returns the interaction coefficient
    and its inferential summary."""
    districts = sorted({r["district"] for r in rows})
    periods = sorted({r["period"] for r in rows})
    dist_idx = {d: i for i, d in enumerate(districts)}
    per_idx = {p: i for i, p in enumerate(periods)}

    n = len(rows)
    # columns: intercept, (len(districts)-1) district dummies, (len(periods)-1) period dummies, interaction
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
        X[i, -1] = r[treatment_key] * r["post"]
        per_voter = r["value_bdt"] / r["total_voters"]
        y[i] = asinh(per_voter)
        cluster[i] = di

    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XtX_inv = np.linalg.pinv(X.T @ X)

    # Cluster-robust (CR1) sandwich variance, clustered by district.
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
        # exp(b)-1 approximates the proportional effect on the untransformed
        # scale for a log-like transform; reported as a rough magnitude, not
        # a precise percentage (asinh isn't exactly log).
        "approx_proportional_effect": round(float(np.exp(b) - 1), 4),
    }


def simple_group_means(rows):
    """The plain, easy-to-verify-by-hand version alongside the regression:
    average value-per-voter by (treatment, pre/post) cell, and the
    resulting 2x2 difference-in-differences -- no fixed effects, no log
    transform, just means."""
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


def main(geo_path, election_path, out_path):
    geo = json.load(open(geo_path))
    election = json.load(open(election_path))

    election_by_district = {}
    for d in election["districts"]:
        election_by_district[display_name(d["district"])] = d

    common_districts = sorted(set(election_by_district) & set(geo["districts"]))

    main_rows = build_panel(geo["districts"], election_by_district, PRE_YEARS_MAIN, POST_LABEL_MAIN,
                             "Elected Government (2026–)")
    placebo_rows = build_panel(geo["districts"], election_by_district, PRE_YEARS_PLACEBO, POST_LABEL_PLACEBO,
                                "Interim Government (2024–2026)")

    main_did = two_way_fe_did(main_rows)
    placebo_did = two_way_fe_did(placebo_rows)
    main_simple = simple_group_means(main_rows)
    placebo_simple = simple_group_means(placebo_rows)

    # Continuous-treatment robustness check: bnp_vote_share instead of the
    # binary bnp_won -- run on BOTH panels, not just the one that might look
    # more favourable. A robustness check reported alone, without its own
    # placebo, is exactly the kind of selective reporting this whole file
    # exists to avoid.
    continuous_did = two_way_fe_did(main_rows, treatment_key="bnp_vote_share")
    continuous_placebo_did = two_way_fe_did(placebo_rows, treatment_key="bnp_vote_share")

    # Per-district scatter for the dashboard: BNP vote share vs. how much
    # a district's per-voter spending changed from the interim to the
    # elected era (raw, not fixed-effects-adjusted -- for the chart, the
    # regression above is the actual test).
    scatter = []
    for dist in common_districts:
        e = election_by_district[dist]
        g = geo["districts"][dist]
        if e["total_voters"] < MIN_VOTERS_FOR_INCLUSION:
            continue
        interim = g["by_era"].get("Interim Government (2024–2026)", {"value_bdt": 0, "count": 0})
        elected = g["by_era"].get("Elected Government (2026–)", {"value_bdt": 0, "count": 0})
        interim_pv = interim["value_bdt"] / e["total_voters"]
        elected_pv = elected["value_bdt"] / e["total_voters"]
        scatter.append({
            "district": dist, "bnp_vote_share": e["bnp_vote_share"], "bnp_seat_share": e["bnp_seat_share"],
            "bnp_won": 1 if (e["bnp_seat_share"] or 0) > 0.5 else 0,
            "interim_value_per_voter_bdt": round(interim_pv, 2), "elected_value_per_voter_bdt": round(elected_pv, 2),
            "total_voters": e["total_voters"],
        })

    payload = {
        "meta": {
            "hypothesis": "Districts that did not elect a BNP-led-alliance seat majority in "
                          "the Feb 2026 election are underrepresented in e-GP development spending.",
            "method": "Two-way fixed effects (district + period) panel difference-in-differences, "
                      "asinh(value per registered voter), cluster-robust SEs by district.",
            "districts_matched": len(common_districts),
            "pre_years_main": PRE_YEARS_MAIN, "post_period_main": POST_LABEL_MAIN,
            "pre_years_placebo": PRE_YEARS_PLACEBO, "post_period_placebo": POST_LABEL_PLACEBO,
        },
        "main_did": main_did,
        "main_did_simple": main_simple,
        "placebo_did": placebo_did,
        "placebo_did_simple": placebo_simple,
        "continuous_vote_share_did": continuous_did,
        "continuous_vote_share_placebo_did": continuous_placebo_did,
        "district_scatter": scatter,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{len(common_districts)} districts matched between election and e-GP data")
    print(f"MAIN (post-election) DiD: b={main_did['coefficient']} se={main_did['std_error']} "
          f"p={main_did['p_value']} (n={main_did['n_obs']} obs, {main_did['n_districts']} clusters)")
    print(f"  simple group-means DiD: Tk {main_simple['did_bdt_per_voter']}/voter")
    print(f"PLACEBO (pre-election) DiD: b={placebo_did['coefficient']} se={placebo_did['std_error']} "
          f"p={placebo_did['p_value']}")
    print(f"  simple group-means DiD: Tk {placebo_simple['did_bdt_per_voter']}/voter")
    print(f"continuous vote-share (post-election): b={continuous_did['coefficient']} p={continuous_did['p_value']}")
    print(f"continuous vote-share (placebo):        b={continuous_placebo_did['coefficient']} p={continuous_placebo_did['p_value']}")
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
