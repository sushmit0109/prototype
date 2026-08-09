"""District population, from the BBS Population & Housing Census 2022.

Static reference data — it is not scraped and does not change between runs.
Figures are the census 2022 district totals in persons. They are used to put
load-shedding on a per-person footing, so a small zone shedding 200 MW is not
mistaken for a lighter burden than a large zone shedding 400 MW.

District -> PGCB zone mapping lives in geo_build.DISTRICT_ZONE; the zone totals
below are derived from it, so the two can never drift apart.

Source: Bangladesh Bureau of Statistics, Population & Housing Census 2022,
        National Report (district totals).
"""
from __future__ import annotations

CENSUS_YEAR = 2022
SOURCE_EN = "BBS Population & Housing Census 2022"
SOURCE_BN = "বিবিএস আদমশুমারি ও গৃহগণনা ২০২২"

DISTRICT_POPULATION = {
    # Dhaka zone
    "dhaka": 14_734_000, "gazipur": 5_263_000, "narayanganj": 3_909_000,
    "narsingdi": 2_584_000, "manikganj": 1_558_000, "munshiganj": 1_625_000,
    "tangail": 4_037_000, "kishoreganj": 3_268_000, "faridpur": 2_162_000,
    "gopalganj": 1_295_000, "madaripur": 1_303_000, "rajbari": 1_152_000,
    "shariatpur": 1_294_000,
    # Mymensingh zone
    "mymensingh": 5_911_000, "jamalpur": 2_499_000, "netrokona": 2_324_000,
    "sherpur": 1_502_000,
    # Chattogram zone
    "chattogram": 9_169_000, "coxsbazar": 2_824_000, "rangamati": 647_000,
    "bandarban": 482_000, "khagrachari": 714_000,
    # Cumilla zone
    "cumilla": 6_212_000, "brahmanbaria": 3_306_000, "chandpur": 2_638_000,
    "noakhali": 3_626_000, "feni": 1_650_000, "lakshmipur": 1_940_000,
    # Sylhet zone
    "sylhet": 3_857_000, "moulvibazar": 2_123_000, "habiganj": 2_358_000,
    "sunamganj": 2_695_000,
    # Khulna zone
    "khulna": 2_613_000, "bagerhat": 1_613_000, "satkhira": 2_201_000,
    "jashore": 3_076_000, "jhenaidah": 1_980_000, "magura": 1_003_000,
    "narail": 790_000, "kushtia": 2_149_000, "chuadanga": 1_293_000,
    "meherpur": 706_000,
    # Barishal zone
    "barishal": 2_570_000, "bhola": 1_932_000, "patuakhali": 1_727_000,
    "pirojpur": 1_198_000, "barguna": 992_000, "jhalokati": 687_000,
    # Rajshahi zone
    "rajshahi": 2_873_000, "natore": 1_898_000, "naogaon": 2_700_000,
    "chapainawabganj": 1_833_000, "pabna": 2_752_000, "sirajganj": 3_438_000,
    "bogura": 3_741_000, "joypurhat": 951_000,
    # Rangpur zone
    "rangpur": 3_169_000, "dinajpur": 3_319_000, "thakurgaon": 1_493_000,
    "panchagarh": 1_133_000, "nilphamari": 1_991_000, "lalmonirhat": 1_428_000,
    "kurigram": 2_069_000, "gaibandha": 2_562_000,
}


def zone_population() -> dict:
    """Population per PGCB zone, summed from its districts."""
    from geo_build import DISTRICT_ZONE
    out: dict = {}
    for district, pop in DISTRICT_POPULATION.items():
        zone = DISTRICT_ZONE.get(district)
        if zone:
            out[zone] = out.get(zone, 0) + pop
    return out


def missing_districts() -> list:
    """Districts in the zone map that carry no population figure."""
    from geo_build import DISTRICT_ZONE
    return sorted(set(DISTRICT_ZONE) - set(DISTRICT_POPULATION))
