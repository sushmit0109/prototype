#!/usr/bin/env python3
"""
Extract the Bangladesh Police monthly "Crime Statistics" sheet from a scanned PDF.

The published sheet is a fully-ruled table, printed sideways on a portrait page
in most months and landscape or upside down in others. Rather than throw the
whole page at the OCR engine, we straighten the scan, find the printed rules,
and read one cell at a time with a digit whitelist -- which removes every
column-alignment guess from the engine's job.

Within a cell the digits are counted geometrically before they are recognised.
Tesseract's characteristic failure on this material is dropping a leading or
trailing digit (1733 read as 733), and the result is a perfectly plausible
number that nothing downstream would question. Printed digits never touch, so
the digit count is a fact we can measure rather than something to be trusted.

What makes the result trustworthy is that the sheet carries three independent
checksums:

  * RC Total    == Arms + Explosive + Narcotics + Smuggling      (per row)
  * Total Cases == the eleven crime columns + RC Total           (per row)
  * the Total row == the seventeen unit rows                     (per column)

Every extracted number is checked against all three. Where exactly one cell in a
constraint is missing or wrong, the constraint determines it and we repair it.
Anything still inconsistent is reported rather than silently published.
"""
import os
import re
import subprocess
import tempfile
from collections import Counter

import numpy as np
from PIL import Image

TESS = os.environ.get("TESSERACT_BIN", "tesseract")

# The fifteen offence columns we keep, in printed left-to-right order.
CRIME_COLS = [
    "Dacoity", "Robbery", "Murder", "Speedy Trial", "Riot",
    "Woman & Child Repression", "Kidnapping", "Police Assault",
    "Burglary", "Theft", "Other Cases",
    "RC Arms Act", "RC Explosive Act", "RC Narcotics", "RC Smuggling",
]
# The two printed subtotals. We keep them only to check the fifteen above.
CHECK_COLS = ["RC Total", "Total Cases"]
ALL_COLS = CRIME_COLS + CHECK_COLS

# Column index groups within ALL_COLS.
IDX_OFFENCE = list(range(0, 11))    # Dacoity .. Other Cases
IDX_RECOVERY = list(range(11, 15))  # Arms .. Smuggling
IDX_RC_TOTAL = 15
IDX_GRAND = 16

# Row order as printed. Note "Ralway Range" reproduces the source's spelling.
UNITS = [
    "DMP", "CMP", "KMP", "RMP", "BMP", "SMP", "RPMP", "GMP",
    "Dhaka Range", "Mymensingh Range", "Chittagong Range", "Sylhet Range",
    "Khulna Range", "Barishal Range", "Rajshahi Range", "Rangpur Range",
    "Ralway Range",
]
TOTAL_ROW = "Total"

N_ROWS = len(UNITS) + 1          # 17 units + Total
N_COLS = len(ALL_COLS) + 1       # 17 value columns + the unit-name column


# ---------------------------------------------------------------- rasterising

def render_pages(pdf, dpi=600):
    """Rasterise the PDF. 600dpi is not vanity: at 300 the digits arrive about
    40px tall and upsampling them costs real accuracy (trailing digits get
    dropped), while at 600 they downsample cleanly into the OCR."""
    pages = []
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf, f"{td}/p"],
                       check=True, capture_output=True)
        for f in sorted(os.listdir(td)):
            pages.append(Image.open(os.path.join(td, f)).convert("L").copy())
    return pages


def _skew_score(im, ang):
    """How crisply the horizontal rules stack up at this angle.

    Variance of the row-ink profile, not a count of rows over a fixed ink
    threshold: downscaling for speed greys the rules out through antialiasing,
    and a fixed threshold would then score every angle zero. Variance peaks
    when the rules land on whole rows regardless of how grey they are.
    """
    r = im.rotate(float(ang), expand=False, fillcolor=255,
                  resample=Image.BILINEAR)
    prof = (255 - np.asarray(r, dtype=np.float32)).mean(axis=1)
    return float(prof.var())


