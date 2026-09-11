#!/usr/bin/env python3
"""
Full ministry -> division -> office navigation, for readers who want one
specific office's buying habits rather than a national aggregate.
build_office_profiles.py already does this for the top 30 offices by value;
this covers all ~9,800 procuring entities that ever signed a contract, so a
reader can look up their own upazila's LGED office or a small district
hospital, not just the handful of billion-taka national agencies.

Two outputs, split for load size the same way contracts/tenders already are
sharded by year:

  <index_out>            -- one row per ministry, division and office (id,
                             name, parent ids, count, value_bdt). Small
                             enough to load eagerly: it drives the
                             ministry/division/office pickers and the
                             free-text office search.
  <offices_out_dir>/<ministry_id>.json
                          -- full profile for every office under that
                             ministry, fetched only when a reader picks it:
                             yearly trend, procurement-nature mix, top
                             vendors, top districts, and its largest
                             individual contracts.

A minority of offices appear under more than one division or ministry
across the years (reorganisations, or two spellings of a parent ministry
resolving to the same office) -- see MULTI_PARENT below. Each is filed
under whichever parent it worked with most often; this only ever
misattributes a small share of an office's own history, never another
office's.

Procurement nature (Goods/Works/Services) is joined from the master tender
list exactly as build_office_profiles.py and build_geo.py do it, with the
same partial (~53%) coverage -- read nature mixes as based on the matched
subset, not the office's full contract history. It's a coarse, legally-
defined split, not a description of what was actually bought -- for that,
this also joins in the free-text `description` field that build_contracts.py
strips out of the bulk data/contracts/<year>.json files (it's ~38% of their
raw size, see that file's docstring) but raw/contracts/ still keeps
verbatim, keyed the same way build_contracts.py dedups: (tender_id,
pkg_lot_id). That gives two more concrete things per office: the actual
one-line description behind each of its biggest contracts, and its most
frequently *recurring phrases* -- literal 2-4 word fragments ("purchase of
computers", "training of farmers") mined straight out of its own
description text (see find_recurring_phrases below), not a fixed category
system or a bag-of-words frequency count. Both of those were tried first
and rejected: single-word frequency mostly just re-states procurement
nature at a fancier grain (a road office's contracts are all
"construction"/"improvement"/"pavement" regardless of which specific road),
and a hand-curated category lexicon can only ever recognise the domains it
was written to expect, missing anything like "poultry feed dissemination"
that wasn't anticipated. Literal recurring phrases have neither problem --
whatever an office actually repeats becomes visible on its own.

    python3 build_office_explorer.py <data/contracts/> <data/tenders/> <raw/contracts/> <office_index.json> <data/offices/>
"""
import glob
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict

from entity import normalize_company

TOP_VENDORS = 5
TOP_DISTRICTS = 5
TOP_CONTRACTS = 5
TOP_PHRASES = 8
DESCRIPTION_SNIPPET_LEN = 160

# What's actually being bought, read off the description text as literal
# recurring phrases -- "purchase of computers", "training of farmers" --
# rather than single-word frequency (which just re-states procurement
# nature at a fancier grain: a road office's contracts are all
# "construction"/"improvement"/"pavement" regardless of which specific
# road) or a hand-curated category lexicon (which can only ever recognise
# domains it was written to expect).
#
# Grammar words are stripped, and so are digits/measurements/chainages
# ("891.00m", "Ch. 0+000-3+650km", "Road ID: 17725200") -- otherwise two
# descriptions that are the same activity at two different sites never
# share a phrase. What's left is split into 2-4 word n-grams, tallied per
# office by how many of its distinct contracts use each one, then
# consolidated: a shorter phrase is dropped if a longer selected phrase
# already accounts for nearly all of its occurrences (so "of computers"
# doesn't survive alongside "purchase of computers" as a separate, weaker
# echo of the same thing). Place names are excluded from phrases the same
# way find_place_words below detects them: a word that shows up almost
# exclusively right before "Upazila"/"Union"/etc. is where an office
# operates, not what it buys, and top_districts already covers that.
# "of"/"for"/"to"/"the"/"and" are deliberately NOT in here: a phrase like
# "purchase of computers" or "training of farmers" needs "of" to survive
# in the middle of the n-gram. They're excluded only from the *edges* of a
# candidate phrase (via _PHRASE_GLUE below), not from the word stream
# itself.
PHRASE_STOPWORDS = {
    "a", "an", "or", "in", "at", "on", "with", "by", "from",
    "as", "is", "be", "this", "that", "under", "during", "into", "its",
    "will", "no", "nos", "date", "period", "financial", "year", "years", "fy",
    "over",
    # Form-field labels and abbreviations that recur constantly across e-GP
    # road/works descriptions -- structural boilerplate, not a purchase.
    # "ch" is chainage ("Ch 2900 to 4745m"), "mx" a leftover from
    # concatenated dimension notation ("1.5Mx1.5M") the numeric-noise regex
    # doesn't fully catch, "up" is Union Parishad (LGED shorthand, not the
    # English preposition, in this corpus), "word" a common OCR/typing
    # variant of "Ward" (a sub-union unit) seen in the source data.
    "latitude", "longitude", "code", "ch", "mx", "up", "ward", "word",
}
_PHRASE_GLUE = {"of", "for", "and", "the", "to"}

