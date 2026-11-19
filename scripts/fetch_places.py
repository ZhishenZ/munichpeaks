"""Cities and towns for map labels (Overpass), so the page needs no label tile service.

Each place has its local name ("name": München, Trento, Bozen) and, where OSM has one, an
English name ("en": Munich, Trent, Bolzano); the page switches between the two.

Writes: web/data/places.geojson
Usage:  uv run scripts/fetch_places.py
"""
from __future__ import annotations

import json
import re
import time

import requests

from routing_common import ROOT

OUT = ROOT / "web" / "data" / "places.geojson"
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = (45.6, 8.3, 49.8, 14.6)  # S, W, N, E — the 3 h zone plus margin
QUERY = f"""
[out:json][timeout:180];
node["place"~"^(city|town)$"]["name"]({",".join(map(str, BBOX))});
out;
"""


def local_name(t: dict) -> str:
    """Local name; for bilingual OSM names ("Bolzano - Bozen") prefer the German form."""
    parts = re.split(r" - | / |/", t["name"])
    if len(parts) > 1 and t.get("name:de") in [p.strip() for p in parts]:
        return t["name:de"]
    return parts[0].strip()


def main() -> None:
    for attempt in range(6):   # Overpass is often busy (429 / 504): back off and retry
        r = requests.post(OVERPASS, data={"data": QUERY}, timeout=300,
                          headers={"User-Agent": "munichpeaks-pipeline/0.1 (open-source hobby project)"})
        if r.status_code == 200:
            break
        print(f"  overpass {r.status_code}, retrying in {30 * (attempt + 1)}s", flush=True)
        time.sleep(30 * (attempt + 1))
    r.raise_for_status()
    feats = []
    for el in r.json()["elements"]:
        t = el["tags"]
        try:
            pop = int(str(t.get("population", "0")).replace(",", "").replace(".", "").split()[0])
        except ValueError:
            pop = 0
        # rank: 1 = big city or state/national capital (Innsbruck, Salzburg, Bregenz, …),
        #       2 = city / large town, 3 = town
        capital = t.get("capital") in ("yes", "2", "4")
        rank = 1 if (pop >= 100_000 or capital) else 2 if (t["place"] == "city" or pop >= 20_000) else 3
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(el["lon"], 5), round(el["lat"], 5)]},
                      "properties": {"name": local_name(t), "en": t.get("name:en"),
                                     "rank": rank, "pop": pop}})
    feats.sort(key=lambda f: (f["properties"]["rank"], -f["properties"]["pop"]))
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False, separators=(",", ":")))
    by = {k: sum(f["properties"]["rank"] == k for f in feats) for k in (1, 2, 3)}
    print(f"wrote {OUT.relative_to(ROOT)}: {len(feats)} places {by} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
