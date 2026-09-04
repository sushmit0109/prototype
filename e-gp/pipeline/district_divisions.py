"""
District -> division (ADM1) lookup, for one purpose: testing whether the
political-spending analysis's district-level comparisons are actually
picking up a REGIONAL story rather than an electoral one. District and
period fixed effects (build_political_spending.py's main design) absorb
each district's constant level and each period's national-average shock,
but NOT a division-specific time trend -- if, say, a coastal-embankment
programme or a char-land development scheme is rolling out unevenly by
division for reasons that have nothing to do with the 2026 election, that
would look exactly like a district-level political effect unless it's
explicitly controlled for.

Source: the same nuhil/bangladesh-geocode GeoJSON used for district
boundaries (build_district_geo.py), which carries ADM1_EN (division)
alongside ADM2_EN (district) per feature.
"""
DISTRICT_DIVISION = {
    "Bagerhat": "Khulna", "Bandarban": "Chittagong", "Barguna": "Barisal",
    "Barisal": "Barisal", "Bhola": "Barisal", "Bogra": "Rajshahi",
    "Brahamanbaria": "Chittagong", "Chandpur": "Chittagong", "Chittagong": "Chittagong",
    "Chuadanga": "Khulna", "Comilla": "Chittagong", "Cox's Bazar": "Chittagong",
    "Dhaka": "Dhaka", "Dinajpur": "Rangpur", "Faridpur": "Dhaka", "Feni": "Chittagong",
    "Gaibandha": "Rangpur", "Gazipur": "Dhaka", "Gopalganj": "Dhaka", "Habiganj": "Sylhet",
    "Jamalpur": "Mymensingh", "Jessore": "Khulna", "Jhalokati": "Barisal",
    "Jhenaidah": "Khulna", "Joypurhat": "Rajshahi", "Khagrachhari": "Chittagong",
    "Khulna": "Khulna", "Kishoreganj": "Dhaka", "Kurigram": "Rangpur",
    "Kushtia": "Khulna", "Lakshmipur": "Chittagong", "Lalmonirhat": "Rangpur",
    "Madaripur": "Dhaka", "Magura": "Khulna", "Manikganj": "Dhaka",
    "Maulvibazar": "Sylhet", "Meherpur": "Khulna", "Munshiganj": "Dhaka",
    "Mymensingh": "Mymensingh", "Naogaon": "Rajshahi", "Narail": "Khulna",
    "Narayanganj": "Dhaka", "Narsingdi": "Dhaka", "Natore": "Rajshahi",
    "Nawabganj": "Rajshahi", "Netrakona": "Mymensingh", "Nilphamari": "Rangpur",
    "Noakhali": "Chittagong", "Pabna": "Rajshahi", "Panchagarh": "Rangpur",
    "Patuakhali": "Barisal", "Pirojpur": "Barisal", "Rajbari": "Dhaka",
    "Rajshahi": "Rajshahi", "Rangamati": "Chittagong", "Rangpur": "Rangpur",
    "Satkhira": "Khulna", "Shariatpur": "Dhaka", "Sherpur": "Mymensingh",
    "Sirajganj": "Rajshahi", "Sunamganj": "Sylhet", "Sylhet": "Sylhet",
    "Tangail": "Dhaka", "Thakurgaon": "Rangpur",
}


def division_of(display_district_name):
    """Takes the DISPLAY name (post-districts.py canonicalisation, e.g.
    'Cumilla' not 'Comilla') -- reverse a couple of the renamed ones back
    to look up against this table, which uses the geojson's own spelling."""
    reverse = {"Cumilla": "Comilla", "Bogura": "Bogra", "Barishal": "Barisal",
               "Jashore": "Jessore", "Chattogram": "Chittagong"}
    key = reverse.get(display_district_name, display_district_name)
    return DISTRICT_DIVISION.get(key)
