#!/usr/bin/env python3
"""Extract the 2015 and 2026 step ladders from the 17-Sep-2026 gazette.

That gazette prints BOTH ladders side by side -- grade | 2015 scale | 2026
corresponding scale -- which makes it the authoritative source for the 2015
ladder too (previously we only had its start and max).

Two things make naive extraction fail, and both are handled here:

  * the grade column is a single Bengali digit, and OCR confuses ৪ with Latin
    "8" and drops ১/২ entirely. So grades are NOT read -- they are assigned from
    the known page layout below, which is far more robust.
  * ladders wrap over several OCR lines inside one cell, and the header row and
    neighbouring rows bleed in. Cells are therefore cut by x-band (2015 vs 2026)
    and by y-gaps between rows, with the header excluded explicitly.

Every ladder is validated before it is accepted: strictly increasing, and each
step within a tight band of the ladder's own median step ratio.

Output: 06_structured/scale_2026_gazette.csv
"""
import csv, json, pathlib, re, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "04_ocr_md" / "2026__gazette-2026"
OUTD = ROOT / "06_structured"; OUTD.mkdir(exist_ok=True)
BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# which grades the ladder table carries on each page, in top-to-bottom order
PAGE_GRADES = {4: [1, 2, 3, 4],
               5: [5, 6, 7, 8, 9, 10, 11, 12],
               6: [13, 14, 15, 16, 17, 18, 19],
               7: [20]}

# Segmenting the number stream purely on "a ladder only rises" mis-cut the dense
# pages: an OCR slip inside one ladder reads as the start of the next. The first
# step of every grade is instead pinned here, read off the gazette's own table,
# so each ladder is cut at a known anchor and any stray value lands outside it.
START = {
    "2015": {1: 78000, 2: 66000, 3: 56500, 4: 50000, 5: 43000, 6: 35500,
             7: 29000, 8: 23000, 9: 22000, 10: 16000, 11: 12500, 12: 11300,
             13: 11000, 14: 10200, 15: 9700, 16: 9300, 17: 9000, 18: 8800,
             19: 8500, 20: 8250},
    "2026": {1: 156000, 2: 132000, 3: 113000, 4: 100000, 5: 86000, 6: 71000,
             7: 58000, 8: 46000, 9: 44000, 10: 32000, 11: 25000, 12: 24300,
             13: 24000, 14: 23500, 15: 22800, 16: 21900, 17: 21400, 18: 21000,
             19: 20500, 20: 20000},
}


# Surya occasionally renders a whole ladder line in Latin digits instead of
# Bengali, and those lines are wrong (৫২৪৮০-৫৫১১০-৫৭৮৭০-৬০৭৭০ came back as
# "67860-66720-69690-60990"; confidence drops to 0.80-0.93 on exactly these).
# There are nine such lines across the four table pages. Each is replaced here
# with the values read from the page image, keyed by page and the line's y so the
# substitution is auditable against the source.
# keyed by (page, y, column) -- both columns carry lines at nearly the same y,
# so the column is part of the key or a fix lands in the wrong ladder
LINE_FIX = {
    (4, 2462, "L"): [74400],
    (5,  883, "L"): [52480, 55110, 57870, 60770],
    (5, 1104, "L"): [40840, 42890, 45040, 47300],
    (5, 1472, "L"): [47900, 50300, 52820, 55470],
    (5, 1053, "R"): [70500, 74100, 77800, 81700, 85700],
    (5, 1592, "R"): [53500, 56200, 59000, 62000, 65100],
    (5, 1924, "R"): [49700, 52200, 54800, 57500, 60400],
    (6, 1642, "R"): [43400, 45600, 47900, 50200, 52900],
    (6, 2576, "R"): [40600, 42700, 44800, 47000, 49600],
    # second pass: lines that mix Bengali and Latin digits (Latin 8 stands for ৪,
    # 9 for ৭), which the Latin-only detector missed
    (5, 1374, "R"): [71400, 75000, 78700, 82700, 86800],
    (6,  728, "R"): [47600, 49900, 52400, 55100, 58000],
    (6, 1336, "R"): [45200, 47400, 49800, 52300, 55200],
    (6, 1954, "R"): [42400, 44500, 46800, 49100, 51900],
    (6, 2264, "R"): [41600, 43700, 45900, 48200, 50900],
}

# Surya does not merely misread lines -- on the grade-8 2026 cell it dropped one
# outright, so the ladder jumped 53300 -> 71400 with six steps missing. A dropped
# line cannot be detected as a bad value; it shows up only as a ratio gap. Lines
# recovered from the page image are re-inserted here, before the line at `y`.
LINE_INSERT = {
    (5, 1374, "R"): [56000, 58800, 61700, 64800, 68000],
}


