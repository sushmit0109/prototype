# Bangladesh Overseas Employment

Where Bangladesh's overseas workers come from and where they go: every emigration
clearance BMET has issued since 19 June 2023, by home district and destination
country, rebuilt daily.

Live at <https://sushmit0109.github.io/prototype/overseas-employment/>

```
index.html          the page
styles.css          design tokens + layout, light and dark
app.js              projections, linked filtering, charts (no libraries)
data/*.json         what the page reads — rebuilt by the pipeline
pipeline/           the crawler and the build
```

## The source, and why the crawler is shaped like this

<https://www.oep.gov.bd/reports/geo-clearance-count> renders a table of
`Division | District | Total` for a date range. **Country is a filter, not a
column**, so a district x country breakdown only exists if you issue one request
per (country, date) and read the district table out of each response.

The naive space is 202 countries x 1,155 days = **233,310 requests**. The crawler
funnels it to ~74,000 without losing a record, by screening countries over the
whole range, then by month, then by week for sparse months, and by skipping days
the country-agnostic control series says had no clearances at all (Fridays,
Saturdays, public holidays).

Refreshes are incremental — the crawl database is cached between runs and only
the last 21 days are re-fetched, because BMET keeps entering records against
dates that have already passed:

| | requests | time |
|---|---|---|
| First full crawl | ~74,000 | ~80 min |
| Daily refresh | ~1,000 | **~1.5 min** |

## Data quality — what is filtered, and why

**42 of the 106 district-dropdown entries are not districts.** They are foreign
address fragments — `RIYADH`, `DUBAI`, `Al Murabba`, `Geylang Road`,
`Shimo Karako - 1906` — plus test strings like `asacv` and `1235`. They are
rejected *structurally*, not by a blocklist: every district option carries a
`division-<id>` class, and these hang off division ids 150 and 264–300, which do
not appear in the division dropdown at all. Filtering to divisions 1–8 leaves
exactly 64 districts, matching Bangladesh's actual geography.

Checked against the source rather than assumed: all 42 together hold **1 record**
out of 3.3 million. `pipeline/verify.py districts` re-runs that test and fails if
any rejected entry ever exceeds 50 records, so a genuinely new district cannot be
silently discarded.

**2023-06-19 is excluded entirely.** It is the system's earliest date and behaves
as a catch-all bucket rather than a day — it went 2,168 → 3,065 (+41%) during a
single crawl session while every neighbouring date returned byte-identical
totals. It appears to absorb records with no usable approval date.

**`Unknown` district (~1.3% of records)** is real — clearances whose district was
never recorded. Excluded from the maps, never silently dropped.

**Côte d'Ivoire is listed twice** in the source ("Ivory Coast" and
"Cote d'Ivoire"); the two are merged.

## Reading the dashboard

The two maps are **linked filters**, which is what makes a 64 × 157 flow legible
without drawing 10,000 arrows. Each view is aggregated against *the other* view's
filter, so a selection never blanks out the map you clicked it on.

Nationally Malaysia is the second destination; for **Comilla**, Qatar overtakes
it. That is the kind of sub-stratum difference the corridor view exists for.

The period is set by dragging the timeline or by the buttons above it (All time,
Last 12 months, or a single year). **Months / By year** switches the timeline to
a year-over-year view — the same twelve months with one line per year — which is
the only way to see whether the current year is running above or below the last.
It replaces the timeline rather than sitting beside it, so there are never two
time axes competing for the same glance.

Every ranking row carries its own **sparkline and trend %** for the selected
period, so trends compare twelve at a time rather than one. Selecting Comilla
shows its destination mix shifting hard: Malaysia down 100% (to zero), Maldives
up 458%, Portugal up 387%, UAE down 83%.

## Design notes

**Both maps are heatmaps, on deliberately different scales.** Districts use
quantile breaks (64 values, ~2 orders of magnitude). Destinations use
order-of-magnitude breaks — 100 / 1k / 10k / 100k / 1M — because they span six
orders and one country is ~58% of all records; quantile bins there would colour
Russia at 8.5k as darkly as Saudi Arabia at 1.9M. The breaks are spaced so the
low bands stay pale, since a choropleth of counts inflates whatever is
physically large and Russia, Canada and Brazil are big on screen but small in
the data. Countries with no polygon at 110m — Singapore, Maldives, Malta, Hong
Kong, Bahrain — are drawn as dots filled from the same ramp.

Origin is blue, destination is orange — one sequential hue per context. Dark mode
is re-stepped rather than flipped, so near-zero recedes toward the background.

## Caveats

A clearance is permission to work abroad — intent to travel, not arrival, and one
person may appear once per clearance. Districts are the worker's **home
district**, not a route or current location. The most recent days are incomplete
while data entry continues.

## Running it

```bash
pip install -r pipeline/requirements.txt
cd pipeline
python run_crawl.py all      # first run: ~80 min
python build_dashboard.py
```

Environment overrides: `BMET_DB` (crawl database), `BMET_SITE` (where
`data/*.json` is written), `BMET_GEO_CACHE` (downloaded boundaries).

Boundaries: districts from geoBoundaries (BGD ADM2), world from Natural Earth via
world-atlas.
