#!/usr/bin/env python3
"""
Which vendors are growing fastest, which have gone from nothing to major
in just a few years, and -- the sharper question -- whether a beneficial
owner already known (build_ownership.py) to sit on more than one company
shows a *combined* footprint across all of them growing even where no
single company on its own looks remarkable. That last case is the one
this analysis exists for: one person spreading a growing volume of
government business across two or three corporate shells reads as several
small, unremarkable vendors individually, and only as a pattern once their
ownership is known and their numbers are added together.

Two independent, deliberately narrow tests -- narrow because a growth
ratio computed off a near-zero base is exactly the kind of number that
looks dramatic and means nothing, the same lesson the debarment
false-positive (flag_debarred_awards.py) and the plan/award join
false-positive (build_plan_vs_actual.py) already taught this pipeline the
hard way:

1. Fastest growers: baseline period 2016-2019 vs. recent period
   2024-2026, per-year averages so the different window lengths are
   comparable, and a floor on the baseline (a real prior footprint must
   already exist) before any ratio is trusted at all.
2. New dominants: literally zero baseline activity, first contract no
   earlier than 2021, but already substantial in the recent window --
   the "appeared from nowhere and immediately won big" shape, which is a
   distinct pattern from organic growth and arguably the more suspicious
   one.

Both are cross-referenced against data/ownership.json's shared-owner
groups (itself already filtered for name-collision risk -- see that
file's docstring) to flag any riser that is one piece of a multi-company
owner's portfolio, and the owner groups themselves get their combined
trajectory computed the same way.

Company identity uses entity.normalize_company -- the same key
pick_vendor_samples.py uses to build the ownership sample, so this joins
against data/ownership.json directly by re-normalising its company names.

    python3 build_growth.py <data/contracts/> <data/ownership.json> <out.json>
"""
import glob
import json
import os
import sys
from collections import Counter, defaultdict

from entity import normalize_company
from eras import ERA_NAMES, era_of

BASELINE_YEARS = ["2016", "2017", "2018", "2019"]
RECENT_YEARS = ["2024", "2025", "2026"]
CRORE = 1e7

MIN_BASELINE_VALUE_BDT = 1 * CRORE      # a real prior footprint, not noise
MIN_BASELINE_COUNT = 3
MIN_GROWTH_RATIO = 3.0                  # at least 3x per-year average to be worth listing

NEW_DOMINANT_FIRST_YEAR_FLOOR = "2021"  # must not appear before this to count as "new"
NEW_DOMINANT_MIN_RECENT_VALUE_BDT = 10 * CRORE

TOP_N = 40


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def new_vendor():
    return {
        "display": None,
        "by_year": defaultdict(lambda: {"count": 0, "value_bdt": 0.0}),
        "first_year": None,
        "recent_ministries": Counter(),
        "recent_offices": Counter(),
    }


