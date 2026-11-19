"""Administrative regions for the "browse by region" feature (Overpass), simplified to GeoJSON.

One level per country, chosen so each region is a meaningful hiking area:
  DE  Regierungsbezirk (admin_level 5): Oberbayern, Schwaben, Niederbayern, Tübingen, …
  AT  Bundesland      (admin_level 4): Tirol, Salzburg, Vorarlberg, …
  CH  Kanton          (admin_level 4): Graubünden, St. Gallen, Glarus, …
  IT  Provincia       (admin_level 6): Südtirol, Trentino, Belluno, Sondrio, …
  LI  the whole country
Only regions that overlap the 3 h drive zone are kept.

Reads:  web/data/isochrones.geojson (run isochrones.py first)
Writes: web/data/regions.geojson
Usage:  uv run scripts/fetch_regions.py
"""
from __future__ import annotations

import json
import re
import time

import requests
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import linemerge, polygonize, polylabel, unary_union

from routing_common import ROOT

ISO = ROOT / "web" / "data" / "isochrones.geojson"
OUT = ROOT / "web" / "data" / "regions.geojson"
OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "munichpeaks-pipeline/0.1 (open-source hobby project)"}
SIMPLIFY_DEG = 0.002   # ~150 m

QUERY = """
[out:json][timeout:600];
area["ISO3166-2"="DE-BY"]->.by;
area["ISO3166-2"="DE-BW"]->.bw;
(
  rel(area.by)["boundary"="administrative"]["admin_level"="5"];
  rel(area.bw)["boundary"="administrative"]["admin_level"="5"];
  rel["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"~"^(AT|CH)-"];
  rel["boundary"="administrative"]["admin_level"="6"]["ISO3166-2"~"^IT-"]({bbox});
  rel["boundary"="administrative"]["admin_level"="2"]["ISO3166-1"="LI"];
);
out geom;
"""


def overpass(query: str) -> dict:
    for attempt in range(6):
        r = requests.post(OVERPASS, data={"data": query}, headers=HEADERS, timeout=900)
        if r.status_code == 200:
            return r.json()
        wait = 30 * (attempt + 1)
        print(f"  overpass {r.status_code}, retrying in {wait}s", flush=True)
        time.sleep(wait)
    r.raise_for_status()
    raise RuntimeError("Overpass kept refusing")


def assemble(rel: dict):
    """Polygon(s) from a relation's outer/inner member ways."""
    rings = {"outer": [], "inner": []}
    for m in rel.get("members", []):
        if m.get("type") == "way" and m.get("geometry") and m.get("role") in ("outer", "inner", ""):
            coords = [(p["lon"], p["lat"]) for p in m["geometry"]]
            if len(coords) >= 2:
                rings["inner" if m["role"] == "inner" else "outer"].append(LineString(coords))
    outer = unary_union(list(polygonize(linemerge(rings["outer"])))) if rings["outer"] else None
    if outer is None or outer.is_empty:
        return None
    if rings["inner"]:
        inner = unary_union(list(polygonize(linemerge(rings["inner"]))))
        outer = outer.difference(inner)
    return outer.buffer(0)


def country(t: dict) -> str:
    iso = t.get("ISO3166-2") or t.get("ISO3166-1") or ""
    if iso[:2] in ("AT", "CH", "IT", "LI"):
        return iso[:2]
    return "DE"


def clean(n: str) -> str:
    n = re.sub(r"^(Regierungsbezirk|Government Region of|Provincia (autonoma )?di) ", "", n)
    n = re.sub(r"^(Autonomous Province|Province) of ", "", n)
    n = re.sub(r" (Region|Government Region)$", "", n)
    return re.split(r" - | – |/", n)[0].strip()


def names(t: dict) -> tuple[str, str]:
    """(local, English) names: ("Tirol", "Tyrol"), ("Oberbayern", "Upper Bavaria"), …"""
    if t.get("ISO3166-2") == "IT-BZ":     # bilingual province; German is the majority language
        return "Südtirol", "South Tyrol"
    local = clean(t["name"])
    return local, clean(t.get("name:en") or local)


def main() -> None:
    zone = unary_union([shape(f["geometry"]) for f in json.loads(ISO.read_text())["features"]
                        if not f["properties"].get("outside")])
    w, s, e, n = zone.bounds
    data = overpass(QUERY.replace("{bbox}", f"{s},{w},{n},{e}"))
    feats = []
    for rel in data["elements"]:
        t = rel.get("tags", {})
        geom = assemble(rel)
        if geom is None or not geom.intersects(zone):
            continue
        geom = geom.simplify(SIMPLIFY_DEG, preserve_topology=True)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        label = polylabel(max(geom.geoms, key=lambda g: g.area), tolerance=0.01)
        local, en = names(t)
        feats.append({"type": "Feature", "id": rel["id"],
                      "geometry": json.loads(json.dumps(mapping(geom))),
                      "properties": {"id": rel["id"], "name": local, "en": en, "country": country(t),
                                     "lon": round(label.x, 4), "lat": round(label.y, 4),
                                     "bbox": [round(v, 4) for v in geom.bounds]}})
    feats.sort(key=lambda f: (f["properties"]["country"], f["properties"]["name"]))
    text = json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False,
                      separators=(",", ":"))
    text = re.sub(r"(\d+\.\d{5})\d+", r"\1", text)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(feats)} regions ({len(text) / 1024:.0f} KB)")
    for f in feats:
        print(f"  {f['properties']['country']} {f['properties']['name']} / {f['properties']['en']}")


if __name__ == "__main__":
    main()
