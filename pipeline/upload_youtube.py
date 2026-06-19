# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth-oauthlib", "google-api-python-client", "google-auth", "python-dotenv"]
# ///
"""
Direct YouTube uploader — the lightweight replacement for the Postiz YouTube path.

Pushes a rendered MP4 straight to the channel via the official YouTube Data API v3
(videos.insert). No Docker stack, no Postiz: just an OAuth refresh token in
pipeline/.secrets/. Title / description / tags come from the VideoSpec JSON the brain
produced (youtube_title, youtube_description, hashtags). A vertical 1080x1920 clip is
auto-classified by YouTube as a Short — there's no "short" flag.

This is the YOUTUBE half of the hybrid poster. TikTok + Instagram are posted via the
attended `post-social` skill (Playwright browser automation); see post_packet.py.
NO footage is uploaded — only our rendered MP4.

Why a separate token from youtube_analytics.py: that one is read-only analytics
(yt-analytics.readonly); this one needs the write scope (youtube.upload). Same OAuth
client, different scope + token file.

ONE-TIME OWNER SETUP (only you can do the consent click):
  1. Google Cloud Console -> same project as analytics/Postiz (#821403730517):
     - APIs & Services > Library > ensure "YouTube Data API v3" is ENABLED.
     - OAuth consent screen > Data Access > Add or remove scopes > add BOTH (paste into
       the "manually add scopes" box if not listed):
         .../auth/youtube.upload      (upload the MP4)
         .../auth/youtube.force-ssl   (post/reply to comments — automation)
       Update > Save.
     (The consent screen is already in Production, so the refresh token won't expire
      every 7 days the way the old Postiz Testing-mode token did.)
  2. The Desktop OAuth client JSON already exists at pipeline/.secrets/yt_oauth_client.json
     (reused from the analytics script). No new client needed.
  3. Authorize (two steps — no interactive prompt, works headless/WSL):
       uv run pipeline/upload_youtube.py auth
     prints a URL -> open it, pick the channel's account, authorize (unverified-app
     screen -> Advanced > continue). The browser redirects to a localhost page that
     won't load; copy the FULL address-bar URL, then:
       uv run pipeline/upload_youtube.py auth-finish "<paste the full URL>"

THEN (no browser again — refresh token is stored):
  uv run pipeline/upload_youtube.py upload out/specs/<stem>.json out/renders/<stem>.mp4 \
      [--visibility public|unlisted|private]

  # Tip: use --visibility unlisted for the first test so a misfire isn't public.

Env (.env, optional overrides):
  YT_OAUTH_CLIENT   path to the downloaded client JSON (default pipeline/.secrets/yt_oauth_client.json)
  YT_UPLOAD_TOKEN   path to store the upload token     (default pipeline/.secrets/yt_upload_token.json)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Write scopes for this token:
#   youtube.upload   — videos.insert (upload the rendered MP4). Minimal upload scope.
#   youtube.force-ssl — read + POST/reply/moderate comments (commentThreads.insert,
#                       comments.insert). Needed for comment automation; reading PUBLIC
#                       comments alone needs no OAuth (the YOUTUBE_API_KEY works for that).
# Both live on one token so a future comment-reply tool reuses pipeline/.secrets/yt_upload_token.json.
# Note: force-ssl is broad (it can also edit/delete videos+comments) — the token is stored
# plaintext under pipeline/.secrets/ (gitignored), so keep that dir local + private.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
HERE = Path(__file__).resolve().parent
SECRETS = HERE / ".secrets"
DEFAULT_CLIENT = SECRETS / "yt_oauth_client.json"
DEFAULT_TOKEN = SECRETS / "yt_upload_token.json"

REDIRECT_URI = "http://localhost:8765/"  # desktop clients allow any loopback port
PENDING = SECRETS / "upload_oauth_pending.json"
SPORTS_CATEGORY_ID = "17"  # YouTube "Sports" category


# ──────────────────────────────────────────────────────────────────────────────
# OAuth (cloned from youtube_analytics.py — same headless/WSL two-step flow)
# ──────────────────────────────────────────────────────────────────────────────
def _relax_env() -> None:
    # allow the http loopback redirect + tolerate Google reordering the returned scope string
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def _client_path() -> Path:
    p = Path(os.getenv("YT_OAUTH_CLIENT", DEFAULT_CLIENT))
    if not p.exists():
        sys.exit(
            f"Missing OAuth client JSON at {p}.\n"
            "Download it from Google Cloud (Desktop app OAuth client) and save it there,\n"
            "or reuse the analytics one. See the setup steps at the top of this file."
        )
    return p


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = Path(os.getenv("YT_UPLOAD_TOKEN", DEFAULT_TOKEN))
    if not token_path.exists():
        sys.exit("Not authorized yet. Run:  uv run pipeline/upload_youtube.py auth")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


def do_auth() -> None:
    """Step 1: print the consent URL (desktop client uses its client_secret, no PKCE)."""
    from google_auth_oauthlib.flow import Flow

    client_path = _client_path()
    SECRETS.mkdir(parents=True, exist_ok=True)
    _relax_env()

    flow = Flow.from_client_secrets_file(
        str(client_path), scopes=SCOPES, autogenerate_code_verifier=False
    )
    flow.redirect_uri = REDIRECT_URI
    auth_url, _state = flow.authorization_url(access_type="offline", prompt="consent")
    PENDING.write_text(json.dumps({"client": str(client_path)}))

    print("\nStep 1 — open this URL, sign in with the CHANNEL's Google account, and authorize:\n")
    print(auth_url)
    print("\n  (If an 'unverified app' screen appears: Advanced > continue — it's your own app.)")
    print("\nStep 2 — the browser redirects to a localhost page that WON'T load")
    print("         (http://localhost:8765/?code=...  — 'site can't be reached'). That's expected.")
    print("         Copy the FULL address-bar URL and run this, with the URL in quotes:\n")
    print('   uv run pipeline/upload_youtube.py auth-finish "<paste the full URL>"\n')


def do_auth_finish(resp: str) -> None:
    """Step 2: exchange the pasted redirect URL (or bare code) for a token."""
    from urllib.parse import parse_qs, unquote, urlparse

    from google_auth_oauthlib.flow import Flow

    if not PENDING.exists():
        sys.exit("No pending auth. Run `auth` first to get the URL.")
    p = json.loads(PENDING.read_text())
    _relax_env()

    resp = resp.strip()
    code = (parse_qs(urlparse(resp).query).get("code") or [None])[0] if "code=" in resp else resp
    if not code:
        sys.exit("Could not find an auth code in that input.")
    code = unquote(code)

    flow = Flow.from_client_secrets_file(
        p["client"], scopes=SCOPES, autogenerate_code_verifier=False
    )
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)

    token_path = Path(os.getenv("YT_UPLOAD_TOKEN", DEFAULT_TOKEN))
    token_path.write_text(flow.credentials.to_json())
    PENDING.unlink(missing_ok=True)
    print(f"Authorized.  Upload token saved to {token_path}")
    print("Now try:  uv run pipeline/upload_youtube.py upload out/specs/<stem>.json out/renders/<stem>.mp4")


# ──────────────────────────────────────────────────────────────────────────────
# Spec -> snippet/status (mirrors publish.py's field choices)
# ──────────────────────────────────────────────────────────────────────────────
def _description(spec: dict) -> str:
    """YouTube description = description body + hashtag tagline (same as publish._caption_for)."""
    body = spec.get("youtube_description") or spec.get("instagram_caption") or ""
    tags = spec.get("hashtags") or []
    tagline = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
    return (body + ("\n\n" + tagline if tagline else "")).strip()


def _tags(spec: dict) -> list[str]:
    return [t.lstrip("#") for t in (spec.get("hashtags") or [])][:15]


def _append_post_log(stem: str, vid: str, url: str) -> None:
    """Index the spec->video-id link so the analytics loop can find this video.

    Mirrors the post-social skill's out/published/post-log.jsonl convention and
    extends it with an explicit machine-readable `video_id` join key.
    """
    import datetime as _dt

    log = ROOT / "out" / "published" / "post-log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "stem": stem,
        "platform": "youtube",
        "status": "posted",
        "url_or_note": url,
        "video_id": vid,
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with log.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"Logged -> {log.name}  (stem={stem}, video_id={vid})")
    except Exception as e:
        print(f"(note) could not append to post-log: {e}")


def cmd_upload(spec_path: Path, video_path: Path, visibility: str,
               publish_at: str | None = None) -> None:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    import datetime as _dt

    spec = json.loads(spec_path.read_text())
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")

    title = (spec.get("youtube_title") or spec.get("topic") or "TikiTakaFootyTV")[:100]
    status_body = {
        "privacyStatus": visibility,  # public | unlisted | private
        "selfDeclaredMadeForKids": False,
        "madeForKids": False,
        "containsSyntheticMedia": True,
    }

    if publish_at:
        when = _dt.datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        if when <= _dt.datetime.now(_dt.timezone.utc):
            sys.exit(f"publish-at ({publish_at}) is in the past — cannot schedule.")
        status_body["privacyStatus"] = "private"
        status_body["publishAt"] = publish_at
        label = f"scheduled for {publish_at}"
    else:
        label = visibility

    body = {
        "snippet": {
            "title": title,
            "description": _description(spec),
            "tags": _tags(spec),
            "categoryId": SPORTS_CATEGORY_ID,
        },
        "status": status_body,
    }

    youtube = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    size_mb = video_path.stat().st_size / 1e6
    print(f"Uploading {video_path.name} ({size_mb:.1f} MB) as '{title}' [{label}] ...")
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024,
                            resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100):3d}%")
    vid = response["id"]
    url = f"https://youtu.be/{vid}"
    print(f"Done. Uploaded -> {url}  (id={vid})")
    if publish_at:
        print(f"Scheduled to go public at {publish_at} (video is private until then).")
    else:
        print("Vertical 1080x1920 auto-classifies as a Short; check the channel shortly.")
    _append_post_log(spec_path.stem, vid, url)

    # Move the render OUT of out/renders -> out/published (same convention as publish.py),
    # so published videos are visibly separated from unpublished drafts.
    try:
        dest_dir = ROOT / "out" / "published"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / video_path.name
        if video_path.resolve() != dest.resolve():
            shutil.move(str(video_path), str(dest))
            print(f"Moved render -> {dest}")
    except Exception as e:
        print(f"(note) could not move render into out/published: {e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload a rendered MP4 straight to YouTube (Data API).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="One-time OAuth step 1: print the consent URL")
    pf = sub.add_parser("auth-finish", help="One-time OAuth step 2: paste the redirect URL")
    pf.add_argument("response", help="The full http://localhost:8765/?code=... URL (in quotes)")

    up = sub.add_parser("upload", help="Upload an MP4 to YouTube")
    up.add_argument("spec", type=Path, help="VideoSpec JSON (out/specs/<name>.json)")
    up.add_argument("video", type=Path, help="Rendered MP4")
    up.add_argument("--visibility", default="public",
                    choices=["public", "unlisted", "private"],
                    help="YouTube privacy (default public; use unlisted for first test)")
    up.add_argument("--publish-at", metavar="ISO",
                    help='Schedule for future publication (ISO 8601), e.g. "2026-06-20T15:00:00Z". '
                         'Overrides visibility to private (YouTube flips to public at the given time).')

    args = ap.parse_args()
    if args.cmd == "auth":
        do_auth()
    elif args.cmd == "auth-finish":
        do_auth_finish(args.response)
    elif args.cmd == "upload":
        cmd_upload(args.spec, args.video, args.visibility, args.publish_at)


if __name__ == "__main__":
    main()