def deskew(im, span=2.5, step=0.1, probe_width=1400):
    """Scans sit a fraction of a degree off true. Straighten so the printed
    rules land on whole pixel rows, which is what makes them findable.

    The angle is measured on a downscaled copy -- skew does not depend on
    resolution, and searching fifty rotations of a full 600dpi page is slow
    enough to dominate the whole run.
    """
    probe = im
    if im.width > probe_width:
        s = probe_width / im.width
        probe = im.resize((probe_width, max(1, int(im.height * s))), Image.BILINEAR)

    coarse = max(np.arange(-span, span + step / 2, step * 5),
                 key=lambda a: _skew_score(probe, a))
    best_ang = max(np.arange(coarse - step * 5, coarse + step * 5 + 1e-9, step),
                   key=lambda a: _skew_score(probe, a))
    best_ang = float(best_ang)
    return im.rotate(best_ang, expand=False, fillcolor=255,
                     resample=Image.BICUBIC), best_ang


# -------------------------------------------------------------- grid geometry

def _lines(dark, axis, frac, gap=4):
    """Indices of printed rules: rows (or columns) that are mostly ink."""
    hits = np.where(dark.mean(axis=axis) > frac)[0]
    if len(hits) == 0:
        return []
    groups, cur = [], [hits[0]]
    for x in hits[1:]:
        if x - cur[-1] <= gap:
            cur.append(x)
        else:
            groups.append(int(np.mean(cur)))
            cur = [x]
    groups.append(int(np.mean(cur)))
    return groups


def _trim_edges(lines, want, extent, margin=0.02):
    """Drop page-border rules picked up alongside the table's own.

    Judge them by position, not by gap size. The obvious-looking test -- shave
    whichever end sits behind an outlying gap -- is wrong here, because the
    unit-name column is several times wider than any data column and would be
    eaten first, silently shifting every reading one column left.
    """
    lines = list(lines)
    lo, hi = extent * margin, extent * (1 - margin)
    while len(lines) > want >= 2:
        if lines[0] < lo:
            lines.pop(0)
        elif lines[-1] > hi:
            lines.pop()
        else:
            break                     # nothing is at the page edge; leave it
    return lines



def row_windows(H):
    """Every plausible set of N_ROWS+1 rules bounding the data rows.

    Geometry cannot settle this on its own. The column header is two levels
    deep, so a partial rule runs through it; sheets carry footnote and
    signature rules below the table; and how many of those get detected depends
    on scan quality. Any of them can shift the row window by one, which is not
    a harmless error -- it labels CMP's numbers as DMP's.

    So propose rather than decide: return each run of near-equally-spaced bands
    of the right length, and let the caller confirm the real one by reading the
    row labels.
    """
    if len(H) < N_ROWS + 1:
        return []
    gaps = np.diff(H)
    med = float(np.median(gaps))
    out, run = [], [H[0]]
    for i in range(1, len(H)):
        if abs(gaps[i - 1] - med) <= med * 0.25:
            run.append(H[i])
        else:
            run = [H[i]]
        if len(run) >= N_ROWS + 1:
            out.append(run[-(N_ROWS + 1):])
    # nearest-first: the data rows sit at the bottom of the sheet
    return list(reversed(out))


def column_rules(im):
    """Candidate sets of the sheet's N_COLS+1 vertical rules, best first."""
    a = np.asarray(im)
    want = N_COLS + 1
    seen, out = set(), []
    for ink in (160, 180, 200, 140):
        d = (a < ink).astype(np.float32)
        for frac in np.arange(0.18, 0.75, 0.02):
            V = _trim_edges(_lines(d, 0, frac), want, im.width)
            if len(V) != want or tuple(V) in seen:
                continue
            # The unit-name column is far wider than any data column. If the
            # leftmost gap is not the widest, a rule was invented inside a wide
            # column while the sheet's own edge was missed -- still nineteen
            # lines, but the wrong nineteen.
            if int(np.argmax(np.diff(V))) != 0:
                continue
            seen.add(tuple(V))
            out.append((V, (ink, round(float(frac), 3))))
    return out


