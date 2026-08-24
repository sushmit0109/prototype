# Bangladesh e-GP procurement tracker

An ontology-linked dataset and dashboard over Bangladesh's national
e-Government Procurement portal (eprocure.gov.bd) -- tenders, awarded
contracts, debarred tenderers, experience records, and annual procurement
plans, cross-referenced instead of read as six unconnected search results:
which offices spend how much on what, which vendors cross ministry lines,
which companies share a beneficial owner, and which debarred companies won
contracts anyway.

**Live:** <https://sushmit0109.github.io/prototype/e-gp/> *(not yet published
-- see Status)*

## Status

Every source the portal exposes at row level is now wired end-to-end
(crawl -> archive -> build). Registration turned out not to be a row-level
source at all (see below). Two sources are deliberately *sampled* rather than
exhaustive, both for the same reason -- they are per-record detail pages
holding data that doesn't vary per record, so they are crawled
highest-value-first and resumed daily: award detail pages (Tenderer ID,
beneficial ownership) and the itemised Annual Procurement Plan. Coverage is
tracked honestly in `data/*.json` `meta` blocks rather than implied by the
presence of a dashboard.

| Source | Portal page | Status |
|---|---|---|
| Debarment register | `DebarmentRpt.jsp` | **Live** -- 1,021 records, reason-tagged and severity-tiered |
| eContracts (awards) | `SearchNOA.jsp` | **Live** -- 871,684 records, full history (2011-2026) |
| Master tender list | `AllTenders.jsp` / `TenderDetailsServlet` | **Live** -- 620,723 records, full history -- gives the invited/processing/awarded/cancelled funnel, since SearchNOA alone only has the awarded ones |
| eExperience (eCMS) | `SearcheCMS.jsp` | **Live** -- ~186K completed/ongoing work records, including the one real per-company ID (`company_unique_id`) anywhere on the site |
| Annual Procurement Plans | `SearchAPP.jsp` | **Live** -- 45,719 records across 18 financial years (PE/project summary level) |
| Debarred-entity-won-a-contract flagging | -- | **Live** -- see "On the flagging methodology" below |
| Spending, vendor recurrence & concentration, tender funnel | -- | **Live** -- `build_insights.py`, see the dashboard's Spending/Vendors/Tenders sections |
| Registration | `RegistrationDetails.jsp` | **Resolved as out of scope** -- the page only exposes aggregate national counts, no per-record search or ID; would have been the source of a real tenderer ID for matching, but doesn't expose one |
| Award detail pages (Tenderer ID, beneficial ownership, project/funding) | `ViewAwardedContracts.jsp` | **Live, sampled** -- one representative contract per vendor (most-recent, not highest-value -- the field is a ~2025-era addition, older award pages don't have it at all), largest vendors first; see "Ownership network" below |
| Office spend profiles, cross-departmental vendors | -- | **Live** -- `build_office_profiles.py`, see the dashboard's Spending (offices table) and Networks sections |
| Shared-beneficial-owner network | -- | **Live, heavily caveated** -- `build_ownership.py`, see "On the ownership-matching methodology" below |
| Tender funnel counts | `Tenders.jsp` | **Skipped by design** -- the master tender list's own `status` field gives a richer breakdown (10 categories) than this page's 3 buckets, with no separate crawl needed |
| Annual Procurement Plan per-office line items (itemised estimates + planned method) | `resources/common/StdSearch.jsp` -> `SearchAPPServlet` (`action=advSearch`) | **Live, sampled** -- the government's own pre-tender cost estimate and planned procurement method, package by package. An earlier pass wrongly recorded this as unreachable: the link on SearchAPP.jsp is *relative*, so it resolves under `/resources/common/`, and requesting `/StdSearch.jsp` at the site root returns an "Invalid Page" shell. Crawled busiest-offices-first, resumable. |
| Plan vs. outcome (estimate vs. award, planned vs. actual method) | -- | **Live** -- `build_plan_vs_actual.py`, see the dashboard's Finding 03 |
| ৳50 crore administrative-ceiling bunching & split-pattern detection | -- | **Live** -- `build_ceiling.py`, see Finding 05 |
| Tender topic mix (CPV category) | `GetCpvTree` / `TenderDetailsServlet` (`cpvCategory` filter) | **Live** -- 61 top-level categories, counted overall and per political era (see Sectors below); the top 25 also have their full tender-id lists crawled and joined against `data/contracts` to rank by *awarded value*, not just tender count |
| Geographic spend by district | derived from `district` on eContracts | **Live** -- `build_geo.py`; map geometry is a one-off static asset from an external open-data source, not eprocure.gov.bd -- see "Where the district map geometry comes from" in the dashboard's Methodology. Each district also carries a yearly time series (for the map's trend sparklines) and a procurement-nature mix (the closest thing to a per-district sector breakdown this data supports -- CPV category can't be attributed to a district, since the tender search has no location filter) |
| Political-era segmentation (Awami League / interim / elected government) | -- | **Live** -- `eras.py`, applied across contracts, plan-vs-actual, the ceiling analysis, debarment flags, and CPV counts; see the dashboard's Governments section |

## Headline numbers (as of the last full build)

- **871,684** contracts, **৳744,946 Cr** total value, 2011-2026.
- **246 active-violation** flags -- contracts signed while the awardee's
  debarment was in force -- worth ৳698.6M combined, across 58 distinct
  companies. (**1,721 post-debarment-award** flags separately -- recidivism
  tracking, not a violation.) These are *after* the false-positive filtering
  described below; read them as leads to verify, not proven findings.
- The single largest recipient, Mohammed Eunus & Brothers (Pvt.) Ltd., has
  won ৳7,841 Cr across 605 different procuring entities and 23 ministries --
  spread thin enough that this reads as a large, genuine national
  contractor, not a concentration red flag.
- **25%** of contract value nationally bypassed fully open tendering (OTM),
  going instead through LTM (limited/invitation-only -- 44% of contracts by
  *count* but only 15% by value, i.e. used mostly for smaller purchases),
  RFQ, or direct methods.
- **2%** of tenders end up cancelled or rejected rather than awarded.
- **26%** of contracts that can be matched to their Annual Procurement Plan
  entry are awarded within half a percentage point of *exactly 10% below* the
  government's own pre-tender estimate, and a further **18%** land on exactly
  5% below -- so about **44% of awards sit on one of two round discounts**.
  Genuine price competition against an estimate produces a smooth spread, not
  narrow spikes on round numbers; the figure looks set by convention rather
  than discovered by bidding. (This is also the likeliest explanation for the
  repeated-price-point clustering above: plan estimates themselves cluster on
  clean round figures -- Tk 3,00,000 / 5,00,000 / 10,00,000 -- and awards land
  at a fixed discount underneath them.)
- **224** matched packages (0.5%) were awarded more than 15% over their own
  estimate, ৳92.8 crore above what was budgeted for them on those alone.
- The typical discount off estimate is not one national number -- it's a
  habit that differs by ministry, from ~1.5% below (Water Resources) to
  ~16.4% below (Communications), measured on the median ratio rather than
  the overrun tail (see the retraction note below for why). The "10%-below"
  convention itself only becomes routine from the late 2010s on -- under 4%
  of matched packages in 2013-2014, 30%+ every year from 2020. See
  `data/plan_vs_actual.json` -> `cost_structure`.
- The **Tk 50 crore** administrative-approval ceiling shows the bunching
  shape a threshold gets gamed into: 1.5x as many contracts land just under
  it (Tk 45-50cr) as just over it (Tk 50-55cr), and 402 office-vendor pairs
  show multiple sub-threshold awards within 45 days of each other summing
  past it. See `pipeline/build_ceiling.py` / `data/ceiling.json`. Neither
  test proves splitting on its own -- each is a lead, not a verdict.
- By CPV (Common Procurement Vocabulary) category -- the only source here
  with real topical detail, beyond the three-way Works/Goods/Services split
  -- **Construction work** alone is 54.3% of all tenders nationally; the
  entirety of **Computer and related services** (government ICT
  procurement) is 1.2%. See `pipeline/scrape_cpv.py` / `data/cpv_categories.json`.

  *A note on the plan-vs-award figures above:* an earlier pass over the
  first ~107k plan line items gave 40%/11%/28x on the discount-spike and
  method-change numbers; ~301k items moved them to 26%/18%/10x. The
  itemised-plan crawl is ordered busiest-office-first, so a partial run is a
  biased sample, not a random one -- treat any figure here as provisional
  until the crawl covers all 10,205 offices. The dashboard reads these from
  `data/plan_vs_actual.json` rather than hardcoding them, so it self-corrects
  as coverage grows.

  *A retraction:* the plan/award join is on package reference text alone,
  and some offices type office-shorthand ("se", "ee"), a bare running number
  ("01", "280"), or even the literal placeholder "na" into that field
  instead of a real package code. Those aren't unique, so the join was
  pairing a plan estimate with whichever unrelated contract happened to
  share the same short text -- the same false-positive shape as the
  debarment name-collision bug below (one "na"-to-"na" collision alone
  produced 16 bogus matches). This is what originally drove the reported
  **"10x more downgrades than upgrades"** method-change claim (568 vs 59):
  after excluding references shared by more than 3 procuring entities
  nationally, references under 6 characters, and matches at an implausible
  ratio (>10x or <0.1x -- no real estimate-to-award relationship differs by
  two orders of magnitude), the true count is **19 vs 18** -- no detectable
  direction at this sample size. The same bug had inflated the per-ministry
  overrun comparison in an earlier draft (Finance and Education looked like
  high-overrun outliers; that vanished once the false matches were removed).
  Both claims have been removed from the dashboard rather than kept with
  smaller numbers. See `GENERIC_PE_SPREAD`, `MIN_REF_LEN`, and
  `SANITY_RATIO_MIN`/`MAX` in `build_plan_vs_actual.py`.
- **30** vendors are awarded by three or more different ministries -- several
  well-known national conglomerates (Smart Technologies, RFL Plastics,
  Global Brand, Star Tech, Hatil) among them, none looking like a
  concentration concern given how widely spread their business is.
- Beneficial-ownership data sampled for 4,241 of the largest vendors
  (71% of total contract value): 2,162 had the field populated, and 56 owner
  names turn up on 2+ different companies -- some real (RFL Plastics'
  chairman correctly tying it to two sister companies), some almost
  certainly just common-name collisions ("Abul Kalam Azad" across three
  unrelated small firms). See "On the ownership-matching methodology" --
  every one of these needs a human look before it means anything.
- Contracts bunch **1.54x** more just under the Tk 50 crore administrative
  approval ceiling (Tk 45-50cr) than just over it (Tk 50-55cr), and **402**
  office-vendor pairs show multiple sub-threshold awards clustered within 45
  days of each other summing past it -- the shape a threshold gets gamed
  into. See `build_ceiling.py`.
- By CPV category, **Construction work** is **54.3%** of all tenders
  nationally; the whole of **Computer and related services** (government ICT
  procurement) is **1.2%**. Split by political era, construction's own share
  runs 59.4% (Awami League) -> 37.9% (interim) -> 26.7% (elected), while
  categories like computing equipment and food products roughly double their
  share over the same span -- the state's purchasing mix has genuinely
  shifted, not just its total. See `scrape_cpv.py` / `data/cpv_categories.json`.
- Split by district (`build_geo.py` + `build_district_geo.py`), spend varies
  more than 10x between districts of otherwise comparable size, Dhaka aside.
  Boundaries are traced from an external open-data source, not
  eprocure.gov.bd -- see the dashboard's Methodology.
- Split by government (`eras.py`: Awami League through 2024-08-07, an
  interim government through 2026-02-16, an elected government since), the
  pace of contracting has risen every era (141 -> 271 -> 378 contracts/day)
  and open tendering's share has held or improved (75.1% -> 71.8% -> 81.7%
  of value) -- though the elected-government window is, as of this build,
  only a few months old and the smallest of the three. See the dashboard's
  Governments section for the full comparison, including debarment
  violations and the discount-convention share by era.

