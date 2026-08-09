# বাংলাদেশের বিদ্যুৎ ও লোডশেডিং · Bangladesh electricity & load-shedding

A live dashboard over the electricity figures the Bangladeshi authorities
publish: hourly demand/supply/load-shed, the daily NLDC system report, the
per-power-station table with its stated reasons, and area-wise demand — collected
automatically every hour, cross-checked, and shown in Bengali and English.

**Live:** <https://sushmit0109.github.io/prototype/electricity/>

## Layout

```
electricity/
  index.html  app.js  styles.css   the dashboard (static, no build step)
  data/                            everything the page reads (built artefacts)
  raw/                             the collected archive (the pipeline's store)
  pipeline/                        collectors + the build
```

The page never touches a government site directly — it only reads `data/`.

## Sources

| Source | What it gives | Coverage |
|---|---|---|
| [PGCB hourly table](https://erp.powergrid.gov.bd/web/generations/view_demand_supply_loadshed_bn) | hourly demand, supply, load-shed (Bengali numerals) | 2015-04 → today (~98k rows) |
| [BPDB daily generation archive](https://misc.bpdb.gov.bd/daily-generation-archive) | NLDC PDF reports: system summary, zone×fuel energy, per-plant output **and stated reason**, grid substation peak loads | 2024-07 → today |
| [BPDB area-wise demand](https://misc.bpdb.gov.bd/area-wise-demand) | zone demand & load-shed, one request per date | 2015 → today |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | plant/substation coordinates, district boundaries | — |

## Pipeline

```bash
cd pipeline && pip install -r requirements.txt

python scrape_pgcb.py --full          # full hourly backfill (~2,020 pages)
python scrape_areawise.py --since 2015-01-01
python scrape_bpdb_index.py --full    # enumerate archive PDF links
python parse_bpdb_pdf.py --all        # download + parse the PDFs
python geo_build.py                   # OSM layers (cached; only needed rarely)
python build_site.py                  # raw/ -> data/
```

Incremental (what the hourly job runs) is the same commands with small windows.
`.github/workflows/electricity-update.yml` runs at :17 past every hour and
commits only what changed.

### Notes on the sources

Things worth knowing, all handled in the pipeline rather than papered over:

- **Both government hosts serve an incomplete TLS chain.** `common.get()` tries
  verified first and falls back per-host on `SSLError`.
- **The `page_1/2/3` slots in the archive are not a fixed form** — which NLDC
  sheet lands in which slot varies by day, so each PDF is classified by its own
  title before parsing.
- **The archive listing date is the publication date**; the report inside is
  normally for the previous day. The date is taken from the PDF text.
- **The area-wise page's own "Total" row is hard-coded to 0** — zones are summed
  instead. Its pre-2016 rows repeat one value across all nine zones and are
  flagged `suspect`.
- **A few PGCB rows carry a mistyped year** (`05-08-0008`) or an impossible
  load-shed (65,359 MW, more than twice national capacity). Both are quarantined
  and counted, not charted.

## What the data shows about itself

The dashboard's last section reports these, computed at build time:

1. **"Demand" is an accounting identity, not a measurement.** In PGCB's hourly
   table demand = supply + load-shed exactly in ~99.5% of rows that have all
   three; in the NLDC report energy demand = generated + unserved in 100% of
   days. Demand is derived *from* the load-shed figure, so the two cannot be used
   to check each other, and true demand may be higher than published.
2. **The area-wise page is not an independent second source** — it republishes
   the NLDC evening-peak table, agreeing exactly on nearly every day compared.
3. **The 11-year archive is mostly empty.** Demand and supply are blank before
   2026, and before 2022 the load-shed column reads 0 in ~99.9% of hours. The
   site marks that period "not reported" rather than drawing it as zero.

## Storage

Files are bucketed so the hourly commit stays small: hourly data is one file per
month, area-wise one file per year, and the daily/monthly aggregates exclude the
still-accumulating current day, so they change once a day rather than 24 times.

## Licence

Underlying figures are published by PGCB and BPDB. Basemap, boundaries and
coordinates © OpenStreetMap contributors (ODbL).
