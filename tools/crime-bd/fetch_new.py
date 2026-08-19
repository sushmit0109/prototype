#!/usr/bin/env python3
"""
Look for crime-statistics sheets we do not have yet, and read the ones we find.

This is the unattended half of the project, so its guiding rule is that it would
rather publish nothing than publish something wrong. A newly downloaded month is
OCR'd, reconciled against the three checksums the sheet prints, and only written
into `truth/` if all 53 of them balance. Anything short of that is left in
`needs_review/` with a report, and the run reports failure so a human looks.

    python3 fetch_new.py <truth_dir> <work_dir> [--limit N]
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

import numpy as np

from ocr_extract import ALL_COLS, UNITS, read_sheet, render_pages
from reconcile import reconcile

LISTING = "https://www.police.gov.bd/index.php/en/january_2020"
UA = "Mozilla/5.0 (compatible; crime-bd-dashboard/1.0; +https://sushmit0109.github.io/prototype/)"
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}
MONTHS["jun"] = 6
MONTHS["jul"] = 7
ROWS = UNITS + ["Total"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def listing():
    """Every published monthly sheet, newest first, as {'YYYY-MM': url}."""
    html = ""
    for page in ("", "?page=2"):
        html += get(LISTING + page).decode("utf-8", "replace")
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        title = re.search(r"Crime Statistics,\s*([A-Za-z]+)-(\d{4})", tr)
        pdf = re.search(r'href="(https://www\.police\.gov\.bd/storage/upload/announcement/[^"]+)"', tr)
        if not title or not pdf:
            continue
        mon = MONTHS.get(title.group(1).lower())
        if mon:
            out[f"{title.group(2)}-{mon:02d}"] = pdf.group(1)
    return out


def process(pdf_path):
    """OCR one sheet and reconcile it. Returns (rows, report)."""
    pages = render_pages(pdf_path, 400)
    grid, conf, meta = read_sheet(pages[0])
    if grid is None:
        return None, {"clean": False, "error": meta.get("error", "unreadable")}
    fixed, report = reconcile(grid, conf)
    report["meta"] = meta
    if not report["clean"]:
        return None, report
    return {ROWS[r]: [int(v) for v in fixed[r]] for r in range(len(ROWS))}, report


def main(truth_dir, work_dir, limit=None):
    os.makedirs(work_dir, exist_ok=True)
    review = os.path.join(truth_dir, "..", "needs_review")
    have = {f[:-5] for f in os.listdir(truth_dir) if re.fullmatch(r"\d{4}-\d{2}\.json", f)}

    published = listing()
    missing = sorted(k for k in published if k not in have)
    # Only months the compiled CSV does not already cover.
    missing = [k for k in missing if k >= "2025-06"]
    if limit:
        missing = missing[-int(limit):]

    print(f"published: {len(published)} monthly sheets, newest {max(published)}")
    print(f"already transcribed: {len(have)}")
    print(f"to fetch: {missing or 'nothing new'}")

    added, failed = [], []
    for key in missing:
        pdf = os.path.join(work_dir, f"{key}.pdf")
        if not os.path.exists(pdf):
            print(f"  downloading {key} ...", flush=True)
            with open(pdf, "wb") as fh:
                fh.write(get(published[key]))
        print(f"  reading {key} ...", flush=True)
        rows, report = process(pdf)
        if rows is None:
            failed.append(key)
            os.makedirs(review, exist_ok=True)
            json.dump(report, open(os.path.join(review, f"{key}.report.json"), "w"),
                      indent=1, default=str)
            print(f"  ! {key} did NOT reconcile — left for review")
            continue
        json.dump(rows, open(os.path.join(truth_dir, f"{key}.json"), "w"), indent=1)
        added.append(key)
        print(f"  + {key} added ({len(report['repaired'])} cell(s) repaired by checksum)")

    print(f"\nadded {len(added)}, failed {len(failed)}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"added={' '.join(added)}\n")
            fh.write(f"failed={' '.join(failed)}\n")
            fh.write(f"changed={'true' if added else 'false'}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lim = next((a.split("=")[1] for a in sys.argv[1:] if a.startswith("--limit")), None)
    sys.exit(main(args[0], args[1], lim))
