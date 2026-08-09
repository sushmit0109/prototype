"""Build the map layers from OpenStreetMap.

Three products, all cached under raw/geo/ so a rebuild costs no network:

  districts.geojson  64 district polygons, each tagged with the PGCB zone it
                     belongs to. Zones are what the reports use; districts are
                     what people recognise, so we colour districts by the value
                     of their parent zone.
  plants.json        OSM power plants (name, fuel, lat/lon) used to place the
                     BPDB per-plant table on the map.
  substations.json   OSM substations >= 132 kV, used to place the NLDC
                     "maximum load served by grid sub-station" table.

  python geo_build.py            # use cache where present
  python geo_build.py --refresh  # re-query Overpass
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time

import requests

from common import RAW, SITE_DATA, write_json, read_json

GEO = RAW / "geo"
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

Q_PLANTS = """
[out:json][timeout:180];
area["ISO3166-1"="BD"][admin_level=2]->.bd;
(
  node(area.bd)["power"="plant"];
  way(area.bd)["power"="plant"];
  relation(area.bd)["power"="plant"];
);
out center tags;
"""

Q_SUBSTATIONS = """
[out:json][timeout:180];
area["ISO3166-1"="BD"][admin_level=2]->.bd;
(
  node(area.bd)["power"="substation"];
  way(area.bd)["power"="substation"];
  relation(area.bd)["power"="substation"];
);
out center tags;
"""

# Grid substations are almost always named after the town they sit in, so a
# settlement gazetteer geocodes the ones OSM has no power=substation node for.
Q_PLACES = """
[out:json][timeout:180];
area["ISO3166-1"="BD"][admin_level=2]->.bd;
(
  node(area.bd)["place"~"^(city|town|suburb|municipality)$"];
);
out;
"""

Q_DISTRICTS = """
[out:json][timeout:240];
area["ISO3166-1"="BD"][admin_level=2]->.bd;
relation(area.bd)["boundary"="administrative"]["admin_level"="5"];
out geom;
"""

# --------------------------------------------------------- district -> zone

DISTRICT_ZONE = {
    # Dhaka zone
    "dhaka": "dhaka", "gazipur": "dhaka", "narayanganj": "dhaka",
    "narsingdi": "dhaka", "manikganj": "dhaka", "munshiganj": "dhaka",
    "tangail": "dhaka", "kishoreganj": "dhaka", "faridpur": "dhaka",
    "gopalganj": "dhaka", "madaripur": "dhaka", "rajbari": "dhaka",
    "shariatpur": "dhaka",
    # Mymensingh zone
    "mymensingh": "mymensingh", "jamalpur": "mymensingh",
    "netrokona": "mymensingh", "sherpur": "mymensingh",
    # Chattogram zone
    "chattogram": "chattogram", "coxsbazar": "chattogram",
    "bandarban": "chattogram", "rangamati": "chattogram",
    "khagrachari": "chattogram",
    # Cumilla zone
    "cumilla": "cumilla", "brahmanbaria": "cumilla", "chandpur": "cumilla",
    "noakhali": "cumilla", "feni": "cumilla", "lakshmipur": "cumilla",
    # Sylhet zone
    "sylhet": "sylhet", "moulvibazar": "sylhet", "habiganj": "sylhet",
    "sunamganj": "sylhet",
    # Khulna zone
    "khulna": "khulna", "bagerhat": "khulna", "satkhira": "khulna",
    "jashore": "khulna", "jhenaidah": "khulna", "magura": "khulna",
    "narail": "khulna", "kushtia": "khulna", "chuadanga": "khulna",
    "meherpur": "khulna",
    # Barishal zone
    "barishal": "barishal", "bhola": "barishal", "patuakhali": "barishal",
    "pirojpur": "barishal", "barguna": "barishal", "jhalokati": "barishal",
    # Rajshahi zone
    "rajshahi": "rajshahi", "natore": "rajshahi", "naogaon": "rajshahi",
    "chapainawabganj": "rajshahi", "pabna": "rajshahi", "sirajganj": "rajshahi",
    "bogura": "rajshahi", "joypurhat": "rajshahi",
    # Rangpur zone
    "rangpur": "rangpur", "dinajpur": "rangpur", "thakurgaon": "rangpur",
    "panchagarh": "rangpur", "nilphamari": "rangpur", "lalmonirhat": "rangpur",
    "kurigram": "rangpur", "gaibandha": "rangpur",
}

# OSM still carries a mix of pre- and post-2018 spellings.
DISTRICT_ALIAS = {
    "chittagong": "chattogram", "comilla": "cumilla", "barisal": "barishal",
    "jessore": "jashore", "bogra": "bogura", "netrakona": "netrokona",
    "jhalakathi": "jhalokati", "jhalokathi": "jhalokati", "nawabganj": "chapainawabganj",
    "chapainababganj": "chapainawabganj", "chapai": "chapainawabganj",
    "brahmanbaria": "brahmanbaria", "coxbazar": "coxsbazar",
    "khagrachhari": "khagrachari", "moulavibazar": "moulvibazar",
    "maulvibazar": "moulvibazar", "munshigonj": "munshiganj",
    "sunamgonj": "sunamganj", "gaibandha": "gaibandha",
}


def norm_district(name: str) -> str:
    t = (name or "").lower()
    t = re.sub(r"\b(district|zila|zilla|hill|tracts?)\b", " ", t)
    t = re.sub(r"[^a-z]", "", t)
    return DISTRICT_ALIAS.get(t, t)


# ------------------------------------------------------------ overpass io

def overpass(query: str, cache_name: str, refresh: bool):
    GEO.mkdir(parents=True, exist_ok=True)
    path = GEO / cache_name
    if path.exists() and not refresh:
        print(f"[geo] cache hit {cache_name}")
        return read_json(path)
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                # Overpass expects the query form-encoded as `data=`; a raw body
                # is answered with 406.
                r = requests.post(ep, data={"data": query}, timeout=300,
                                  verify=False,
                                  headers={"User-Agent": "bd-electricity-dashboard/1.0"})
                if r.status_code == 200:
                    data = r.json()
                    write_json(path, data)
                    print(f"[geo] fetched {cache_name}: "
                          f"{len(data.get('elements', []))} elements")
                    return data
                last = f"HTTP {r.status_code}"
                # 429/504 are the standard Overpass "slot busy" answers
                time.sleep(30 if r.status_code in (429, 504) else 5 * (attempt + 1))
                continue
            except Exception as e:  # noqa: BLE001
                last = type(e).__name__
            time.sleep(5 * (attempt + 1))
        print(f"[geo] {ep} failed ({last}), trying next")
    raise SystemExit(f"[geo] all Overpass endpoints failed: {last}")


# --------------------------------------------------------- ring assembly

def _key(pt, p=5):
    return (round(pt["lat"], p), round(pt["lon"], p))


def assemble_rings(members):
    """Stitch OSM boundary 'outer' ways into closed rings."""
    ways = [m["geometry"] for m in members
            if m.get("role") in ("outer", "") and m.get("geometry")]
    rings, pool = [], [list(w) for w in ways]

    while pool:
        ring = pool.pop(0)
        changed = True
        while changed and _key(ring[0]) != _key(ring[-1]):
            changed = False
            for i, w in enumerate(pool):
                if _key(w[0]) == _key(ring[-1]):
                    ring += w[1:]
                elif _key(w[-1]) == _key(ring[-1]):
                    ring += list(reversed(w))[1:]
                elif _key(w[-1]) == _key(ring[0]):
                    ring = w[:-1] + ring
                elif _key(w[0]) == _key(ring[0]):
                    ring = list(reversed(w))[:-1] + ring
                else:
                    continue
                pool.pop(i)
                changed = True
                break
        if len(ring) >= 4:
            if _key(ring[0]) != _key(ring[-1]):
                ring.append(ring[0])
            rings.append(ring)
    return rings


def _seg_dist(p, a, b):
    """Perpendicular distance from p to segment a-b (degenerate -> point dist)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / math.hypot(dx, dy)


