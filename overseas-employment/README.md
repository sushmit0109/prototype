# Dashboard — publishing to GitHub Pages

The `site/` directory is the whole website: no build step, no framework, no CDN.
Copy it to a repo, turn Pages on, and it works.

```
site/
  index.html
  assets/style.css        design tokens + layout, light and dark
  assets/app.js           projections, linked filtering, charts
  data/dashboard.json     the cube (623 KB)
  data/insights.json      the findings tab, built by ../build_insights.py
  data/bd-districts.geo.json
  data/world.geo.json
```

## Publishing to sushmit0109.github.io/prototype/

1. Create a repo named **`prototype`** under your account.
2. Put the contents of `site/` at the repo root (or keep this whole project in
   the repo and set Pages to serve `/site`).
3. **Settings → Pages → Source: GitHub Actions**.
4. Push. The URL is `https://sushmit0109.github.io/prototype/`.

Everything is relative-path, so it works from a subdirectory without config.

## Keeping it current

`.github/workflows/update-data.yml` refreshes and redeploys daily at 02:30
Dhaka time, and can be run by hand from the Actions tab.

The important part is that the refresh is **incremental**. The crawl database is
cached between runs, `refresh_window.py` drops the last 21 days so BMET's
backfilling is picked up, and only those dates are re-fetched:

| | requests | time |
|---|---|---|
| First full crawl | ~74,000 | ~80 min |
| Daily refresh | ~1,000 | **~1.5 min** |

A cache miss costs a slow run, never a wrong result — the crawl re-derives
everything it needs from the database it finds.

## How to read the dashboard

The two maps are **linked filters**, which is what makes a many-to-many flow
legible without a hairball of arrows:

- **Click a district** → the world map and the destination ranking redraw for
  that district only. The district map keeps showing the national pattern so
  you never lose your bearings.
- **Click a country** → the district map recolours to show which districts feed
  it.
- **Click both** → a single corridor, e.g. Comilla → Qatar.
- **Drag the timeline**, or use the period buttons (All time · Last 12 months ·
  each year) → every panel follows. Click the chart once to reset the period.
- **All / Men / Women** in the corridor bar slices every panel at once — both
  maps, the timeline, both rankings. Women are ~6% of all clearances, so the
  slice changes the destination mix sharply rather than just scaling it down.
- **People / Money / Insights** tabs sit at page level, directly under the title, because
  the switch changes every panel. A control that restructures the whole page
  does not belong inside one panel's header — the earlier version put it in the
  district map's toolbar, where its scope was invisible. Panel-level toggles
  (Total / Per 100k / Per 100k · 15–64) stay in the panel they govern.
- **Money's timeline has three views**: *Fiscal years* (the bars that select
  the period), *Month by month* (national remittance from July 2014) and
  *By year* (the same twelve months, one line per fiscal year — the Ramadan and
  Eid peaks are the recurring spikes). Only the national series is monthly;
  Bangladesh Bank publishes district and country money annually, so the monthly
  views show the shape and do not drive the map selection.
- **Money** switches the whole page to a second dataset — both maps, both
  rankings and the timeline. The district map becomes recipient districts, the
  world map becomes *source* countries, and the timeline switches to a
  fiscal-year axis (FY2016-17 → FY2025-26), because the money series is annual
  and runs seven years deeper than the clearance data. A **Workers vs money**
  panel appears with it.
- **Remittance** on the origin panel is a second dataset, not another cut of
  the first: Bangladesh Bank's district remittance (million USD, by fiscal
  year). It answers "where does the money land", which is a different question
  from "where do the workers come from".
- **Total / Per 100k / Per 100k · 15–64** on the origin panel switches the
  district map, ranking and KPI between absolute clearances, clearances per
  100,000 residents, and per 100,000 working-age residents (15–64, 67.0% of the
  population nationally — the closer denominator, since almost every migrant is
  of working age).
  Absolute counts largely rank districts by how big they are; the rate measures
  propensity. Only the origin side is normalised — a rate per Bangladeshi head
  is meaningless on a destination country.
- **Months / By year** switches the timeline between the continuous series and a
  year-over-year view: the same twelve months with one line per year, which is
  the only way to see whether this year is running above or below the last.
- **Every ranking row carries its own sparkline and trend %** for the selected
  period, so you compare twelve trajectories at once instead of one at a time.
  With a district selected, the destination sparklines *are* that district's
  changing destination mix.

Each view is aggregated against *the other* view's filter, so a selection never
blanks out the map you selected it on.

