#!/usr/bin/env python3
"""
Aggregate the polling-station-level 2026 election results (see
scrape_election_2026.py) up to three levels: union (the source's native
granularity), constituency (the actual electoral unit -- a seat is won or
lost as a whole), and district (the finest geography e-GP contract data
carries, and therefore the level build_political_spending.py's analysis
actually runs at).

District names here already match districts.py's canonical set exactly --
both this election source and our district geometry ultimately trace back
to the same government/BBS administrative boundary standard, so no alias
table is needed for this join, unlike the e-GP `district` field's mess of
pre/post-2018 spellings.

"Winner" at any level is whichever alliance holds the plurality of votes
aggregated to that level -- for a district containing several
constituencies, that is NOT the same question as "how many of this
district's seats did BNP win", which is also computed (seats_won) since
the two can disagree (a party can win a district's total vote while losing
one of its seats, or vice versa).

    python3 build_election.py <raw/election_2026_centers.csv.gz> <data/election_2026.json> <data/election_2026_unions.json>
"""
import csv
import gzip
import json
import sys
from collections import defaultdict

PARTIES = ["BNP-led alliance", "Independent", "Jamaat-led alliance", "Other party"]


def empty_tally():
    return {p: 0.0 for p in PARTIES}


def add_tally(dst, row):
    for p in PARTIES:
        v = row.get(p)
        if v:
            dst[p] += float(v)


def winner_of(tally):
    total = sum(tally.values())
    if total <= 0:
        return None, None, None
    ranked = sorted(tally.items(), key=lambda kv: -kv[1])
    first, second = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0)
    margin_pct = round((first[1] - second[1]) / total, 4)
    return first[0], round(first[1] / total, 4), margin_pct


def main(csv_path, out_district_path, out_union_path):
    constituencies = defaultdict(lambda: {"tally": empty_tally(), "total_voters": 0, "valid_votes": 0,
                                           "name": None, "district": None})
    districts = defaultdict(lambda: {"tally": empty_tally(), "total_voters": 0, "valid_votes": 0,
                                      "constituency_ids": set()})
    unions = defaultdict(lambda: {"tally": empty_tally(), "total_voters": 0, "valid_votes": 0,
                                   "district": None, "upazila": None, "union": None,
                                   "constituency_ids": set()})
    stations_read = 0
    national = empty_tally()
    national_voters = 0

    with gzip.open(csv_path, "rt", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            stations_read += 1
            cid = row["constituency_id"]
            dist = row["District"]
            ukey = (dist, row["Upazila"], row["Union"])
            voters = int(float(row["total_voters"])) if row.get("total_voters") else 0
            valid = int(float(row["valid_votes"])) if row.get("valid_votes") else 0

            c = constituencies[cid]
            c["name"] = c["name"] or row["constituency_name_en"]
            c["district"] = c["district"] or dist
            add_tally(c["tally"], row)
            c["total_voters"] += voters
            c["valid_votes"] += valid

            d = districts[dist]
            add_tally(d["tally"], row)
            d["total_voters"] += voters
            d["valid_votes"] += valid
            d["constituency_ids"].add(cid)

            u = unions[ukey]
            u["district"], u["upazila"], u["union"] = dist, row["Upazila"], row["Union"]
            add_tally(u["tally"], row)
            u["total_voters"] += voters
            u["valid_votes"] += valid
            u["constituency_ids"].add(cid)

            add_tally(national, row)
            national_voters += voters

    # Constituencies, finalised: winner/margin plus each district's seat count.
    const_out = []
    seats_won_by_district_party = defaultdict(lambda: defaultdict(int))
    for cid, c in constituencies.items():
        winner, share, margin = winner_of(c["tally"])
        seats_won_by_district_party[c["district"]][winner] += 1
        const_out.append({
            "constituency_id": cid, "name": c["name"], "district": c["district"],
            "votes": {p: round(v) for p, v in c["tally"].items()},
            "total_voters": c["total_voters"], "valid_votes": c["valid_votes"],
            "winner": winner, "winner_share": share, "margin": margin,
        })
    const_out.sort(key=lambda x: int(x["constituency_id"]))

    district_out = []
    for dist, d in districts.items():
        winner, share, margin = winner_of(d["tally"])
        seats = seats_won_by_district_party[dist]
        district_out.append({
            "district": dist,
            "votes": {p: round(v) for p, v in d["tally"].items()},
            "total_voters": d["total_voters"], "valid_votes": d["valid_votes"],
            "seats_total": len(d["constituency_ids"]),
            "seats_won": dict(seats),
            "vote_winner": winner, "vote_share": share, "vote_margin": margin,
            "bnp_vote_share": round(d["tally"]["BNP-led alliance"] / sum(d["tally"].values()), 4) if sum(d["tally"].values()) else None,
            "bnp_seat_share": round(seats.get("BNP-led alliance", 0) / len(d["constituency_ids"]), 4) if d["constituency_ids"] else None,
        })
    district_out.sort(key=lambda x: -x["total_voters"])

    union_out = []
    for (dist, upz, uni), u in unions.items():
        winner, share, margin = winner_of(u["tally"])
        union_out.append({
            "district": dist, "upazila": upz, "union": uni,
            "constituency_ids": sorted(u["constituency_ids"]),
            "votes": {p: round(v) for p, v in u["tally"].items()},
            "total_voters": u["total_voters"], "valid_votes": u["valid_votes"],
            "winner": winner, "winner_share": share, "margin": margin,
        })
    union_out.sort(key=lambda x: (x["district"], x["upazila"], x["union"]))

    nat_winner, nat_share, nat_margin = winner_of(national)
    seats_national = defaultdict(int)
    for c in const_out:
        seats_national[c["winner"]] += 1

    payload = {
        "meta": {
            "source": "https://interactive.netra.news/bangladesh-election-2026-map/ (Nazmul Ahasan & Aaqib Md. Shatil, netra.news)",
            "election_date": "2026-02", "results_as_of": "2026-03-11",
            "vote_data_source": "Bangladesh Election Commission publications",
            "boundary_source": "geoBoundaries (CC-BY 4.0)",
            "polling_stations_in_source": stations_read,
            "polling_stations_nationwide": 42779,
            "constituencies_covered": len(const_out), "constituencies_total": 300,
            "constituencies_suspended": [145, 279, 281],
            "constituencies_suspended_reason": "candidate death or court dispute (source's own note)",
            "districts_covered": len(district_out),
            "unions_covered": len(union_out),
            "note": "No Awami League column exists in the source: the party did not contest "
                    "this election, barred from registering after the 2024 political transition "
                    "(see eras.py). Votes split across BNP-led alliance, Jamaat-led alliance, "
                    "Independent, and Other party.",
        },
        "national": {
            "votes": {p: round(v) for p, v in national.items()}, "total_voters": national_voters,
            "seats": dict(seats_national), "vote_winner": nat_winner, "vote_share": nat_share,
        },
        "districts": district_out,
        "constituencies": const_out,
    }
    with open(out_district_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    with open(out_union_path, "w") as fh:
        json.dump({"meta": payload["meta"], "unions": union_out}, fh, ensure_ascii=False, indent=1)

    print(f"{stations_read:,} polling stations -> {len(const_out)} constituencies, "
          f"{len(district_out)} districts, {len(union_out)} unions")
    print(f"national: {dict(seats_national)}")
    print(f"wrote -> {out_district_path}, {out_union_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
