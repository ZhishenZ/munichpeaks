"""Shared helpers for the routing scripts (local Valhalla via pyvalhalla)."""
from __future__ import annotations

import json
import math
from pathlib import Path

from valhalla import Actor

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "routing" / "valhalla.json"
ORIGIN = json.loads((ROOT / "config" / "origin.json").read_text())


def make_actor() -> Actor:
    """Actor with service limits raised: we run offline and need big matrices / 3 h isochrones."""
    if not CONFIG.exists():
        raise SystemExit("routing/valhalla.json missing — run scripts/build_routing.py first")
    cfg = json.loads(CONFIG.read_text())
    lim = cfg["service_limits"]
    lim["auto"]["max_matrix_location_pairs"] = 100_000
    lim["auto"]["max_matrix_distance"] = 2_000_000
    lim["auto"]["max_distance"] = 2_000_000
    lim["isochrone"]["max_time_contour"] = 300
    lim["isochrone"]["max_distance"] = 2_000_000
    lim["isochrone"]["max_locations"] = 10
    lim["isochrone"]["max_contours"] = 8
    cfg["loki"]["service_defaults"]["minimum_reachability"] = 50
    for section in cfg.values():  # quiet: the build config logs to stdout
        if isinstance(section, dict) and isinstance(section.get("logging"), dict):
            section["logging"]["type"] = ""
    tmp = CONFIG.with_name("valhalla.runtime.json")
    tmp.write_text(json.dumps(cfg))
    return Actor(str(tmp))


def call(actor: Actor, method: str, req: dict) -> dict | list:
    res = getattr(actor, method)(json.dumps(req))
    return json.loads(res) if isinstance(res, str) else res


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