## Dashboard design

The page is structured as **eight findings**, not as a data browser. Earlier
versions were a KPI wall over dumped tables -- which is strictly worse than
the government's own portal, since that at least has a search box. If a
reader wanted an info-dump they would go to eprocure.gov.bd; the only reason
to build this is to say something the raw source cannot.

So each section states one claim in a sentence, supports it with exactly one
chart chosen for that claim, and closes with a two-column "why it matters /
what it isn't" note. `build_analysis.py` precomputes the findings into
`data/analysis.json`; `app.js` renders hand-built inline SVG (no chart
library, no build step). Series colours are the four validated slots from the
`dataviz` reference palette, checked against this page's own dark surface
(`#131620`): all pass the lightness band, chroma floor, adjacent CVD
separation, normal-vision floor and 3:1 contrast.

Three things this pass caught that are worth recording, because each was a
claim that would have shipped wrong:

- **The "concentration paradox" that wasn't.** Reading the top of a sorted
  list of offices by top-vendor share suggested rampant local monopoly. The
  actual distribution is the opposite: of 1,333 offices large enough to test,
  1,001 give their biggest supplier under 20%, and only **9** exceed 60%. The
  finding is a short named watchlist, not a systemic claim -- and the chart
  shows the whole distribution so the reader can see that for themselves.
