"""Drop the last N days from the crawl's memory so they are fetched again.

BMET keeps entering records against dates that have already passed, so a date
crawled once is not final. Deleting the recent window's fetch_log entries and
rows makes the next crawl re-fetch exactly that window and nothing else.

    python3 refresh_window.py [days]      # default 21

Also drops the month and week screening spans that overlap the window, so the
screen phase re-derives which countries were active in it.
"""

from __future__ import annotations

import datetime as dt
import sys

from bmet_crawler import connect, today


def main(days: int = 21) -> None:
    cutoff = (today() - dt.timedelta(days=days)).isoformat()
    con = connect()

    # Match on the span's END date, not its start. A month span like
    # 2026-07-01..2026-07-31 starts before the cutoff but still covers days
    # inside the window; keying on the start would leave its fetch_log entry in
    # place while its span_total row is deleted below, so the screen phase would
    # skip it and the month would vanish from the country rollup.
    n_log = con.execute(
        "DELETE FROM fetch_log WHERE substr(key,12,10) >= ?", (cutoff,)
    ).rowcount
    n_dc = con.execute("DELETE FROM daily_country WHERE date >= ?", (cutoff,)).rowcount
    n_da = con.execute("DELETE FROM daily_all WHERE date >= ?", (cutoff,)).rowcount
    # any screening span that ends on or after the cutoff overlaps the window
    n_sp = con.execute("DELETE FROM span_total WHERE date_to >= ?", (cutoff,)).rowcount
    con.execute("DELETE FROM fetch_error")
    con.commit()

    print(
        f"[refresh-window] re-fetching from {cutoff} ({days} days): "
        f"cleared {n_log} log entries, {n_dc} country rows, {n_da} control rows, "
        f"{n_sp} screening spans"
    )
    con.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 21)
