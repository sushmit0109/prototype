"""Independent checks against the live site.

    python3 verify.py sample [n]    re-fetch n random (country, day) queries and
                                    compare cell by cell with the database
    python3 verify.py districts     test the district-validity rule itself:
                                    does every rejected entry really hold no
                                    records, and is every accepted one real?
    python3 verify.py all           both

The districts check matters because the validity rule is structural (division
id must be 1-8). If BMET ever files a genuine district under a new division id,
that rule would silently discard real data - this check catches that by asking
the site how many records each rejected entry actually holds.
"""

from __future__ import annotations

import asyncio
import sys

from bmet_crawler import (
    BASE,
    DATA_START,
    VOLATILE_DATES,
    Crawler,
    connect,
    parse_report,
    today,
)

# A rejected entry holding more than this many records is not plausibly a
# data-entry artefact and should be re-examined by hand.
JUNK_TOLERANCE = 50


async def check_sample(n: int = 150) -> bool:
    con = connect()
    rows = con.execute(
        "SELECT DISTINCT date, country_id FROM daily_country ORDER BY RANDOM() LIMIT ?",
        (n,),
    ).fetchall()
    if not rows:
        print("no daily_country data to verify yet")
        return True

    print(f"[sample] re-fetching {len(rows)} random (country, day) queries ...")
    ok = mismatch = failed = 0
    problems: list[str] = []

    async with Crawler(con) as cr:
        async def one(day, cid):
            nonlocal ok, mismatch, failed
            try:
                live = await cr.fetch(day, day, cid)
            except Exception as e:  # noqa: BLE001
                failed += 1
                problems.append(f"FETCH FAIL {day} c={cid}: {e}")
                return
            stored = {
                (d, s): c
                for d, s, c in con.execute(
                    "SELECT division, district, count FROM daily_country"
                    " WHERE date=? AND country_id=?",
                    (day, cid),
                )
            }
            fresh = {(r.division, r.district): r.count for r in live}
            if fresh == stored:
                ok += 1
            else:
                mismatch += 1
                diff_live = {k: v for k, v in fresh.items() if stored.get(k) != v}
                diff_db = {k: v for k, v in stored.items() if fresh.get(k) != v}
                problems.append(
                    f"MISMATCH {day} c={cid}\n"
                    f"    live differs: {dict(list(diff_live.items())[:5])}\n"
                    f"    db   differs: {dict(list(diff_db.items())[:5])}"
                )

        await asyncio.gather(*[one(d, c) for d, c in rows])

    print(f"  identical : {ok}\n  mismatched: {mismatch}\n  fetch fail: {failed}")
    for p in problems[:20]:
        print("  " + p)
    passed = mismatch == 0 and failed == 0
    print("  PASS" if passed else "  FAIL")
    con.close()
    return passed


