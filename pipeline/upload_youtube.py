# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth-oauthlib", "google-api-python-client", "google-auth", "python-dotenv", "python-dateutil", "tzdata"]
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

SCHEDULING (publish later — YouTube keeps the video private until the chosen time, then
flips it public on its own). Times are FRIENDLY and default to US Eastern (the channel's
timezone) — no UTC math needed:
  uv run pipeline/upload_youtube.py schedule out/specs/<stem>.json out/published/<stem>.mp4 "tomorrow 9am"
  uv run pipeline/upload_youtube.py schedule out/specs/<stem>.json out/published/<stem>.mp4 "in 3 hours"
  uv run pipeline/upload_youtube.py schedule out/specs/<stem>.json out/published/<stem>.mp4 "jun 22 6pm et"
  # (`upload ... --publish-at "tomorrow 9am"` accepts the same friendly strings.)

MANAGE the schedule queue (no YouTube Studio needed):
  uv run pipeline/upload_youtube.py scheduled                 # list what's queued, in ET
  uv run pipeline/upload_youtube.py reschedule <stem|id> "tonight 8pm"
  uv run pipeline/upload_youtube.py cancel <stem|id>          # unschedule (stays private)
  uv run pipeline/upload_youtube.py cancel <stem|id> --now    # publish immediately instead

Env (.env, optional overrides):
  YT_OAUTH_CLIENT   path to the downloaded client JSON (default pipeline/.secrets/yt_oauth_client.json)
  YT_UPLOAD_TOKEN   path to store the upload token     (default pipeline/.secrets/yt_upload_token.json)
  TTV_SCHEDULE_TZ   default timezone for friendly times (default America/New_York)
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

# Friendly times default to the channel's timezone (the owner thinks in ET, not UTC).
DEFAULT_TZ = os.getenv("TTV_SCHEDULE_TZ", "America/New_York")
SCHEDULE_LEDGER = ROOT / "out" / "published" / "scheduled.jsonl"

# Short tz aliases the owner is likely to type, mapped to IANA zoneinfo names.
TZ_ALIASES = {
    "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York",
    "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago",
    "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver",
    "pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "utc": "UTC", "gmt": "UTC", "z": "UTC",
}


# ──────────────────────────────────────────────────────────────────────────────
# Friendly time parsing — turn what the owner types into a UTC publishAt
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_tz(name: str):
    from zoneinfo import ZoneInfo

    key = TZ_ALIASES.get(name.strip().lower(), name)
    try:
        return ZoneInfo(key)
    except Exception:
        raise ValueError(
            f"Unknown timezone '{name}'. Use an IANA name (America/New_York) "
            "or a short alias like et / ct / mt / pt / utc."
        )


