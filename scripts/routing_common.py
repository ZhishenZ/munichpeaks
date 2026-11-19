"""Shared helpers for the pipeline scripts (local Valhalla via pyvalhalla, data file output)."""
from __future__ import annotations

import json
import math
import re
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


def dumps_records(obj: dict, key: str, decimals: int | None = None) -> str:
    """JSON with one record per line: obj[key] is the list of records (peaks, features).

    Readable in an editor and gives one-line git diffs per changed peak / region, at almost no
    size cost. `decimals` rounds all floats (e.g. coordinates) to that many digits.
    """
    def one(x) -> str:
        text = json.dumps(x, ensure_ascii=False)
        return re.sub(rf"(\d+\.\d{{{decimals}}})\d+", r"\1", text) if decimals else text

    head = one({k: v for k, v in obj.items() if k != key})
    body = ",\n".join(one(r) for r in obj[key])
    return head[:-1] + (", " if len(head) > 2 else "") + f'"{key}": [\n{body}\n]}}\n'
