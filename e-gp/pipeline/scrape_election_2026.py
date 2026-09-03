#!/usr/bin/env python3
"""
Bangladesh's February 2026 general election results, at polling-station
level -- the ground truth for the political-spending analysis
(build_political_spending.py). Not from eprocure.gov.bd; this is the one
external, non-procurement source in the whole pipeline.

Source: netra.news's own interactive results map
(https://interactive.netra.news/bangladesh-election-2026-map/), a static
site (GitHub Pages behind Cloudflare -- a plain browser User-Agent is
enough, no API key or auth). Their own methodology note, verbatim from the
page: "Vote counts come from Election Commission publications, while
polling station locations were sourced from a now-defunct EC website.
Union boundary data comes from geoBoundaries under a CC-BY 4.0 license."

What the CSV actually is: one row per polling STATION (not per union) --
39,761 of the 42,779 nationwide (2,603 the source couldn't geolocate; three
constituencies -- 145, 279, 281 -- were suspended entirely for candidate
death or court disputes, so 297 of 300 seats are covered). Each row already
carries Union/Upazila/District, so aggregating up to any of those levels is
a simple group-by, done in build_election.py rather than here.

Four vote columns, not five -- there is no "Awami League" column. It does
not contest this election; the party was barred from registering following
the 2024 political transition (see eras.py for the timeline this whole
pipeline uses). Vote totals are split across BNP-led alliance,
Jamaat-led alliance, Independent, and Other party.

One-off download, like build_district_geo.py -- an election is a fixed
historical event, not something that changes day to day. Re-run manually
only if this needs to be refreshed from source.

    python3 scrape_election_2026.py <out.csv.gz>
"""
import gzip
import shutil
import sys
import urllib.request

URL = "https://interactive.netra.news/bangladesh-election-2026-map/dict/alliance_level_data.csv"
UA = ("Mozilla/5.0 (compatible; egp-dashboard/1.0; "
      "+https://sushmit0109.github.io/prototype/e-gp/) -- one-off election-data fetch")


def main(out_path):
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    print(f"downloaded {len(data):,} bytes")
    with gzip.open(out_path, "wb", compresslevel=9) as fh:
        fh.write(data)
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