- **"Open tendering never recovered"** was too strong: it fell 94% -> 66% by
  2019, then partly rebounded into the 70-80% band. The claim now says that.
- **"Those contracts are almost all invitation-only"** was too strong for the
  top-20 repeated price points: the count-weighted LTM share is 70%, not
  ~90% (the very top prices hit 87-93%, but Tk 3,00,000 is only 34% and drags
  the aggregate down). The claim now gives 70% against the 44% baseline.

Layout is verified by rendering the chart code headlessly against the real
data and asserting no `NaN`/`undefined` geometry and no label overflowing its
SVG viewBox -- which caught two real overflows (`chartConc`, `chartCross`)
that a colour validator never would.

## Layout

```
e-gp/
  index.html  app.js  styles.css   the dashboard (static, no build step)
  data/                            everything the page reads (built artefacts)
  raw/                             the collected archive (the pipeline's store)
  pipeline/                        collectors + the build
```

The page only ever reads `data/`, never the government site directly.

## Pipeline

```bash
cd pipeline

python3 scrape_debarment.py ../raw/debarments.jsonl
python3 scrape_noa.py "../raw/contracts/backfill_$(date -u +%F).jsonl"        # full crawl
python3 scrape_noa.py "../raw/contracts/incoming_$(date -u +%F).jsonl" \
    --stop-known=<file of known tender_ids>                                   # incremental
python3 scrape_tenders.py "../raw/tenders/backfill_$(date -u +%F).jsonl"      # same full/incremental split
python3 scrape_ecms.py ../raw/ecms.jsonl
python3 scrape_app.py ../raw/app_plans.jsonl

python3 build_site.py ../raw/debarments.jsonl ../data/debarments.json
python3 build_contracts.py ../raw/contracts ../data/contracts
python3 build_tenders.py ../raw/tenders ../data/tenders
python3 build_ecms.py ../raw/ecms.jsonl ../data/ecms
python3 build_app.py ../raw/app_plans.jsonl ../data/app_plans.json
python3 flag_debarred_awards.py ../data/debarments.json ../data/contracts ../data/flags.json
python3 build_insights.py ../data/contracts ../data/insights.json ../data/tenders
python3 build_office_profiles.py ../data/contracts ../data/tenders ../data/office_profiles.json
python3 build_analysis.py ../data/contracts ../data/tenders ../data/analysis.json

python3 scrape_app_items.py ../raw/app_plans.jsonl ../raw/app_items.jsonl --limit=1200 --resume
python3 build_plan_vs_actual.py ../raw/app_items.jsonl ../data/contracts ../data/plan_vs_actual.json

python3 pick_vendor_samples.py ../data/contracts ../raw/vendor_samples.jsonl --limit=20000
python3 scrape_award_details.py ../raw/vendor_samples.jsonl ../raw/award_details.jsonl --resume
python3 build_ownership.py ../raw/award_details.jsonl ../data/ownership.json

python3 build_ceiling.py ../data/contracts ../data/ceiling.json
python3 scrape_cpv.py ../raw/cpv_categories.json                              # ~250 lightweight requests, ~2min
python3 build_cpv.py ../raw/cpv_categories.json ../data/cpv_categories.json
python3 build_geo.py ../data/contracts ../data/geo.json                       # daily; geometry itself is not

# One-off, not part of the daily job -- district boundaries don't change day to day:
python3 build_district_geo.py <districts.geojson> ../data/bd_districts_geo.json
```