def rdp(points, eps):
    """Ramer-Douglas-Peucker on an *open* polyline of (lon, lat) tuples.

    Iterative: district rings run to thousands of points, deep enough to blow
    the recursion limit.
    """
    n = len(points)
    if n < 3:
        return list(points)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, i
        a, b = points[i], points[j]
        for k in range(i + 1, j):
            d = _seg_dist(points[k], a, b)
            if d > dmax:
                dmax, idx = d, k
        if dmax > eps:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(ring, eps):
    """Simplify a closed ring.

    Splitting at the vertex farthest from the start keeps two well-conditioned
    open polylines; running RDP straight across a closed ring would compare
    every point against a zero-length baseline.
    """
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else list(ring)
    if len(pts) < 4:
        return []
    a = pts[0]
    far = max(range(len(pts)), key=lambda i: math.hypot(pts[i][0] - a[0],
                                                        pts[i][1] - a[1]))
    if far == 0:
        return []
    first = rdp(pts[:far + 1], eps)
    second = rdp(pts[far:] + [a], eps)
    out = first[:-1] + second
    if len(out) < 4:
        return []
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def ring_area(ring):
    """Shoelace area in squared degrees — only used to rank/drop islets."""
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(s) / 2


def build_districts(refresh: bool, eps: float, keep: int):
    data = overpass(Q_DISTRICTS, "districts_raw.json", refresh)
    feats, unmapped = [], []

    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name_en = tags.get("name:en") or tags.get("name") or ""
        key = norm_district(name_en)
        zone = DISTRICT_ZONE.get(key)
        if not zone:
            unmapped.append(name_en)
            continue

        rings = assemble_rings(el.get("members", []))
        polys = []
        for ring in rings:
            pts = [(round(p["lon"], 6), round(p["lat"], 6)) for p in ring]
            simp = simplify_ring(pts, eps)
            if simp and ring_area(simp) > 1e-4:
                polys.append([[[round(x, 5), round(y, 5)] for x, y in simp]])
        if not polys:
            continue
        polys.sort(key=lambda p: ring_area([tuple(c) for c in p[0]]), reverse=True)
        polys = polys[:keep]

        feats.append({
            "type": "Feature",
            "properties": {
                "name_en": name_en.replace(" District", "").strip(),
                "name_bn": tags.get("name:bn") or "",
                "zone": zone,
            },
            "geometry": {"type": "MultiPolygon", "coordinates": polys},
        })

    if unmapped:
        print(f"[geo] WARNING unmapped districts: {unmapped}")
    fc = {"type": "FeatureCollection", "features": feats}
    write_json(SITE_DATA / "geo" / "districts.json", fc)
    npts = sum(len(r[0]) for f in feats for r in f["geometry"]["coordinates"])
    print(f"[geo] districts: {len(feats)} features, {npts} points")
    return fc


