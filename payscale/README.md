# The Civil Service Paybook · বাংলাদেশের জাতীয় বেতনস্কেল ১৯৭৩–২০২৬

The 2026 pay order doubles the civil service pay scale. This page works out what
the doubling actually does — grade by grade, step by step, against the prices it
is meant to cover — from the Finance Division's own gazettes.

**Live:** <https://sushmit.org/prototype/payscale/>

## Layout

```
payscale/
  index.html  app.js  styles.css   the page (static, no build step)
  data/payscale.json               everything the page reads
  pipeline/                        the scripts that produce it
```

The page computes every figure in the browser from the primitives in
`data/payscale.json` — ladders, the price index, GDP per head — so the numbers on
screen and the numbers in the source CSVs cannot drift apart.

## Where the figures come from

The gazette of 17 September 2026 (*চাকরি (বেতন ও ভাতাদি) আদেশ, ২০২৬*, Bangladesh
Gazette Extraordinary, pp. 25193–25211) prints the 2015 and 2026 step ladders
**side by side**, step by step. That makes it authoritative for both scales, and
every step amount shown for 2015 and 2026 was read from that table.

Scales from 1973 to 2009 are expanded from the increment bands the earlier
gazettes print (`7x490;11x540`) and cross-checked against the same scale as
reprinted in other service chapters.

Prices are a chained index: World Bank WDI consumer price index (`FP.CPI.TOTL`)
from 1986, extended back to 1980 and forward through 2028 with IMF World Economic
Outlook inflation. GDP per head is World Bank `NY.GDP.PCAP.CN` and
`NY.GDP.PCAP.PP.KD`.

## How the ladders were verified

OCR on a Bengali numeric table is not trustworthy on its own, so arithmetic does
the checking. Every ladder must rise strictly, and every step must sit within ±5%
of that ladder's own median step ratio. Fifteen lines failed:

* fourteen where the recogniser rendered Bengali numerals as Latin digits
  (`৪`→`8`, `৭`→`9`, `৮`→`6`), which drops confidence to 0.78–0.93 on exactly
  those lines;
* one that was dropped from the output altogether, leaving grade 8 jumping from
  ৳53,300 to ৳71,400 with six steps missing.

Each was re-read from the page image and recorded in `pipeline/extract_2026_gazette.py`
as an explicit override keyed by page, line position and column, so every
substitution is auditable against the source. The extractor then reports zero
validation failures across all 40 ladders, and grade 6 reproduces the published
ladder exactly.

## Rebuilding the data

The pipeline runs against the OCR output in the separate `payscale` working
repository, in this order:

```
python3 pipeline/extract_2026_gazette.py   # 2015 + 2026 ladders from the gazette table
python3 pipeline/build_ladders.py          # all nine scales into one ladders.json
python3 pipeline/analyse.py                # fixation tables, anomalies, phased release
python3 pipeline/build_portal_data.py      # -> data/payscale.json
```

`pipeline/payfix.py` is the fixation engine on its own, if you want to check a
single case from a shell. The browser's `fixPay()` in `app.js` mirrors it exactly.

## What the page covers

* **A calculator** over any two pay scales, any grade and any step, showing every
  stage of the article 5 derivation so a result can be checked against the
  gazette by hand.
* **Inter-grade and intra-grade comparison** — the raise is progressive between
  grades and sharply regressive within them.
* **A compression diagram** mapping each 2015 step onto the 2026 step it lands on.
* **Macro tests** against consumer prices, nominal GDP per head and real income
  per head at purchasing power parity.
* **Every commission since 1973**, on the same four measures.
* **A discrepancy register**, where each entry names the figure on the page that
  tests it.

Figures are basic pay only. Allowances are tabulated but never added in, and they
can exceed half of basic.
