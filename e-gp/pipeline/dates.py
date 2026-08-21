"""Parsing for the one date format every source on the portal uses: DD-Mon-YYYY."""
import re
from datetime import datetime

_DATE_RE = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})")


def parse_dmy(raw):
    m = _DATE_RE.search(raw or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%d-%b-%Y").date()
    except ValueError:
        return None
