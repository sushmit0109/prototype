#!/usr/bin/env python3
"""
Trace real Bangladesh district boundaries into compact inline-SVG paths for
the geographic finding on the dashboard.

Source: nuhil/bangladesh-geocode's districts.geojson (ADM2, 64 districts),
itself derived from the standard UN OCHA/HDX Bangladesh administrative
boundary set. This is a one-off build step, not part of the daily crawl --
district boundaries don't change day to day -- run manually if the source
geometry ever needs updating:

    python3 build_district_geo.py <districts.geojson> <out.json>

Two things happen to the raw geometry before it's usable on a web page:

1. Projection. Lon/lat is projected to flat SVG coordinates with a simple
   equirectangular transform, scaling longitude by cos(mean latitude) so
   the country isn't visibly stretched east-west -- Bangladesh sits at
   ~23.6N, where that correction is a real ~8% effect. Fine for a country
   this size; nothing here needs a proper geodesic projection.

2. Simplification. The raw file carries ~44,000 coordinate pairs across 64
   districts (mostly coastline/river detail no reader will ever resolve at
   dashboard scale) -- multiple megabytes of path data. Ramer-Douglas-
   Peucker simplification (implemented here with no dependencies) cuts that
   by roughly 90% at a tolerance tuned for legibility at a few hundred
   pixels wide, which is the only scale this ever renders at.
"""
import json
import math
import sys

from districts import CANONICAL_DISPLAY, DISTRICT_ALIASES

# In final SVG units (after projection+scaling below, roughly 0-800 wide).
# Larger = more simplification. Tuned by hand against the rendered result.
SIMPLIFY_TOLERANCE = 0.7
TARGET_WIDTH = 760


def rdp(points, tolerance):
    """Ramer-Douglas-Peucker on a list of (x, y) points."""
    if len(points) < 3:
        return points

    def perp_dist(p, a, b):
        if a == b:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        (ax, ay), (bx, by) = a, b
        num = abs((by - ay) * p[0] - (bx - ax) * p[1] + bx * ay - by * ax)
        den = math.hypot(bx - ax, by - ay)
        return num / den

    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i

    if dmax > tolerance:
        left = rdp(points[:idx + 1], tolerance)
        right = rdp(points[idx:], tolerance)
        return left[:-1] + right
    return [points[0], points[-1]]


def main(geojson_path, out_path):
    with open(geojson_path) as fh:
        gj = json.load(fh)

    lons = [pt[0] for f in gj["features"]
            for poly in (f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]])
            for ring in poly for pt in ring]
    lats = [pt[1] for f in gj["features"]
            for poly in (f["geometry"]["coordinates"] if f["geometry"]["type"] == "MultiPolygon" else [f["geometry"]["coordinates"]])
            for ring in poly for pt in ring]
    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)
    lat_mid = (lat_min + lat_max) / 2
    cos_lat = math.cos(math.radians(lat_mid))

    scale = TARGET_WIDTH / ((lon_max - lon_min) * cos_lat)

    def project(lon, lat):
        x = (lon - lon_min) * cos_lat * scale
        y = (lat_max - lat) * scale  # flip: SVG y grows downward, lat grows upward
        return x, y

    raw_points = 0
    kept_points = 0
    paths = {}
    for feat in gj["features"]:
        name = feat["properties"]["ADM2_EN"]
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        subpaths = []
        for poly in polys:
            for ring in poly:
                raw_points += len(ring)
                projected = [project(lon, lat) for lon, lat in ring]
                simplified = rdp(projected, SIMPLIFY_TOLERANCE)
                kept_points += len(simplified)
                pts = [f"{x:.1f},{y:.1f}" for x, y in simplified]
                subpaths.append("M" + "L".join(pts) + "Z")
        paths[name] = "".join(subpaths)

    height = (lat_max - lat_min) * scale
    payload = {
        "view_box": f"0 0 {TARGET_WIDTH:.0f} {height:.0f}",
        "source": "https://github.com/nuhil/bangladesh-geocode (ADM2, derived from UN OCHA/HDX Bangladesh administrative boundaries)",
        "canonical_display": CANONICAL_DISPLAY,
        "district_aliases": DISTRICT_ALIASES,
        "paths": paths,
    }
    with open(out_path, "w") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    unmatched_geo = set(paths) - set(DISTRICT_ALIASES.values())
    unmatched_alias_targets = set(DISTRICT_ALIASES.values()) - set(paths)
    print(f"{len(paths)} district paths, {raw_points:,} -> {kept_points:,} points "
          f"({100*kept_points/raw_points:.1f}% kept)")
    if unmatched_geo:
        print(f"WARNING: geojson districts with no alias mapping to them: {unmatched_geo}")
    if unmatched_alias_targets:
        print(f"WARNING: alias targets not found in geojson: {unmatched_alias_targets}")
    print(f"wrote -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
