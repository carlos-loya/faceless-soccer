# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
EXPANDED player-photo fetcher — casts a wider net than fetch_player_candidates.py by adding
DIFFERENT sources beyond Commons-search/Openverse:
  1. Wikidata  — the entity's PREFERRED image (P18), often a clean portrait
  2. Per-language Wikipedia LEAD images via Wikidata sitelinks (en + ko + cs + de + es)
     — the Korean/Czech Wikipedia lead for a Korean/Czech player is frequently a
       NATIONAL-KIT shot that the English page / Commons search miss.
Only FREE-licensed, Commons-hosted files are kept (url must contain "/commons/"), so the
no-paid-agency rule holds. Output mirrors the base fetcher so vision-review is identical.

Usage:  uv run pipeline/fetch_player_candidates_plus.py <slug>:"<Full Name>" [...]
Output: out/candidates/<slug>/plus-N.<ext> + plus.json
"""
import json
import sys
import time
from pathlib import Path

import requests

WD_API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "TikiTakaFootyTV/1.0 (faceless-soccer content tool; +https://github.com/carlos-loya/faceless-soccer)"}
LANGS = ["en", "ko", "cs", "de", "es", "tr"]  # languages whose Wikipedia leads we harvest
MIN_W = 500


def is_image(b: bytes) -> bool:
    return (
        b[:3] == b"\xff\xd8\xff" or b[:4] == b"\x89PNG"
        or b[:3] == b"GIF" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")
    )


def commons_only(url: str) -> bool:
    """Free-license guardrail: keep only Commons-hosted files (local non-free wiki uploads excluded)."""
    return "/wikipedia/commons/" in url


def wikidata_qid(name: str) -> str | None:
    r = requests.get(WD_API, params={
        "action": "wbsearchentities", "search": name, "language": "en",
        "type": "item", "limit": 5, "format": "json"}, headers=UA, timeout=30).json()
    for hit in r.get("search", []):
        desc = (hit.get("description") or "").lower()
        if any(k in desc for k in ("football", "soccer", "goalkeeper", "footballer")):
            return hit["id"]
    return r.get("search", [{}])[0].get("id") if r.get("search") else None


def imageinfo(title: str) -> dict | None:
    """Resolve a Commons File: title to {url,width,license,credit}."""
    r = requests.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "format": "json"}, headers=UA, timeout=30).json()
    pages = r.get("query", {}).get("pages", {})
    for p in pages.values():
        ii = (p.get("imageinfo") or [None])[0]
        if not ii:
            return None
        em = ii.get("extmetadata", {})
        return {
            "url": ii["url"], "width": ii.get("width"),
            "license": em.get("LicenseShortName", {}).get("value", "?"),
            "credit": em.get("Artist", {}).get("value", "?"), "title": title,
        }
    return None


def from_wikidata(name: str) -> list[dict]:
    out, qid = [], wikidata_qid(name)
    if not qid:
        return out
    ent = requests.get(WD_API, params={
        "action": "wbgetentities", "ids": qid, "props": "claims|sitelinks", "format": "json"},
        headers=UA, timeout=30).json().get("entities", {}).get(qid, {})
    # 1) P18 preferred image
    for claim in ent.get("claims", {}).get("P18", []):
        fn = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if fn:
            info = imageinfo("File:" + fn)
            if info:
                info["source"] = "wikidata-P18"
                out.append(info)
    # 2) per-language Wikipedia lead images
    sit = ent.get("sitelinks", {})
    for lang in LANGS:
        key = f"{lang}wiki"
        if key not in sit:
            continue
        title = sit[key]["title"]
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params={
            "action": "query", "titles": title, "prop": "pageimages",
            "piprop": "original", "format": "json"}, headers=UA, timeout=30).json()
        for p in r.get("query", {}).get("pages", {}).values():
            src = (p.get("original") or {}).get("source")
            if src and commons_only(src):
                out.append({"url": src, "width": (p.get("original") or {}).get("width"),
                            "license": "(Commons)", "credit": "?", "title": f"{lang}wiki lead",
                            "source": f"{lang}wiki"})
        time.sleep(0.2)
    return out


def fetch_for(slug: str, name: str) -> None:
    d = Path("out/candidates") / slug
    d.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {name} ({slug}) — expanded sources ===")
    pool, seen, kept = from_wikidata(name), set(), []
    for c in pool:
        url = c["url"]
        if url in seen or not commons_only(url):
            continue
        seen.add(url)
        try:
            b = requests.get(url, headers=UA, timeout=60).content
        except Exception:
            continue
        if not is_image(b) or len(b) < 8000:
            continue
        i = len(kept) + 1
        ext = url.rsplit(".", 1)[-1].split("?")[0].lower()[:4]
        fp = d / f"plus-{i}.{ext}"
        fp.write_bytes(b)
        c["file"] = str(fp)
        kept.append(c)
        w = c.get("width") or "?"
        print(f"  [{i:2}] {c['source']:14} {str(w):>6}px  {c['license']:20} | {c['title'][:48]}")
    (d / "plus.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2))
    print(f"  -> {len(kept)} expanded candidates in {d}/ (plus-N) — vision-pick the best national-kit shot")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('usage: uv run pipeline/fetch_player_candidates_plus.py <slug>:"<Full Name>" ...')
        sys.exit(1)
    for a in args:
        slug, _, name = a.partition(":")
        fetch_for(slug.strip(), (name or slug).strip())
