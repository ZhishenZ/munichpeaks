#!/usr/bin/env bash
# Download the Geofabrik extracts listed in config/regions.json into routing/pbf/.
# Resumable: re-run to continue interrupted downloads.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p routing/pbf
python3 -c 'import json; print("\n".join(json.load(open("config/regions.json"))["extracts"]))' |
while read -r path; do
  name="$(basename "$path")"
  echo "==> $name"
  curl -fL --retry 3 -C - -o "routing/pbf/$name-latest.osm.pbf" \
    "https://download.geofabrik.de/$path-latest.osm.pbf"
done
echo "done"; ls -lh routing/pbf
