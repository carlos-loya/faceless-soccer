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
import json
import re
import sys
import time
from pathlib import Path

import requests

COMMONS = "https://commons.wikimedia.org/w/api.php"
OPENVERSE = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "TikiTakaFootyTV/1.0 (faceless-soccer content tool; contact: exafterdev@gmail.com)"}
FREE = re.compile(r"\b(cc0|pdm|public domain|cc by|cc-by|by-sa|by 2|by 3|by 4|attribution)\b", re.I)
MIN_W = 500


def is_image(b: bytes) -> bool:
    return (
        (b[:3] == b"\xff\xd8\xff")
        or (b[:4] == b"\x89PNG")
        or (b[:3] == b"GIF")
        or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")
    )


def get_image(url: str, tries: int = 4) -> bytes | None:
    for k in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 429:
                time.sleep(1.5 * (k + 1)); continue
            b = r.content
            if b and len(b) >= 12 and is_image(b):
                return b
        except Exception:
            pass
        time.sleep(1.0 * (k + 1))
    return None


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _from_commons_pages(pages: list) -> list[dict]:
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [None])[0]
        if not ii or not re.search("jpeg|png", ii.get("mime", "") or ""):
            continue
        if (ii.get("width") or 0) < MIN_W:
            continue
        md = ii.get("extmetadata", {}) or {}
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not FREE.search(lic):
            continue
        artist = strip_html((md.get("Artist", {}) or {}).get("value", ""))
        out.append({
            "url": ii["url"], "title": p.get("title", ""), "width": ii.get("width", 0),
            "license": lic, "credit": f"{artist or 'Wikimedia'} / {lic} via Wikimedia Commons",
            "source": "commons",
        })
    return out


def commons_search(query: str, limit: int) -> list[dict]:
    r = requests.get(COMMONS, params={
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "format": "json",
    }, headers=UA, timeout=60).json()
    pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return _from_commons_pages(pages)


def commons_category(name: str, limit: int) -> list[dict]:
    r = requests.get(COMMONS, params={
        "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{name}",
        "gcmtype": "file", "gcmlimit": limit, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "format": "json",
    }, headers=UA, timeout=60).json()
    pages = list(r.get("query", {}).get("pages", {}).values())
    return _from_commons_pages(pages)


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
    out.mkdir(parents=True, exist_ok=True)

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

    manifest, i = [], 0
    for c in uniq:
        if i >= n:
            break
        data = get_image(c["url"])
        if not data:
            continue
        ext = (c["url"].split(".")[-1].split("?")[0] or "jpg")[:4].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        i += 1
        fn = out / f"cand-{i}.{ext}"
        fn.write_bytes(data)
        manifest.append({"index": i, "file": str(fn), "title": c["title"], "url": c["url"],
                         "license": c["license"], "credit": c["credit"], "source": c["source"]})
        print(f"  [{i:2}] {c['source']:18} {c.get('width','?')}px  {c['title'][:46]}")
        time.sleep(0.4)

    (out / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print(f"  -> {i} candidates in {out}/ (look + pick the national-kit shot)")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--n"]
    n = 12
    if "--n" in sys.argv:
        idx = sys.argv.index("--n")
        if idx + 1 < len(sys.argv):
            n = int(sys.argv[idx + 1]); args = [a for a in args if a != str(n)]
    if not args:
        sys.exit("usage: uv run pipeline/fetch_player_candidates.py <slug> [<slug> ...] [--n 12]")
    for slug in args:
        fetch_for(slug, n)


if __name__ == "__main__":
    main()
