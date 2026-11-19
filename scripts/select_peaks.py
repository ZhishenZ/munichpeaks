"""Pick the peaks shown on the map and write the compact web data file.

Rules (tunable below):
  - reachable within MAX_MIN minutes
  - famous enough: >= MIN_SITELINKS Wikipedia language editions (forced includes bypass this)
  - de-duplicate summits closer than DEDUP_KM, or linked to the same Wikipedia article
    (keep the more famous one, e.g. Zugspitze W/E summit, Watzmann Mittel-/Südspitze)
  - rank by fame (sitelinks, then prominence, then elevation) -> tier 1/2/3 for progressive display

Each peak also gets the id of the region it lies in ("reg"), from web/data/regions.geojson
(run fetch_regions.py first); the region file gets each region's peak count.

Reads:  data/peaks_routed.json, config/peaks_include.json, config/origin.json,
        web/data/regions.geojson
Writes: web/data/peaks.json, peak counts into web/data/regions.geojson
Usage:  uv run scripts/select_peaks.py
"""
from __future__ import annotations

import json
from datetime import date

from shapely import STRtree
from shapely.geometry import Point, shape

from routing_common import ORIGIN, ROOT, dumps_records, haversine_km

IN = ROOT / "data" / "peaks_routed.json"
OUT = ROOT / "web" / "data" / "peaks.json"
INCLUDE = ROOT / "config" / "peaks_include.json"
REGIONS = ROOT / "web" / "data" / "regions.geojson"

MAX_MIN = 180
MIN_SITELINKS = 3
DEDUP_KM = 0.6
TIER1, TIER2 = 40, 160   # cumulative counts


def band_of(m: int) -> int:
    """Drive-time band matching the isochrone rings: 1 = up to 60 min, then one per 30 min."""
    return 1 if m <= 60 else min(5, 2 + (m - 61) // 30)


def fame_key(p: dict) -> tuple:
    return (-(p.get("sitelinks") or 0), -(p.get("prominence") or 0), -(p.get("ele") or 0))


def main() -> None:
    peaks = json.loads(IN.read_text())
    forced = {int(x["osm_id"]) for x in json.loads(INCLUDE.read_text())["include"]} if INCLUDE.exists() else set()

    cand = [p for p in peaks
            if p.get("drive_min") is not None and p["drive_min"] <= MAX_MIN
            and (p["osm_id"] in forced or (p.get("sitelinks") or 0) >= MIN_SITELINKS)]
    cand.sort(key=fame_key)

    kept: list[dict] = []
    seen_items: set[str] = set()
    for p in cand:
        item = p.get("wiki_qid")
        if p["osm_id"] not in forced:
            if item and item in seen_items:      # several summit nodes, one famous mountain
                continue
            if any(haversine_km(p["lon"], p["lat"], k["lon"], k["lat"]) < DEDUP_KM for k in kept):
                continue
        kept.append(p)
        if item:
            seen_items.add(item)

    regions = json.loads(REGIONS.read_text())
    geoms = [shape(f["geometry"]) for f in regions["features"]]
    tree = STRtree(geoms)

    def region_of(lon: float, lat: float):
        pt = Point(lon, lat)
        hits = [i for i in tree.query(pt) if geoms[i].contains(pt)]
        if not hits:   # summit exactly on a border line: take the nearest region
            hits = [int(tree.nearest(pt))]
        return regions["features"][hits[0]]["properties"]["id"]

    out = []
    for rank, p in enumerate(kept):
        m = p["drive_min"]
        alt = p.get("name_de") if p.get("name_de") and p["name_de"] != p["name"] else None
        if not alt and p.get("name_en") and p["name_en"] != p["name"]:
            alt = p["name_en"]
        th = p.get("trailhead")
        out.append({
            "id": p["osm_id"], "name": p["name"], "alt": alt, "ele": p["ele"],
            "lon": p["lon"], "lat": p["lat"],
            "min": m, "km": p["drive_km"], "band": band_of(m),
            "rank": rank, "tier": 1 if rank < TIER1 else 2 if rank < TIER2 else 3,
            "wd": p.get("wikidata"), "wp": p.get("wikipedia"),
            "gap": p.get("access_gap_km"), "th": th.get("name") if th else None,
            "reg": region_of(p["lon"], p["lat"]),
        })

    for f in regions["features"]:
        f["properties"]["n"] = sum(1 for x in out if x["reg"] == f["properties"]["id"])
    REGIONS.write_text(dumps_records(regions, "features"))

    origin = dict(ORIGIN)
    origin.setdefault("short", "Munich Hbf")
    data = {"generated": date.today().isoformat(), "origin": origin,
            "rules": {"max_min": MAX_MIN, "min_sitelinks": MIN_SITELINKS},
            "peaks": out}
    OUT.write_text(dumps_records(data, "peaks"))
    bands = {b: sum(1 for x in out if x["band"] == b) for b in range(1, 6)}
    print(f"{len(cand)} candidates -> {len(out)} peaks {bands} -> {OUT.relative_to(ROOT)} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")
    print("regions:", ", ".join(f"{f['properties']['name']} {f['properties']['n']}"
                                for f in regions["features"] if f["properties"]["n"]))
    print("top 15:", ", ".join(f"{x['name']} ({x['min']}')" for x in out[:15]))


if __name__ == "__main__":
    main()
