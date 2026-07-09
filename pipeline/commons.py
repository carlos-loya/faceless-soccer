# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Shared Wikimedia Commons helpers for the fetch_* image scripts.

Every fetcher pulls FREE-licensed (CC / CC0 / public domain) images from Wikimedia Commons and
re-implemented the same download/validate/parse code. This module is the one copy. Imported by
fetch_images / fetch_candidates / fetch_scene_candidates / fetch_player_candidates(_plus).

`uv run pipeline/<fetcher>.py` puts pipeline/ on sys.path[0], so `from commons import ...` works.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

UA = {"User-Agent": "TikiTakaFootyTV/1.0 (faceless-soccer content tool; +https://github.com/carlos-loya/faceless-soccer)"}
WP = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FREE = re.compile(r"\b(cc0|pdm|public domain|cc by|cc-by|by-sa|by 2|by 3|by 4|attribution)\b", re.I)
MIN_W = 500  # min image width kept from Commons search/category


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def is_free(lic: str) -> bool:
    return bool(FREE.search(lic or ""))


def is_image(b: bytes) -> bool:
    """Reject HTML/error pages downloaded with an image name."""
    return (b[:3] == b"\xff\xd8\xff" or b[:4] == b"\x89PNG"
            or b[:3] == b"GIF" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP"))


def get_image(url: str, tries: int = 4) -> bytes | None:
    """Download with 429-backoff — Wikimedia rate-limits rapid file fetches. Returns validated bytes."""
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
        time.sleep(1.0)
    return None


def _from_commons_pages(pages: list, min_w: int = MIN_W) -> list[dict]:
    """imageinfo pages -> free-licensed, wide-enough jpeg/png rows {url,title,width,license,credit,source}."""
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [None])[0]
        if not ii or not re.search("jpeg|png", ii.get("mime", "") or ""):
            continue
        if (ii.get("width") or 0) < min_w:
            continue
        md = ii.get("extmetadata", {}) or {}
        lic = (md.get("LicenseShortName", {}) or {}).get("value", "")
        if not is_free(lic):
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


def download_candidates(cands: list[dict], out_dir: Path, n: int, prefix: str = "cand") -> list[dict]:
    """Download up to n candidate rows into out_dir as <prefix>-i.<ext>; return manifest rows (index,file,+row keys)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest, i = [], 0
    for c in cands:
        if i >= n:
            break
        data = get_image(c["url"])
        if not data:
            continue
        ext = (c["url"].split(".")[-1].split("?")[0] or "jpg")[:4].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        i += 1
        fn = out_dir / f"{prefix}-{i}.{ext}"
        fn.write_bytes(data)
        manifest.append({"index": i, "file": str(fn), **{k: c[k] for k in
                         ("title", "url", "license", "credit", "source", "width") if k in c}})
        time.sleep(0.4)
    return manifest


def candidates_for(query: str, out_dir: Path, n: int) -> list[dict]:
    """One Commons keyword query -> up to n downloaded, validated candidate rows."""
    return download_candidates(commons_search(query, n * 3), out_dir, n)


if __name__ == "__main__":
    assert is_image(b"\xff\xd8\xff\x00stuff") and is_image(b"\x89PNG\r\n")
    assert not is_image(b"<html>nope")
    assert strip_html("<b>Foo</b> &amp;") == "Foo &amp;"
    assert is_free("CC BY-SA 4.0") and is_free("Public domain") and not is_free("All rights reserved")
    print("commons.py self-check ok")