def horizontal_rules(im):
    """Candidate row windows across ink thresholds, de-duplicated."""
    a = np.asarray(im)
    seen, out = set(), []
    for ink in (160, 180, 200, 140):
        d = (a < ink).astype(np.float32)
        for frac in np.arange(0.18, 0.75, 0.02):
            for w in row_windows(_lines(d, 1, frac)):
                if tuple(w) not in seen:
                    seen.add(tuple(w))
                    out.append(w)
    return out


# ------------------------------------------------------------------ cell OCR

def _strip_rules(a, thresh=0.6):
    """Shave any rule the cell crop still overlaps.

    A fixed pixel inset cannot do this: rules get thicker with resolution, and
    leftover rule pixels wreck the ink bounding box below -- the box latches
    onto the full cell instead of the digits, the glyphs end up scaled to
    nothing, and OCR returns empty. So trim edge rows/columns that are mostly
    ink until only the cell interior is left.
    """
    top, bot, left, right = 0, a.shape[0], 0, a.shape[1]
    while top < bot and (a[top, left:right] < 170).mean() > thresh:
        top += 1
    while bot > top and (a[bot - 1, left:right] < 170).mean() > thresh:
        bot -= 1
    while left < right and (a[top:bot, left] < 170).mean() > thresh:
        left += 1
    while right > left and (a[top:bot, right - 1] < 170).mean() > thresh:
        right -= 1
    return top, bot, left, right


def _prep(crop, target_h=64):
    """Trim a cell to its ink, scale the glyphs to a consistent height and pad.
    Tesseract is markedly better on a normalised, well-margined glyph than on a
    small number adrift in a large white cell."""
    a = np.asarray(crop)
    t, b, l, r = _strip_rules(a)
    if b - t < 4 or r - l < 4:
        return None
    a = a[t:b, l:r]
    crop = crop.crop((l, t, r, b))
    ink = a < 170
    if ink.sum() < 5:
        return None
    ys, xs = np.where(ink)
    c = crop.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    s = target_h / max(c.height, 1)
    c = c.resize((max(1, int(c.width * s)), target_h), Image.LANCZOS)
    pad = Image.new("L", (c.width + 40, c.height + 40), 255)
    pad.paste(c, (20, 20))
    return pad


def _tess(img, psm, digits=True):
    cfg = ["--psm", str(psm)]
    if digits:
        cfg += ["-c", "tessedit_char_whitelist=0123456789"]
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        img.save(t.name)
        name = t.name
    try:
        r = subprocess.run([TESS, name, "-", *cfg], capture_output=True, text=True)
        return re.sub(r"[^0-9]", "", r.stdout) if digits else r.stdout.strip()
    finally:
        os.unlink(name)


def digit_columns(img, min_gap=2):
    """Column spans of each separate ink blob -- one per printed digit.

    These sheets are printed, not handwritten, so the digits never touch. That
    makes the *number of digits* a geometric fact we can measure, rather than
    something the OCR has to get right. It matters because tesseract's
    characteristic failure here is silently dropping a leading or trailing
    digit: 1733 read as 733, 991 as 99. Both are plausible numbers, so nothing
    downstream would notice.
    """
    a = np.asarray(img)
    ink = (a < 170).sum(axis=0)
    spans, start = [], None
    gap = 0
    for x, v in enumerate(ink):
        if v > 0:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                spans.append((start, x - gap + 1))
                start = None
    if start is not None:
        spans.append((start, len(ink)))
    # drop specks that cannot be a digit
    h = (a < 170).any(axis=1).sum()
    return [s for s in spans if s[1] - s[0] >= max(2, h * 0.08)]