`pipeline/common.py` holds the shared HTTP client used by every source: one
session cookie (the portal's search pages are POST servlets behind a plain
JSESSIONID, no CAPTCHA), a UA that identifies this project, and a bounded
concurrency + rate limiter (8 sockets in flight, ~8 req/s aggregate --
enough that the full 871K-award history took about 10 minutes, capped well
short of anything that would strain a government server). New source
crawlers should use it rather than opening their own connections.

`pipeline/entity.py` and `pipeline/dates.py` hold the name-normalisation and
date-parsing every other stage shares. `pipeline/eras.py` holds the
political-era boundaries (Awami League / interim / elected government) used
by `build_analysis.py`, `build_plan_vs_actual.py`, `build_ceiling.py`,
`flag_debarred_awards.py`, and `scrape_cpv.py`. `pipeline/districts.py`
holds the district name normalisation (pre-/post-2018 spelling variants)
shared by `build_geo.py` and `build_district_geo.py`.

### On the flagging methodology (read this before trusting a number)

A name-only first pass -- match `awarded_to` against the debarment register
on normalised company name, no other check -- produced **8,707** "active
violation" flags worth **৳53.4 billion**. It was wrong. The top offender,
company_key `"khan enterprise"`, alone accounted for 637 of them: "Khan" is
one of the most common surnames in Bangladesh and "Enterprise" a generic
small-firm suffix, and that exact name string appears on 1,984 contracts
across 15+ districts nationwide, while the debarment register has exactly
one such firm, registered at one address in Mirpur, Dhaka. That's obviously
dozens of unrelated small businesses sharing a name pattern, not one company
evading a ban -- and shipping that number as a corruption finding would have
been a real, public false accusation against real, named companies.

