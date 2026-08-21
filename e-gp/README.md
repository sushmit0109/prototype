# Bangladesh e-GP procurement tracker

An ontology-linked dataset and dashboard over Bangladesh's national
e-Government Procurement portal (eprocure.gov.bd) -- tenders, awarded
contracts, debarred tenderers, experience records, registrations and annual
procurement plans, cross-referenced so that a debarred company still winning
government contracts shows up as a flag instead of six unconnected search
results.

**Live:** <https://sushmit0109.github.io/prototype/e-gp/> *(not yet published
-- see Status)*

## Status

Five of seven sources are wired end-to-end (crawl -> archive -> build).
Registration turned out not to be a row-level source at all (see below), and
award detail pages / the beneficial-ownership graph are the one piece still
genuinely not started. Coverage is tracked honestly in `data/*.json` `meta`
blocks rather than implied by the presence of a dashboard.

| Source | Portal page | Status |
|---|---|---|
| Debarment register | `DebarmentRpt.jsp` | **Live** -- 1,021 records, reason-tagged and severity-tiered |
| eContracts (awards) | `SearchNOA.jsp` | **Live** -- 871,684 records, full history (2011-2026) |
| Master tender list | `AllTenders.jsp` / `TenderDetailsServlet` | **Live** -- 620,723 records, full history -- gives the invited/processing/awarded/cancelled funnel, since SearchNOA alone only has the awarded ones |
| eExperience (eCMS) | `SearcheCMS.jsp` | **Live** -- ~186K completed/ongoing work records, including the one real per-company ID (`company_unique_id`) anywhere on the site |
| Annual Procurement Plans | `SearchAPP.jsp` | **Live** -- 45,719 records across 18 financial years (PE/project summary level; per-office line items are one level deeper, not crawled) |
| Debarred-entity-won-a-contract flagging | -- | **Live** -- see "On the flagging methodology" below |
| Spending, vendor recurrence & concentration, tender funnel | -- | **Live** -- `build_insights.py`, see the dashboard's Spending/Vendors/Tenders sections |
| Registration | `RegistrationDetails.jsp` | **Resolved as out of scope** -- the page only exposes aggregate national counts, no per-record search or ID; would have been the source of a real tenderer ID for matching, but doesn't expose one |
| Award detail pages (beneficial ownership, project codes) | `ViewAwardedContracts.jsp` | Not started -- the list page already covers what flagging/spending analysis needs; detail pages would add the beneficial-ownership graph |
| Tender funnel counts | `Tenders.jsp` | **Skipped by design** -- the master tender list's own `status` field gives a richer breakdown (10 categories) than this page's 3 buckets, with no separate crawl needed |

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

## Dashboard design

The first version of this page was a KPI wall followed by several fully-
dumped tables (1,967 flag rows rendered at once, no search, no pagination) --
information density with no hierarchy, which is a bad trade for a page meant
to be read by people who don't already know what they're looking for. The
current version leads with a handful of headline findings stated as plain
sentences (`renderHeadlines` in `app.js`), then lets anyone go as deep as
they want: tabbed + searchable vendor tables, a filterable + paginated flags
table (20 rows at a time), and all the honest methodology caveats moved into
one collapsible section at the bottom instead of a paragraph blocking every
section. The headline numbers are computed from the real procurement-method
mix, not guessed -- an early draft used `DPM` (direct, no-bid) as the
"non-competitive" headline and got 0.1%, which undersells the real story:
`LTM` (limited/invitation-only tendering) is 44% of contracts by count.

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
```

`pipeline/common.py` holds the shared HTTP client used by every source: one
session cookie (the portal's search pages are POST servlets behind a plain
JSESSIONID, no CAPTCHA), a UA that identifies this project, and a bounded
concurrency + rate limiter (8 sockets in flight, ~8 req/s aggregate --
enough that the full 871K-award history took about 10 minutes, capped well
short of anything that would strain a government server). New source
crawlers should use it rather than opening their own connections.

`pipeline/entity.py` and `pipeline/dates.py` hold the name-normalisation and
date-parsing every other stage shares.

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