def main(contracts_dir, ownership_path, out_path):
    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)

    vendors = defaultdict(new_vendor)
    for c in load_contracts(contracts_dir):
        key = normalize_company(c.get("awarded_to"))
        if not key:
            continue
        v = vendors[key]
        v["display"] = v["display"] or c["awarded_to"]
        year = (c.get("contract_signing_date") or "")[:4]
        val = c.get("value_bdt") or 0
        if year:
            yb = v["by_year"][year]
            yb["count"] += 1
            yb["value_bdt"] += val
            if v["first_year"] is None or year < v["first_year"]:
                v["first_year"] = year
            if year in RECENT_YEARS:
                mid = c.get("ministry_id")
                if mid is not None:
                    v["recent_ministries"][dims["ministries"][mid]] += 1
                pid = c.get("procuring_entity_id")
                if pid is not None:
                    v["recent_offices"][dims["procuring_entities"][pid]] += 1

    def period(v, years):
        cnt = sum(v["by_year"][y]["count"] for y in years if y in v["by_year"])
        val = sum(v["by_year"][y]["value_bdt"] for y in years if y in v["by_year"])
        return cnt, val

    def recent_era_split(v):
        out = {e: {"count": 0, "value_bdt": 0.0} for e in ERA_NAMES}
        for y in RECENT_YEARS:
            if y not in v["by_year"]:
                continue
            # a whole-year bucket can straddle an era boundary; attribute it
            # to the era holding 1 July of that year, close enough for a
            # yearly-resolution series and far simpler than re-deriving this
            # from per-contract dates a second time.
            era = era_of(f"{y}-07-01")
            if era:
                out[era]["count"] += v["by_year"][y]["count"]
                out[era]["value_bdt"] += v["by_year"][y]["value_bdt"]
        return out

    def base_entry(key, v):
        base_cnt, base_val = period(v, BASELINE_YEARS)
        rec_cnt, rec_val = period(v, RECENT_YEARS)
        top_office = v["recent_offices"].most_common(1)
        top_office_share = (top_office[0][1] / rec_cnt) if rec_cnt and top_office else None
        return {
            "company": v["display"], "company_key": key,
            "first_year": v["first_year"],
            "baseline_value_bdt": round(base_val, 2), "baseline_count": base_cnt,
            "recent_value_bdt": round(rec_val, 2), "recent_count": rec_cnt,
            "recent_by_era": {e: {"count": s["count"], "value_bdt": round(s["value_bdt"], 2)}
                              for e, s in recent_era_split(v).items()},
            "recent_distinct_ministries": len(v["recent_ministries"]),
            "recent_top_ministry": v["recent_ministries"].most_common(1)[0][0] if v["recent_ministries"] else None,
            "recent_distinct_offices": len(v["recent_offices"]),
            "recent_top_office": top_office[0][0] if top_office else None,
            "recent_top_office_share": round(top_office_share, 4) if top_office_share else None,
        }, base_cnt, base_val, rec_cnt, rec_val

    growers, new_dominants = [], []
    for key, v in vendors.items():
        entry, base_cnt, base_val, rec_cnt, rec_val = base_entry(key, v)

        if base_val >= MIN_BASELINE_VALUE_BDT and base_cnt >= MIN_BASELINE_COUNT:
            base_avg = base_val / len(BASELINE_YEARS)
            rec_avg = rec_val / len(RECENT_YEARS)
            ratio = rec_avg / base_avg if base_avg else None
            if ratio and ratio >= MIN_GROWTH_RATIO:
                growers.append({**entry, "growth_ratio_value": round(ratio, 2)})

        if (base_cnt == 0 and rec_val >= NEW_DOMINANT_MIN_RECENT_VALUE_BDT
                and v["first_year"] and v["first_year"] >= NEW_DOMINANT_FIRST_YEAR_FLOOR):
            new_dominants.append(entry)

    growers.sort(key=lambda x: -x["growth_ratio_value"])
    new_dominants.sort(key=lambda x: -x["recent_value_bdt"])
    growers = growers[:TOP_N]
    new_dominants = new_dominants[:TOP_N]

    # Cross-reference against known shared-owner groups: does a riser sit
    # inside one, and -- the sharper question -- what does that owner's
    # *combined* portfolio look like even for owners whose individual
    # companies didn't make either list above.
    owner_groups_out = []
    key_to_owners = defaultdict(list)
    try:
        with open(ownership_path) as fh:
            ownership = json.load(fh)
    except FileNotFoundError:
        ownership = {"shared_owner_groups": []}

    for group in ownership.get("shared_owner_groups", []):
        member_keys = []
        combined_base_val = combined_rec_val = 0.0
        combined_base_cnt = combined_rec_cnt = 0
        ministries = Counter()
        for company in group["companies"]:
            ck = normalize_company(company["company"])
            if not ck or ck not in vendors:
                continue
            member_keys.append(ck)
            bc, bv = period(vendors[ck], BASELINE_YEARS)
            rc, rv = period(vendors[ck], RECENT_YEARS)
            combined_base_val += bv
            combined_rec_val += rv
            combined_base_cnt += bc
            combined_rec_cnt += rc
            ministries.update(vendors[ck]["recent_ministries"])
        if len(member_keys) < 2:
            continue
        base_avg = combined_base_val / len(BASELINE_YEARS)
        rec_avg = combined_rec_val / len(RECENT_YEARS)
        ratio = round(rec_avg / base_avg, 2) if base_avg else None
        owner_groups_out.append({
            "owner_key": group["owner_key"],
            "owner_name": group["companies"][0]["owner_name_as_shown"],
            "companies": [{"company": c["company"], "designation": c.get("designation")}
                          for c in group["companies"]],
            "member_companies_matched": len(member_keys),
            "combined_baseline_value_bdt": round(combined_base_val, 2),
            "combined_recent_value_bdt": round(combined_rec_val, 2),
            "combined_recent_count": combined_rec_cnt,
            "combined_growth_ratio_value": ratio,
            "combined_recent_distinct_ministries": len(ministries),
        })
        for ck in member_keys:
            key_to_owners[ck].append(group["owner_key"])

    owner_groups_out.sort(key=lambda g: -g["combined_recent_value_bdt"])

    for entry in growers + new_dominants:
        entry["shared_owner_keys"] = key_to_owners.get(entry["company_key"], [])

    payload = {
        "meta": {
            "baseline_years": BASELINE_YEARS, "recent_years": RECENT_YEARS,
            "min_baseline_value_bdt": MIN_BASELINE_VALUE_BDT,
            "min_growth_ratio": MIN_GROWTH_RATIO,
            "new_dominant_min_recent_value_bdt": NEW_DOMINANT_MIN_RECENT_VALUE_BDT,
            "new_dominant_first_year_floor": NEW_DOMINANT_FIRST_YEAR_FLOOR,
            "vendors_scanned": len(vendors),
            "ownership_groups_checked": len(ownership.get("shared_owner_groups", [])),
        },
        "top_growers": growers,
        "new_dominants": new_dominants,
        "owner_group_growth": owner_groups_out[:TOP_N],
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{len(vendors):,} vendors scanned -> {len(growers)} fast growers, "
          f"{len(new_dominants)} new dominants, {len(owner_groups_out)} multi-company owner groups matched")
    for g in growers[:5]:
        print(f"  {g['growth_ratio_value']:>6.1f}x  {g['company'][:50]}")
    for o in owner_groups_out[:5]:
        print(f"  combined {o['combined_recent_value_bdt']/CRORE:>8,.0f} cr  "
              f"({o['member_companies_matched']} companies)  {o['owner_name']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