# ------------------------------------------------------------- point sets

def elem_point(el):
    c = el.get("center") or {}
    lat = c.get("lat", el.get("lat"))
    lon = c.get("lon", el.get("lon"))
    return (lat, lon) if lat is not None and lon is not None else (None, None)


def build_points(refresh: bool):
    out = {}
    for kind, query, cache in (("plants", Q_PLANTS, "plants_raw.json"),
                               ("substations", Q_SUBSTATIONS, "substations_raw.json"),
                               ("places", Q_PLACES, "places_raw.json")):
        data = overpass(query, cache, refresh)
        items = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name:en") or tags.get("name")
            if not name:
                continue
            lat, lon = elem_point(el)
            if lat is None:
                continue
            rec = {"name": name, "lat": round(lat, 5), "lon": round(lon, 5)}
            if kind == "plants":
                rec["source"] = tags.get("plant:source") or tags.get("generator:source") or ""
                rec["output"] = tags.get("plant:output:electricity") or ""
            else:
                rec["voltage"] = tags.get("voltage") or ""
            items.append(rec)
        write_json(GEO / f"{kind}.json", items)
        print(f"[geo] {kind}: {len(items)} named")
        out[kind] = items
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--eps", type=float, default=0.006,
                    help="RDP tolerance in degrees (~660 m at 0.006)")
    ap.add_argument("--keep", type=int, default=6,
                    help="max polygons kept per district (drops tiny islets)")
    args = ap.parse_args()

    requests.packages.urllib3.disable_warnings()  # gov/overpass chains vary
    build_points(args.refresh)
    build_districts(args.refresh, args.eps, args.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