def parse_when(text: str, tz: str = DEFAULT_TZ) -> str:
    """Turn a friendly time string into a UTC ISO 'YYYY-MM-DDTHH:MM:SSZ' string.

    Times are read in `tz` (default America/New_York — the channel's timezone) unless the
    text ends with a tz token (et/ct/mt/pt/utc) or already carries an ISO offset/Z.
    Accepts: 'tomorrow 9am', 'tonight', 'today 6pm', 'in 3 hours', 'in 90 minutes',
    'jun 22 6pm et', '2026-06-22 09:00', and bare ISO. Raises ValueError on past /
    unparseable / 'now' input so callers can show a clean message.
    """
    import datetime as _dt
    import re as _re

    from dateutil import parser as _dparser

    if not text or not str(text).strip():
        raise ValueError("No time given. Try 'tomorrow 9am', 'in 3 hours', or 'jun 22 6pm et'.")
    raw = str(text).strip()
    low = raw.lower()
    if low in ("now", "immediately", "asap"):
        raise ValueError("'now' means publish immediately — leave the schedule time empty to post now.")

    # A trailing tz token (… et / … utc) overrides the default zone for interpretation.
    tzname = tz
    m = _re.search(r"\b(et|est|edt|ct|cst|cdt|mt|mst|mdt|pt|pst|pdt|utc|gmt)\b\s*$", low)
    if m:
        tzname = m.group(1)
        raw = raw[: m.start()].strip() or raw
        low = low[: m.start()].strip()
    zone = _resolve_tz(tzname)
    now = _dt.datetime.now(zone)

    dt = None
    # Relative — "in 3 hours" / "in 90 minutes" / "in 2 days" / "in 1 week"
    rel = _re.match(r"^in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|h|days?|d|weeks?|w)\b", low)
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        if unit.startswith(("min", "m")) and not unit.startswith("month"):
            delta = _dt.timedelta(minutes=n)
        elif unit.startswith(("hour", "hr")) or unit == "h":
            delta = _dt.timedelta(hours=n)
        elif unit.startswith("day") or unit == "d":
            delta = _dt.timedelta(days=n)
        else:
            delta = _dt.timedelta(weeks=n)
        dt = now + delta
    else:
        # Day words with an optional time-of-day. Day-only → default 9am (the channel's slot).
        base_day, rest = None, low
        if low.startswith("tomorrow"):
            base_day, rest = (now + _dt.timedelta(days=1)).date(), low[len("tomorrow"):]
        elif low.startswith("tonight"):
            base_day, rest = now.date(), (low[len("tonight"):].strip() or "8pm")
        elif low.startswith("today"):
            base_day, rest = now.date(), low[len("today"):]
        if base_day is not None:
            timepart = rest.strip().lstrip("at").strip() or "9am"
            anchor = _dt.datetime(base_day.year, base_day.month, base_day.day, 9, 0)
            try:
                t = _dparser.parse(timepart, default=anchor)
            except (ValueError, OverflowError):
                raise ValueError(f"Couldn't read the time '{rest.strip()}' in '{raw}'.")
            dt = t.replace(year=base_day.year, month=base_day.month, day=base_day.day)
        else:
            try:
                probe = _dparser.parse(raw, default=now.replace(tzinfo=None))
            except (ValueError, OverflowError):
                raise ValueError(
                    f"Couldn't understand '{raw}'. Try 'tomorrow 9am', 'in 3 hours', "
                    "'jun 22 6pm et', or an ISO time like 2026-06-22T13:00:00Z."
                )
            if probe.tzinfo is not None:
                dt = probe  # explicit ISO offset / Z — honor it verbatim
            else:
                # Parse against two different anchors; any field that comes out the same was
                # actually present in the string. Fields the user omitted get clean defaults
                # (date → today, time → the channel's 9am slot) instead of leaking 'now'.
                a1 = _dparser.parse(raw, default=_dt.datetime(1999, 1, 3, 1, 1, 1))
                a2 = _dparser.parse(raw, default=_dt.datetime(2008, 7, 27, 13, 47, 43))
                year = a1.year if a1.year == a2.year else now.year
                month = a1.month if a1.month == a2.month else now.month
                day = a1.day if a1.day == a2.day else now.day
                if a1.hour == a2.hour:  # an explicit time was given
                    hour = a1.hour
                    minute = a1.minute if a1.minute == a2.minute else 0
                    second = a1.second if a1.second == a2.second else 0
                else:  # date only → 9am ET slot
                    hour, minute, second = 9, 0, 0
                dt = _dt.datetime(year, month, day, hour, minute, second)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zone)
    dt_utc = dt.astimezone(_dt.timezone.utc)
    if dt_utc <= _dt.datetime.now(_dt.timezone.utc):
        raise ValueError(
            f"That time is in the past ({dt.astimezone(zone):%Y-%m-%d %H:%M %Z}). Pick a future time."
        )
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt_local(iso_z: str, tz: str = DEFAULT_TZ) -> str:
    """Render a UTC '…Z' timestamp as a human line in the channel timezone."""
    import datetime as _dt

    zone = _resolve_tz(tz)
    when = _dt.datetime.fromisoformat(iso_z.replace("Z", "+00:00")).astimezone(zone)
    return when.strftime("%a %b %d, %-I:%M %p %Z")


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


def _service():
    """Build an authorized YouTube Data API client (shared by upload + schedule mgmt)."""
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=_creds(), cache_discovery=False)


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


