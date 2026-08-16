# District-wise inward remittance — what exists, and how to get it

Short answer: **Bangladesh Bank does publish district-wise remittance, but never
as a downloadable series.** It exists only as tables inside PDFs, and how far
back you can go depends on which of three shapes you use.

| Shape | Granularity | Coverage | Where |
|---|---|---|---|
| **Annex-IV** of the monthly report | district × **fiscal year** | **FY 2017-18 → FY 2024-25** | every recent monthly report |
| **Table 4/5** of the monthly report | district × **month** | ~Sep 2024 → current | one PDF per month |
| `districtwise_remittance.pdf` | district × month, current FY only | overwritten monthly | `econdata`, Wayback for old ones |

**FY 2017-18 is the floor.** Bangladesh Bank began collecting district-level
remittance through its `T_ME_D_REMITTANCE` template around then; nothing
district-level exists before it. Anything earlier (back to 1972 in Economic
Trends) is national or country-wise, not district.

## Why the monthly series is short

The *Monthly Report on Workers' Remittance Inflows* is itself new — the earliest
issue on the Bank's site and in the Wayback Machine is **September 2024**. So
district × month effectively starts mid-2024, not 2017.

Each report shows roughly the **last six months of the current fiscal year**
plus the FY-to-date total. So two reports cover a fiscal year: the **December**
issue gives July–December, the **June** issue gives January–June.

## Sources

- Index of monthly reports:
  <https://www.bb.org.bd/en/index.php/publication/publictn/3/87>
- Remittance data page:
  <https://www.bb.org.bd/en/index.php/econdata/wageremitance>
- Current district snapshot:
  <https://www.bb.org.bd/econdata/remittance/districtwise_remittance.pdf>
- Historical snapshots of that file (only three exist):
  `http://web.archive.org/web/{20240108100516,20240911034625,20241118073334}id_/https://www.bb.org.bd/econdata/remittance/districtwise_remittance.pdf`

**The site blocks scripted downloads.** `bb.org.bd` sits behind an F5/BIG-IP
JavaScript challenge: `curl` gets an HTML interstitial, and even a real browser's
request context is connection-reset on direct `.pdf` paths. Fetching the PDFs
needs a tool that renders the challenge. Wayback copies download normally.

## Usage

```bash
python3 parse_bb_remittance.py pdfs/*.pdf
```

Writes `remittance_monthly.csv` (district, fiscal_year, year, month, date,
remittance_musd) and `remittance_annual_fy.csv` (district, fiscal_year,
remittance_musd). Values are **million USD**. Needs poppler's `pdftotext`.

District names are normalised to the BMET spellings in
`districts_canonical.json`, so these join straight onto the emigration data.

## Extraction traps this handles

The tables are laid out for print, and every one of these silently corrupted the
output before it was fixed:

- **Column order came from the title.** "Annex-IV … FY 2017-18 to FY 2025-26"
  put those two labels first, shifting every district's values by several years.
  Dhaka's FY 2024-25 read 3,599 instead of 10,569. Columns are now taken from
  the header row only.
- **Cumulative columns look like months.** "July-October" and "July-June" were
  read as months, dropping a fiscal-year total onto a single month. Ranges are
  stripped before month names are matched.
- **Continuation pages carry no title.** A long table spills onto the next page
  with only a Division/District header; requiring the title dropped 24 of the
  64 districts.
- **The annexure's continuation page** has no "Annex" marker either, and was
  then read as monthly. It is identified by its many fiscal-year tokens.
- **Leading annual columns.** The snapshot layout puts three fiscal-year columns
  before the monthly ones, so month values are aligned from the right.
- **Bangladesh Bank misspells Gaibandha as "GAIBANDAH"** in every report.
- Spellings otherwise differ from BMET's (Cumilla/Comilla, Barishal/Barisal,
  Jashore/Jessore, Bogura/Bogra, Chapai Nawabganj/Chapainawabganj).

Rows are whitelisted against the canonical 64 districts, which is what keeps
division subtotals and the national annexure out of the district tables.

## Validation

Monthly sums are checked against the totals Bangladesh Bank states in prose in
the same reports:

| Month | Extracted | BB stated |
|---|---:|---:|
| Jul 2024 | 1,913.7 | 1,913.77 |
| Aug 2024 | 2,224.2 | 2,224.2 |
| Sep 2024 | 2,404.4 | 2,404.1 |
| Oct 2024 | 2,394.9 | 2,395.1 |
| Jun 2025 | 2,822.5 | 2,822.53 |
| Jul 2025 | 2,477.8 | 2,477.87 |

Residuals are rounding on one-decimal district figures. The annual table
reproduces Dhaka FY 2024-25 at 10,569.1 exactly, and the FY 2024-25 national
total at 30,329 m USD — matching Bangladesh's reported ~$30bn.

## Current coverage in this folder

`remittance_annual_fy.csv` is complete: 64 districts × FY2017-18…FY2024-25.

`remittance_monthly.csv` has Jul–Oct 2024, Jan–Jul 2025 and Jul 2026. To fill
the rest, download these from the index above into `pdfs/` and re-run:

- `dec 2025.pdf` → Jul–Dec 2025
- `publication may 26.pdf` → Dec 2025–May 2026
- `publication.pdf` (latest) → current FY
- `01_compressed.pdf`, `monthly publication _november 24 (1).pdf` → Nov–Dec 2024

Jan–Jun 2024 has no monthly source: the report series had not started, and no
Wayback snapshot of the FY2023-24 file covers it. Use the FY2023-24 annual
figure for that period.
