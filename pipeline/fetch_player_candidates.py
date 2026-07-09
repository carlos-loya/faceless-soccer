# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Player-portrait candidate fetcher (the wider net) — gathers MANY free-licensed photos of a
player from multiple sources so we can VISION-PICK one where they're in their NATIONAL kit
(or at least club kit) for a clean cutout. Sources, all FREE-license only (no agency/paid):
  1. Wikimedia Commons full-text SEARCH (not just the Wikipedia lead image)
  2. The player's Commons CATEGORY (Category:<name>) — usually the richest match-photo pool
  3. Openverse API (aggregates Flickr CC + others; no API key needed)

Usage:  uv run pipeline/fetch_player_candidates.py <player-slug> [<slug> ...] [--n 12]
Output: out/candidates/<slug>/cand-N.<ext> + candidates.json
        (each entry has source + license + credit; only CC/PD/CC0 kept)
Next:   look at the candidates, pick the national-kit shot, write it to the KB entity's
        `image` field (url+license+attribution), then `uv run pipeline/cutout.py <slug>`.
        (The `pick-images` skill automates the "look + choose" step.)
"""
import argparse
import json
from pathlib import Path

import requests

from commons import UA, COMMONS, _from_commons_pages, commons_search, download_candidates

OPENVERSE = "https://api.openverse.org/v1/images/"


def commons_category(name: str, limit: int) -> list[dict]:
    r = requests.get(COMMONS, params={
        "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{name}",
        "gcmtype": "file", "gcmlimit": limit, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "format": "json",
    }, headers=UA, timeout=60).json()
    return _from_commons_pages(list(r.get("query", {}).get("pages", {}).values()))


def openverse_search(query: str, limit: int) -> list[dict]:
    try:
        r = requests.get(OPENVERSE, params={
            "q": query, "license": "by,by-sa,cc0,pdm", "extension": "jpg,png",
            "mature": "false", "page_size": limit,
        }, headers=UA, timeout=60).json()
    except Exception:
        return []
    out = []
    for it in r.get("results", []) or []:
        url = it.get("url")
        if not url:
            continue
        lic = f"CC {(it.get('license') or '').upper()} {it.get('license_version') or ''}".strip()
        creator = it.get("creator") or "Unknown"
        src = it.get("source") or "openverse"
        out.append({
            "url": url, "title": it.get("title", ""), "width": it.get("width") or 0,
            "license": lic, "credit": f"{creator} / {lic} via {src} (Openverse)",
            "source": f"openverse:{src}",
        })
    return out


def fetch_for(slug: str, n: int) -> None:
    ent_path = Path(f"kb/entities/{slug}.json")
    name = slug.replace("-", " ").title()
    if ent_path.exists():
        name = json.loads(ent_path.read_text()).get("name", name)

    out = Path("out/candidates") / slug
    print(f"\n=== {name} ({slug}) ===")
    pool: list[dict] = []
    pool += commons_category(name, n * 2)
    pool += commons_search(f"{name} football", n * 2)
    pool += commons_search(f"{name} soccer", n)
    pool += openverse_search(f"{name} football", n * 2)

    # dedupe by url, prefer wider images first
    seen, uniq = set(), []
    for c in sorted(pool, key=lambda c: -(c.get("width") or 0)):
        if c["url"] in seen:
            continue
        seen.add(c["url"]); uniq.append(c)

    manifest = download_candidates(uniq, out, n)
    for c in manifest:
        print(f"  [{c['index']:2}] {c.get('source',''):18} {c.get('width','?')}px  {c.get('title','')[:46]}")
    (out / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print(f"  -> {len(manifest)} candidates in {out}/ (look + pick the national-kit shot)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="+")
    ap.add_argument("--n", type=int, default=12)
    args = ap.parse_args()
    for slug in args.slugs:
        fetch_for(slug, args.n)


if __name__ == "__main__":
    main()
