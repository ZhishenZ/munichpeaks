"""Fetch named peaks from OpenStreetMap via Overpass and apply curation rules.

Output: data/peaks_raw.json  (all candidates, before routing)

Selection:
  natural=peak with name, ele >= MIN_ELE and a wikidata tag, inside BBOX,
  minus config/peaks_exclude.json, plus config/peaks_include.json (by OSM node id).

Usage:  uv run scripts/fetch_peaks.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "peaks_raw.json"
INCLUDE = ROOT / "config" / "peaks_include.json"
EXCLUDE = ROOT / "config" / "peaks_exclude.json"

OVERPASS = "https://overpass-api.de/api/interpreter"
# south, west, north, east — the Alps within ~3 h of Munich (generous; routing decides).
BBOX = (45.9, 8.8, 48.0, 14.0)
MIN_ELE = 1500

QUERY = """
[out:json][timeout:300];
(
  node["natural"="peak"]["name"]["ele"]["wikidata"]({s},{w},{n},{e});
  {include}
);
out body;
"""


def parse_ele(raw: str | None) -> int | None:
    if not raw:
        return None
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)", raw)
    return round(float(m.group(1).replace(",", "."))) if m else None


def load_ids(path: Path, key: str) -> set[int]:
    if not path.exists():
        return set()
    return {int(x["osm_id"]) for x in json.loads(path.read_text())[key]}


def main() -> None:
    include = load_ids(INCLUDE, "include")
    exclude = load_ids(EXCLUDE, "exclude")
    inc_q = f"node(id:{','.join(map(str, include))});" if include else ""
    s, w, n, e = BBOX
    q = QUERY.format(s=s, w=w, n=n, e=e, include=inc_q)

    r = requests.post(OVERPASS, data={"data": q}, timeout=400,
                      headers={"User-Agent": "munichpeaks-pipeline/0.1"})
    r.raise_for_status()
    elements = r.json()["elements"]

    peaks = []
    for el in elements:
        t = el.get("tags", {})
        ele = parse_ele(t.get("ele"))
        forced = el["id"] in include
        if el["id"] in exclude:
            continue
        if not forced and (ele is None or ele < MIN_ELE):
            continue
        peaks.append({
            "osm_id": el["id"],
            "name": t.get("name"),
            "name_de": t.get("name:de"),
            "name_en": t.get("name:en"),
            "ele": ele,
            "lon": round(el["lon"], 6),
            "lat": round(el["lat"], 6),
            "wikidata": t.get("wikidata"),
            "wikipedia": t.get("wikipedia"),
            "prominence": parse_ele(t.get("prominence")),
            "trailhead": None,  # reserved: hand-picked trailhead {lon, lat, name}
        })

    peaks.sort(key=lambda p: -(p["ele"] or 0))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(peaks, ensure_ascii=False, indent=1))
    with_wp = sum(1 for p in peaks if p["wikipedia"])
    with_prom = sum(1 for p in peaks if p["prominence"])
    print(f"{len(elements)} elements -> {len(peaks)} peaks "
          f"({with_wp} with wikipedia, {with_prom} with prominence) -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
