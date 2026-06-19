# /// script
# requires-python = ">=3.10"
# dependencies = ["rembg[cpu]", "pillow", "requests"]
# ///
"""
Cutout layer — turn a KB entity photo into a transparent-PNG cutout (iPhone-sticker style).

Removes the background (rembg / U2Net) and tight-crops to the subject, so the render can
pin a real cutout of the player in the corner with a white outline + shadow — not a circle.

Run:  uv run pipeline/cutout.py lamine-yamal [more-slugs...]
Output: out/cutouts/<slug>.png  (transparent)
First run downloads the ~176MB U2Net model (cached to ~/.u2net).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image
from rembg import remove


def main() -> None:
    slugs = sys.argv[1:]
    if not slugs:
        sys.exit("usage: uv run pipeline/cutout.py <entity-slug> [...]")
    out_dir = Path("out/cutouts")
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        ent_path = Path(f"kb/entities/{slug}.json")
        if not ent_path.exists():
            print(f"  ✗ {slug}: no KB entity"); continue
        ent = json.loads(ent_path.read_text())
        url = (ent.get("image") or {}).get("url")
        if not url:
            print(f"  ✗ {slug}: no KB image"); continue
        try:
            if url.startswith(("http://", "https://")):
                data = requests.get(url, headers={"User-Agent": "TikiTakaFootyTV/1.0"}, timeout=60).content
            else:  # owner-provided LOCAL asset (e.g. assets/source/<name>.jpg)
                p = Path(url) if Path(url).is_absolute() else Path.cwd() / url
                data = p.read_bytes()
            if not (data[:3] == b"\xff\xd8\xff" or data.startswith(b"\x89PNG") or data[:4] == b"RIFF"):
                print(f"  ✗ {slug}: downloaded a non-image (HTML/error page) — skipped"); continue
            src = Image.open(io.BytesIO(data)).convert("RGBA")
            cut = remove(src)                 # background removed -> RGBA with alpha
            bbox = cut.getbbox()              # tight-crop to the subject
            if bbox:
                cut = cut.crop(bbox)
            dest = out_dir / f"{slug}.png"
            cut.save(dest)
            print(f"  ✓ {slug}: cutout {cut.size[0]}x{cut.size[1]} -> {dest}")
        except Exception as e:
            print(f"  ✗ {slug}: {str(e).splitlines()[0][:70]}")


if __name__ == "__main__":
    main()