async def check_districts() -> bool:
    """Ask the site how many records each dropdown entry actually holds."""
    con = connect()
    entries = con.execute(
        "SELECT district_id, name, division_id, is_valid FROM district ORDER BY district_id"
    ).fetchall()
    fr, to = DATA_START.isoformat(), today().isoformat()
    print(f"[districts] querying {len(entries)} dropdown entries over {fr}..{to} ...")

    results: dict[int, int] = {}
    sem = asyncio.Semaphore(6)

    async with Crawler(con) as cr:
        # district_name is not part of Crawler.fetch's signature, so issue these
        # through the same client with the extra filter.
        async def one_district(did):
            params = {"date_from": fr, "date_to": to, "district_name": did}
            async with sem:
                for attempt in range(4):
                    try:
                        r = await cr.client.get(BASE, params=params)
                        r.raise_for_status()
                        results[did] = sum(x.count for x in parse_report(r.text))
                        return
                    except Exception:  # noqa: BLE001
                        await asyncio.sleep(2 * (attempt + 1))
                results[did] = -1

        await asyncio.gather(*[one_district(d) for d, _, _, _ in entries])

    rejected = [(d, n, v) for d, n, _, v in entries if not v]
    accepted = [(d, n, v) for d, n, _, v in entries if v]

    rej_tot = sum(max(results.get(d, 0), 0) for d, _, _ in rejected)
    acc_tot = sum(max(results.get(d, 0), 0) for d, _, _ in accepted)
    loud = [(d, n, results.get(d, 0)) for d, n, _ in rejected if results.get(d, 0) > JUNK_TOLERANCE]
    empty_accepted = [(d, n) for d, n, _ in accepted if results.get(d, 0) == 0]
    errs = [d for d, v in results.items() if v < 0]

    print(f"  accepted entries : {len(accepted):>3}   records held: {acc_tot:>12,}")
    print(f"  rejected entries : {len(rejected):>3}   records held: {rej_tot:>12,}")
    if acc_tot:
        print(f"  rejected share of all records: {100*rej_tot/(acc_tot+rej_tot):.6f}%")
    print(f"  query errors     : {len(errs)}")

    nonzero = sorted(
        ((results.get(d, 0), n, d) for d, n, _ in rejected if results.get(d, 0) > 0), reverse=True
    )
    if nonzero:
        print("  rejected entries that DO hold records:")
        for c, n, d in nonzero:
            print(f"    id={d:<5} {n[:34]:<36} {c:,}")
    else:
        print("  no rejected entry holds a single record")

    if empty_accepted:
        print(f"  !! accepted districts with zero records ({len(empty_accepted)}):")
        for d, n in empty_accepted[:20]:
            print(f"    id={d:<5} {n}")

    passed = not loud and not errs
    if loud:
        print("  !! FAIL - these rejected entries hold real volume, re-examine the rule:")
        for d, n, c in loud:
            print(f"    id={d:<5} {n[:34]:<36} {c:,}")
    print("  PASS - the division-id rule is not discarding real data" if passed else "  FAIL")
    con.close()
    return passed


async def check_stability(repeats: int = 5) -> bool:
    """Query the same dates several times and report any whose total moves.

    A historical day must return the same figure every time. One that climbs is
    not a day at all but a bucket still absorbing records, and including it in a
    time series produces a phantom trend.
    """
    con = connect()
    days = [d for (d,) in con.execute(
        "SELECT DISTINCT date FROM daily_all ORDER BY RANDOM() LIMIT 12"
    )]
    days = sorted(set(days) | set(VOLATILE_DATES))
    print(f"[stability] querying {len(days)} dates x{repeats} ...")

    moving: list[tuple[str, list[int]]] = []
    async with Crawler(con) as cr:
        for day in days:
            totals = []
            for _ in range(repeats):
                try:
                    totals.append(sum(r.count for r in await cr.fetch(day, day)))
                except Exception:  # noqa: BLE001
                    totals.append(-1)
            stable = len(set(totals)) == 1
            known = day in VOLATILE_DATES
            mark = "" if stable else ("  <- known volatile" if known else "  <- UNEXPECTED")
            print(f"  {day}  {totals}{mark}")
            if not stable:
                moving.append((day, totals))

    unexpected = [d for d, _ in moving if d not in VOLATILE_DATES]
    stable_but_flagged = [d for d in VOLATILE_DATES if d in days and d not in dict(moving)]
    if unexpected:
        print(f"  FAIL - undeclared volatile dates: {unexpected}")
        print("  add them to VOLATILE_DATES in bmet_crawler.py")
    if stable_but_flagged:
        print(f"  note - flagged but stable in this run: {stable_but_flagged}")
    if not unexpected:
        print("  PASS - every date outside VOLATILE_DATES returned a frozen total")
    con.close()
    return not unexpected


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    results = []
    if which in ("sample", "all"):
        results.append(await check_sample(n))
    if which in ("districts", "all"):
        results.append(await check_districts())
    if which in ("stability", "all"):
        results.append(await check_stability())
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
