"""
District population from BBS's 2022 Population & Housing Census, for one
purpose: an alternative denominator to the election data's total_voters in
build_political_spending.py.

Registered-voter counts are an imperfect stand-in for a district's
population/development need -- voter rolls are affected by registration
drives, out-migration for work, and how recently they were updated, none of
which is about how much development spending a district needs or should get.
Census population is a cleaner, independent denominator: if the political
result looks the same whether spending is scaled by voters or by the actual
resident population, that is a real robustness check; if it doesn't, the
voter-count denominator itself may have been doing some of the work.

Source: BBS 2022 census district population totals, curated in the sibling
`bbs census` project (data/processed from bbs.gov.bd's zila reports). Copied
here as a static snapshot -- population is fixed at census time and doesn't
need re-crawling on a schedule the way contract data does.
"""

DISTRICT_POPULATION_2022 = {
    "Bagerhat": 1582590,
    "Bandarban": 450692,
    "Barguna": 992721,
    "Barishal": 2496625,
    "Bhola": 1904358,
    "Bogura": 3651917,
    "Brahamanbaria": 3227902,
    "Chandpur": 2580728,
    "Chattogram": 8813087,
    "Chuadanga": 1219036,
    "Cox's Bazar": 2740161,
    "Cumilla": 6017180,
    "Dhaka": 13514349,
    "Dinajpur": 3236651,
    "Faridpur": 2103804,
    "Feni": 1589784,
    "Gaibandha": 2529359,
    "Gazipur": 4983154,
    "Gopalganj": 1251723,
    "Habiganj": 2321098,
    "Jamalpur": 2475535,
    "Jashore": 3004239,
    "Jhalokati": 647167,
    "Jhenaidah": 1969715,
    "Joypurhat": 938110,
    "Khagrachhari": 690804,
    "Khulna": 2535569,
    "Kishoreganj": 3201295,
    "Kurigram": 2305840,
    "Kushtia": 2119248,
    "Lakshmipur": 1894560,
    "Lalmonirhat": 1413455,
    "Madaripur": 1259062,
    "Magura": 1017133,
    "Manikganj": 1526711,
    "Maulvibazar": 2088869,
    "Meherpur": 699477,
    "Munshiganj": 1563778,
    "Mymensingh": 5737380,
    "Naogaon": 2731917,
    "Narail": 774876,
    "Narayanganj": 3740835,
    "Narsingdi": 2499690,
    "Natore": 1828058,
    "Nawabganj": 1816475,
    "Netrakona": 2281021,
    "Nilphamari": 2064574,
    "Noakhali": 3541700,
    "Pabna": 2852250,
    "Panchagarh": 1160775,
    "Patuakhali": 1687450,
    "Pirojpur": 1171839,
    "Rajbari": 1169673,
    "Rajshahi": 2816532,
    "Rangamati": 616090,
    "Rangpur": 3082438,
    "Satkhira": 2169317,
    "Shariatpur": 1271446,
    "Sherpur": 1482436,
    "Sirajganj": 3289850,
    "Sunamganj": 2675216,
    "Sylhet": 3751330,
    "Tangail": 3956331,
    "Thakurgaon": 1505539,
}


def population_of(display_district_name):
    """Takes the e-GP pipeline's canonical display name (districts.py's
    spelling, e.g. 'Cumilla', 'Chattogram') and returns 2022 census
    population, or None if unknown."""
    return DISTRICT_POPULATION_2022.get(display_district_name)
