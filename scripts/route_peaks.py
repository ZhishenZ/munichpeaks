"""Drive time + distance from the origin to every candidate peak (local Valhalla).

Each peak is snapped to the nearest *public* drivable road (residential class or better;
forest tracks and service roads are excluded because many alpine tracks lack proper
access tags). The straight-line gap from that road point to the summit is stored as
access_gap_km to flag peaks where the estimate is unreliable (candidates for a hand-set
trailhead). If a peak has a "trailhead" {lon, lat} set, we route there instead.

We use one `route` request per peak (in parallel worker processes) rather than the
`matrix` endpoint: Valhalla's costmatrix dropped or inflated a noticeable share of
results for this data (e.g. Wendelstein missing, Zugspitze +60 min).

Reads:  data/peaks_raw.json
Writes: data/peaks_routed.json
Usage:  uv run scripts/route_peaks.py [--workers 8]
"""
from __future__ import annotations

import json
import sys
import time
from multiprocessing import Pool

from routing_common import ORIGIN, ROOT, call, haversine_km, make_actor

IN = ROOT / "data" / "peaks_raw.json"
OUT = ROOT / "data" / "peaks_routed.json"
SEARCH_FILTER = {"min_road_class": "residential"}   # lowest road class we snap to

_actor = None


def _init() -> None:
    global _actor
    _actor = make_actor()


def target(p: dict) -> dict:
    th = p.get("trailhead")
    lon, lat = (th["lon"], th["lat"]) if th else (p["lon"], p["lat"])
    return {"lon": lon, "lat": lat}


def decode_last(shape: str, precision: int = 6) -> tuple[float, float]:
    """Last point of a Valhalla encoded polyline (precision 6) -> (lon, lat)."""
    idx = lat = lon = 0
    factor = 10 ** precision
    while idx < len(shape):
        for which in (0, 1):
            result = shift = 0
            while True:
                b = ord(shape[idx]) - 63
                idx += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += d
            else:
                lon += d
    return lon / factor, lat / factor


def route_one(p: dict) -> dict:
    t = target(p)
    req = {"locations": [{"lon": ORIGIN["lon"], "lat": ORIGIN["lat"]},
                         {**t, "search_filter": SEARCH_FILTER}],
           "costing": "auto", "units": "kilometers", "directions_type": "none"}
    try:
        r = call(_actor, "route", req)
        s = r["trip"]["summary"]
        lon, lat = decode_last(r["trip"]["legs"][-1]["shape"])
        return {"drive_min": round(s["time"] / 60), "drive_km": round(s["length"]),
                "road_lon": round(lon, 6), "road_lat": round(lat, 6),
                "access_gap_km": round(haversine_km(t["lon"], t["lat"], lon, lat), 2)}
    except RuntimeError:
        return {"drive_min": None, "drive_km": None, "road_lon": None, "road_lat": None,
                "access_gap_km": None}


def main() -> None:
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8
    peaks = json.loads(IN.read_text())
    t0 = time.time()
    with Pool(workers, initializer=_init) as pool:
        for i, res in enumerate(pool.imap(route_one, peaks, chunksize=16), 1):
            peaks[i - 1].update(res)
            if i % 500 == 0 or i == len(peaks):
                print(f"  {i}/{len(peaks)}  ({time.time() - t0:.0f}s)", flush=True)

    OUT.write_text(json.dumps(peaks, ensure_ascii=False, indent=1))
    ok = [p for p in peaks if p["drive_min"] is not None]
    within = [p for p in ok if p["drive_min"] <= 180]
    print(f"routed {len(ok)}/{len(peaks)}; {len(within)} within 180 min -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
