"""Shared helpers for the Bangladesh electricity pipeline.

Sources
-------
PGCB  : https://erp.powergrid.gov.bd  (hourly demand / supply / load-shed, Bengali)
BPDB  : https://misc.bpdb.gov.bd      (daily NLDC PDF reports, area-wise demand)

Note on TLS: erp.powergrid.gov.bd serves an incomplete certificate chain (the
intermediate CA is not bundled), so stock clients fail to verify it. These are
public, read-only government pages, so we disable verification for that host
only and keep verification on everywhere else.
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Layout: <repo>/electricity/{pipeline,raw,data}
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
SITE_DATA = ROOT / "data"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

# Hosts found to serve an incomplete chain; populated lazily on first SSLError
# so we always *try* to verify before falling back.
_NO_VERIFY: set[str] = set()

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def bn2en(s: str) -> str:
    """Convert Bengali-Indic digits to ASCII digits."""
    return (s or "").translate(BN_DIGITS)


def en2bn(s) -> str:
    """Convert ASCII digits to Bengali-Indic digits."""
    return str(s).translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))


def num(s):
    """Parse a possibly-Bengali, possibly-comma'd numeric string. None if blank."""
    if s is None:
        return None
    t = bn2en(str(s)).replace(",", "").strip()
    if t in ("", "-", "--", "N/A", "n/a"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    return int(v) if v.is_integer() else v


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en,bn;q=0.9"})
    return s


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def get(sess: requests.Session, url: str, tries: int = 4, timeout: int = 45, **kw):
    """GET with retry/backoff.

    Several bd government hosts serve an incomplete certificate chain. We try
    verified first; on an SSL failure the host is remembered and retried
    unverified for the rest of the run. Returns Response, or None.
    """
    host = _host(url)
    last = None
    for attempt in range(tries):
        verify = host not in _NO_VERIFY
        try:
            r = sess.get(url, timeout=timeout, verify=verify, **kw)
            if r.status_code == 200:
                return r
            # 404 on a missing archive file is a real answer, not a transient error
            if r.status_code in (404, 410):
                return None
            last = f"HTTP {r.status_code}"
        except requests.exceptions.SSLError:
            last = "SSLError"
            if verify:
                _NO_VERIFY.add(host)
                continue  # immediate unverified retry, no backoff
        except Exception as e:  # noqa: BLE001 - network layer, log and retry
            last = type(e).__name__
        time.sleep(min(2 ** attempt, 12) + random.random())
    print(f"  ! give up {url} ({last})")
    return None


# ---------------------------------------------------------------- atomic IO

def write_json(path: Path, obj, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), indent=indent)
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def write_csv(path: Path, rows, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def read_csv(path: Path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------- PGCB zone canonical

# The nine NLDC/PGCB operational zones. BPDB's HTML pages and its PDF reports
# spell several of these differently (colonial vs. current transliteration);
# everything is normalised onto these keys.
ZONES = ["dhaka", "chattogram", "cumilla", "mymensingh", "sylhet",
         "khulna", "barishal", "rajshahi", "rangpur"]

ZONE_ALIASES = {
    "dhaka": "dhaka",
    "chittagong": "chattogram", "chattogram": "chattogram", "chattagram": "chattogram",
    "comilla": "cumilla", "cumilla": "cumilla", "komilla": "cumilla",
    "mymensingh": "mymensingh", "maymensingh": "mymensingh",
    "sylhet": "sylhet",
    "khulna": "khulna",
    "barisal": "barishal", "barishal": "barishal",
    "rajshahi": "rajshahi",
    "rangpur": "rangpur",
}

ZONE_BN = {
    "dhaka": "ঢাকা", "chattogram": "চট্টগ্রাম", "cumilla": "কুমিল্লা",
    "mymensingh": "ময়মনসিংহ", "sylhet": "সিলেট", "khulna": "খুলনা",
    "barishal": "বরিশাল", "rajshahi": "রাজশাহী", "rangpur": "রংপুর",
}

ZONE_EN = {z: z.capitalize() for z in ZONES}


def zone_key(name: str):
    t = re.sub(r"\s*zone\s*$", "", (name or "").strip(), flags=re.I).strip().lower()
    return ZONE_ALIASES.get(t)


FUELS = ["gas", "coal", "hfo", "hsd", "hydro", "solar", "wind", "import"]

FUEL_BN = {
    "gas": "গ্যাস", "coal": "কয়লা", "hfo": "ফার্নেস তেল", "hsd": "ডিজেল",
    "hydro": "জলবিদ্যুৎ", "solar": "সৌর", "wind": "বায়ু", "import": "আমদানি",
}
FUEL_EN = {
    "gas": "Gas", "coal": "Coal", "hfo": "Furnace oil", "hsd": "Diesel",
    "hydro": "Hydro", "solar": "Solar", "wind": "Wind", "import": "Import",
}
