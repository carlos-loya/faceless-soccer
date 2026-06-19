# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
Publish stage — push a rendered MP4 + caption to Postiz (self-hosted scheduler), which
fans it out to the connected channel(s): YouTube Shorts, then later TikTok / Instagram.

Postiz runs locally via docker (deploy/postiz). This script talks to its PUBLIC API:
  - POST /public/v1/upload   (multipart) -> {id, path}     # upload the video
  - GET  /public/v1/integrations          -> [{id,name,...}] # list connected channels
  - POST /public/v1/posts                  -> schedule/post now

Caption + title come from the VideoSpec JSON the brain produced (youtube_title,
youtube_description, *_caption, hashtags). NO footage is uploaded — only our rendered MP4.

Setup (one-time, in the Postiz UI at http://localhost:4007):
  1. Register, connect a YouTube channel (Settings > add channel > YouTube).
  2. Settings > Developers > Public API -> copy the API key into .env as POSTIZ_API_KEY.

Usage:
  uv run pipeline/publish.py channels
      List connected channels + their integration ids (copy the id you want).

  uv run pipeline/publish.py publish out/specs/<spec>.json out/renders/<video>.mp4 \
      --integration <integration-id> [--platform youtube] [--when now|2026-06-20T15:00:00Z]

Env (.env):  POSTIZ_API_KEY (required),  POSTIZ_URL (default http://localhost:4007)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

POSTIZ_URL = os.environ.get("POSTIZ_URL", "http://localhost:4007").rstrip("/")
API_KEY = os.environ.get("POSTIZ_API_KEY", "").strip()


def _headers(json_body: bool = False) -> dict:
    if not API_KEY:
        sys.exit(
            "POSTIZ_API_KEY is not set. Get it from the Postiz UI "
            "(Settings > Developers > Public API) and add it to .env as POSTIZ_API_KEY."
        )
    h = {"Authorization": API_KEY}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


def _api(path: str) -> str:
    # Self-hosted Postiz proxies the backend (and its public API) under /api.
    return f"{POSTIZ_URL}/api/public/v1{path}"


def cmd_channels() -> None:
    """List connected integrations/channels and their ids."""
    r = requests.get(_api("/integrations"), headers=_headers(), timeout=30)
    r.raise_for_status()
    data = r.json()
    items = data if isinstance(data, list) else data.get("integrations", data)
    if not items:
        print("No channels connected yet. Connect one in the Postiz UI at " + POSTIZ_URL)
        return
    print(f"Connected channels ({len(items)}):")
    for it in items:
        ident = it.get("id", "?")
        name = it.get("name", "?")
        platform = it.get("identifier") or it.get("provider") or it.get("platform") or "?"
        disabled = " [disabled]" if it.get("disabled") else ""
        print(f"  - {name:<24} platform={platform:<12} id={ident}{disabled}")


def _caption_for(spec: dict, platform: str) -> str:
    """Pick the best caption field for the target platform, append hashtags."""
    if platform == "youtube":
        body = spec.get("youtube_description") or spec.get("instagram_caption") or ""
    elif platform == "tiktok":
        body = spec.get("tiktok_caption") or spec.get("instagram_caption") or ""
    else:  # instagram / default
        body = spec.get("instagram_caption") or spec.get("tiktok_caption") or ""
    tags = spec.get("hashtags") or []
    tagline = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    return (body + ("\n\n" + tagline if tagline else "")).strip()


def _settings_for(spec: dict, platform: str, visibility: str = "public") -> dict:
    """Platform-specific post settings. YouTube needs a title + privacy + made-for-kids.

    A vertical 1080x1920 clip is auto-classified as a Short by YouTube — there's no
    'short' setting; `type` is the privacy status (public|private|unlisted). Tags must be
    objects ({value,label}), and selfDeclaredMadeForKids is the string "yes"/"no".
    """
    if platform == "youtube":
        tags = [t.lstrip("#") for t in (spec.get("hashtags") or [])][:15]
        return {
            "__type": "youtube",
            "title": (spec.get("youtube_title") or spec.get("topic") or "TikiTakaFootyTV")[:100],
            "type": visibility,  # public | private | unlisted
            "selfDeclaredMadeForKids": "no",
            "tags": [{"value": t, "label": t} for t in tags],
        }
    return {"__type": platform}


def cmd_publish(spec_path: Path, video_path: Path, integration_id: str,
                platform: str, when: str, visibility: str = "public") -> None:
    spec = json.loads(spec_path.read_text())
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    # 1) upload the rendered MP4
    print(f"Uploading {video_path.name} ({video_path.stat().st_size/1e6:.1f} MB) ...")
    with video_path.open("rb") as fh:
        up = requests.post(
            _api("/upload"),
            headers=_headers(),
            files={"file": (video_path.name, fh, "video/mp4")},
            timeout=600,
        )
    up.raise_for_status()
    media = up.json()
    media_ref = {"id": media["id"], "path": media["path"]}
    print(f"  uploaded -> id={media_ref['id']}")

    # 2) build the post
    content = _caption_for(spec, platform)
    post_type = "now" if when == "now" else "schedule"
    payload = {
        "type": post_type,
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": integration_id},
                "value": [{"content": content, "image": [media_ref]}],
                "settings": _settings_for(spec, platform, visibility),
            }
        ],
    }
    if post_type == "schedule":
        payload["date"] = when  # ISO 8601, e.g. 2026-06-20T15:00:00.000Z
    else:  # "now" still requires a `date` field (Postiz API) — use the current UTC time
        from datetime import datetime, timezone
        payload["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # 3) create it
    print(f"Creating {post_type} post on integration {integration_id} ({platform}) ...")
    r = requests.post(_api("/posts"), headers=_headers(json_body=True),
                      data=json.dumps(payload), timeout=120)
    if not r.ok:
        sys.exit(f"Postiz rejected the post ({r.status_code}): {r.text}")
    print("Done. Postiz response:")
    print(json.dumps(r.json(), indent=2)[:1500])
    if post_type == "now":
        print("\nPosting now — check the channel shortly (Postiz queues it via Temporal).")
    else:
        print(f"\nScheduled for {when}. Manage/preview it at {POSTIZ_URL}")

    # 4) move the render OUT of out/renders -> out/published, so published/scheduled videos
    #    are visibly separated from unpublished drafts (Postiz already holds the uploaded copy).
    try:
        import shutil
        dest_dir = Path("out/published")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / video_path.name
        if video_path.resolve() != dest.resolve():
            shutil.move(str(video_path), str(dest))
            print(f"Moved render -> {dest}")
    except Exception as e:
        print(f"(note) could not move render into out/published: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description="Publish a rendered video to Postiz.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("channels", help="List connected channels + integration ids")

    pub = sub.add_parser("publish", help="Upload an MP4 + schedule/post it")
    pub.add_argument("spec", type=Path, help="VideoSpec JSON (out/specs/<name>.json)")
    pub.add_argument("video", type=Path, help="Rendered MP4")
    pub.add_argument("--integration", required=True, help="Integration id (see `channels`)")
    pub.add_argument("--platform", default="youtube",
                     choices=["youtube", "tiktok", "instagram"])
    pub.add_argument("--when", default="now",
                     help='"now" or ISO 8601 datetime, e.g. 2026-06-20T15:00:00.000Z')
    pub.add_argument("--visibility", default="public",
                     choices=["public", "private", "unlisted"],
                     help="YouTube privacy (default public)")

    args = p.parse_args()
    if args.cmd == "channels":
        cmd_channels()
    elif args.cmd == "publish":
        cmd_publish(args.spec, args.video, args.integration, args.platform,
                    args.when, args.visibility)


if __name__ == "__main__":
    main()
