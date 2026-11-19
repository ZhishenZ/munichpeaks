# munichpeaks

A 3D map of ~530 well-known hiking peaks within a 3-hour drive of Munich, with drive-time zones.

**Live:** https://zhishenz.github.io/munichpeaks/

A static site: all data is precomputed. At runtime it loads only map tiles, with no API keys.

## Data & attribution

| | Source | License |
|---|---|---|
| Peaks, places, regions, roads | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors | ODbL |
| Peak fame | [Wikidata](https://www.wikidata.org) | CC0 |
| Drive times | [Valhalla](https://github.com/valhalla/valhalla) on OSM data | ODbL (derived) |
| Elevation | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) ([sources](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)) | various |
| Satellite | [Sentinel-2 cloudless](https://s2maps.eu) by EOX (Copernicus Sentinel data 2020) | CC BY-NC-SA 4.0 |
| Font | [Noto Sans](https://fonts.google.com/noto) | OFL 1.1 |
| Renderer | [MapLibre GL JS](https://maplibre.org) | BSD-3 |

The files in `web/data/` contain OpenStreetMap data and are licensed under the ODbL.

## License

Code: [MIT](LICENSE).
