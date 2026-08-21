#!/usr/bin/env python3
"""
The actual cross-affiliation signal: which beneficial owners appear on more
than one company's award-detail page.

Company-name matching (entity.py, flag_debarred_awards.py) already taught
one lesson about matching on a small, repetitive vocabulary -- and a
person's name is an even smaller, more collision-prone namespace than a
company's. "Md. Rahman" is nothing like distinctive enough to conclude two
companies share an owner; it just means Bangladesh has a lot of people
named Rahman. So this applies the same discipline that fixed the debarment
false-positive, adapted to names instead of companies:

1. Normalise conservatively: lowercase, whitespace-collapsed, common
   honorific prefixes stripped (md/mr/mrs/ms/dr/mohammad/mohammed as a
   leading token) -- NOT stripped down to a bare surname, since that's
   exactly the over-aggressive move that caused the company-name problem.
2. Require at least three space-separated tokens in the normalised name.
   Two-token South Asian names ("Md Karim") are common enough on their own
   to be worthless as a match key; a fuller name is a real, if still
   imperfect, reduction in collision risk.
3. Still not proof. Every group below is people worth checking by hand
   against the source, not a finding.

Input is scrape_award_details.py's output: one representative contract per
(sampled) vendor, so this only sees ownership for however many of the
56,330 total vendors were actually crawled -- check the meta block for
coverage before reading too much into an empty result for some vendor.

    python3 build_ownership.py <raw/award_details.jsonl> <out.json>
"""
import json
import re
import sys
from collections import defaultdict

HONORIFIC_RE = re.compile(r"^(md|mr|mrs|ms|dr|mohammad|mohammed|engr|eng)\.?\s+")
WS_RE = re.compile(r"\s+")
MIN_TOKENS = 3


def normalize_owner(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = WS_RE.sub(" ", n)
    n = HONORIFIC_RE.sub("", n)
    return n


def main(raw_path, out_path):
    with open(raw_path) as fh:
        records = [json.loads(line) for line in fh]

    with_owners = [r for r in records if r["beneficial_owners"]]
    with_tenderer_id = [r for r in records if r.get("tenderer_id")]

    owner_to_companies = defaultdict(dict)  # normalized owner -> {company_key: record}
    for r in with_owners:
        for owner in r["beneficial_owners"]:
            key = normalize_owner(owner["name"])
            if len(key.split()) < MIN_TOKENS:
                continue
            owner_to_companies[key].setdefault(r["company_key"], {
                "company": r["awarded_to"],
                "tenderer_id": r.get("tenderer_id"),
                "owner_name_as_shown": owner["name"],
                "designation": owner["designation"],
                "ownership_pct": owner["ownership_pct"],
            })

    shared = [
        {
            "owner_key": owner_key,
            "companies": list(companies.values()),
            "distinct_companies": len(companies),
        }
        for owner_key, companies in owner_to_companies.items()
        if len(companies) >= 2
    ]
    shared.sort(key=lambda s: -s["distinct_companies"])

    # A tenderer_id shared across different company names is a much stronger
    # signal than a name match -- it's the portal's own identifier, not ours.
    tid_to_companies = defaultdict(set)
    for r in with_tenderer_id:
        tid_to_companies[r["tenderer_id"]].add(r["company_key"])
    tenderer_id_aliases = [
        {"tenderer_id": tid, "company_keys": sorted(keys)}
        for tid, keys in tid_to_companies.items() if len(keys) >= 2
    ]

    payload = {
        "meta": {
            "vendors_sampled": len(records),
            "vendors_with_owner_data": len(with_owners),
            "vendors_with_tenderer_id": len(with_tenderer_id),
            "owner_data_coverage": round(len(with_owners) / len(records), 3) if records else 0,
        },
        "shared_owner_groups": shared,
        "tenderer_id_aliases": tenderer_id_aliases,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"{len(records)} vendors sampled, {len(with_owners)} with ownership data "
          f"({100*len(with_owners)/len(records):.0f}%)")
    print(f"{len(shared)} owner names appear on 2+ distinct companies")
    print(f"{len(tenderer_id_aliases)} tenderer IDs appear under 2+ distinct company names")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
