"""Phase runner for the BMET geo-clearance crawl.

Usage:
    python3 run_crawl.py bootstrap
    python3 run_crawl.py daily-all
    python3 run_crawl.py screen
    python3 run_crawl.py daily-country
    python3 run_crawl.py all            # every phase in order

Each phase is resumable: work already recorded in fetch_log is skipped.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time

import httpx

from bmet_crawler import (
    BASE,
    DATA_START,
    DENSE_MONTH_TOTAL,
    HEADERS,
    Crawler,
    connect,
    daterange,
    months_between,
    parse_reference,
    qkey,
    today,
    weeks_in,
)


def log_ok(con, key, rows, total):
    con.execute(
        "INSERT OR REPLACE INTO fetch_log(key, rows, total, fetched_at) VALUES (?,?,?,?)",
        (key, rows, total, dt.datetime.now().isoformat(timespec="seconds")),
    )


def log_err(con, key, err):
    con.execute(
        "INSERT INTO fetch_error(key, error, at) VALUES (?,?,?)",
        (key, str(err)[:500], dt.datetime.now().isoformat(timespec="seconds")),
    )


def done_keys(con) -> set[str]:
    return {k for (k,) in con.execute("SELECT key FROM fetch_log")}


def dead_days(con) -> set[str]:
    """Days the unfiltered control series says had no clearances at all.

    No country can hold a record on a day when the country-agnostic total is
    zero, so every per-country request for such a day is guaranteed empty and
    is skipped. These are overwhelmingly Fridays, Saturdays and public holidays.
    """
    fetched = {
        k.rsplit("|", 1)[0].split("|")[0]
        for (k,) in con.execute("SELECT key FROM fetch_log WHERE key LIKE '%|ALL'")
    }
    with_rows = {d for (d,) in con.execute("SELECT DISTINCT date FROM daily_all WHERE count > 0")}
    return fetched - with_rows


# --------------------------------------------------------------------------


def phase_bootstrap(con) -> None:
    print("[1/5] bootstrap: reference data")
    r = httpx.get(BASE, headers=HEADERS, timeout=60, follow_redirects=True)
    r.raise_for_status()
    ref = parse_reference(r.text)

    con.executemany(
        "INSERT OR REPLACE INTO division(division_id, name) VALUES (:division_id, :name)",
        ref["divisions"],
    )
    con.executemany(
        "INSERT OR REPLACE INTO district(district_id, name, division_id, is_valid)"
        " VALUES (:district_id, :name, :division_id, :is_valid)",
        ref["districts"],
    )
    # Insert-or-ignore keeps has_data/total_records from a previous screen, but
    # then never refreshes a changed label, so update names separately.
    con.executemany(
        "INSERT OR IGNORE INTO country(country_id, name) VALUES (:country_id, :name)",
        ref["countries"],
    )
    con.executemany(
        "UPDATE country SET name = :name WHERE country_id = :country_id", ref["countries"]
    )
    con.commit()

    nv = sum(d["is_valid"] for d in ref["districts"])
    print(
        f"      divisions={len(ref['divisions'])}  "
        f"districts={len(ref['districts'])} (valid={nv}, junk={len(ref['districts'])-nv})  "
        f"countries={len(ref['countries'])}"
    )


# --------------------------------------------------------------------------


async def phase_daily_all(con) -> None:
    """One request per day with no country filter: the control totals."""
    end = today()
    days = [d.isoformat() for d in daterange(DATA_START, end)]
    have = done_keys(con)
    todo = [d for d in days if qkey(d, d, None) not in have]
    print(f"\n[2/5] daily-all: {len(todo)} days to fetch ({len(days)} total)")
    if not todo:
        return

    async with Crawler(con) as cr:
        buf: list[tuple] = []

        async def one(day: str):
            key = qkey(day, day, None)
            try:
                rows = await cr.fetch(day, day)
            except Exception as e:  # noqa: BLE001
                cr.n_err += 1
                log_err(con, key, e)
                return
            buf.append((day, rows))
            cr.n_done += 1
            if cr.n_done % 25 == 0:
                cr.progress("daily-all", len(todo))

        await asyncio.gather(*[one(d) for d in todo])
        cr.progress("daily-all", len(todo))

    for day, rows in buf:
        con.executemany(
            "INSERT OR REPLACE INTO daily_all(date, division, district, count) VALUES (?,?,?,?)",
            [(day, r.division, r.district, r.count) for r in rows],
        )
        log_ok(con, qkey(day, day, None), len(rows), sum(r.count for r in rows))
    con.commit()
    print()


# --------------------------------------------------------------------------


async def phase_screen(con) -> None:
    """Country x month totals, so phase 4 can skip empty spans entirely."""
    end = today()
    countries = [c for (c,) in con.execute("SELECT country_id FROM country ORDER BY country_id")]
    spans = months_between(DATA_START, end)
    have = done_keys(con)

    todo = [
        (c, a.isoformat(), b.isoformat())
        for c in countries
        for a, b in spans
        if qkey(a.isoformat(), b.isoformat(), c) not in have
    ]
    print(
        f"\n[3/5] screen: {len(countries)} countries x {len(spans)} months "
        f"= {len(countries)*len(spans)} pairs, {len(todo)} to fetch"
    )
    if todo:
        async with Crawler(con) as cr:
            buf: list[tuple] = []

            async def one(cid, a, b):
                key = qkey(a, b, cid)
                try:
                    rows = await cr.fetch(a, b, cid)
                except Exception as e:  # noqa: BLE001
                    cr.n_err += 1
                    log_err(con, key, e)
                    return
                buf.append((cid, a, b, sum(r.count for r in rows), len(rows)))
                cr.n_done += 1
                if cr.n_done % 50 == 0:
                    cr.progress("screen", len(todo))

            await asyncio.gather(*[one(*t) for t in todo])
            cr.progress("screen", len(todo))

        con.executemany(
            "INSERT OR REPLACE INTO span_total(country_id, date_from, date_to, total) VALUES (?,?,?,?)",
            [(c, a, b, t) for c, a, b, t, _ in buf],
        )
        for c, a, b, t, n in buf:
            log_ok(con, qkey(a, b, c), n, t)
        con.commit()
        print()

    # Roll month totals up into the country table. span_total also holds week
    # spans (written by phase 4a), and a week that sits inside one month looks
    # identical to a month span under a substr(date,1,7) test - so match the
    # month spans exactly rather than by pattern, or the rollup double counts.
    month_spans = {(a.isoformat(), b.isoformat()) for a, b in spans}
    con.execute("UPDATE country SET total_records = 0, has_data = 0")
    totals: dict[int, int] = {}
    for cid, a, b, t in con.execute(
        "SELECT country_id, date_from, date_to, total FROM span_total"
    ):
        if (a, b) in month_spans:
            totals[cid] = totals.get(cid, 0) + t
    con.executemany(
        "UPDATE country SET total_records = ?, has_data = ? WHERE country_id = ?",
        [(t, int(t > 0), c) for c, t in totals.items()],
    )
    con.commit()

    live = con.execute("SELECT COUNT(*) FROM country WHERE has_data").fetchone()[0]
    tot = con.execute("SELECT SUM(total_records) FROM country").fetchone()[0]
    print(f"      countries with data: {live}  |  records covered: {tot:,}")


# --------------------------------------------------------------------------


async def phase_daily_country(con) -> None:
    """Expand live country-months to daily rows.

    Dense months go straight to per-day requests. Sparse months are screened by
    week first, so a country with three records in a month costs ~5 week probes
    plus the days of one week instead of 30 day probes.
    """
    end = today()
    # span_total mixes month spans (phase 3) and week spans (phase 4a); select
    # the month spans by exact date pair so a resumed run cannot mistake a week
    # for a month.
    month_spans = {(a.isoformat(), b.isoformat()) for a, b in months_between(DATA_START, end)}
    live_months = [
        (cid, a, b, t)
        for cid, a, b, t in con.execute(
            "SELECT country_id, date_from, date_to, total FROM span_total"
            " WHERE total > 0 ORDER BY country_id, date_from"
        )
        if (a, b) in month_spans
    ]
    print(f"\n[4/5] daily-country: {len(live_months)} live country-months")

    have = done_keys(con)
    dead = dead_days(con)
    print(f"      skipping {len(dead)} days with no clearances nationwide")

    def live_days(a: dt.date, b: dt.date) -> list[str]:
        return [d.isoformat() for d in daterange(a, b) if d.isoformat() not in dead]

    # --- 4a: week screen for sparse months -------------------------------
    week_todo = []
    for cid, a, b, total in live_months:
        if total >= DENSE_MONTH_TOTAL:
            continue
        for wa, wb in weeks_in(dt.date.fromisoformat(a), dt.date.fromisoformat(b)):
            if not live_days(wa, wb):
                continue  # whole week is dead nationwide
            k = qkey(wa.isoformat(), wb.isoformat(), cid)
            if k not in have:
                week_todo.append((cid, wa.isoformat(), wb.isoformat()))

    if week_todo:
        print(f"      4a week-screen: {len(week_todo)} requests")
        async with Crawler(con) as cr:
            buf: list[tuple] = []
            lock = asyncio.Lock()

            async def flush_weeks():
                payload, buf[:] = list(buf), []
                con.executemany(
                    "INSERT OR REPLACE INTO span_total(country_id, date_from, date_to, total)"
                    " VALUES (?,?,?,?)",
                    [(c, a, b, t) for c, a, b, t, _, _ in payload],
                )
                # A span of one day (the 29th of a leap February is the only
                # case a 7-day split produces) has the same fetch_log key as a
                # day request. Store its rows too, or phase 4b will treat the
                # key as done and the day never reaches daily_country.
                con.executemany(
                    "INSERT OR REPLACE INTO daily_country(date, country_id, division, district, count)"
                    " VALUES (?,?,?,?,?)",
                    [
                        (a, c, r.division, r.district, r.count)
                        for c, a, b, _, _, rows in payload
                        if a == b and rows
                        for r in rows
                    ],
                )
                for c, a, b, t, n, _ in payload:
                    log_ok(con, qkey(a, b, c), n, t)
                con.commit()

            async def one(cid, a, b):
                try:
                    rows = await cr.fetch(a, b, cid)
                except Exception as e:  # noqa: BLE001
                    cr.n_err += 1
                    log_err(con, qkey(a, b, cid), e)
                    return
                buf.append(
                    (cid, a, b, sum(r.count for r in rows), len(rows), rows if a == b else None)
                )
                cr.n_done += 1
                if cr.n_done % 50 == 0:
                    cr.progress("week-screen", len(week_todo))
                if len(buf) >= 400:
                    async with lock:
                        if len(buf) >= 400:
                            await flush_weeks()

            await asyncio.gather(*[one(*t) for t in week_todo])
            async with lock:
                await flush_weeks()
            cr.progress("week-screen", len(week_todo))
        print()

    # --- 4b: build the day list ------------------------------------------
    have = done_keys(con)
    day_todo: list[tuple[int, str]] = []

    for cid, a, b, total in live_months:
        ma, mb = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        if total >= DENSE_MONTH_TOTAL:
            spans = [(ma, mb)]
        else:
            spans = []
            for wa, wb in weeks_in(ma, mb):
                row = con.execute(
                    "SELECT total FROM span_total WHERE country_id=? AND date_from=? AND date_to=?",
                    (cid, wa.isoformat(), wb.isoformat()),
                ).fetchone()
                if row and row[0] > 0:
                    spans.append((wa, wb))
        for sa, sb in spans:
            for ds in live_days(sa, sb):
                if qkey(ds, ds, cid) not in have:
                    day_todo.append((cid, ds))

    print(f"      4b daily: {len(day_todo)} requests")
    if not day_todo:
        return

    async with Crawler(con) as cr:
        buf: list[tuple] = []
        flush_lock = asyncio.Lock()

        async def flush():
            payload, buf[:] = list(buf), []
            rowvals = [
                (day, cid, r.division, r.district, r.count)
                for cid, day, rows in payload
                for r in rows
            ]
            con.executemany(
                "INSERT OR REPLACE INTO daily_country(date, country_id, division, district, count)"
                " VALUES (?,?,?,?,?)",
                rowvals,
            )
            for cid, day, rows in payload:
                log_ok(con, qkey(day, day, cid), len(rows), sum(r.count for r in rows))
            con.commit()

        async def one(cid, day):
            try:
                rows = await cr.fetch(day, day, cid)
            except Exception as e:  # noqa: BLE001
                cr.n_err += 1
                log_err(con, qkey(day, day, cid), e)
                return
            buf.append((cid, day, rows))
            cr.n_done += 1
            if cr.n_done % 50 == 0:
                cr.progress("daily-country", len(day_todo))
            if len(buf) >= 400:
                async with flush_lock:
                    if len(buf) >= 400:
                        await flush()

        await asyncio.gather(*[one(*t) for t in day_todo])
        async with flush_lock:
            await flush()
        cr.progress("daily-country", len(day_todo))
    print()


# --------------------------------------------------------------------------


async def phase_repair(con) -> None:
    """Re-fetch any day whose fetch_log entry has no rows in daily_country.

    The log records that a query succeeded; daily_country holds what it
    returned. Those two can disagree if a request is logged by one code path
    and stored by another - which is exactly how single-day week spans lost
    their rows. This phase re-derives the gap from the data itself rather than
    trusting any particular phase to have been correct.
    """
    gaps = con.execute(
        """
        SELECT l.key, l.rows, l.total FROM fetch_log l
        LEFT JOIN (
            SELECT date, country_id, COUNT(*) n FROM daily_country GROUP BY date, country_id
        ) d ON d.date = substr(l.key, 1, 10)
          AND d.country_id = CAST(substr(l.key, 23) AS INTEGER)
        WHERE l.key NOT LIKE '%|ALL'
          AND substr(l.key, 1, 10) = substr(l.key, 12, 10)
          AND l.rows > 0
          AND d.n IS NULL
        """
    ).fetchall()
    print(f"\n[repair] day fetches logged but absent from daily_country: {len(gaps)}")
    if not gaps:
        print("      nothing to repair")
        return

    todo = []
    for key, _, _ in gaps:
        day, _, cid = key.split("|")
        todo.append((int(cid), day))

    async with Crawler(con) as cr:
        recovered = []

        async def one(cid, day):
            try:
                rows = await cr.fetch(day, day, cid)
            except Exception as e:  # noqa: BLE001
                cr.n_err += 1
                log_err(con, qkey(day, day, cid), e)
                return
            recovered.append((cid, day, rows))
            cr.n_done += 1

        await asyncio.gather(*[one(*t) for t in todo])

    con.executemany(
        "INSERT OR REPLACE INTO daily_country(date, country_id, division, district, count)"
        " VALUES (?,?,?,?,?)",
        [
            (day, cid, r.division, r.district, r.count)
            for cid, day, rows in recovered
            for r in rows
        ],
    )
    for cid, day, rows in recovered:
        log_ok(con, qkey(day, day, cid), len(rows), sum(r.count for r in rows))
    con.commit()
    n = sum(sum(r.count for r in rows) for _, _, rows in recovered)
    print(f"      repaired {len(recovered)} day-country fetches, {n:,} records recovered")


PHASES = {
    "bootstrap": ("sync", phase_bootstrap),
    "daily-all": ("async", phase_daily_all),
    "screen": ("async", phase_screen),
    "daily-country": ("async", phase_daily_country),
    "repair": ("async", phase_repair),
}


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    con = connect()
    order = list(PHASES) if which == "all" else [which]
    for name in order:
        if name not in PHASES:
            print(f"unknown phase {name!r}; choose from {list(PHASES)} or 'all'")
            sys.exit(2)
        kind, fn = PHASES[name]
        t = time.time()
        if kind == "sync":
            fn(con)
        else:
            asyncio.run(fn(con))
        print(f"      [{name} done in {(time.time()-t)/60:.1f} min]")
    con.close()


if __name__ == "__main__":
    main()