def line_override(page, line, col):
    y = round(line["bbox"][1])
    for (p_, y_, c_), vals in LINE_FIX.items():
        if p_ == page and c_ == col and abs(y_ - y) <= 3:
            return vals
    return None


def line_insert(page, line, col):
    y = round(line["bbox"][1])
    for (p_, y_, c_), vals in LINE_INSERT.items():
        if p_ == page and c_ == col and abs(y_ - y) <= 3:
            return vals
    return []


def w(s):
    return (s or "").translate(BN)


def load_lines(page):
    fp = SRC / f"p{page:04d}.lines.json"
    return json.loads(fp.read_text())["lines"] if fp.exists() else None


def header_row(lines):
    """The two column headings, identified as a side-by-side pair sharing a y."""
    c = [l for l in lines
         if re.search(r"বেতন\s*স্?কে?ল", l["text"]) and re.search(r"২০[০-৯]{2}", l["text"])]
    best = None
    for i, a in enumerate(c):
        ay = (a["bbox"][1] + a["bbox"][3]) / 2
        for b in c[i + 1:]:
            by = (b["bbox"][1] + b["bbox"][3]) / 2
            if abs(ay - by) > 40:
                continue
            lo, hi = sorted([a, b], key=lambda l: l["bbox"][0])
            gap = hi["bbox"][0] - lo["bbox"][0]
            if gap < 200:
                continue
            if best is None or gap > best[2]:
                best = (lo, hi, gap)
    if not best:
        return None
    lo, hi, _ = best
    # the header block can be two lines deep; take the lowest line that sits in
    # either heading's x-neighbourhood as the true bottom of the header
    xs = (lo["bbox"][0], hi["bbox"][0])
    bottom = max(l["bbox"][3] for l in lines
                 if any(abs(l["bbox"][0] - x) < 40 for x in xs)
                 and l["bbox"][1] < lo["bbox"][3] + 90)
    return lo["bbox"][0], hi["bbox"][0], bottom


def number_stream(page):
    """-> {"2015":[...], "2026":[...]} every ladder number on the page, in
    reading order, with the header excluded."""
    lines = load_lines(page)
    if not lines:
        return None
    hr = header_row(lines)
    if not hr:
        return None
    x15, x26, hdr_bottom = hr
    split = (x15 + x26) / 2
    buckets = {"2015": [], "2026": []}
    for l in sorted(lines, key=lambda l: ((l["bbox"][1] + l["bbox"][3]) / 2, l["bbox"][0])):
        if l["bbox"][1] <= hdr_bottom + 4:
            continue
        cx = (l["bbox"][0] + l["bbox"][2]) / 2
        if cx < x15 - 40:
            continue
        era = "2015" if cx < split else "2026"
        col = "L" if era == "2015" else "R"
        buckets[era].extend(line_insert(page, l, col))
        ov = line_override(page, l, col)
        if ov is not None:
            buckets[era].extend(ov)
            continue
        for m in re.findall(r"\d{3,6}", w(l["text"]).replace(",", "")):
            v = int(m)
            if 150 <= v <= 300000:
                buckets[era].append(v)
    return buckets


def split_at_anchors(stream, grades, era):
    """Cut the stream at the known first step of each grade on this page."""
    anchors = [(g, START[era][g]) for g in grades]
    idx, pos = [], 0
    for g, a in anchors:
        try:
            i = stream.index(a, pos)
        except ValueError:
            idx.append((g, None)); continue
        idx.append((g, i)); pos = i + 1
    out = {}
    found = [(g, i) for g, i in idx if i is not None]
    for k, (g, i) in enumerate(found):
        end = found[k + 1][1] if k + 1 < len(found) else len(stream)
        out[g] = stream[i:end]
    return out


def split_ladders(stream):
    """A ladder only ever rises, so a DROP marks the start of the next grade.

    This replaces trying to recover table rows from bounding boxes: the gap
    between grade rows is barely larger than the gap between wrapped lines
    inside one cell, so geometry merged every grade into one block. The numbers
    segment themselves.
    """
    out, cur = [], []
    for v in stream:
        if cur and v <= cur[-1]:
            out.append(cur); cur = []
        cur.append(v)
    if cur:
        out.append(cur)
    return out


def validate(steps):
    if len(steps) < 2:
        return [True] * len(steps), None
    ratios = [b / a for a, b in zip(steps, steps[1:]) if a]
    med = statistics.median(ratios)
    flags = [True]
    for a, b in zip(steps, steps[1:]):
        r = b / a if a else 0
        flags.append(bool(a and b > a and 0.95 * med <= r <= 1.05 * med))
    return flags, med


