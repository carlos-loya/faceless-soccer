# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Post-packet builder — the handoff between a finished render and the attended
`post-social` skill (Playwright browser automation for TikTok + Instagram).

Reads a VideoSpec JSON + the rendered MP4 and prints a clean per-platform JSON
"packet" so Claude doesn't have to parse the raw spec while it's driving the browser.
The captions are formatted IDENTICALLY to the old Postiz path: _caption_for below is
the same logic as publish._caption_for, inlined here so this helper stays dependency-free
(publish.py imports `requests`, which the browser path doesn't need).

Usage:
  uv run pipeline/post_packet.py out/specs/<stem>.json out/renders/<stem>.mp4

Emits (stdout, JSON):
  { "video_path": "<ABSOLUTE path the file picker needs>",
    "tiktok":    { "caption": "<tiktok_caption + #hashtags>" },
    "instagram": { "caption": "<instagram_caption + #hashtags>" },
    "comment_bait": "...", "subject": "...", "duration_seconds": 0.0 }

(YouTube is NOT here — it goes through the official API via upload_youtube.py.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _caption_for(spec: dict, platform: str) -> str:
    """Pick the best caption field for the target platform, append hashtags.

    Kept identical to publish._caption_for so TikTok/Instagram captions match whatever
    the old Postiz path produced.
    """
    if platform == "tiktok":
        body = spec.get("tiktok_caption") or spec.get("instagram_caption") or ""
    else:  # instagram / default
        body = spec.get("instagram_caption") or spec.get("tiktok_caption") or ""
    tags = spec.get("hashtags") or []
    tagline = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    return (body + ("\n\n" + tagline if tagline else "")).strip()


def build_packet(spec_path: Path, video_path: Path) -> dict:
    spec = json.loads(spec_path.read_text())
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")
    return {
        "video_path": str(video_path.resolve()),
        "tiktok": {"caption": _caption_for(spec, "tiktok")},
        "instagram": {"caption": _caption_for(spec, "instagram")},
        "comment_bait": spec.get("comment_bait", ""),
        "subject": spec.get("subject", ""),
        "duration_seconds": spec.get("target_duration_seconds", 0.0),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a per-platform post packet for TikTok/Instagram.")
    ap.add_argument("spec", type=Path, help="VideoSpec JSON (out/specs/<name>.json)")
    ap.add_argument("video", type=Path, help="Rendered MP4")
    args = ap.parse_args()
    print(json.dumps(build_packet(args.spec, args.video), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