# ──────────────────────────────────────────────────────────────────────────────
# Schedule ledger — local record of what we've queued, so list/cancel/reschedule
# have a video-id set to reconcile against YouTube (YouTube stays source of truth).
# ──────────────────────────────────────────────────────────────────────────────
def _append_schedule_ledger(stem: str, vid: str, url: str, publish_at: str) -> None:
    import datetime as _dt

    SCHEDULE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "stem": stem,
        "video_id": vid,
        "url": url,
        "publish_at": publish_at,
        "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with SCHEDULE_LEDGER.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        print(f"(note) could not append to schedule ledger: {e}")


def _read_ledger() -> list[dict]:
    if not SCHEDULE_LEDGER.exists():
        return []
    rows = []
    for line in SCHEDULE_LEDGER.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def _rewrite_ledger(rows: list[dict]) -> None:
    SCHEDULE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULE_LEDGER.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _resolve_video_id(target: str) -> str:
    """Map a stem (latest scheduled row) or a raw video id to a video id."""
    rows = _read_ledger()
    if any(r.get("video_id") == target for r in rows):
        return target
    matches = [r for r in rows if r.get("stem") == target]
    if matches:
        return matches[-1]["video_id"]
    return target  # assume the caller passed a raw video id not in the ledger


def cmd_upload(spec_path: Path, video_path: Path, visibility: str,
               publish_at: str | None = None) -> None:
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

    youtube = _service()
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
        print(f"Scheduled to go public at {_fmt_local(publish_at)} (video is private until then).")
        _append_schedule_ledger(spec_path.stem, vid, url, publish_at)
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


def cmd_scheduled(as_json: bool = False) -> None:
    """List videos that are currently scheduled (private + a future publishAt).

    Reads the local ledger for candidate ids, confirms live state against YouTube, prunes
    rows that have already gone public/been deleted, and prints them in channel-local time.
    """
    rows = _read_ledger()
    latest: dict[str, dict] = {}
    for r in rows:
        vid = r.get("video_id")
        if vid:
            latest[vid] = r  # last row wins (reschedules append)

    items: list[dict] = []
    ids = list(latest.keys())
    if ids:
        yt = _service()
        for i in range(0, len(ids), 50):  # videos.list caps at 50 ids
            resp = yt.videos().list(part="snippet,status", id=",".join(ids[i:i + 50])).execute()
            for v in resp.get("items", []):
                st = v.get("status", {})
                if st.get("privacyStatus") == "private" and st.get("publishAt"):
                    items.append({
                        "video_id": v["id"],
                        "title": v["snippet"]["title"],
                        "publish_at": st["publishAt"],
                        "stem": latest.get(v["id"], {}).get("stem", ""),
                    })

    live = {it["video_id"] for it in items}
    _rewrite_ledger([r for r in rows if r.get("video_id") in live])  # prune stale rows
    items.sort(key=lambda x: x["publish_at"])

    if as_json:
        print(json.dumps(items))
        return
    if not items:
        print("No videos are currently scheduled.")
        return
    print(f"{len(items)} scheduled (times in {DEFAULT_TZ}):")
    for it in items:
        print(f"  • {it['title'][:64]}")
        print(f"      publishes {_fmt_local(it['publish_at'])}   [{it['stem'] or it['video_id']}]")


def cmd_cancel(target: str, go_now: bool = False) -> None:
    """Cancel a scheduled publish. Default leaves the video private; --now publishes it."""
    vid = _resolve_video_id(target)
    yt = _service()
    items = yt.videos().list(part="status", id=vid).execute().get("items", [])
    if not items:
        sys.exit(f"Video '{vid}' not found (check the id/stem with `scheduled`).")
    status = items[0]["status"]
    status.pop("publishAt", None)  # removing publishAt unschedules it
    status["privacyStatus"] = "public" if go_now else "private"
    yt.videos().update(part="status", body={"id": vid, "status": status}).execute()
    print(f"{vid}: {'published now (public)' if go_now else 'unscheduled — now private'}.")
    _rewrite_ledger([r for r in _read_ledger() if r.get("video_id") != vid])


