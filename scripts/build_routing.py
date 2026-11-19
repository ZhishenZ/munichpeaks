"""Build Valhalla routing tiles from the OSM extracts in routing/pbf/ (no Docker).

Writes:
  routing/valhalla.json        Valhalla config
  routing/admins.sqlite        admin boundaries (country-specific road rules)
  routing/valhalla_tiles/      graph tiles (what the routing scripts load)

Takes roughly 30-90 min and up to ~10 GB of disk.
Usage:  uv run scripts/build_routing.py [--skip-admins]
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from valhalla import get_config

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "routing"
PBF_DIR = R / "pbf"
TILE_DIR = R / "valhalla_tiles"
ADMINS = R / "admins.sqlite"
CONFIG = R / "valhalla.json"


def valhalla(*args: str) -> None:
    cmd = [sys.executable, "-m", "valhalla", *args]
    print("$", " ".join(cmd[2:]), flush=True)
    t = time.time()
    subprocess.run(cmd, check=True)
    print(f"  ({(time.time() - t) / 60:.1f} min)", flush=True)


def main() -> None:
    pbfs = sorted(str(p) for p in PBF_DIR.glob("*.osm.pbf"))
    if not pbfs:
        sys.exit("no .osm.pbf files in routing/pbf — run scripts/download_osm.sh first")
    TILE_DIR.mkdir(parents=True, exist_ok=True)

    cfg = get_config(tile_extract="", tile_dir=TILE_DIR, verbose=True)
    m = cfg["mjolnir"]
    m["admin"] = str(ADMINS)
    m["timezone"] = ""            # not needed: we don't use time-dependent routing
    m["concurrency"] = 8          # 10-core / 16 GB machine; leaves headroom
    cfg["additional_data"] = {"elevation": ""}
    CONFIG.write_text(json.dumps(cfg, indent=1))

    if "--skip-admins" not in sys.argv:
        valhalla("valhalla_build_admins", "-c", str(CONFIG), *pbfs)
    valhalla("valhalla_build_tiles", "-c", str(CONFIG), *pbfs)
    size = sum(f.stat().st_size for f in TILE_DIR.rglob("*") if f.is_file())
    print(f"done: {TILE_DIR} ({size / 2**30:.2f} GB)")


if __name__ == "__main__":
    main()
