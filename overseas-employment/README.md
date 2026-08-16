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

## Design notes

**The world map uses circles, not colour.** One destination is ~58% of all
records. Any choropleth binning either flattens Saudi Arabia or paints Russia
(8.5k) as dark as it. Circle *area* is honest at that skew — and it is the only
way Singapore and Maldives appear at all, since neither has a polygon at 110m
resolution despite being the 4th and 7th largest destinations.

**Bangladesh uses a colour ramp** with quantile breaks: 64 districts are far less
skewed, and a heatmap is the clearest read of regional concentration.

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