def cmd_reschedule(target: str, when: str, tz: str) -> None:
    """Move a scheduled video's publish time to a new (friendly) time."""
    iso = parse_when(when, tz)
    vid = _resolve_video_id(target)
    yt = _service()
    items = yt.videos().list(part="status", id=vid).execute().get("items", [])
    if not items:
        sys.exit(f"Video '{vid}' not found (check the id/stem with `scheduled`).")
    status = items[0]["status"]
    status["privacyStatus"] = "private"
    status["publishAt"] = iso
    yt.videos().update(part="status", body={"id": vid, "status": status}).execute()
    prior = [r for r in _read_ledger() if r.get("video_id") == vid]
    stem = prior[-1]["stem"] if prior else ""
    url = (prior[-1].get("url") if prior else None) or f"https://youtu.be/{vid}"
    _append_schedule_ledger(stem, vid, url, iso)
    print(f"{vid}: rescheduled to {_fmt_local(iso)}.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload a rendered MP4 straight to YouTube (Data API).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("auth", help="One-time OAuth step 1: print the consent URL")
    pf = sub.add_parser("auth-finish", help="One-time OAuth step 2: paste the redirect URL")
    pf.add_argument("response", help="The full http://localhost:8765/?code=... URL (in quotes)")

    up = sub.add_parser("upload", help="Upload an MP4 to YouTube (now, or scheduled with --publish-at)")
    up.add_argument("spec", type=Path, help="VideoSpec JSON (out/specs/<name>.json)")
    up.add_argument("video", type=Path, help="Rendered MP4")
    up.add_argument("--visibility", default="public",
                    choices=["public", "unlisted", "private"],
                    help="YouTube privacy (default public; use unlisted for first test)")
    up.add_argument("--publish-at", metavar="WHEN",
                    help='Schedule for later — a friendly time ("tomorrow 9am", "in 3 hours", '
                         '"jun 22 6pm et") or ISO 8601. Forces private until that time, then '
                         "YouTube flips it public. Default timezone is the channel's (ET).")
    up.add_argument("--tz", default=DEFAULT_TZ, metavar="ZONE",
                    help=f"Timezone for --publish-at (default {DEFAULT_TZ}; aliases et/ct/mt/pt/utc).")

    sc = sub.add_parser("schedule", help="Friendly alias: upload now but publish at a later time")
    sc.add_argument("spec", type=Path, help="VideoSpec JSON (out/specs/<name>.json)")
    sc.add_argument("video", type=Path, help="Rendered MP4")
    sc.add_argument("when", help='When to publish: "tomorrow 9am", "in 3 hours", "jun 22 6pm et", ISO')
    sc.add_argument("--tz", default=DEFAULT_TZ, metavar="ZONE",
                    help=f"Timezone for the time (default {DEFAULT_TZ}; aliases et/ct/mt/pt/utc).")

    ls = sub.add_parser("scheduled", help="List videos currently scheduled to publish")
    ls.add_argument("--json", action="store_true", help="Emit machine-readable JSON (for the dashboard)")

    cl = sub.add_parser("cancel", help="Cancel a scheduled publish (stays private, or --now to publish)")
    cl.add_argument("target", help="Video id, or the spec stem (latest scheduled)")
    cl.add_argument("--now", action="store_true", help="Publish immediately instead of just unscheduling")

    rs = sub.add_parser("reschedule", help="Move a scheduled video to a new time")
    rs.add_argument("target", help="Video id, or the spec stem (latest scheduled)")
    rs.add_argument("when", help='New time: "tonight 8pm", "in 2 hours", "jun 22 6pm et", ISO')
    rs.add_argument("--tz", default=DEFAULT_TZ, metavar="ZONE",
                    help=f"Timezone for the time (default {DEFAULT_TZ}; aliases et/ct/mt/pt/utc).")

    args = ap.parse_args()
    try:
        if args.cmd == "auth":
            do_auth()
        elif args.cmd == "auth-finish":
            do_auth_finish(args.response)
        elif args.cmd == "upload":
            publish_at = parse_when(args.publish_at, args.tz) if args.publish_at else None
            cmd_upload(args.spec, args.video, args.visibility, publish_at)
        elif args.cmd == "schedule":
            cmd_upload(args.spec, args.video, "private", parse_when(args.when, args.tz))
        elif args.cmd == "scheduled":
            cmd_scheduled(as_json=args.json)
        elif args.cmd == "cancel":
            cmd_cancel(args.target, go_now=args.now)
        elif args.cmd == "reschedule":
            cmd_reschedule(args.target, args.when, args.tz)
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
