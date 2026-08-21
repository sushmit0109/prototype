#!/usr/bin/env python3
"""
Pick one representative contract per vendor, highest-value vendors first.

The award detail page (ViewAwardedContracts.jsp) carries the one real
per-company identifier on the whole site (Tenderer ID) plus a full
beneficial-ownership table -- but it's a per-contract page, and a vendor's
ownership doesn't change contract to contract, so crawling every one of a
vendor's 871K contracts to learn who owns it once is wasted work. This picks
one representative contract per distinct vendor.

That field is also new: older award pages don't have a Tenderer ID or
Beneficial Ownership section at all (confirmed directly -- an award from
mid-2024 has neither field in the HTML, one from August 2026 has both),
almost certainly tracking a 2025-era Public Procurement Rules requirement.
So the representative is each vendor's MOST RECENT contract, not their
highest-value one -- an older, bigger contract is worthless for this if the
page predates the field entirely. Vendors are still ranked by total value
(ties go to whoever matters more economically), so a time-boxed crawl run
covers the most significant vendors first regardless of where it stops --
top 10K of 56K vendors already covers 85% of total contract value.

    python3 pick_vendor_samples.py <data/contracts/> <out.jsonl> [--limit N]
"""
import glob
import json
import sys

from entity import normalize_company


def load_contracts(contracts_dir):
    for path in sorted(glob.glob(f"{contracts_dir}/*.json")):
        if path.endswith(("summary.json", "dimensions.json")):
            continue
        with open(path) as fh:
            yield from json.load(fh)


def main(contracts_dir, out_path, limit=None):
    most_recent = {}   # company_key -> most-recent-dated record seen so far
    total_value = {}   # company_key -> sum of value_bdt, for ranking

    for r in load_contracts(contracts_dir):
        key = normalize_company(r.get("awarded_to"))
        if not key:
            continue
        total_value[key] = total_value.get(key, 0) + (r.get("value_bdt") or 0)
        date = r.get("contract_signing_date") or ""
        if key not in most_recent or date > (most_recent[key].get("contract_signing_date") or ""):
            most_recent[key] = r

    ranked_keys = sorted(most_recent, key=lambda k: -total_value[k])
    if limit:
        ranked_keys = ranked_keys[:limit]

    with open(out_path, "w") as fh:
        for key in ranked_keys:
            r = most_recent[key]
            fh.write(json.dumps({
                "company_key": key,
                "awarded_to": r.get("awarded_to"),
                "tender_id": r["tender_id"],
                "pkg_lot_id": r["pkg_lot_id"],
                "total_value_bdt": round(total_value[key], 2),
                "sampled_contract_date": r.get("contract_signing_date"),
            }, ensure_ascii=False) + "\n")

    print(f"{len(most_recent)} distinct vendors, wrote {len(ranked_keys)} representative samples -> {out_path}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    limit = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--limit=")), None)
    main(args[0], args[1], limit)
