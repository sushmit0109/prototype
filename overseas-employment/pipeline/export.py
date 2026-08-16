"""Validate the crawled data and export analysis-ready files.

Run after the crawl phases:

    python3 export.py

Writes to out/:
    emigration_daily_district_country.csv[.parquet]  main fact table
    emigration_daily_district_all.csv                control totals, no country filter
    districts.csv / countries.csv                    reference dimensions
    validation_report.txt                            every check, with numbers
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from bmet_crawler import (
    DATA_START,
    DB_PATH,
    VALID_DIVISION_IDS,
    VOLATILE_DATES,
    connect,
    months_between,
    today,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"

# Rows the report emits for records whose district was never recorded. They are
# real clearances and must survive into the fact table, but flagged so an
# analyst never mistakes them for a district.
UNKNOWN_MARKERS = {("unknown", "unknown")}


def reference(con):
    districts = pd.read_sql_query("SELECT * FROM district", con)
    divisions = pd.read_sql_query("SELECT * FROM division", con)
    countries = pd.read_sql_query("SELECT * FROM country", con)
    districts = districts.merge(
        divisions.rename(columns={"name": "division_name"}), on="division_id", how="left"
    )
    return districts, divisions, countries


def classify(df: pd.DataFrame, valid_pairs: set, valid_names: set) -> pd.DataFrame:
    """Tag every observed (division, district) pair with a record_class."""
    d = df.copy()
    key = list(zip(d["division"].str.strip().str.lower(), d["district"].str.strip().str.lower()))

    def cls(k):
        if k in UNKNOWN_MARKERS:
            return "unknown_district"
        if k in valid_pairs:
            return "valid"
        if k[1] in valid_names:
            return "valid_name_wrong_division"
        return "invalid"

    d["record_class"] = [cls(k) for k in key]
    return d


def main() -> None:
    OUT.mkdir(exist_ok=True)
    con = connect()
    districts, divisions, countries = reference(con)

    valid = districts[districts.is_valid == 1]
    valid_pairs = set(
        zip(valid["division_name"].str.strip().str.lower(), valid["name"].str.strip().str.lower())
    )
    valid_names = set(valid["name"].str.strip().str.lower())

    rep: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        rep.append(s)

    say("=" * 78)
    say("BMET / OEP geo-clearance crawl - validation report")
    say(f"generated {dt.datetime.now():%Y-%m-%d %H:%M}")
    say("=" * 78)

    # ---- reference integrity -------------------------------------------
    say("\n[1] REFERENCE DATA")
    say(f"  divisions in source            : {len(divisions)}")
    say(f"  district dropdown entries      : {len(districts)}")
    say(f"  ... valid (division id 1-8)    : {int(districts.is_valid.sum())}")
    say(f"  ... rejected as junk           : {int((~districts.is_valid.astype(bool)).sum())}")
    say("  rejected entries are foreign cities / test strings attached to")
    say("  division ids outside 1-8; the eight real divisions carry exactly 64")
    say("  districts, which matches Bangladesh's administrative geography.")
    bad = districts[districts.is_valid == 0]["name"].tolist()
    say(f"  rejected sample: {', '.join(bad[:12])} ...")

    if int(districts.is_valid.sum()) != 64:
        say("  !! WARNING: expected exactly 64 valid districts")

    # ---- fact tables ----------------------------------------------------
    say("\n[2] CRAWL COVERAGE")
    # Everything below analyses the unfiltered slice. The gender slices live in
    # the same tables and would otherwise be summed on top of it.
    dall = pd.read_sql_query("SELECT * FROM daily_all WHERE gender_id = 0", con)
    dctry = pd.read_sql_query("SELECT * FROM daily_country WHERE gender_id = 0", con)

    days_expected = (today() - DATA_START).days + 1
    days_all = dall["date"].nunique()
    say(f"  date range                     : {DATA_START} .. {today()}  ({days_expected} days)")
    say(f"  days present in daily_all      : {days_all}")
    say(f"  rows daily_all                 : {len(dall):,}")
    say(f"  rows daily_country             : {len(dctry):,}")
    say(f"  countries represented          : {dctry['country_id'].nunique()}")

    logged = pd.read_sql_query("SELECT COUNT(*) n FROM fetch_log", con)["n"][0]
    errs = pd.read_sql_query("SELECT COUNT(*) n FROM fetch_error", con)["n"][0]
    say(f"  successful requests logged     : {logged:,}")
    say(f"  request errors recorded        : {errs:,}")

    # days that the control series says are missing entirely
    got_days = set(dall["date"])
    missing = [
        (DATA_START + dt.timedelta(days=i)).isoformat()
        for i in range(days_expected)
        if (DATA_START + dt.timedelta(days=i)).isoformat() not in got_days
    ]
    say(f"  days missing from daily_all    : {len(missing)}")
    if missing:
        say(f"    {missing[:10]}")

    # ---- district validation -------------------------------------------
    say("\n[3] DISTRICT VALIDATION (observed rows vs reference)")
    dall = classify(dall, valid_pairs, valid_names)
    dctry = classify(dctry, valid_pairs, valid_names)

    for label, df in (("daily_all", dall), ("daily_country", dctry)):
        g = df.groupby("record_class")["count"].agg(["size", "sum"])
        say(f"  {label}:")
        for k in ["valid", "unknown_district", "valid_name_wrong_division", "invalid"]:
            if k in g.index:
                n, s = int(g.loc[k, "size"]), int(g.loc[k, "sum"])
                pct = 100 * s / max(df["count"].sum(), 1)
                say(f"    {k:<26} rows={n:>8,}  records={s:>12,}  ({pct:5.2f}%)")

    junk = dall[dall.record_class == "invalid"][["division", "district", "count"]]
    if len(junk):
        j = junk.groupby(["division", "district"])["count"].sum().sort_values(ascending=False)
        say("  invalid pairs seen in the data (excluded from the clean export):")
        for (dv, ds), c in j.items():
            say(f"    division={dv!r} district={ds!r} records={int(c)}")

    # ---- reconciliation -------------------------------------------------
    say("\n[4] RECONCILIATION  (sum over countries vs unfiltered control)")
    a = dall.groupby("date")["count"].sum().rename("all_countries")
    b = dctry.groupby("date")["count"].sum().rename("sum_of_countries")
    rec = pd.concat([a, b], axis=1).fillna(0).astype(int)
    rec["residual"] = rec["all_countries"] - rec["sum_of_countries"]

    say(f"  total, unfiltered control      : {int(rec['all_countries'].sum()):,}")
    say(f"  total, summed over countries   : {int(rec['sum_of_countries'].sum()):,}")
    tot_res = int(rec["residual"].sum())
    pct = 100 * tot_res / max(int(rec["all_countries"].sum()), 1)
    say(f"  residual (no country on record): {tot_res:,}  ({pct:.4f}%)")
    say("  A small positive residual is expected: a few clearances carry no")
    say("  country the filter can match. Negative or large values would mean")
    say("  double counting - check these days:")
    off = rec[(rec.residual < 0) | (rec.residual > 0.02 * rec.all_countries.clip(lower=1))]
    say(f"  days outside tolerance         : {len(off)}")
    for d, r in off.head(15).iterrows():
        say(f"    {d}  control={r.all_countries:>7,}  countries={r.sum_of_countries:>7,}  resid={r.residual:>6,}")
    rec.to_csv(OUT / "reconciliation_by_day.csv")

    # ---- month cross-check ---------------------------------------------
    # span_total holds country-month totals fetched as their own single query.
    # Summing the daily rows for that country-month must reproduce it exactly.
    # This checks the daily crawl against an independent observation of the
    # same quantity, and costs no extra requests.
    say("\n[4b] DAILY vs INDEPENDENT MONTH TOTALS")
    month_spans = {(a.isoformat(), b.isoformat()) for a, b in months_between(DATA_START, today())}
    months = pd.read_sql_query(
        "SELECT country_id, date_from, date_to, total FROM span_total WHERE gender_id = 0", con
    )
    # span_total also holds week spans; keep only the true month spans, since a
    # week inside a month is indistinguishable from one by date-prefix alone.
    months = months[
        [(a, b) in month_spans for a, b in zip(months["date_from"], months["date_to"])]
    ].copy()
    months["ym"] = months["date_from"].str[:7]
    months = months.groupby(["country_id", "ym"], as_index=False)["total"].sum()

    dc = dctry.copy()
    dc["ym"] = dc["date"].str[:7]
    daily_m = dc.groupby(["country_id", "ym"], as_index=False)["count"].sum()

    chk = months.merge(daily_m, on=["country_id", "ym"], how="left").fillna({"count": 0})
    chk["count"] = chk["count"].astype(int)
    chk["diff"] = chk["total"] - chk["count"]

    crawled = chk[chk["total"] > 0]
    exact = int((crawled["diff"] == 0).sum())
    say(f"  live country-months                : {len(crawled):,}")
    say(f"  daily sum matches month total      : {exact:,}  ({100*exact/max(len(crawled),1):.2f}%)")
    mism = crawled[crawled["diff"] != 0]
    say(f"  mismatched                         : {len(mism):,}")
    if len(mism):
        say(f"  net record difference              : {int(mism['diff'].sum()):,}")
        cmap0 = countries.set_index("country_id")["name"].to_dict()
        for _, r in mism.head(20).iterrows():
            say(
                f"    {cmap0.get(r.country_id, r.country_id):<28} {r.ym}"
                f"  month={int(r.total):>7,}  daily={int(r['count']):>7,}  diff={int(r['diff']):>6,}"
            )
        mism.assign(country=mism["country_id"].map(cmap0)).to_csv(
            OUT / "month_mismatches.csv", index=False
        )
        say("  -> full list in out/month_mismatches.csv")
    say("  Month totals were fetched before the daily rows, so any month")
    say("  touching a volatile bucket (2023-06) or still being entered will")
    say("  differ by the records added in between. Mismatches confined to those")
    say("  months are expected; anywhere else points to a crawl gap.")
    stray = mism[~mism["ym"].isin({d[:7] for d in VOLATILE_DATES} | {today().strftime("%Y-%m")})]
    say(f"  mismatches outside those months    : {len(stray)}"
        + ("  <- investigate" if len(stray) else "  (none)"))

    # ---- gender completeness --------------------------------------------
    # Male is derived as all minus female minus other, so an incomplete female
    # crawl silently inflates men rather than erroring. Check each crawled
    # gender's per-country sum against its own unfiltered control series.
    say("\n[4c] GENDER SLICES vs THEIR OWN CONTROL")
    grows = pd.read_sql_query(
        "SELECT gender_id, SUM(count) t FROM daily_country GROUP BY gender_id", con
    ).set_index("gender_id")["t"].to_dict()
    arows = pd.read_sql_query(
        "SELECT gender_id, SUM(count) t FROM daily_all GROUP BY gender_id", con
    ).set_index("gender_id")["t"].to_dict()
    if len(arows) <= 1:
        say("  gender slices not crawled yet")
    else:
        names = {0: "all", 1: "male", 2: "female", 3: "other"}
        for g in sorted(arows):
            ctrl, byc = arows.get(g, 0), grows.get(g, 0)
            gap = ctrl - byc
            pctg = 100 * gap / ctrl if ctrl else 0
            flag = "" if abs(pctg) < 3 else "   <- INVESTIGATE"
            say(f"  {names.get(g, g):<7} control={ctrl:>10,}  by country={byc:>10,}"
                f"  residual={gap:>7,} ({pctg:5.2f}%){flag}")
        tot = arows.get(0, 0)
        parts = sum(arows.get(g, 0) for g in (1, 2, 3) if g in arows)
        if 1 not in arows:
            parts = arows.get(0, 0) - arows.get(2, 0) - arows.get(3, 0)
            say(f"  male is derived: all - female - other = {parts:,}")
        say("  The residual is the Unknown-district share plus records with no")
        say("  country; it should sit near the same 1.3% seen for the whole set.")

    # ---- exports --------------------------------------------------------
    say("\n[5] EXPORTS")
    cmap = countries.set_index("country_id")["name"].to_dict()

    fact = dctry.copy()
    fact["country"] = fact["country_id"].map(cmap)
    fact["date_flag"] = fact["date"].where(
        ~fact["date"].isin(VOLATILE_DATES), other="volatile_sentinel"
    )
    fact["date_flag"] = fact["date_flag"].where(fact["date_flag"] == "volatile_sentinel", "ok")
    fact = fact.rename(columns={"division": "division_name", "district": "district_name"})
    fact["date"] = pd.to_datetime(fact["date"])
    fact["year"] = fact["date"].dt.year
    fact["month"] = fact["date"].dt.month
    fact = fact[
        ["date", "year", "month", "division_name", "district_name", "country_id",
         "country", "count", "record_class", "date_flag"]
    ].sort_values(["date", "country", "division_name", "district_name"])

    clean = fact[fact.record_class == "valid"].drop(columns=["record_class"])

    p = OUT / "emigration_daily_district_country.csv"
    clean.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(clean):>9,} rows   (record_class=valid only)")

    p = OUT / "emigration_daily_district_country_with_unknown.csv"
    keep = fact[fact.record_class.isin(["valid", "unknown_district"])]
    keep.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(keep):>9,} rows   (valid + unknown_district)")

    # Nothing the crawl saw is discarded: this keeps every class, so a decision
    # to exclude a row stays reversible at analysis time.
    p = OUT / "emigration_daily_district_country_raw.csv"
    fact.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(fact):>9,} rows   (all classes, unfiltered)")

    try:
        p = OUT / "emigration_daily_district_country.parquet"
        clean.to_parquet(p, index=False)
        say(f"  {p.name:<46} {len(clean):>9,} rows")
    except Exception as e:  # noqa: BLE001
        say(f"  parquet skipped ({e})")

    ctrl = dall.rename(columns={"division": "division_name", "district": "district_name"})
    p = OUT / "emigration_daily_district_all.csv"
    ctrl.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(ctrl):>9,} rows")

    p = OUT / "districts.csv"
    districts.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(districts):>9,} rows")

    p = OUT / "countries.csv"
    countries.sort_values("total_records", ascending=False, na_position="last").to_csv(p, index=False)
    say(f"  {p.name:<46} {len(countries):>9,} rows")

    # convenience rollups
    piv = clean.pivot_table(
        index=["district_name"], columns="country", values="count", aggfunc="sum", fill_value=0
    )
    p = OUT / "pivot_district_x_country.csv"
    piv.to_csv(p)
    say(f"  {p.name:<46} {piv.shape[0]:>9,} x {piv.shape[1]} matrix")

    mon = (
        clean.assign(ym=clean["date"].dt.to_period("M").astype(str))
        .groupby(["ym", "division_name", "district_name", "country"], as_index=False)["count"]
        .sum()
    )
    p = OUT / "emigration_monthly_district_country.csv"
    mon.to_csv(p, index=False)
    say(f"  {p.name:<46} {len(mon):>9,} rows")

    # ---- volatile dates -------------------------------------------------
    say("\n[5b] UNSTABLE DATE BUCKET")
    vol = clean[clean.date_flag == "volatile_sentinel"]
    say(f"  rows flagged volatile_sentinel : {len(vol):,}")
    say(f"  records in them                : {int(vol['count'].sum()):,}")
    say(f"  dates                          : {sorted(VOLATILE_DATES)}")
    say("  2023-06-19 went 2,168 -> 3,065 (+897, +41%) over one crawl session,")
    say("  while 06-20, 06-21, 06-22, 06-24, 06-25 and 06-26 returned")
    say("  byte-identical totals across the same span. It is the system's")
    say("  earliest date and behaves as a catch-all for records with no usable")
    say("  approval date. Growth is bursty, so a repeat-query check can show it")
    say("  as briefly stable. EXCLUDE IT from daily time-series work - it is not")
    say("  a day. Flagged, not dropped, via the date_flag column.")

    # ---- headline sanity ------------------------------------------------
    say("\n[6] HEADLINE FIGURES (clean export)")
    say(f"  clearances covered             : {int(clean['count'].sum()):,}")
    say(f"  distinct districts             : {clean['district_name'].nunique()}")
    say(f"  distinct countries             : {clean['country'].nunique()}")
    top = clean.groupby("country")["count"].sum().sort_values(ascending=False).head(10)
    say("  top destinations:")
    for k, v in top.items():
        say(f"    {k:<34} {int(v):>10,}")
    topd = clean.groupby("district_name")["count"].sum().sort_values(ascending=False).head(10)
    say("  top origin districts:")
    for k, v in topd.items():
        say(f"    {k:<34} {int(v):>10,}")

    (OUT / "validation_report.txt").write_text("\n".join(rep), encoding="utf-8")
    print(f"\nreport written to {OUT/'validation_report.txt'}")
    con.close()


if __name__ == "__main__":
    main()
