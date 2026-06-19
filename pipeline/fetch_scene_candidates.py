# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""
Per-spec image candidates for `commons` scenes — fetch several VALIDATED options per scene so
the `pick-images` skill (Claude vision) can choose the correct one. Keyword search alone returns
plausible-but-wrong images (e.g. "FIFA World Cup Trophy" -> Germany lifting it).

Run:  uv run pipeline/fetch_scene_candidates.py out/specs/<stem>.json
Out:  out/candidates/<stem>/scene<N>/cand-*.<ext>  +  out/candidates/<stem>/candidates.json
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
N = 6  # candidates per scene


def strip_html(s: str) -> str:
    return re.sub("<[^>]+>", "", s or "").strip()


def is_image(b: bytes) -> bool:
    return (b[:3] == b"\xff\xd8\xff" or b.startswith(b"\x89PNG")
            or b[:3] == b"GIF" or (b[:4] == b"RIFF" and b[8:12] == b"WEBP"))


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


def candidates_for(query: str, out_dir: Path) -> list[dict]:
    r = requests.get(COMMONS, params={
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": N * 3, "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size", "format": "json",
    }, headers=UA, timeout=60).json()
    pages = sorted(r.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out, i = [], 0
    for p in pages:
        ii = (p.get("imageinfo") or [None])[0]
        if not ii or not re.search("jpeg|png", ii.get("mime", "")):
            continue
        if ii.get("width", 0) < 600:
            continue
        lic = ((ii.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "")).lower()
        if not re.search(r"cc|public domain|cc0|pdm", lic):
            continue
        data = get_image(ii["url"])
        if not data or len(data) < 12 or not is_image(data):
            continue
        i += 1
        ext = ii["url"].split(".")[-1].split("?")[0][:4]
        fn = out_dir / f"cand-{i}.{ext}"
        fn.write_bytes(data)
        time.sleep(0.5)
        artist = strip_html((ii.get("extmetadata", {}).get("Artist", {}) or {}).get("value", ""))
        lic_name = (ii.get("extmetadata", {}).get("LicenseShortName", {}) or {}).get("value", "CC")
        out.append({
            "index": i, "file": str(fn), "title": p.get("title", ""), "url": ii["url"],
            "credit": f"{artist or 'Wikimedia'} / {lic_name} via Wikimedia Commons",
        })
        if i >= N:
            break
    return out


def main() -> None:
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text())
    base = Path("out/candidates") / spec_path.stem
    base.mkdir(parents=True, exist_ok=True)

    manifest = {}
    for sc in spec.get("scenes", []):
        if sc.get("visual_source") != "commons":
            continue
        idx, q = sc["index"], sc.get("visual_query", "")
        out_dir = base / f"scene{idx}"
        out_dir.mkdir(parents=True, exist_ok=True)
        cands = candidates_for(q, out_dir)
        manifest[str(idx)] = {
            "query": q, "on_screen_text": sc.get("on_screen_text", ""),
            "voiceover": sc.get("voiceover", ""), "candidates": cands,
        }
        print(f"  scene {idx} '{q}': {len(cands)} candidates")

    (base / "candidates.json").write_text(json.dumps(manifest, indent=2))
    print("no commons scenes — nothing to pick." if not manifest
          else f"\n-> {base}/candidates.json  (now run the pick-images skill)")


if __name__ == "__main__":
    main()