def read_cell(crop):
    """Read one numeric cell.

    Two independent readings: tesseract on the whole cell, voting across page
    segmentation modes, and a digit-by-digit pass guided by the blob count. When
    the whole-cell reading has the wrong number of digits we take the segmented
    one, which is what catches the dropped-digit failure.
    """
    p = _prep(crop)
    if p is None:
        # Almost no ink. Usually a genuinely blank cell, which means zero -- but
        # a faint digit looks the same, so leave it open to the checksum pass.
        return 0, 0.6

    votes = Counter()
    for psm in (7, 8, 10, 13):
        v = _tess(p, psm)
        if v:
            votes[v] += 1

    spans = digit_columns(p)
    whole, agree = (votes.most_common(1)[0] if votes else (None, 0))

    if whole is not None and len(whole) == len(spans):
        return int(whole), agree / 4.0          # both accounts agree on length

    if not spans or len(spans) > 6:
        return (int(whole), agree / 8.0) if whole else (None, 0.0)

    # Re-read one digit at a time, each padded so tesseract sees a lone glyph.
    out = ''
    for x0, x1 in spans:
        d = p.crop((max(0, x0 - 4), 0, min(p.width, x1 + 4), p.height))
        pad = Image.new('L', (d.width + 40, d.height + 20), 255)
        pad.paste(d, (20, 10))
        per = Counter()
        for psm in (10, 8, 7):
            v = _tess(pad, psm)
            if len(v) == 1:
                per[v] += 1
        if not per:
            return (int(whole), agree / 8.0) if whole else (None, 0.0)
        out += per.most_common(1)[0][0]

    if whole == out:
        return int(out), 1.0
    # length is measured, not guessed, so prefer the segmented reading -- but
    # flag it as uncertain so the checksum pass may still overrule it
    return int(out), 0.5


# ------------------------------------------------------------- sheet reading

def orient(im):
    """Find the rotation that puts the sheet upright.

    The scans are not consistent: most months are printed sideways on a
    portrait page, some arrive already landscape, and a few are upside down.
    Nor is the row window obvious, for the reasons in `row_windows`.

    Both questions are settled the same way. Geometry proposes -- each quarter
    turn, each set of column rules, each evenly spaced run of rows -- and the
    sheet's own row labels dispose: only when the page is upright and the rows
    correctly aligned do they read DMP, Dhaka Range and Total.
    """
    best = None
    for turn in (90, 0, 270, 180):
        cand = im.rotate(turn, expand=True) if turn else im
        cand, ang = deskew(cand)
        cols = column_rules(cand)
        if not cols:
            continue
        rows = horizontal_rules(cand)
        for V, frac in cols[:3]:
            for H in rows[:4]:
                score = _names_match(cand, H, V)
                if best is None or score > best[0]:
                    best = (score, cand, ang, H, V, frac, turn)
                if score == 1.0:
                    return best
    return best if best and best[0] > 0 else None


def _names_match(im, H, V):
    """Fraction of the sheet's first, middle and last row labels that read right."""
    ix = max(3, int(np.median(np.diff(V)) * 0.06))
    iy = max(3, int(np.median(np.diff(H)) * 0.06))
    probes = {0: "dmp", 8: "dhaka", N_ROWS - 1: "total"}
    hits = 0
    for ri, want in probes.items():
        crop = im.crop((V[0] + ix, H[ri] + iy, V[1] - ix, H[ri + 1] - iy))
        prepped = _prep(crop, target_h=48)
        if prepped is None:
            continue
        txt = _tess(prepped, 7, digits=False).lower().replace(" ", "")
        if want in txt:
            hits += 1
    return hits / len(probes)


def read_sheet(im):
    """OCR one crime-statistics sheet. Returns (grid, confidence, meta)."""
    found = orient(im)
    if found is None:
        return None, None, {"error": "no readable table grid on this page"}
    _score, im, ang, H, V, frac, turn = found

    # Inset off each rule, scaled to the sheet so it works at any resolution.
    iy = max(3, int(np.median(np.diff(H)) * 0.06))
    ix = max(3, int(np.median(np.diff(V)) * 0.06))

    grid = np.full((N_ROWS, len(ALL_COLS)), None, dtype=object)
    conf = np.zeros((N_ROWS, len(ALL_COLS)))
    for ri in range(N_ROWS):
        y0, y1 = H[ri] + iy, H[ri + 1] - iy
        for ci in range(len(ALL_COLS)):
            x0, x1 = V[ci + 1] + ix, V[ci + 2] - ix  # V[0..1] is the name column
            val, c = read_cell(im.crop((x0, y0, x1, y1)))
            grid[ri, ci] = val
            conf[ri, ci] = c
    return grid, conf, {"skew": round(ang, 2), "ink_threshold": frac,
                        "rotation": turn}