_NUMERIC_NOISE_RE = re.compile(
    r"\b\d[\d.,+/-]*\s*(?:km|kg|mt|nos?|pcs?|m)?\b"
    r"|\b\d+(?:\.\d+)?\s*m?\s*x\s*\d+(?:\.\d+)?\s*m?\b"  # "1.5Mx1.5M" / "1.5m x 1.5m" dimension notation
    r"|\bch\.?\s*[\d.,+-]+\b"
    r"|\b(?:road|bridge)\s*id\s*[:#]?\s*\d+\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-zA-Z]+(?:-[a-zA-Z]+)*")

_PLACE_MARKER_RE = re.compile(
    r"\b([a-zA-Z]+(?:-[a-zA-Z]+)*)\s+(?:upazila|upazilla|thana|union|pourashava|paurashava)\b",
    re.IGNORECASE,
)


def find_place_words(descriptions, min_marker_count=3, min_ratio=0.3):
    """A word counts as a place name only if MOST of its occurrences sit
    right before an admin-unit marker, not just once anywhere in ~870K
    descriptions -- a single malformed record ("...Road Upazila-Keraniganj
    ...", missing its separator) is enough to catch a common word like
    "road" otherwise, misclassifying it as a place name nationwide."""
    total = Counter()
    marker = Counter()
    for desc in descriptions:
        for m in _WORD_RE.finditer(desc):
            if len(m.group(0)) >= 3:
                total[m.group(0).lower()] += 1
        for m in _PLACE_MARKER_RE.finditer(desc):
            marker[m.group(1).lower()] += 1
    return {w for w, c in marker.items() if c >= min_marker_count and c / total.get(w, c) >= min_ratio}


def clean_words(text):
    text = _NUMERIC_NOISE_RE.sub(" ", text)
    words = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        if raw.isupper() and len(raw) <= 8:  # acronym/project code (GDDRIDP, RHD, PSC...)
            continue
        w = raw.lower()
        if w not in PHRASE_STOPWORDS:
            words.append(w)
    return words


def ngrams_for(words, place_words, n_min=2, n_max=4):
    """2-4 word phrases from a word list, trimmed so they don't start or
    end on a glue word ("of computers" not "purchase of", "training of
    farmers" not "training of"), and dropped entirely if any word in them
    is a detected place name."""
    out = set()
    L = len(words)
    for n in range(n_min, n_max + 1):
        for i in range(L - n + 1):
            gram = words[i:i + n]
            while gram and gram[0] in _PHRASE_GLUE:
                gram = gram[1:]
            while gram and gram[-1] in _PHRASE_GLUE:
                gram = gram[:-1]
            if len(gram) < 2 or any(w in place_words for w in gram):
                continue
            out.add(" ".join(gram))
    return out


def consolidate_phrases(counts, min_count=3, absorb_ratio=0.85):
    """Keep the longest phrase that explains most of a shorter phrase's
    occurrences, drop the shorter one -- otherwise "purchase of computers",
    "of computers" and "purchase of" would all show up as separate, weaker
    copies of the same recurring thing."""
    candidates = sorted(
        ((p, c) for p, c in counts.items() if c >= min_count),
        key=lambda pc: (-len(pc[0].split()), -pc[1]),
    )
    selected = []
    for phrase, count in candidates:
        absorbed = any(
            phrase != sel_phrase and f" {phrase} " in f" {sel_phrase} " and count <= sel_count / absorb_ratio
            for sel_phrase, sel_count in selected
        )
        if not absorbed:
            selected.append((phrase, count))
    return selected


