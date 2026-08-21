#!/usr/bin/env python3
"""
Crawl ViewAwardedContracts.jsp detail pages for a list of (tender_id,
pkg_lot_id) pairs -- the one page on the whole portal that carries a real
per-company identifier (Tenderer ID) and a full beneficial-ownership table
(name, designation, %, country) per company, plus funding source and
project code. A plain GET with both IDs in the query string; no session
tricks needed (confirmed directly, unlike ViewTenderDetails.jsp which needs
more context than that).

Input is the output of pick_vendor_samples.py: one representative contract
per vendor, so this learns each vendor's ownership once rather than
re-fetching it on every one of their contracts.

    python3 scrape_award_details.py <samples.jsonl> <out.jsonl>
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import common

FIELD_RE = {
    "tenderer_id": re.compile(r"Tenderer ID of the Economic Operator[^:]*:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "business_address": re.compile(r"Business Address of the Economic Operator:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "budget_source": re.compile(r"Budget and Source of Funds:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "development_partner": re.compile(r"Development Partner[^:]*:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "project_code": re.compile(r"Project/Program Code[^:]*:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "project_name": re.compile(r"Project/Program Name[^:]*:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
    "delivery_location": re.compile(r"Location of Delivery/Works/Service Delivery:\s*</td>\s*<td[^>]*>\s*([^<]*)", re.S),
}
OWNER_ROW_RE = re.compile(
    r"<td[^>]*>\s*(\d+)\s*</td>\s*"
    r"<td[^>]*>\s*([^<]*?)\s*</td>\s*"
    r"<td[^>]*>\s*([^<]*?)\s*</td>\s*"
    r"<td[^>]*>\s*([\d.]*)\s*</td>\s*"
    r"<td[^>]*>\s*([^<]*?)\s*</td>",
    re.S,
)
WS_RE = re.compile(r"\s+")


def clean(s):
    return WS_RE.sub(" ", (s or "").replace("&nbsp;", " ")).strip()


def parse_detail(html, tender_id, pkg_lot_id):
    out = {"tender_id": tender_id, "pkg_lot_id": pkg_lot_id}
    for field, pattern in FIELD_RE.items():
        m = pattern.search(html)
        out[field] = clean(m.group(1)) if m else None

    owners = []
    owner_block_m = re.search(r"Beneficial Ownership Information(.*?)Business Address", html, re.S)
    if owner_block_m:
        for m in OWNER_ROW_RE.finditer(owner_block_m.group(1)):
            _, name, designation, pct, country = m.groups()
            name = clean(name)
            if not name or name.lower() in ("name",):
                continue
            owners.append({
                "name": name, "designation": clean(designation),
                "ownership_pct": clean(pct) or None, "country": clean(country),
            })
    out["beneficial_owners"] = owners
    return out


def fetch_and_parse(sample):
    path = f"/resources/common/ViewAwardedContracts.jsp?pkgLotId={sample['pkg_lot_id']}&tenderid={sample['tender_id']}"
    body = common.get(path)
    detail = parse_detail(body, sample["tender_id"], sample["pkg_lot_id"])
    detail["company_key"] = sample["company_key"]
    detail["awarded_to"] = sample["awarded_to"]
    return detail


def already_done(out_path):
    """company_keys already in an existing output file.

    Keyed by company, not (tender_id, pkg_lot_id): pick_vendor_samples.py
    picks each vendor's *most recent* contract as its representative, so
    which exact contract represents a given vendor can change from one day's
    run to the next as new contracts come in. What matters for resuming is
    "do we already know this vendor's ownership," not "did we fetch this
    exact page before."
    """
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["company_key"])
                except (json.JSONDecodeError, KeyError):
                    continue  # a partial last line from a killed run
    return done


def main(samples_path, out_path, resume=False):
    common.bootstrap()
    with open(samples_path) as fh:
        samples = [json.loads(line) for line in fh]

    skip = already_done(out_path) if resume else set()
    todo = [s for s in samples if s["company_key"] not in skip]
    print(f"{len(skip)} already done, {len(todo)} to fetch")

    written = 0
    # Unordered (as_completed), not pool.map: with pool.map, one slow request
    # blocks every already-finished result behind it from being written --
    # looks exactly like a hang for however long that one request takes.
    with open(out_path, "a" if resume else "w") as fh:
        with ThreadPoolExecutor(max_workers=common.MAX_CONCURRENCY) as pool:
            futures = [pool.submit(fetch_and_parse, s) for s in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                fh.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                fh.flush()
                written += 1
                if i % 500 == 0:
                    print(f"{i}/{len(todo)} done")
    print(f"\nwrote {written} new award-detail records -> {out_path}")


if __name__ == "__main__":
    resume = "--resume" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1], resume)
