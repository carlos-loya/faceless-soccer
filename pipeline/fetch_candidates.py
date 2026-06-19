# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Image candidates — fetch several free Wikimedia Commons options for a query so a HUMAN/Claude
can VISUALLY pick the right one (keyword search alone returns plausible-but-wrong images, e.g.
"FIFA World Cup Trophy" -> Germany lifting it). The chosen image is then curated onto a KB
entity for correct, reusable visuals.

Run:  uv run pipeline/fetch_candidates.py "FIFA World Cup Trophy" 8
Out:  out/candidates/<slug>/cand-N.<ext>  +  candidates.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "TikiTakaFootyTV/1.0 (faceless-soccer content tool; contact: exafterdev@gmail.com)"}


def get_image(url: str, tries: int = 4) -> bytes | None:
    """Download with 429-backoff — Wikimedia rate-limits rapid file fetches."""
    for k in range(tries):
        try:
            resp = requests.get(url, headers=UA, timeout=60)
        except Exception:
            time.sleep(1.0); continue
        if resp.status_code == 200:
            return resp.content
        if resp.status_code == 429:
            time.sleep(1.5 * (k + 1)); continue
        return None
    return None


def strip_html(s: str) -> str:
    return re.sub("<[^>]+>", "", s or "").strip()


def is_image(b: bytes) -> bool:
    """Reject HTML/error pages downloaded with an image name."""
    return (b[:3] == b"\xff\xd8\xff" or b.startswith(b"\x89PNG")
            or b[:3] == b"GIF" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP"))


def main() -> None:
    query = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    out = Path("out/candidates") / slug
    out.mkdir(parents=True, exist_ok=True)

    r = requests.get(COMMONS, params={
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": n * 3, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "format": "json",
    }, headers=UA, timeout=60).json()
    pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))

    manifest, i = [], 0
    for p in pages:
        ii = (p.get("imageinfo") or [None])[0]
        if not ii or not re.search("jpeg|png", ii.get("mime", "")):
            continue
        if ii.get("width", 0) < 600:
            continue
        lic = ((ii.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "")).lower()
        if not re.search(r"cc|public domain|cc0|pdm", lic):
            continue
        ext = ii["url"].split(".")[-1].split("?")[0][:4]
        data = get_image(ii["url"])
        if not data or len(data) < 12 or not is_image(data):
            continue
        i += 1
        fn = out / f"cand-{i}.{ext}"
        fn.write_bytes(data)
        time.sleep(0.5)
        artist = strip_html((ii.get("extmetadata", {}).get("Artist", {}) or {}).get("value", ""))
        lic_name = (ii.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "CC")
        manifest.append({
            "index": i, "file": str(fn), "title": p.get("title", ""), "url": ii["url"],
            "credit": f"{artist or 'Wikimedia'} / {lic_name} via Wikimedia Commons",
        })
        print(f"  [{i}] {p.get('title','')}  ({ii.get('width')}x{ii.get('height')})")
        if i >= n:
            break

    (out / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print(f"\n{i} candidates -> {out}/")


if __name__ == "__main__":
    main()
