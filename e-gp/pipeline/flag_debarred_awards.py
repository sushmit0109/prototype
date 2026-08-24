#!/usr/bin/env python3
"""
Cross-reference: which debarred companies won contracts anyway?

This is the point of building one dataset out of six search pages. It
matches each contract's awardee against the debarment register on
normalised company name (entity.normalize_company) and, where both dates are
known, checks the contract's signing date against the debarment window:

- active_debarment_violation: signed while the debarment was in force --
  should be structurally impossible, so this is the headline flag.
- post_debarment_award: signed after the debarment period ended --
  recidivism tracking, not a violation by itself.

Contracts signed before a debarment window are not flagged.

A NAME MATCH ALONE IS NOT ENOUGH TO FLAG. A first full-data run of this
script, before the two checks below existed, produced 8,707 "active
violation" flags -- and the top of that list was company_key "khan
enterprise" alone, 637 times. "Khan" is one of the most common surnames in
Bangladesh and "Enterprise" a generic small-firm suffix; the debarment
register has exactly one such firm, at one Mirpur, Dhaka address, but that
name string appears on 1,984 contracts in 15+ districts nationwide -- plainly
dozens of unrelated small businesses that happen to share a name pattern,
not one company evading a ban. Publishing that number as a corruption
finding would have been a real, public false accusation. So a match is only
flagged if BOTH hold:

1. District corroboration: the contract's district matches a district taken
   from the debarment record's own address field. (Cuts khan-enterprise from
   1,984 to 277 -- better, not sufficient alone in a district the size of
   Dhaka.)
2. Not generic nationwide: the company_key must not appear, as an awardee,
   in more than MAX_DISTRICT_SPREAD districts across the *entire* contracts
   corpus (not just the matched ones). A real single firm doing government
   work plausibly operates in a handful of districts; a name spread across
   15+ is a name pattern, not an entity. This requires a first pass over
   every contract to compute name -> district-spread before any flag can be
   emitted, hence two passes below rather than one.

This remains a heuristic, not proof -- it trades missed real violations
(false negatives) for fewer false accusations, deliberately, because the
cost of the two kinds of error is not symmetric for a tool that publishes
findings about named companies. Every surviving flag should still be read as
a lead to verify against the source, not a proven finding.

    python3 flag_debarred_awards.py <data/debarments.json> <data/contracts/> <data/flags.json>
"""
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

from dates import parse_dmy
from entity import normalize_company
from eras import ERA_NAMES, era_of

SKIP_FILES = {"summary.json", "dimensions.json"}
MAX_DISTRICT_SPREAD = 5


def load_dimensions(contracts_dir):
    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        return json.load(fh)


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(os.path.join(contracts_dir, "*.json"))):
        if os.path.basename(path) in SKIP_FILES:
            continue
        with open(path) as fh:
            yield from json.load(fh)


def parse_iso(raw):
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def debarment_district(address):
    if not address:
        return None
    tail = address.rstrip(". ").split(",")[-1].strip().lower()
    return tail or None


def classify(contract_date, debar_start, debar_end):
    if not contract_date:
        return None
    if debar_start and debar_end and debar_start <= contract_date <= debar_end:
        return "active_debarment_violation"
    if debar_end and contract_date > debar_end:
        return "post_debarment_award"
    return None


def main(debarments_path, contracts_dir, out_path):
    with open(debarments_path) as fh:
        debarments = json.load(fh)["records"]
    dims = load_dimensions(contracts_dir)

    by_key = defaultdict(list)
    for d in debarments:
        by_key[d["company_key"]].append(d)

    # Pass 1: how many distinct districts does each candidate name appear in,
    # across every contract (not just the ones that would otherwise match)?
    district_spread = defaultdict(set)
    for contract in load_contracts(contracts_dir):
        key = normalize_company(contract.get("awarded_to"))
        if key in by_key:
            district_spread[key].add((contract.get("district") or "").strip().lower())
    generic_keys = {k for k, districts in district_spread.items() if len(districts) > MAX_DISTRICT_SPREAD}
    if generic_keys:
        print(f"excluding {len(generic_keys)} company name(s) as too generic "
              f"(appear in >{MAX_DISTRICT_SPREAD} districts nationwide): "
              f"{sorted(generic_keys)[:10]}{' ...' if len(generic_keys) > 10 else ''}")

    # Pass 2: emit flags, name match + district corroboration, skipping generic keys.
    flags = []
    contracts_scanned = 0
    for contract in load_contracts(contracts_dir):
        contracts_scanned += 1
        key = normalize_company(contract.get("awarded_to"))
        if not key or key not in by_key or key in generic_keys:
            continue
        contract_district = (contract.get("district") or "").strip().lower()
        contract_date = parse_iso(contract.get("contract_signing_date"))
        for d in by_key[key]:
            if contract_district != debarment_district(d.get("address")):
                continue
            flag_type = classify(contract_date, parse_dmy(d.get("debar_start")), parse_dmy(d.get("debar_end")))
            if not flag_type:
                continue
            m_id, pe_id = contract.get("ministry_id"), contract.get("procuring_entity_id")
            flags.append({
                "flag_type": flag_type,
                "severity": "critical" if flag_type == "active_debarment_violation" else d["severity"],
                "company": contract.get("awarded_to"),
                "company_key": key,
                "tender_id": contract.get("tender_id"),
                "pkg_lot_id": contract.get("pkg_lot_id"),
                "procuring_entity": dims["procuring_entities"][pe_id] if pe_id is not None else None,
                "ministry": dims["ministries"][m_id] if m_id is not None else None,
                "district": contract.get("district"),
                "contract_signing_date": contract.get("contract_signing_date"),
                "value_bdt": contract.get("value_bdt"),
                "debar_start": d.get("debar_start"),
                "debar_end": d.get("debar_end"),
                "debarred_by": d.get("debarred_by"),
                "debarment_reason": d.get("reason"),
                "debarment_scope": d.get("scope_label"),
            })

    by_type = defaultdict(int)
    value_at_risk = 0.0
    active_by_era = defaultdict(lambda: {"count": 0, "value_bdt": 0.0})
    for f in flags:
        by_type[f["flag_type"]] += 1
        f["era"] = era_of(f.get("contract_signing_date"))
        if f["flag_type"] == "active_debarment_violation":
            if f["value_bdt"]:
                value_at_risk += f["value_bdt"]
            if f["era"]:
                active_by_era[f["era"]]["count"] += 1
                active_by_era[f["era"]]["value_bdt"] += f["value_bdt"] or 0

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contracts_scanned": contracts_scanned,
            "debarment_records": len(debarments),
            "flag_count": len(flags),
            "by_type": dict(by_type),
            "value_at_risk_bdt_active_violations": round(value_at_risk, 2),
            "company_names_excluded_as_generic": len(generic_keys),
            "active_violations_by_era": [
                {"era": e, "count": active_by_era[e]["count"], "value_bdt": round(active_by_era[e]["value_bdt"], 2)}
                for e in ERA_NAMES if e in active_by_era
            ],
        },
        "flags": sorted(flags, key=lambda f: (f["flag_type"] != "active_debarment_violation", f["company"])),
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    print(f"scanned {contracts_scanned} contracts against {len(debarments)} debarment records")
    print(f"flags: {dict(by_type)}")
    print(f"value in active-violation contracts: BDT {value_at_risk:,.0f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
