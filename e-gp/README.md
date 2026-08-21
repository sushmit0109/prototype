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

Two of seven sources are wired end-to-end (crawl -> archive -> build), and
they already cross-reference: the debarment register and the full historical
eContracts award list (871,684 awards, 2011-2026). The rest of the sources
and the beneficial-ownership graph are not built yet. Coverage is tracked
honestly in `data/*.json` `meta` blocks rather than implied by the presence
of a dashboard.

| Source | Portal page | Status |
|---|---|---|
| Debarment register | `DebarmentRpt.jsp` | **Live** -- 1,021 records, reason-tagged and severity-tiered |
| eContracts (awards) | `SearchNOA.jsp` | **Live** -- 871,684 records, full history (2011-2026) |
| Debarred-entity-won-a-contract flagging | -- | **Live** -- see "On the flagging methodology" below |
| Award detail pages (beneficial ownership, project codes) | `ViewAwardedContracts.jsp` | Not started -- list page already covers what flagging needs; detail pages would add the beneficial-ownership graph |
| Master tender list | `StdTenderSearch.jsp` | Not started -- would add Published/Processing tenders that never reach an award |
| eExperience (eCMS) | `SearcheCMS.jsp` | Not started |
| Registration | `RegistrationDetails.jsp` | Not started -- would give a real tenderer ID instead of name-only matching |
| Annual Procurement Plans | `SearchAPP.jsp` | Not started |
| Tender funnel counts | `Tenders.jsp` | Not started |

## Headline numbers (as of the last full build)

- 246 **active-violation** flags -- contracts signed while the awardee's
  debarment was in force -- worth ৳698.6M combined, across 58 distinct
  companies.
- 1,721 **post-debarment-award** flags (recidivism tracking, not a violation).
- These are *after* the false-positive filtering described below. Read them
  as leads to verify against the source, not proven findings.

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

python3 build_site.py ../raw/debarments.jsonl ../data/debarments.json
python3 build_contracts.py ../raw/contracts ../data/contracts
python3 flag_debarred_awards.py ../data/debarments.json ../data/contracts ../data/flags.json
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

`raw/contracts/` is an append-only log -- nothing already committed there is
ever rewritten. The initial 871K-record backfill (548MB as one file) is
split into one gzipped file per year purely to stay well under GitHub's
100MB per-file push limit (largest is 11.6MB); incremental daily runs each
add one small plain `.jsonl`. `data/contracts/<year>.json` resolves
`ministry`/`division`/`procuring_entity` to small integer IDs against
`data/contracts/dimensions.json` instead of repeating those strings on every
record, and drops the free-text `description` field entirely -- a first
pass that kept everything produced 50-77MB *per year*; this version's
largest year is ~30MB. `raw/` keeps the full text for provenance; `data/`
doesn't need to.

## Licence

Underlying figures are published by the Central Procurement Technical Unit
(CPTU) on eprocure.gov.bd.
