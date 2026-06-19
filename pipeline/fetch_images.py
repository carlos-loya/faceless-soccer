# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
CC/Wikimedia image layer — fetch FREE, legally-attributed player portraits into the KB.

For each player entity (kb/entities/*.json of type "player"): find the Wikipedia lead
image, verify it carries a FREE license (CC / CC0 / public domain) on Wikimedia Commons,
and write {url, license, attribution, as_of} into the entity's `image` field.

Only free-licensed images are stored — agency/fair-use lead images are skipped (we never
ship a copyrighted photo). The KB's `image` slot is consumed by the render pipeline.

Run:  uv run pipeline/fetch_images.py            # all player entities
      uv run pipeline/fetch_images.py lamine-yamal kylian-mbappe
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

UA = {"User-Agent": "TikiTakaFootyTV/1.0 (faceless-soccer project; image-sourcing)"}
WP = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FREE_MARKERS = ("cc0", "cc by", "cc-by", "public domain", "pdm", "creative commons")


def strip_html(s: str) -> str:
    return re.sub("<[^>]+>", "", s or "").strip()


def lead_image(title: str):
    r = requests.get(WP, params={
        "action": "query", "titles": title, "prop": "pageimages",
        "piprop": "original|name", "format": "json", "redirects": 1,
    }, headers=UA, timeout=30).json()
    for _, p in r.get("query", {}).get("pages", {}).items():
        name = p.get("pageimage")
        if name:
            return name, p.get("original", {}).get("source")
    return None, None


def license_info(filename: str):
    # iiurlwidth makes Commons rasterize the file to a PNG/JPG thumbnail of that width —
    # essential for SVGs (flags/crests), which the raster-only render pipeline can't use.
    r = requests.get(COMMONS, params={
        "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "extmetadata|url", "iiurlwidth": 1280, "format": "json",
    }, headers=UA, timeout=30).json()
    for _, p in r.get("query", {}).get("pages", {}).items():
        ii = p.get("imageinfo")
        if not ii:
            continue
        md = ii[0].get("extmetadata", {})
        getv = lambda k: (md.get(k, {}) or {}).get("value", "")
        return {
            "url": ii[0].get("url"),
            "thumburl": ii[0].get("thumburl"),   # rasterized PNG/JPG (set when iiurlwidth given)
            "license": getv("LicenseShortName"),
            "license_url": getv("LicenseUrl"),
            "artist": strip_html(getv("Artist")),
        }
    return None


def is_free(lic: str) -> bool:
    l = (lic or "").lower()
    return any(k in l for k in FREE_MARKERS)


def main() -> None:
    today = str(date.today())
    slugs = sys.argv[1:]
    files = ([Path(f"kb/entities/{s}.json") for s in slugs]
             if slugs else sorted(Path("kb/entities").glob("*.json")))
    got = 0
    for f in files:
        if not f.exists():
            print(f"  ✗ {f.name}: not found"); continue
        e = json.loads(f.read_text())
        # When slugs are passed explicitly (e.g. by the auto-fetch step), fetch regardless of
        # type. Otherwise (fetch-all) restrict to depictable types and skip clubs (crests).
        if not slugs and e.get("type") not in ("player", "stadium", "nation"):
            continue
        name = e["name"]
        try:
            fn, orig = lead_image(name)
            if not fn:
                print(f"  · {name}: no Wikipedia lead image"); continue
            info = license_info(fn)
            if not info:
                print(f"  · {name}: no Commons imageinfo"); continue
            if not is_free(info["license"]):
                print(f"  ⚠ {name}: lead image NOT free ({info['license'] or '?'}) — skipped"); continue
            # Prefer a rasterized thumbnail when the source is an SVG (flags/crests) —
            # the render pipeline validates raster magic bytes and rejects raw SVG/XML.
            url = info["url"] or orig
            if (url or "").lower().endswith(".svg") and info.get("thumburl"):
                url = info["thumburl"]
            e["image"] = {
                "url": url,
                "license": info["license"],
                "license_url": info["license_url"],
                "attribution": f"{info['artist'] or 'Unknown'} / {info['license']} via Wikimedia Commons",
                "as_of": today,
            }
            e.pop("image_todo", None)
            f.write_text(json.dumps(e, indent=2) + "\n")
            print(f"  ✓ {name}: {info['license']} — {(info['artist'] or '')[:46]}")
            got += 1
        except Exception as ex:
            print(f"  ✗ {name}: {str(ex).splitlines()[0][:60]}")
        time.sleep(0.3)
    print(f"\n{got} free portraits written to the KB.")


if __name__ == "__main__":
    main()
