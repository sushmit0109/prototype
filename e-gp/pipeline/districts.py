"""
Shared district name normalisation -- one canonical key (the geojson's
ADM2_EN spelling, used as the join key for both geometry and aggregation)
per district, plus the display spelling preferred on the dashboard.

Contract data mixes pre- and post-2018 official spellings (several
districts were renamed around then: Chittagong->Chattogram,
Comilla->Cumilla, Barisal->Barishal, Jessore->Jashore, Bogra->Bogura) plus a
handful of one-off source variants. Kept here rather than duplicated
between build_district_geo.py (one-off geometry build) and build_geo.py
(daily aggregation) so the two never drift apart.
"""

CANONICAL_DISPLAY = {
    "Barisal": "Barishal", "Bogra": "Bogura", "Comilla": "Cumilla",
    "Jessore": "Jashore", "Chittagong": "Chattogram",
}

DISTRICT_ALIASES = {
    "Bagerhat": "Bagerhat", "Bandarban": "Bandarban", "Barguna": "Barguna",
    "Barisal": "Barisal", "Barishal": "Barisal", "Bhola": "Bhola",
    "Bogra": "Bogra", "Bogura": "Bogra", "Brahmanbaria": "Brahamanbaria",
    "Chandpur": "Chandpur", "Chapai Nawabganj": "Nawabganj",
    "Chattogram": "Chittagong", "Chittagong": "Chittagong",
    "Chuadanga": "Chuadanga", "Comilla": "Comilla", "Cumilla": "Comilla",
    "Cox's Bazar": "Cox's Bazar", "Dhaka": "Dhaka", "Dinajpur": "Dinajpur",
    "Faridpur": "Faridpur", "Feni": "Feni", "Gaibandha": "Gaibandha",
    "Gazipur": "Gazipur", "Gopalganj": "Gopalganj", "Habiganj": "Habiganj",
    "Jamalpur": "Jamalpur", "Jashore": "Jessore", "Jessore": "Jessore",
    "Jhalokathi": "Jhalokati", "Jhenaidah": "Jhenaidah",
    "Joypurhat": "Joypurhat", "Khagrachari": "Khagrachhari",
    "Khulna": "Khulna", "Kishoreganj": "Kishoreganj", "Kurigram": "Kurigram",
    "Kushtia": "Kushtia", "Laksmipur": "Lakshmipur",
    "Lalmonirhat": "Lalmonirhat", "Madaripur": "Madaripur",
    "Magura": "Magura", "Manikganj": "Manikganj", "Meherpur": "Meherpur",
    "Moulvibazar": "Maulvibazar", "Munshiganj": "Munshiganj",
    "Mymensingh": "Mymensingh", "Naogaon": "Naogaon", "Narail": "Narail",
    "Narayanganj": "Narayanganj", "Natore": "Natore",
    "Netrokona": "Netrakona", "Nilphamari": "Nilphamari",
    "Noakhali": "Noakhali", "Norshingdi": "Narsingdi", "Pabna": "Pabna",
    "Panchagarh": "Panchagarh", "Patuakhali": "Patuakhali",
    "Perojpur": "Pirojpur", "Rajbari": "Rajbari", "Rajshahi": "Rajshahi",
    "Rangamati": "Rangamati", "Rangpur": "Rangpur", "Satkhira": "Satkhira",
    "Shariatpur": "Shariatpur", "Sherpur": "Sherpur",
    "Sirajganj": "Sirajganj", "Sunamganj": "Sunamganj", "Sylhet": "Sylhet",
    "Tangail": "Tangail", "Thakurgaon": "Thakurgaon",
}


def canonical(raw_district):
    """Raw district string (any spelling seen in the data) -> geojson join key."""
    key = DISTRICT_ALIASES.get((raw_district or "").strip())
    return key


def display_name(canonical_key):
    return CANONICAL_DISPLAY.get(canonical_key, canonical_key)