`flag_debarred_awards.py` now requires two things before it will emit a
flag, not one:

1. **District corroboration** -- the contract's district must match a
   district taken from the debarment record's own address.
2. **Not generic nationwide** -- the same company name must not appear, as
   an awardee, in more than 5 districts across the *entire* contracts
   corpus (not just the matched ones). A real single firm doing government
   work plausibly operates in a handful of districts; a name spread across
   15+ is a name pattern, not an entity.

That cut the result to 246 active-violation flags across 58 companies, at
roughly a hundred times lower total value, and spot-checking the survivors
looks like real signal -- e.g. "Albatross International" appears repeatedly
at the same procuring entity (RPATC Chattogram), same district, entirely
within its debarment window. This is still a heuristic without a shared
company ID between sources, so it deliberately trades missed real
violations for fewer false accusations -- not a judgment call to relax
without a better identity signal (a real tenderer/registration ID, once the
Registration source is built, would be that signal).

- **`entity.py`'s normalisation only strips genuine legal-form suffixes**
  (Ltd/Limited/Pvt/Company/M-S), not business-descriptor words like
  Enterprise/Trading/Construction -- an earlier version stripped those too,
  on the mistaken assumption they were boilerplate, which was the first,
  smaller version of the same false-positive problem.
- **"Reasons" is free text.** `reason_tags` on debarment records is a
  keyword-tagged guess (collusion / forgery / fraud / corruption /
  non-performance / misrepresentation / unspecified), not an official
  category -- the source doesn't provide one.