def titlecase_phrase(phrase):
    words = phrase.split()
    return " ".join(w if i > 0 and w in _PHRASE_GLUE else w[:1].upper() + w[1:] for i, w in enumerate(words))


def load_descriptions(raw_contracts_dir):
    """(tender_id, pkg_lot_id) -> description, straight from the raw crawl
    log -- the one field build_contracts.py deliberately drops from the
    bulk per-year files (see its docstring)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(raw_contracts_dir, "*.jsonl*"))):
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                desc = (r.get("description") or "").strip()
                if desc and r.get("tender_id") is not None and r.get("pkg_lot_id") is not None:
                    out[(r["tender_id"], r["pkg_lot_id"])] = " ".join(desc.split())
    return out


def load_records(data_dir):
    for path in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        if os.path.basename(path) in {"summary.json", "dimensions.json"}:
            continue
        with open(path) as fh:
            yield from json.load(fh)


# The master tender list actually carries five nature strings, not the
# textbook three: "Goods (Framework Agreement)" and "Physical Services" are
# procurement-law variants of Goods and Services respectively, not a
# distinct fourth or fifth thing a general reader would find meaningful.
# Collapsed to the three canonical buckets both for readability (the raw
# variants are longer than build_office_explorer.py's chart labels have
# room for, and clip) and because the whole point of this section is to
# avoid making a reader learn procurement jargon to use it.
def normalize_nature(name):
    if name.startswith("Goods"):
        return "Goods"
    if "Services" in name:
        return "Services"
    return name


def main(contracts_dir, tenders_dir, raw_contracts_dir, index_out, offices_out_dir):
    tender_nature = {}
    for r in load_records(tenders_dir):
        if r.get("procurement_nature"):
            tender_nature[r["tender_id"]] = normalize_nature(r["procurement_nature"])

    descriptions = load_descriptions(raw_contracts_dir)
    place_words = find_place_words(descriptions.values())

    with open(os.path.join(contracts_dir, "dimensions.json")) as fh:
        dims = json.load(fh)
    ministry_names = dims["ministries"]
    division_names = dims["divisions"]
    entity_names = dims["procuring_entities"]

    offices = defaultdict(lambda: {
        "value_bdt": 0.0, "count": 0,
        "ministry_votes": Counter(), "division_votes": Counter(),
        "by_year": defaultdict(lambda: {"value_bdt": 0.0, "count": 0}),
        "nature": Counter(), "vendors": Counter(), "vendor_count": Counter(),
        "districts": Counter(), "phrases": Counter(),
        "contracts": [],
    })

    total = 0
    nature_matched = 0
    for c in load_records(contracts_dir):
        total += 1
        eid = c.get("procuring_entity_id")
        if eid is None:
            continue
        o = offices[eid]
        v = c.get("value_bdt") or 0.0
        o["value_bdt"] += v
        o["count"] += 1
        if c.get("ministry_id") is not None:
            o["ministry_votes"][c["ministry_id"]] += 1
        if c.get("division_id") is not None:
            o["division_votes"][c["division_id"]] += 1
        date = c.get("contract_signing_date") or ""
        if date:
            y = o["by_year"][date[:4]]
            y["value_bdt"] += v
            y["count"] += 1
        nature = tender_nature.get(c.get("tender_id"))
        if nature:
            nature_matched += 1
            o["nature"][nature] += 1
        vendor = c.get("awarded_to")
        if vendor and normalize_company(vendor):
            o["vendors"][vendor] += v
            o["vendor_count"][vendor] += 1
        if c.get("district"):
            o["districts"][c["district"]] += 1
        desc = descriptions.get((c.get("tender_id"), c.get("pkg_lot_id")))
        if desc:
            for phrase in ngrams_for(clean_words(desc), place_words):
                o["phrases"][phrase] += 1
        o["contracts"].append({
            "package_ref": c.get("package_ref"),
            "awarded_to": vendor,
            "value_bdt": v,
            "contract_signing_date": date or None,
            "_tender_id": c.get("tender_id"),
            "_pkg_lot_id": c.get("pkg_lot_id"),
        })

    ministry_agg = defaultdict(lambda: {"value_bdt": 0.0, "count": 0, "office_ids": set()})
    division_agg = defaultdict(lambda: {"value_bdt": 0.0, "count": 0, "office_ids": set(), "ministry_id": None})

    index_offices = []
    by_ministry_profiles = defaultdict(dict)

    for eid, o in offices.items():
        mid = o["ministry_votes"].most_common(1)[0][0] if o["ministry_votes"] else None
        did = o["division_votes"].most_common(1)[0][0] if o["division_votes"] else None
        name = entity_names[eid] if eid < len(entity_names) else f"Office #{eid}"

        index_offices.append({
            "id": eid, "name": name, "ministry_id": mid, "division_id": did,
            "value_bdt": round(o["value_bdt"], 2), "count": o["count"],
        })

        if mid is not None:
            ma = ministry_agg[mid]
            ma["value_bdt"] += o["value_bdt"]
            ma["count"] += o["count"]
            ma["office_ids"].add(eid)
        if did is not None:
            da = division_agg[did]
            da["value_bdt"] += o["value_bdt"]
            da["count"] += o["count"]
            da["office_ids"].add(eid)
            da["ministry_id"] = mid

        top_contracts = sorted(o["contracts"], key=lambda r: -(r["value_bdt"] or 0))[:TOP_CONTRACTS]
        for r in top_contracts:
            r["value_bdt"] = round(r["value_bdt"], 2)
            desc = descriptions.get((r.pop("_tender_id"), r.pop("_pkg_lot_id")))
            r["description"] = desc[:DESCRIPTION_SNIPPET_LEN] if desc else None

        profile = {
            "value_bdt": round(o["value_bdt"], 2),
            "count": o["count"],
            "by_year": {y: {"value_bdt": round(v["value_bdt"], 2), "count": v["count"]}
                        for y, v in sorted(o["by_year"].items())},
            "by_nature": dict(o["nature"]),
            "top_vendors": [
                {"company": c, "value_bdt": round(v, 2), "count": o["vendor_count"][c]}
                for c, v in o["vendors"].most_common(TOP_VENDORS)
            ],
            "top_districts": [
                {"district": d, "count": n} for d, n in o["districts"].most_common(TOP_DISTRICTS)
            ],
            "top_phrases": [
                {"phrase": titlecase_phrase(p), "count": c}
                for p, c in consolidate_phrases(o["phrases"])[:TOP_PHRASES]
            ],
            "top_contracts": top_contracts,
        }
        target = mid if mid is not None else "unknown"
        by_ministry_profiles[target][str(eid)] = profile

    index_ministries = sorted([
        {
            "id": mid, "name": ministry_names[mid] if mid < len(ministry_names) else f"Ministry #{mid}",
            "value_bdt": round(a["value_bdt"], 2), "count": a["count"], "office_count": len(a["office_ids"]),
        }
        for mid, a in ministry_agg.items()
    ], key=lambda m: -m["value_bdt"])

    index_divisions = sorted([
        {
            "id": did, "name": division_names[did] if did < len(division_names) else f"Division #{did}",
            "ministry_id": a["ministry_id"],
            "value_bdt": round(a["value_bdt"], 2), "count": a["count"], "office_count": len(a["office_ids"]),
        }
        for did, a in division_agg.items()
    ], key=lambda d: -d["value_bdt"])

    index_offices.sort(key=lambda o: -o["value_bdt"])

    os.makedirs(offices_out_dir, exist_ok=True)
    with open(index_out, "w") as fh:
        json.dump({
            "meta": {
                "generated_office_count": len(index_offices),
                "ministry_count": len(index_ministries),
                "division_count": len(index_divisions),
                "contracts_scanned": total,
                "nature_matched": nature_matched,
                "nature_match_rate": round(nature_matched / total, 4) if total else 0,
            },
            "ministries": index_ministries,
            "divisions": index_divisions,
            "offices": index_offices,
        }, fh, ensure_ascii=False, indent=1)

    for target, profiles in by_ministry_profiles.items():
        with open(os.path.join(offices_out_dir, f"{target}.json"), "w") as fh:
            json.dump(profiles, fh, ensure_ascii=False, indent=1)

    print(f"{total:,} contracts -> {len(index_offices):,} offices, {len(index_ministries)} ministries, "
          f"{len(index_divisions)} divisions")
    print(f"wrote -> {index_out} and {len(by_ministry_profiles)} per-ministry office-profile files in {offices_out_dir}/")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
