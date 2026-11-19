"""Add a fame score to each peak from Wikidata (count of Wikipedia language editions).

Fame = max over two Wikidata items:
  1. the peak's own `wikidata` tag, and
  2. the item behind its `wikipedia` tag (OSM often links a single summit node such as
     "Watzmann-Mittelspitze" to a minor item, but its wikipedia tag to "de:Watzmann").
Bot-generated Wikipedias (cebuano, waray, swedish Lsjbot stubs) are not counted.

Responses are cached in data/cache/ so a rate-limited run can simply be restarted.

Reads/writes data/peaks_raw.json in place (adds "sitelinks", "wiki_qid", "wikis").
Usage:  uv run scripts/enrich_wikidata.py
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "peaks_raw.json"
CACHE = ROOT / "data" / "cache" / "wikidata.json"
API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "munichpeaks-pipeline/0.1 (open-source hobby project)"}
# Wikipedias where bots mass-created stub articles for (nearly) every GeoNames summit in the
# Alps. Measured on this data set: ceb 3713, zh 1414, lld 1362, sv 1186, arz 653 articles vs.
# en 737 — they say nothing about how well known a peak is, so they don't count toward fame.
BOT_WIKIS = {"cebwiki", "warwiki", "svwiki", "lldwiki", "arzwiki", "uzwiki", "zhwiki",
             "nlwiki", "plwiki", "lmowiki", "azbwiki", "nnwiki"}
NON_WP = {"commonswiki", "specieswiki", "metawiki", "wikidatawiki", "mediawikiwiki", "sourceswiki"}

session = requests.Session()


def api(params: dict) -> dict:
    """GET with polite pacing and backoff on 429 / maxlag."""
    params = {**params, "format": "json", "maxlag": 5}
    for attempt in range(10):
        r = session.get(API, params=params, headers=HEADERS, timeout=60)
        if r.status_code == 200 and '"maxlag"' not in r.text[:300]:
            time.sleep(1.0)
            return r.json()
        wait = int(r.headers.get("Retry-After", 15 * (attempt + 1)))
        print(f"  rate-limited ({r.status_code}), waiting {wait}s", flush=True)
        time.sleep(wait)
    r.raise_for_status()
    raise RuntimeError("Wikidata API kept refusing")


def wikis_of(ent: dict) -> list[str]:
    return sorted(k for k in ent.get("sitelinks", {}) if k.endswith("wiki") and k not in NON_WP)


def main() -> None:
    peaks = json.loads(PATH.read_text())
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {"qid": {}, "title": {}}

    def save() -> None:
        CACHE.write_text(json.dumps(cache))

    # 1) wikipedia tag "de:Watzmann" -> qid (and its sitelinks), batched per language
    by_site: dict[str, list[str]] = defaultdict(list)
    for p in peaks:
        wp = p.get("wikipedia")
        if wp and ":" in wp and not cache["title"].get(wp):   # unresolved/None -> retry
            lang, title = wp.split(":", 1)
            by_site[f"{lang}wiki"].append(title)
    for site, titles in by_site.items():
        titles = sorted(set(titles))
        lang = site[:-4]
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            # note: no "normalize" — the API only allows it for a single title
            data = api({"action": "wbgetentities", "sites": site,
                        "titles": "|".join(t.replace("_", " ") for t in batch),
                        "props": "sitelinks"})
            if "error" in data:
                print(f"  {site}: {data['error'].get('info')}", flush=True)
                continue
            found = {}
            for qid, ent in data.get("entities", {}).items():
                if qid.startswith("Q"):
                    cache["qid"][qid] = wikis_of(ent)
                    sl = ent.get("sitelinks", {}).get(site)
                    if sl:
                        found[sl["title"]] = qid
            for t in batch:
                cache["title"][f"{lang}:{t}"] = found.get(t.replace("_", " "))
            save()
        print(f"  resolved {len(titles)} wikipedia titles on {site}", flush=True)

    # 2) the peaks' own wikidata items
    qids = sorted({p["wikidata"] for p in peaks
                   if (p.get("wikidata") or "").startswith("Q") and p["wikidata"] not in cache["qid"]})
    for i in range(0, len(qids), 50):
        data = api({"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]), "props": "sitelinks"})
        for qid, ent in data.get("entities", {}).items():
            cache["qid"][qid] = wikis_of(ent)
        if (i // 50) % 20 == 0:
            save()
            print(f"  {min(i + 50, len(qids))}/{len(qids)} items", flush=True)
    save()

    def fame(qid: str | None) -> tuple[int, list[str]]:
        w = cache["qid"].get(qid or "", [])
        return sum(1 for k in w if k not in BOT_WIKIS), w

    for p in peaks:
        own, own_w = fame(p.get("wikidata"))
        art_q = cache["title"].get(p.get("wikipedia") or "")
        art, art_w = fame(art_q)
        if art > own:
            p["sitelinks"], p["wikis"], p["wiki_qid"] = art, art_w, art_q
        else:
            p["sitelinks"], p["wikis"], p["wiki_qid"] = own, own_w, p.get("wikidata")

    PATH.write_text(json.dumps(peaks, ensure_ascii=False, indent=1))
    dist = {k: sum(1 for p in peaks if p["sitelinks"] >= k) for k in (1, 2, 3, 5, 10, 20)}
    print(f"{len(peaks)} peaks; count with >= N sitelinks: {dist}")


if __name__ == "__main__":
    main()
