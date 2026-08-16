"""
BMET / OEP geo-clearance crawler.

Source: https://www.oep.gov.bd/reports/geo-clearance-count

The report renders one row per (division, district) with a count, filtered by
an approval-date range and optionally by country and gender. Country is only a
*filter*, never a column, so a district x country x day breakdown requires one
request per (country, day). This module funnels that space down:

  phase 1  bootstrap   parse district/country reference data from the form
  phase 2  daily-all   one request per day, no country filter (control totals)
  phase 3  screen      one request per (country, month); skips empty months
  phase 4  daily-ctry  one request per (country, day) for live months only,
                       with an intermediate week screen for sparse months
  phase 5  export      validate, reconcile and write CSV/Parquet

Every response is recorded in a fetch log keyed by its query, so the crawl is
resumable and re-running only fetches what is missing.
"""

from __future__ import annotations

import asyncio
import calendar
import datetime as dt
import json
import html
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from lxml import html as LH

BASE = "https://www.oep.gov.bd/reports/geo-clearance-count"
ROOT = Path(__file__).resolve().parent
# Overridable so a run can be pointed at a scratch copy (used by CI dry-runs
# and by anything that must not touch the working database).
DB_PATH = Path(os.environ.get("BMET_DB") or (ROOT / "data" / "bmet.sqlite"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# The earliest approval date the report returns anything for, and the first day
# with no data at all before it. Verified by probing 2005..2026.
DATA_START = dt.date(2023, 6, 19)

# Dates whose totals are NOT stable. 2023-06-19 is the system's earliest date
# and behaves as a catch-all bucket rather than a day.
#
# Measured over one session: 2023-06-19 went 2,168 -> 3,065 (+897, +41%) in two
# and a half hours, at times incrementing between back-to-back requests, while
# 06-20, 06-21, 06-22, 06-24, 06-25 and 06-26 returned byte-identical totals
# across the same span. Growth is bursty - the date can sit still for minutes -
# so a single repeat-query check may show it as stable; compare against a total
# recorded earlier instead.
#
# It appears to absorb records carrying no usable approval date, making it an
# inseparable mixture of genuine first-day clearances and an ongoing dump.
# Exclude it from time-series work; a 41% swing in one bucket would otherwise
# read as a real spike at the start of the series.
VOLATILE_DATES = {DATA_START.isoformat()}

# Divisions 1-8 are the eight real administrative divisions of Bangladesh. The
# district dropdown also carries rows attached to division ids 150+ which are
# foreign cities (Riyadh, Dubai, Doha, ...) mistakenly entered as districts.
VALID_DIVISION_IDS = set(range(1, 9))

CONCURRENCY = 8
MAX_RETRIES = 5
# A country-month at or above this total is dense enough that screening its
# weeks costs more requests than it saves; go straight to daily.
DENSE_MONTH_TOTAL = 150


# --------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS division (
    division_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS district (
    district_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    division_id   INTEGER NOT NULL,
    is_valid      INTEGER NOT NULL   -- 0 = junk row in the source dropdown
);

CREATE TABLE IF NOT EXISTS country (
    country_id    INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    has_data      INTEGER,           -- filled in by phase 3
    total_records INTEGER
);

-- one row per (day, gender, division, district), no country filter.
-- gender_id 0 = every gender (the unfiltered control), 1 male, 2 female, 3 other.
CREATE TABLE IF NOT EXISTS daily_all (
    date          TEXT NOT NULL,
    gender_id     INTEGER NOT NULL DEFAULT 0,
    division      TEXT NOT NULL,
    district      TEXT NOT NULL,
    count         INTEGER NOT NULL,
    PRIMARY KEY (date, gender_id, division, district)
);

-- one row per (day, country, gender, division, district): the main dataset.
-- Only genders 0 (all), 2 (female) and 3 (other) are ever crawled - male is
-- derived as all minus female minus other, which is exact and halves the work.
CREATE TABLE IF NOT EXISTS daily_country (
    date          TEXT NOT NULL,
    country_id    INTEGER NOT NULL,
    gender_id     INTEGER NOT NULL DEFAULT 0,
    division      TEXT NOT NULL,
    district      TEXT NOT NULL,
    count         INTEGER NOT NULL,
    PRIMARY KEY (date, country_id, gender_id, division, district)
);

CREATE INDEX IF NOT EXISTS ix_dc_country ON daily_country(country_id);
CREATE INDEX IF NOT EXISTS ix_dc_date    ON daily_country(date);

-- screening results, so phase 4 knows which (country, span) to expand
CREATE TABLE IF NOT EXISTS span_total (
    country_id    INTEGER NOT NULL,
    gender_id     INTEGER NOT NULL DEFAULT 0,
    date_from     TEXT NOT NULL,
    date_to       TEXT NOT NULL,
    total         INTEGER NOT NULL,
    PRIMARY KEY (country_id, gender_id, date_from, date_to)
);

-- every successful request, so a re-run skips completed work
CREATE TABLE IF NOT EXISTS fetch_log (
    key           TEXT PRIMARY KEY,
    rows          INTEGER NOT NULL,
    total         INTEGER NOT NULL,
    fetched_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fetch_error (
    key           TEXT NOT NULL,
    error         TEXT NOT NULL,
    at            TEXT NOT NULL
);
"""


def migrate(con: sqlite3.Connection) -> None:
    """Add the gender dimension to a database crawled before it existed.

    SQLite cannot alter a primary key, so each affected table is rebuilt and
    its rows copied in as gender 0. Row counts are asserted afterwards - a
    silent partial copy here would corrupt the whole dataset.
    """
    for table in ("daily_all", "daily_country", "span_total"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        if not cols or "gender_id" in cols:
            continue
        before = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  [migrate] adding gender to {table} ({before:,} rows)")
        con.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
        con.executescript(SCHEMA)
        con.execute(
            f"INSERT INTO {table}({','.join(cols)}, gender_id) "
            f"SELECT {','.join(cols)}, 0 FROM {table}_old"
        )
        after = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if after != before:
            raise RuntimeError(f"migration lost rows in {table}: {before} -> {after}")
        con.execute(f"DROP TABLE {table}_old")
        con.commit()


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=60)
    con.executescript(SCHEMA)
    migrate(con)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    division: str
    district: str
    count: int


class ParseError(RuntimeError):
    pass


def parse_report(text: str) -> list[Row]:
    """Pull (division, district, count) out of a report page.

    Raises ParseError if the page is not a report page at all (error page,
    WAF interstitial, truncated response), so the caller can retry instead of
    silently recording a zero.
    """
    if "geo-clearance-count" not in text:
        raise ParseError("not a geo-clearance page")

    doc = LH.fromstring(text)
    tables = doc.xpath("//table")
    if not tables:
        raise ParseError("no table in response")

    # Locate the columns by header rather than trusting a fixed order.
    table = tables[0]
    headers = [
        re.sub(r"\s+", " ", (th.text_content() or "")).strip().lower()
        for th in table.xpath(".//tr[1]/th | .//tr[1]/td")
    ]

    def col(*names: str) -> int | None:
        for i, h in enumerate(headers):
            if any(n in h for n in names):
                return i
        return None

    i_div, i_dis, i_tot = col("division"), col("district"), col("total", "count")
    if i_div is None or i_dis is None or i_tot is None:
        raise ParseError(f"unexpected headers: {headers!r}")

    rows: list[Row] = []
    for tr in table.xpath(".//tr"):
        cells = [
            re.sub(r"\s+", " ", (td.text_content() or "")).strip()
            for td in tr.xpath("./td")
        ]
        if len(cells) <= max(i_div, i_dis, i_tot):
            continue
        raw = cells[i_tot].replace(",", "").strip()
        if not raw.isdigit():
            continue
        rows.append(Row(cells[i_div], cells[i_dis], int(raw)))
    return rows


def parse_reference(text: str) -> dict:
    """Extract divisions, districts (with validity) and countries from the form.

    Option labels are read straight out of the raw HTML, so entity references
    survive unless decoded here - the country list genuinely contains
    "Cote d&#039;Ivoire" and "Turks &amp; Caicos Islands".
    """
    out: dict = {"divisions": [], "districts": [], "countries": []}

    def clean(label: str) -> str:
        # Labels carry entities and non-breaking spaces ("North Macedonia\xa0(...)"),
        # both of which break exact-match joins downstream.
        return re.sub(r"\s+", " ", html.unescape(label)).strip()

    blk = re.search(r'<select id="division_name".*?</select>', text, re.S)
    if not blk:
        raise ParseError("division select not found")
    for v, n in re.findall(
        r'<option[^>]*value="(\d+)"[^>]*>\s*(.*?)\s*</option>', blk.group(0), re.S
    ):
        out["divisions"].append({"division_id": int(v), "name": clean(n)})

    blk = re.search(r'<select id="district_name".*?</select>', text, re.S)
    if not blk:
        raise ParseError("district select not found")
    for d, v, n in re.findall(
        r'<option class="district-option division-(\d+)"\s*value="(\d+)"\s*>\s*(.*?)\s*</option>',
        blk.group(0),
        re.S,
    ):
        out["districts"].append(
            {
                "district_id": int(v),
                "name": clean(n),
                "division_id": int(d),
                "is_valid": int(int(d) in VALID_DIVISION_IDS),
            }
        )

    blk = re.search(r'<select id="country_name".*?</select>', text, re.S)
    if not blk:
        raise ParseError("country select not found")
    for v, n in re.findall(
        r'<option[^>]*value="(\d+)"[^>]*>\s*(.*?)\s*</option>', blk.group(0), re.S
    ):
        out["countries"].append({"country_id": int(v), "name": clean(n)})

    return out


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------


# Genders the crawler actually fetches. Male is derived (all - female - other),
# which is exact because the source's three buckets sum to the unfiltered total.
GENDERS = {0: "all", 2: "female", 3: "other"}
MALE_ID = 1


def qkey(date_from: str, date_to: str, country_id: int | None, gender_id: int = 0) -> str:
    """Cache key for one request.

    Gender 0 produces the pre-gender key unchanged, so a database crawled
    before gender existed keeps every one of its ~74k logged requests.
    """
    base = f"{date_from}|{date_to}|{country_id if country_id is not None else 'ALL'}"
    return base if not gender_id else f"{base}|g{gender_id}"


class Crawler:
    def __init__(self, con: sqlite3.Connection, concurrency: int = CONCURRENCY):
        self.con = con
        self.sem = asyncio.Semaphore(concurrency)
        self.concurrency = concurrency
        self.client: httpx.AsyncClient | None = None
        self.n_done = 0
        self.n_err = 0
        self.t0 = time.time()

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(90.0, connect=30.0),
            limits=httpx.Limits(
                max_connections=self.concurrency,
                max_keepalive_connections=self.concurrency,
            ),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def fetch(
        self, date_from: str, date_to: str, country_id: int | None = None,
        gender_id: int = 0,
    ) -> list[Row]:
        params: dict = {"date_from": date_from, "date_to": date_to}
        if country_id is not None:
            params["country_name[]"] = country_id
        if gender_id:
            params["gender_id"] = gender_id

        last: Exception | None = None
        async with self.sem:
            for attempt in range(MAX_RETRIES):
                try:
                    r = await self.client.get(BASE, params=params)
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise RuntimeError(f"HTTP {r.status_code}")
                    r.raise_for_status()
                    return parse_report(r.text)
                except Exception as e:  # noqa: BLE001 - retry everything
                    last = e
                    await asyncio.sleep(min(2**attempt, 30) + 0.25 * attempt)
        raise RuntimeError(f"{qkey(date_from, date_to, country_id, gender_id)}: {last}")

    def progress(self, label: str, total: int) -> None:
        el = time.time() - self.t0
        rate = self.n_done / el if el > 0 else 0
        eta = (total - self.n_done) / rate if rate > 0 else 0
        print(
            f"\r  {label}: {self.n_done}/{total}  "
            f"{rate:4.1f} req/s  err={self.n_err}  eta {eta/60:5.1f}m",
            end="",
            flush=True,
        )


# --------------------------------------------------------------------------
# date helpers
# --------------------------------------------------------------------------


def daterange(a: dt.date, b: dt.date):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def months_between(a: dt.date, b: dt.date) -> list[tuple[dt.date, dt.date]]:
    out = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        first = dt.date(y, m, 1)
        last = dt.date(y, m, calendar.monthrange(y, m)[1])
        out.append((max(first, a), min(last, b)))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def weeks_in(a: dt.date, b: dt.date) -> list[tuple[dt.date, dt.date]]:
    out, d = [], a
    while d <= b:
        end = min(d + dt.timedelta(days=6), b)
        out.append((d, end))
        d = end + dt.timedelta(days=1)
    return out


def today() -> dt.date:
    return dt.date.today()
