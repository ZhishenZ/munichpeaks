# munichpeaks

A static 3D map of well-known hiking peaks within a 3-hour drive of Munich.
Built for picking a weekend mountain.

- Three drive-time zones (isochrones): ≤ 1 h, ≤ 2 h, ≤ 3 h.
- Each peak is a marker, colored by its drive-time zone.
- Click a peak to fly into a tilted, rotating 3D terrain view showing name, elevation,
  drive time and distance from Munich.

The site is fully static (GitHub Pages). Everything is precomputed offline and stored as JSON/GeoJSON in this repo.
At runtime the page only loads map tiles (basemap + elevation) and needs no API keys.

> **Status:** early development. Phase 1 (single-peak 3D demo) only.

## Running locally

```sh
cd web
python3 -m http.server 8000
# open http://localhost:8000
```

## Data sources & attribution

| Data | Source | License |
|---|---|---|
| Peaks, roads | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors | ODbL 1.0 |
| Elevation (terrain, hillshade) | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Mapzen / Tilezen; sources include SRTM, Copernicus/EU-DEM, and others) | see [attribution list](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) |
| Topographic basemap | © [OpenTopoMap](https://opentopomap.org) | CC BY-SA 3.0 |
| Satellite basemap | [Sentinel-2 cloudless](https://s2maps.eu) by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2020) | CC BY-NC-SA 4.0 (non-commercial) |
| Map renderer | [MapLibre GL JS](https://maplibre.org) | BSD-3-Clause |

## Regenerating the data

_Coming in Phase 2._ The pipeline lives in `scripts/` (Python): Overpass for peaks,
a local routing engine (Valhalla in Docker) on Geofabrik extracts for drive times and isochrones.
The origin is configurable in `config/origin.json` (default: München Hauptbahnhof).

## Known limitations

- **Drive times are free-flow estimates.** Weekend traffic can make the real trip much longer.
- **Peaks are not parking lots.** Routes go to the drivable road nearest to the summit, which can be far from the
  actual trailhead. A `trailhead` field is reserved for hand-picked trailheads later.
- **The peak list is a curated subset**, not every named summit in OSM.

## License

Code: [MIT](LICENSE). Data and tiles keep their own licenses (see above).