- **Severity is derived, not sourced.** `severity` combines scope breadth (a
  Single Tender ban scores lower than a nationwide e-GP Portal ban),
  duration, and whether the same company recurs in the list -- a first-pass
  heuristic, not an official rating.

### On the ownership-matching methodology

`ViewAwardedContracts.jsp` carries the one real per-company identifier on
the whole site (Tenderer ID) and a full beneficial-ownership table, but only
on recent award pages -- confirmed directly: an award from mid-2024 has
neither field in its HTML at all, one from August 2026 has both, which
tracks a ~2025-era Public Procurement Rules requirement rather than being
patchy data collection. Crawling all 871,684 contracts to learn ownership
that doesn't change per-contract would be wasted work, so
`pick_vendor_samples.py` samples one representative contract per distinct
vendor (their most recent, since recency is what determines whether the
field exists at all), largest vendors by total value first -- the top
10,000 of 56,330 vendors already account for 85% of total contract value.

Matching a shared owner across companies inherits the same lesson as the
debarment flagging, made worse: a personal name is an even smaller,
more collision-prone namespace than a company name. `build_ownership.py`
requires at least three space-separated tokens in the normalised name before
treating two owner entries as the same person -- but this is nowhere near
airtight. In the data crawled so far, the owner name **"Abul Kalam Azad"**
groups three companies (M/S Abul Kalam Azad, Mac International, M/S Mitu
Traders) that are, on inspection, almost certainly three unrelated people --
it's one of the most common male names in Bangladesh. Compare that to
**"Ahsan Khan Chowdhury"**, which correctly ties RFL Plastics Limited to two
of its real sister companies (Property Development Limited, Rangpur Metal
Industries) -- he's the real, public chairman of the PRAN-RFL Group. Both
pass the same three-token filter; only one is right. There is no automated
signal in this dataset that reliably tells them apart -- every group in
`data/ownership.json` needs a human glance at whether the companies look
like an actual corporate family before it means anything. `tenderer_id`
matches (the same portal-assigned ID under two different company-name
spellings) are the one much stronger signal here, when they occur.

### Storage

`raw/contracts/` and `raw/tenders/` are append-only logs -- nothing already
committed there is ever rewritten. Each initial backfill (548MB / ~430MB as
one file) is split into one gzipped file per year purely to stay well under
GitHub's 100MB per-file push limit (largest is ~12MB); incremental daily
runs each add one small plain `.jsonl`. `data/contracts/<year>.json` and
`data/tenders/<year>.json` resolve the administrative hierarchy
(ministry/division/organization/procuring_entity) to small integer IDs
against a `dimensions.json` instead of repeating those strings on every
record, and drop free-text description fields entirely -- a first pass at
contracts that kept everything produced 50-77MB *per year*; this version's
largest year is ~30MB. `raw/` keeps the full text for provenance; `data/`
doesn't need to. eCMS and APP are small enough (~186K and ~46K records) that
neither bucketing nor dimension-encoding was worth the complexity yet.

## Licence

Underlying figures are published by the Central Procurement Technical Unit
(CPTU) on eprocure.gov.bd.
