#!/usr/bin/env python3
"""
Where each policing unit sits, and how many people it polices.

Bangladesh Police reports by command, not by administrative area. The eight
"...MP" units are metropolitan forces covering one city each; the eight
"... Range" units cover the rest of a division. Railway Range is a functional
command over the rail network with no territory of its own, so it is carried in
the totals but never drawn on the map.

Populations come from the 2022 Population and Housing Census (BBS). They are a
close but inexact fit: a metropolitan police jurisdiction is not identical to
its city corporation boundary, and a Range is taken as its division less the
metropolitan areas inside it. Rates built on them are sound for comparison and
should not be quoted as exact.
"""

# Division populations, BBS 2022 Census.
DIVISION_POP = {
    "Dhaka": 44_215_107,
    "Chattogram": 33_202_326,
    "Rajshahi": 20_353_119,
    "Rangpur": 17_610_956,
    "Khulna": 17_416_645,
    "Mymensingh": 12_368_730,
    "Sylhet": 11_362_271,
    "Barishal": 9_325_820,
}

# code -> (label, kind, division, population, lat, lon)
# lat/lon is the city centre for metropolitan units; Ranges are drawn as the
# division polygon instead, so their coordinates are only a label anchor.
UNITS = {
    "DMP":  ("Dhaka Metropolitan",      "metro", "Dhaka",      10_278_882, 23.8103, 90.4125),
    "CMP":  ("Chattogram Metropolitan", "metro", "Chattogram",  3_227_246, 22.3569, 91.7832),
    "KMP":  ("Khulna Metropolitan",     "metro", "Khulna",        718_735, 22.8456, 89.5403),
    "RMP":  ("Rajshahi Metropolitan",   "metro", "Rajshahi",      552_791, 24.3745, 88.6042),
    "BMP":  ("Barishal Metropolitan",   "metro", "Barishal",      419_371, 22.7010, 90.3535),
    "SMP":  ("Sylhet Metropolitan",     "metro", "Sylhet",        532_426, 24.8949, 91.8687),
    "GMP":  ("Gazipur Metropolitan",    "metro", "Dhaka",       2_674_697, 23.9999, 90.4203),
    "RPMP": ("Rangpur Metropolitan",    "metro", "Rangpur",       795_041, 25.7439, 89.2752),

    "Dhaka Range":      ("Dhaka Range",      "range", "Dhaka",      None, 24.20, 90.05),
    "Chittagong Range": ("Chattogram Range", "range", "Chattogram", None, 22.90, 91.90),
    "Rajshahi Range":   ("Rajshahi Range",   "range", "Rajshahi",   None, 24.60, 88.90),
    "Rangpur Range":    ("Rangpur Range",    "range", "Rangpur",    None, 25.90, 89.10),
    "Khulna Range":     ("Khulna Range",     "range", "Khulna",     None, 22.90, 89.30),
    "Mymensingh Range": ("Mymensingh Range", "range", "Mymensingh", None, 24.90, 90.30),
    "Sylhet Range":     ("Sylhet Range",     "range", "Sylhet",     None, 24.80, 91.60),
    "Barishal Range":   ("Barishal Range",   "range", "Barishal",   None, 22.50, 90.30),

    # Spelled as the source spells it.
    "Ralway Range":     ("Railway Range",    "railway", None,       None, None, None),
}


def resolve():
    """Fill in Range populations as division-minus-metropolitan."""
    out = {}
    metro_in_div = {}
    for code, (_l, kind, div, pop, _a, _o) in UNITS.items():
        if kind == "metro":
            metro_in_div[div] = metro_in_div.get(div, 0) + pop
    for code, (label, kind, div, pop, lat, lon) in UNITS.items():
        if kind == "range":
            pop = DIVISION_POP[div] - metro_in_div.get(div, 0)
        # A compact form for tight places -- ranked lists and axis labels --
        # where "Chattogram Metropolitan" would simply be truncated.
        short = label.replace(" Metropolitan", " city")
        out[code] = {"code": code, "label": label, "short": short, "kind": kind,
                     "division": div, "population": pop, "lat": lat, "lon": lon}
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(resolve(), indent=1))