It surfaces things a national total hides. Nationally Malaysia is the second
destination; for **Comilla**, Qatar overtakes it. That is the sub-stratum
difference the corridor view is for.

## Design decisions worth knowing

**Both maps are heatmaps, but on different scales — deliberately.** Districts
use quantile breaks: 64 values spanning ~2 orders of magnitude, where equal-count
bins read cleanly. Destinations use **order-of-magnitude breaks** (100 / 1k / 10k
/ 100k / 1M), because they span *six* orders and one country is ~58% of all
records. Quantile bins there would colour Russia at 8.5k as darkly as Saudi
Arabia at 1.9M. The breaks are spaced so the top band isolates the single
dominant destination and the low bands stay pale — a choropleth of counts
inflates whatever is physically large, and Russia, Canada and Brazil are big on
screen but small in the data. Every break is labelled on the legend.

**Countries too small to draw get a dot** filled from the same ramp — Singapore,
Maldives, Malta, Hong Kong, Bahrain and the island states have no polygon at
110m resolution, and Singapore is the 4th largest destination. One encoding,
two mark types.

**Connection arcs are drawn inside the world map, not between the panels.**
Curves spanning the two panels would need a page-level overlay tracking two
separate SVGs through scroll and resize, and on mobile the panels stack
vertically so the curves would run backwards. Arcs within one SVG are plain
bezier paths that render identically everywhere. They are capped at the 30
busiest corridors and drawn at hairline weight: they carry no value the circles
do not already show, so their only job is to make the corridor read as a link.

**Bangladesh uses a colour ramp** with quantile breaks, because 64 districts are
far less skewed and a heatmap is the clearest read of regional concentration.

**Origin is blue, destination is orange** — one sequential hue per context, so
the two halves of the page are never confused.

**The year view replaces the timeline rather than joining it.** A second chart
would have meant two time axes on screen competing for the same glance. The
period buttons and the view switch are one row each — about 30px of added
height for both features.

**Years take an ordinal ramp, not categorical hues,** because years are ordered:
older lighter, current darkest and at double stroke weight, each line labelled at
its end so identity never rests on colour. Selecting a single year moves that
emphasis onto it, so the chart and the period buttons always agree. The ramp has
its own tokens — the sequential map ramp is tuned for large filled areas and left
the oldest line too dim to follow at 1.7px.

**The two remittance maps are deliberately not linked.** Bangladesh Bank
publishes remittance by source country (Annex-III) and by recipient district
(Annex-IV) as separate marginals and never crosses them, so "how much money
from Saudi Arabia reached Comilla" does not exist in any published source.
Clicking a country therefore cannot filter the district map, and the hint on
each panel says so rather than implying a breakdown that was never published.

**Remittance per migrant, not per clearance.** An earlier version put each
country's share of clearances beside its share of remittance. That was a
category error: clearances are a *flow* (new workers over three years) and
remittance comes from the *stock* (everyone settled abroad, over decades), so
the comparison mostly reported when a diaspora formed. "United States: 0.0% of
workers, 13.3% of money" says nothing about earnings.

The denominator is now the number of Bangladeshis actually living in each
country, from UN DESA's International Migrant Stock 2024, and the figure is
per year. That is a fair comparison, and it inverts the earlier reading: on FY
2025-26, South Africa is about $20,500 per migrant per year, the UK $17,000 and
Malaysia $12,000, against Saudi Arabia's much lower figure on a stock of 2.4
million. Countries with fewer than 20,000 residents are suppressed, and the
stock is a 2024 snapshot applied across the selected years.

**Money per head is per resident per year, not per 100,000.** Per-100k is the
right unit for counting people and a nonsense one for currency — it produced
figures in the hundreds of millions, which then met a formatter expecting
millions and rendered as "521030.40bn USD". The buttons relabel to *Per person*
on the money lens for the same reason.

**There is deliberately no "USD per clearance".** Bangladesh Bank credits
remittance to the *recipient's* district, while a clearance records the worker's
*home* district. Dhaka takes 34.8% of remittance against 4.1% of clearances, so
the ratio puts it at 15.6x the national median — a fact about where bank
accounts are, presented as if it were about migrant earnings. The lens shows
remittance on its own and puts both shares in the tooltip instead, which makes
the mismatch visible without inventing a metric that misleads.

Remittance is annual and has no destination breakdown, so the country filter
cannot apply to it; the hint says so when a country is selected, and the
monthly sparkline is dropped in that mode rather than showing a clearance
series beside an annual figure.