def repair(steps):
    """Fix OCR digit slips inside a ladder using the ladder's own geometry.

    Surya confuses several Bengali digits against Latin ones (৪/8, ৮/6, ৫/6),
    so a run of mid-ladder values can come back badly wrong -- ৪০৮৪০ reads as
    "80680". Pairwise repair cannot bridge a run, so instead: mark every step
    that breaks the ladder, then rebuild each broken RUN by geometric
    interpolation between the good values either side of it, rounding to the
    nearest 100 as the gazette does. Each rebuilt value is reported, and the
    rows carry ok=False so downstream can discount or exclude them.
    """
    n = len(steps)
    if n < 4:
        return steps, []
    ok, med = validate(steps)
    if all(ok):
        return steps, []
    good = [i for i in range(n) if ok[i]]
    # a step is trustworthy only if it also agrees with the NEXT good one
    fixed, notes = list(steps), []
    i = 1
    while i < n:
        if ok[i]:
            i += 1
            continue
        j = i
        while j < n and not ok[j]:
            j += 1
        lo_i, hi_i = i - 1, j            # good anchors either side of the run
        if hi_i >= n:                    # run reaches the end: extrapolate
            for k in range(i, n):
                cand = round(fixed[k - 1] * med / 100) * 100
                notes.append(f"step {k}: {steps[k]} -> {cand} (extrapolated)")
                fixed[k] = cand
        else:
            span = hi_i - lo_i
            r = (fixed[hi_i] / fixed[lo_i]) ** (1 / span)
            for k in range(i, hi_i):
                cand = round(fixed[lo_i] * r ** (k - lo_i) / 100) * 100
                notes.append(f"step {k}: {steps[k]} -> {cand} (interpolated)")
                fixed[k] = cand
        i = j + 1
    return fixed, notes


def trim(steps):
    """Drop a leading value that belongs to the row above (it breaks the ratio)."""
    while len(steps) > 2:
        f, _ = validate(steps)
        if f[1]:
            break
        steps = steps[1:]
    return steps


def main():
    out, issues = [], []
    for page, grades in PAGE_GRADES.items():
        st = number_stream(page)
        if not st:
            print(f"  page {page}: not ready / no table found")
            continue
        for era in ("2015", "2026"):
            lads = split_at_anchors(st[era], grades, era)
            missing = [g for g in grades if g not in lads]
            if missing:
                issues.append(f"page {page} {era}: no anchor found for grades {missing}")
            for g, steps in sorted(lads.items()):
                # The last grade on a page gets everything to the end of the
                # stream, and page 7 carries two paragraphs of prose after the
                # table -- a special-pay figure, repeated "২০২৬" tokens and a
                # worked example quoting a whole other ladder. None of it
                # continues the ladder's ratio, so cut at the first step that
                # breaks it: every genuine step is now verified against the page
                # image, so a break means the table has ended.
                flags, _ = validate(steps)
                if not all(flags):
                    cut = flags.index(False)
                    if len(steps) - cut:
                        issues.append(f"grade {g} {era}: cut {len(steps)-cut} "
                                      f"trailing value(s) after step {cut-1} "
                                      f"({steps[cut:cut+4]}...)")
                    steps = steps[:cut]
                flags, med = validate(steps)
                for i, (v, ok) in enumerate(zip(steps, flags)):
                    out.append({"grade": g, "era": "nps_" + era, "step_index": i,
                                "amount": v,
                                "ratio_to_prev": round(v / steps[i-1], 5) if i else "",
                                "median_ratio": round(med, 5) if med else "",
                                "ok": ok, "page": page})
                if not all(flags):
                    issues.append(f"grade {g} {era}: {steps}")
    if not out:
        print("no ladders recovered yet")
        return
    with open(OUTD / "scale_2026_gazette.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["grade", "era", "step_index", "amount",
                                           "ratio_to_prev", "median_ratio", "ok", "page"])
        wr.writeheader(); wr.writerows(out)
    g15 = sorted({r["grade"] for r in out if r["era"] == "nps_2015"})
    g26 = sorted({r["grade"] for r in out if r["era"] == "nps_2026"})
    print(f"scale_2026_gazette.csv: {len(out)} step rows")
    print(f"  2015 grades ({len(g15)}): {g15}")
    print(f"  2026 grades ({len(g26)}): {g26}")
    print(f"  steps failing validation: {sum(1 for r in out if not r['ok'])}")
    for s_ in issues[:10]:
        print("   !", s_)


if __name__ == "__main__":
    main()
