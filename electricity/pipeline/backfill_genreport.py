"""One-off: fetch only the Daily Electricity Generation Report for each archive
date and merge it into the existing daily record. Much cheaper than re-parsing
every sheet, since the other forms are already stored.

    python backfill_genreport.py [--force]
"""
import sys
from concurrent.futures import ThreadPoolExecutor

from common import RAW, read_json, session, write_json
from parse_bpdb_pdf import DAILY, INDEX, classify, parse_genreport, pdf_text

force = "--force" in sys.argv
index = read_json(INDEX, {}) or {}
todo = []
for listing, links in sorted(index.items()):
    url = links.get("summary")
    if not url:
        continue
    f = DAILY / f"{listing}.json"
    rec = read_json(f)
    if not rec or rec.get("failed"):
        continue
    if rec.get("genreport") and not force:
        continue
    todo.append((listing, url, f, rec))

print(f"[genreport] {len(todo)} dates to fetch")
sess = session()
ok = fail = 0


def work(item):
    listing, url, f, rec = item
    pdf, text = pdf_text(sess, url)
    if not pdf:
        return listing, None
    with pdf:
        if classify(text) != "genreport":
            return listing, "wrongform"
        g = parse_genreport(text)
    if not g or not g.get("data_date"):
        return listing, None
    rec["genreport"] = g
    rec.setdefault("sources", {})["genreport"] = url
    write_json(f, rec)
    return listing, "ok"


with ThreadPoolExecutor(max_workers=5) as ex:
    for i, (d, st) in enumerate(ex.map(work, todo), 1):
        if st == "ok":
            ok += 1
        else:
            fail += 1
        if i % 100 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} ok={ok} other={fail}", flush=True)
print(f"[genreport] done ok={ok} other={fail}")