**Male is derived, not crawled.** The source's three gender buckets sum exactly
to the unfiltered total (3,135,331 + 200,894 + 9 = 3,336,234), so crawling women
and "other" is enough — men fall out by subtraction. That halves what would
otherwise be a second and third full pass. The build refuses to emit a male cube
if any cell comes out negative, which is what an incomplete female crawl would
produce.

**"Other" has no button.** It is nine records in three years. It stays inside
*All* so the totals reconcile, but a third of the control real estate for nine
records would be noise.

**The data files are fetched with `cache: 'no-cache'`.** `app.js` and the JSON
are cached independently (`max-age=600` on Pages), so a returning visitor could
run new code against a data file from before a schema change — which is exactly
how the per-100k view once came up blank on a stale cache. Revalidating costs a
304 when nothing changed. As a second line of defence, a denominator missing
from the data disables its button rather than rendering an empty map.

**Per-100k uses the 2022 census**, from the UN OCHA Common Operational Dataset
(UNFPA / BBS) — the same eight spelling variants as the boundary file, and the
build fails if any district is left without a population. The denominator is
fixed at 2022, so internal migration since then is not reflected, and the
measure is a propensity rate rather than a headcount.

**Dark mode is stepped, not flipped.** On the dark surface the ramp inverts so
near-zero recedes toward the background. The steps are also re-spaced rather
than mirrored: the low bands sit close to the surface (~1.6:1) and the contrast
is spent at the top (~10:1), or the mid-tones — which is where the physically
large, low-volume countries land — end up louder than the destinations that
matter.

**No value-ramp on the bar charts.** Bars are one hue; length already encodes
the value.

**The Insights tab replaces the page rather than adding a panel to it.** It is a
reading column at a fixed measure — the findings are an argument that has to be
followed in order, and none of them respond to a district, country or period
selection. Leaving the maps and the corridor bar on screen would advertise
controls that do nothing to what is below them, so `.dash` elements are hidden
and the tab draws once from `data/insights.json`.

Its charts are deliberately plainer than the dashboard's: no tooltips, no
legends to decode, every value printed at the end of its own bar. Each one
exists to make a single sentence checkable. Two of them earned specific
treatments:

- **The horse-race coefficients share one axis and one zero line,** because the
  finding is not that 0.739 is large — it is that one interval clears zero and
  the other contains it. An interval spanning zero is drawn in grey so that
  reads before anyone does the arithmetic.
- **The fragility chart shows top-destination share, not the implied loss.**
  The loss is `1 − exp(−0.896 · share)`, a monotone transform, and across the
  nine most concentrated districts it compressed everything into 47–51% —
  ten bars of visibly equal length. The variation lives in the input, so the
  chart shows the input, across its real range (81% down to 43%) by pairing the
  six most concentrated districts with the four least.

**Findings are built, not typed.** `build_insights.py` re-reads the corridor
benchmark, the Malaysia difference-in-differences and the network horse race
from `../../bbs census/causal/`, plus the crawl database and the Bangladesh Bank
CSVs, and emits every number the tab prints. Rerun it when any of those change.

**The KPI row follows the lens.** `aggregate()` only ever walks the clearance
cube — remittance is a separate annual series read through `remValue` /
`countryValue` — so on the money lens three of the four tiles used to report
people on a page whose maps, rankings and timeline were all money ("Busiest
month · Aug 2025 · 147,372 clearances" beside "Dhaka · 65.13bn USD"). They now
switch with the tab, and *Busiest month* becomes *Biggest year*, because the
district series is annual and a monthly label over it could not be true. The
total's subtitle reports the fiscal years that actually contributed rather than
the selected span: the country series (Annex-III) starts a year before the
district series (Annex-IV), so the span can include a year no district covers.

## Data caveats shown on the page

- A clearance is permission to work abroad — intent to travel, not arrival.
- Districts are the worker's **home district**, not a route or a current location.
- ~1.3% of records carry no district (`Unknown`) and are excluded from the maps.
- **2023-06-19 is excluded entirely.** It is a catch-all bucket in the source
  that keeps absorbing records (+41% observed in one session) rather than a real
  day. See the project README.
- The most recent days are incomplete while data entry continues.

## Local preview

```bash
python3 -m http.server 8000 --directory site
# http://localhost:8000
```

Regenerate the data files after a crawl with `python3 build_dashboard.py`.
