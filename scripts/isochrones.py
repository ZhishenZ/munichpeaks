"""Drive-time isochrones (60/90/120/150/180 min) from the origin, simplified to small GeoJSON.

Output bands are non-overlapping rings: 0-60, 60-90, …, 150-180 min, so the map can
fill each with its own color without opacity stacking. A fourth feature ("outside": true)
covers everything beyond 180 min, so the map can grey out what is out of range.

Writes: web/data/isochrones.geojson
Usage:  uv run scripts/isochrones.py
"""
from __future__ import annotations

import json
import re

from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.validation import make_valid

from routing_common import ORIGIN, ROOT, call, make_actor

OUT = ROOT / "web" / "data" / "isochrones.geojson"
MINUTES = [60, 90, 120, 150, 180]
SIMPLIFY_DEG = 0.003   # ~250 m; plenty for a regional overview
MIN_HOLE_AREA = 0.002  # drop tiny unreachable specks (deg^2)


def clean(geom):
    geom = make_valid(geom).buffer(0)
    polys = getattr(geom, "geoms", [geom])
    out = []
    for p in polys:
        if p.geom_type != "Polygon":
            continue
        holes = [h for h in p.interiors if Polygon(h).area > MIN_HOLE_AREA]
        out.append(Polygon(p.exterior, holes))
    return MultiPolygon(out) if len(out) > 1 else out[0]


def main() -> None:
    actor = make_actor()
    res = call(actor, "isochrone", {
        "locations": [{"lon": ORIGIN["lon"], "lat": ORIGIN["lat"]}],
        "costing": "auto",
        "contours": [{"time": m} for m in MINUTES],
        "polygons": True,
        "denoise": 0.3,
        "generalize": 150,
    })
    by_min = {round(f["properties"]["contour"]): clean(shape(f["geometry"])) for f in res["features"]}

    feats, inner = [], None
    for m in MINUTES:
        full = by_min[m]
        band = full if inner is None else full.difference(inner)
        band = band.simplify(SIMPLIFY_DEG, preserve_topology=True)
        lo = 0 if inner is None else MINUTES[MINUTES.index(m) - 1]
        feats.append({"type": "Feature",
                      "properties": {"min_from": lo, "min_to": m},
                      "geometry": json.loads(json.dumps(mapping(band)))})
        inner = full

    # Everything beyond the last contour (world box minus the 180 min area). Holes inside
    # the reachable area (unreachable valleys) stay part of the mask.
    outside = box(-180, -85, 180, 85).difference(inner).simplify(SIMPLIFY_DEG, preserve_topology=True)
    feats.append({"type": "Feature", "properties": {"outside": True, "min_from": MINUTES[-1]},
                  "geometry": json.loads(json.dumps(mapping(outside)))})

    gj = {"type": "FeatureCollection",
          "properties": {"origin": ORIGIN, "note": "Free-flow drive time (no traffic)."},
          "features": feats}
    # 5 decimals ≈ 1 m precision: keeps the file small
    text = json.dumps(gj, separators=(",", ":"))
    text = re.sub(r"(\d+\.\d{5})\d+", r"\1", text)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
