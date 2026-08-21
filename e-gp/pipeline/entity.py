"""
Company-name normalisation shared by every pipeline stage that needs to tell
whether two source records name the same entity.

There is no single stable company ID across the portal's sources -- the
debarment register, the eContracts list and (eventually) registration each
spell a firm's name slightly differently ("M/S. Ashik Construction" vs
"Ashik Construction Ltd."). This does exact matching on a normalised key:
lowercased, punctuation and *legal-form* words stripped -- Ltd/Limited/Pvt/
Company/M/S, which are genuinely interchangeable suffixes in Bangladeshi
company naming.

It deliberately does NOT strip business-descriptor words like Enterprise,
Trading, Traders, Construction or Corporation: an earlier version did, on
the assumption they were boilerplate like "Ltd" -- but they're often the
operative part of a small firm's name (a first test run confirmed "Alam
Enterprise" and a hypothetical "Alam Trading" would collapse to the same
"alam" key and could each get credited with the other's contracts and
debarment history). Keeping them makes exact-match miss more true matches
that vary that word, but for a tool that publishes corruption flags, a missed
match (silence) is a far smaller harm than a false one (a wrong accusation).

Also refuses to produce a match key shorter than MIN_KEY_LEN: very short
normalised names ("ns", "ms") are too generic to trust on name alone. This
is deliberately not fuzzy (no rapidfuzz/Levenshtein) for the same reason --
exact-on-normalised is the conservative first pass. Any two-name comparison
it doesn't resolve fails safe (no flag) rather than guessing.
"""
import re

_STRIP_SUFFIXES = re.compile(r"\b(ltd|limited|pvt|private|co|company|m/s)\b")
_PUNCT = re.compile(r"[.,]")
_WS = re.compile(r"\s+")
MIN_KEY_LEN = 4


def normalize_company(name):
    if not name:
        return ""
    n = _PUNCT.sub("", name.lower().strip())
    n = _STRIP_SUFFIXES.sub("", n)
    n = _WS.sub(" ", n).strip()
    return n if len(n) >= MIN_KEY_LEN else ""
