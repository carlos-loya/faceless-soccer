# /// script
# requires-python = ">=3.10"
# dependencies = ["google-auth-oauthlib", "google-api-python-client", "google-auth", "python-dotenv", "requests"]
# ///
"""
YouTube Analytics puller — the REAL diagnostic (retention curve + swipe-away), which the
public Data API key cannot give. Uses owner OAuth (scope yt-analytics.readonly).

This is read-only analytics; it never touches publishing (that's Postiz / publish.py).

ONE-TIME OWNER SETUP (only you can do the consent click):
  1. Google Cloud Console -> same project as Postiz (#821403730517):
     APIs & Services > Library > enable "YouTube Analytics API".
  2. Credentials > Create Credentials > OAuth client ID > Application type: "Desktop app"
     > name it (e.g. tikitaka-analytics) > Create > DOWNLOAD JSON.
  3. OAuth consent screen (already Production for Postiz): Data Access > Add scopes >
     add  .../auth/yt-analytics.readonly  > Save.
  4. Save the downloaded JSON to:  pipeline/.secrets/yt_oauth_client.json
  5. Authorize (two steps — no interactive prompt, works headless/WSL):
       uv run pipeline/youtube_analytics.py auth
     prints a URL -> open it, pick the channel's account, authorize (unverified app screen ->
     Advanced > continue). The browser redirects to a localhost page that won't load; copy the
     FULL address-bar URL, then:
       uv run pipeline/youtube_analytics.py auth-finish "<paste the full URL>"

THEN (no browser again — refresh token is stored):
     uv run pipeline/youtube_analytics.py retention <video-url-or-id>
     uv run pipeline/youtube_analytics.py summary  <video-url-or-id>

Env (.env, optional overrides):
  YT_OAUTH_CLIENT   path to the downloaded client JSON (default pipeline/.secrets/yt_oauth_client.json)
  YT_OAUTH_TOKEN    path to store the auth token       (default pipeline/.secrets/yt_analytics_token.json)
  YOUTUBE_API_KEY   (optional) used only to fetch the video TITLE for nicer output
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SECRETS = HERE / ".secrets"
DEFAULT_CLIENT = SECRETS / "yt_oauth_client.json"
DEFAULT_TOKEN = SECRETS / "yt_analytics_token.json"
CHANNEL_START = "2026-06-01"  # channel created 2026-06-09; safe lower bound for startDate
MATURE_DAYS = 3  # analytics lags ~2-3 days; skip videos younger than this in `collect`


def _video_id(s: str) -> str:
    """Accept a raw id, a /watch?v=, a youtu.be/, or a /shorts/ URL."""
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    sys.exit(f"Could not parse a video id from: {s!r}")


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = Path(os.getenv("YT_OAUTH_TOKEN", DEFAULT_TOKEN))
    if not token_path.exists():
        sys.exit("Not authorized yet. Run:  uv run pipeline/youtube_analytics.py auth")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


REDIRECT_URI = "http://localhost:8765/"  # desktop clients allow any loopback port
PENDING = SECRETS / "oauth_pending.json"


def _relax_env() -> None:
    # allow the http loopback redirect + tolerate Google reordering the returned scope string
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


def _client_path() -> Path:
    p = Path(os.getenv("YT_OAUTH_CLIENT", DEFAULT_CLIENT))
    if not p.exists():
        sys.exit(
            f"Missing OAuth client JSON at {p}.\n"
            "Download it from Google Cloud (Desktop app OAuth client) and save it there.\n"
            "See the setup steps at the top of this file."
        )
    return p


def do_auth() -> None:
    """Step 1: print the consent URL (no PKCE — desktop client uses its client_secret)."""
    import json as _json

    from google_auth_oauthlib.flow import Flow

    client_path = _client_path()
    SECRETS.mkdir(parents=True, exist_ok=True)
    _relax_env()

    flow = Flow.from_client_secrets_file(
        str(client_path), scopes=SCOPES, autogenerate_code_verifier=False
    )
    flow.redirect_uri = REDIRECT_URI
    auth_url, _state = flow.authorization_url(access_type="offline", prompt="consent")
    PENDING.write_text(_json.dumps({"client": str(client_path)}))

    print("\nStep 1 — open this URL, sign in with the channel's Google account, and authorize:\n")
    print(auth_url)
    print("\n  (If an 'unverified app' screen appears: Advanced > continue — it's your own app.)")
    print("\nStep 2 — the browser redirects to a localhost page that WON'T load")
    print("         (http://localhost:8765/?code=...  — 'site can't be reached'). That's expected.")
    print("         Copy the FULL address-bar URL and run this, with the URL in quotes:\n")
    print('   uv run pipeline/youtube_analytics.py auth-finish "<paste the full URL>"\n')


def do_auth_finish(resp: str) -> None:
    """Step 2: exchange the pasted redirect URL for a token, reusing the saved PKCE verifier."""
    import json as _json

    from google_auth_oauthlib.flow import Flow

    from urllib.parse import parse_qs, unquote, urlparse

    if not PENDING.exists():
        sys.exit("No pending auth. Run `auth` first to get the URL.")
    p = _json.loads(PENDING.read_text())
    _relax_env()

    # Accept the full redirect URL OR just the bare code. Exchange the code directly
    # (no authorization_response state-string matching — robust to shell-splitting/copy issues).
    resp = resp.strip()
    code = (parse_qs(urlparse(resp).query).get("code") or [None])[0] if "code=" in resp else resp
    if not code:
        sys.exit("Could not find an auth code in that input.")
    code = unquote(code)

    flow = Flow.from_client_secrets_file(
        p["client"], scopes=SCOPES, autogenerate_code_verifier=False,
    )
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)

    token_path = Path(os.getenv("YT_OAUTH_TOKEN", DEFAULT_TOKEN))
    token_path.write_text(flow.credentials.to_json())
    PENDING.unlink(missing_ok=True)
    print(f"Authorized.  Token saved to {token_path}")
    print("Now try:  uv run pipeline/youtube_analytics.py retention <video-url>")


def _analytics():
    from googleapiclient.discovery import build

    return build("youtubeAnalytics", "v2", credentials=_creds(), cache_discovery=False)


def _title(vid: str) -> str:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return vid
    import requests

    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "id": vid, "key": key},
            timeout=10,
        ).json()
        return r["items"][0]["snippet"]["title"]
    except Exception:
        return vid


def _iso_dur_to_s(iso: str) -> int | None:
    """Parse an ISO-8601 duration like 'PT1M34S' / 'PT45S' to whole seconds."""
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)


def _public_stats(vids: list[str]) -> dict[str, dict]:
    """Near-real-time public stats via the Data API (NO 2-3 day lag, unlike Analytics).

    Returns {video_id: {views, likes, comments, published_at, duration_s, title}} for the
    given ids. Empty dict if no YOUTUBE_API_KEY. Counts are ints; likeCount can be hidden.
    """
    key = os.getenv("YOUTUBE_API_KEY")
    if not key or not vids:
        return {}
    import requests

    out: dict[str, dict] = {}
    for i in range(0, len(vids), 50):  # Data API caps id list at 50
        chunk = vids[i : i + 50]
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet,statistics,contentDetails",
                        "id": ",".join(chunk), "key": key},
                timeout=20,
            ).json()
        except Exception:
            continue
        for v in r.get("items", []):
            st, sn = v.get("statistics", {}), v.get("snippet", {})
            out[v["id"]] = {
                "views": int(st["viewCount"]) if "viewCount" in st else None,
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "comments": int(st["commentCount"]) if "commentCount" in st else None,
                "published_at": sn.get("publishedAt"),
                "duration_s": _iso_dur_to_s(v.get("contentDetails", {}).get("duration", "")),
                "title": sn.get("title"),
            }
    return out


def summary_data(vid: str) -> dict | None:
    """Return {metric: value} for a video, or None if analytics has no data yet."""
    vid = _video_id(vid)
    today = date.today().isoformat()
    metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained"
    resp = (
        _analytics()
        .reports()
        .query(
            ids="channel==MINE",
            startDate=CHANNEL_START,
            endDate=today,
            metrics=metrics,
            filters=f"video=={vid}",
        )
        .execute()
    )
    rows = resp.get("rows")
    if not rows:
        return None
    cols = [h["name"] for h in resp["columnHeaders"]]
    return dict(zip(cols, rows[0]))


def summary(vid: str) -> None:
    data = summary_data(vid)
    print(f"\n=== SUMMARY — {_title(_video_id(vid))} ({_video_id(vid)}) ===")
    if data is None:
        print("No data yet (analytics can take up to ~2 days to process for a new video).")
        return
    for name, val in data.items():
        print(f"  {name:24}: {val}")


def _watch_at(curve: list, ratio: float) -> float | None:
    """audienceWatchRatio at the curve point nearest a given elapsedVideoTimeRatio."""
    if not curve:
        return None
    best = min(curve, key=lambda p: abs(p[0] - ratio))
    return best[1]


def retention_data(vid: str) -> dict | None:
    """Return the retention curve + derived stats for a video, or None if no data yet.

    IMPORTANT — metric semantics: `audienceWatchRatio` is normalized so it CAN exceed
    1.0 (a segment watched more than once via replays/loops). So the raw first-point
    value is NOT "the % who survived the hook", and `1 - start` is NOT swipe-away — that
    was a bug. We instead report curve values RELATIVE TO THE OPENING audience (anchored
    at 1.0 at t=0), which is bounded and honest, plus `relativeRetentionPerformance`
    (how this video holds vs comparable YouTube videos). The clean ABSOLUTE retention
    headline is `averageViewPercentage` from summary_data(), surfaced in the record.

    Shape: {curve: [[t, watch_ratio, rel_perf], ...],   # raw
            retained_to_end,           # opening-audience fraction still watching at the end
            early_leak,                # opening-audience fraction lost by ~15% elapsed (hook/early-body)
            biggest_leak: {at_ratio, drop_frac},   # steepest single drop, as fraction of opening
            mean_relative_performance} # avg rel-to-comparable-videos, or None
    """
    vid = _video_id(vid)
    today = date.today().isoformat()
    resp = (
        _analytics()
        .reports()
        .query(
            ids="channel==MINE",
            startDate=CHANNEL_START,
            endDate=today,
            dimensions="elapsedVideoTimeRatio",
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            filters=f"video=={vid}",
            sort="elapsedVideoTimeRatio",
        )
        .execute()
    )
    rows = resp.get("rows")
    if not rows:
        return None
    # rows: [elapsedVideoTimeRatio, audienceWatchRatio, relativeRetentionPerformance]
    curve = [
        [float(r[0]), float(r[1]), (float(r[2]) if r[2] is not None else None)]
        for r in rows
    ]
    opening = curve[0][1] or 1.0  # anchor: audience at the very start
    # steepest single drop, expressed as a fraction of the opening audience
    worst_drop, worst_at = 0.0, None
    for (t0, w0, _), (t1, w1, _) in zip(curve, curve[1:]):
        d = w0 - w1
        if d > worst_drop:
            worst_drop, worst_at = d, t1
    rels = [r for _, _, r in curve if r is not None]
    early = _watch_at(curve, 0.15)
    return {
        "curve": curve,
        "retained_to_end": (curve[-1][1] / opening) if opening else None,
        "early_leak": (1.0 - early / opening) if (early is not None and opening) else None,
        "biggest_leak": {
            "at_ratio": worst_at,
            "drop_frac": (worst_drop / opening) if opening else None,
        },
        "mean_relative_performance": (sum(rels) / len(rels)) if rels else None,
    }


def retention(vid: str) -> None:
    vid = _video_id(vid)
    data = retention_data(vid)
    print(f"\n=== AUDIENCE RETENTION — {_title(vid)} ({vid}) ===")
    if data is None:
        print("No retention data yet (processing can take up to ~2 days after publish).")
        return
    pts = [(t, w) for t, w, _ in data["curve"]]
    # All figures are RELATIVE TO THE OPENING audience (the raw watch ratio can exceed
    # 100% on loops, so we don't report a misleading absolute "hook survival" number).
    if data["early_leak"] is not None:
        print(f"  early leak (→15%): {data['early_leak']*100:5.1f}%  of the opening audience (hook/early body)")
    if data["retained_to_end"] is not None:
        print(f"  retained to end  : {data['retained_to_end']*100:5.1f}%  of the opening audience")
    leak = data["biggest_leak"]
    if leak["at_ratio"] is not None and leak["drop_frac"] is not None:
        print(f"  biggest leak     : -{leak['drop_frac']*100:4.1f}% around {leak['at_ratio']*100:.0f}% through the video")
    mrp = data["mean_relative_performance"]
    if mrp is not None:
        print(f"  vs similar videos: {mrp*100:5.1f}%  (relativeRetentionPerformance; >100% = better than comparable)")
    # compact sparkline (sample ~40 of the points)
    blocks = "▁▂▃▄▅▆▇█"
    step = max(1, len(pts) // 40)
    sampled = pts[::step]
    mx = max(w for _, w in sampled) or 1.0
    line = "".join(blocks[min(len(blocks) - 1, int(w / mx * (len(blocks) - 1)))] for _, w in sampled)
    print(f"  curve (0→100%)   : {line}")
    print(f"  ({len(pts)} data points; raw watch ratio >100% = a segment was re-watched/looped)")


# ──────────────────────────────────────────────────────────────────────────────
# collect — join published-video analytics with each spec's design levers into a
# machine-readable performance store the `analytics-review` skill interprets.
# ──────────────────────────────────────────────────────────────────────────────
POST_LOG = ROOT / "out" / "published" / "post-log.jsonl"
SPECS_DIR = ROOT / "out" / "specs"
PERF_STORE = ROOT / "analytics" / "performance.jsonl"


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO/RFC3339 timestamp (post-log 'Z' form or Data API publishedAt) as UTC-aware."""
    s = ts.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _read_post_log() -> list[dict]:
    """Return YouTube post-log rows, each augmented with a resolved `video_id`.

    New rows carry `video_id` explicitly; legacy rows only have the id inside
    `url_or_note` (https://youtu.be/<id>) — recover it with the shared parser.
    Deduped by video_id, latest row wins (so a re-upload supersedes).
    """
    if not POST_LOG.exists():
        return []
    by_id: dict[str, dict] = {}
    for line in POST_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("platform") != "youtube" or row.get("status") != "posted":
            continue
        vid = row.get("video_id")
        if not vid:
            try:
                vid = _video_id(row.get("url_or_note", ""))
            except SystemExit:
                continue  # no parseable id in this legacy row
        row["video_id"] = vid
        by_id[vid] = row  # latest line for this id wins
    return list(by_id.values())


def _load_spec(stem: str) -> dict | None:
    p = SPECS_DIR / f"{stem}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def map_ratio_to_scene(spec: dict, ratio: float | None) -> dict:
    """Map an elapsedVideoTimeRatio (0..1) to the scene playing at that moment.

    Denominator is the sum of scene durations (the rendered length the VO drives),
    which tracks the real video better than target_duration_seconds.
    """
    if ratio is None:
        return {}
    scenes = spec.get("scenes", []) or []
    if not scenes:
        return {}
    total = sum(float(s.get("duration_seconds", 0) or 0) for s in scenes) or 1.0
    t_seconds = ratio * total
    cum = 0.0
    for s in scenes:
        d = float(s.get("duration_seconds", 0) or 0)
        if t_seconds < cum + d or s is scenes[-1]:
            return {
                "scene_index": s.get("index"),
                "graphic_type": s.get("graphic_type"),
                "on_screen_text": s.get("on_screen_text"),
                "scene_start_s": round(cum, 1),
                "scene_end_s": round(cum + d, 1),
                "elapsed_s": round(t_seconds, 1),
            }
        cum += d
    return {}


def _design_from_spec(spec: dict) -> dict:
    """Extract the controllable design levers from a spec, with cumulative scene timings."""
    scenes_in = spec.get("scenes", []) or []
    scenes, cum = [], 0.0
    for s in scenes_in:
        d = float(s.get("duration_seconds", 0) or 0)
        scenes.append({
            "index": s.get("index"),
            "graphic_type": s.get("graphic_type"),
            "duration_seconds": d,
            "start_s": round(cum, 1),
            "end_s": round(cum + d, 1),
            "on_screen_text": s.get("on_screen_text"),
        })
        cum += d
    hook = spec.get("hook", {}) or {}
    blob = " ".join(
        (s.get("on_screen_text", "") + " " + s.get("voiceover", "")) for s in scenes_in
    ).lower()
    # Subscribe approach, so the loop can A/B it: "chip_climax" = the new small overlay on the
    # climax beat (subscribe_chip flag, 2026-06-21); "final_beat" = the old dedicated end ask;
    # "none" = no subscribe ask present.
    has_chip = any(s.get("subscribe_chip") for s in scenes_in)
    subscribe_style = "chip_climax" if has_chip else ("final_beat" if "subscribe" in blob else "none")
    return {
        "format": spec.get("format"),
        "hook_type": hook.get("hook_type"),
        "first_frame_text": hook.get("first_frame_text"),
        "spoken_hook": hook.get("spoken_hook"),
        "retention_mechanic": spec.get("retention_mechanic"),
        "subject": spec.get("subject"),
        "matchup": spec.get("matchup", []),
        "target_duration_seconds": spec.get("target_duration_seconds"),
        "rendered_duration_seconds": round(cum, 1),
        "num_scenes": len(scenes),
        "scenes": scenes,
        "comment_bait": spec.get("comment_bait"),
        "has_subscribe_scene": "subscribe" in blob,
        "subscribe_style": subscribe_style,
    }


def _build_record(post: dict, spec: dict, public: dict | None, summ: dict | None,
                  ret: dict | None, now: datetime) -> dict:
    design = _design_from_spec(spec)
    public = public or {}
    # Views/likes/comments come from the Data API (no lag, authoritative); subscribersGained,
    # averageViewPercentage and shares are Analytics-only (lag ~2-3 days, may be absent).
    views = float(public.get("views") or (summ or {}).get("views") or 0)
    likes = public.get("likes")
    comments = public.get("comments") if public.get("comments") is not None else (summ or {}).get("comments")
    subs_gained = (summ or {}).get("subscribersGained")
    attribution = {
        "hook_scene": map_ratio_to_scene(spec, 0.0),
        "biggest_leak_scene": {},
        "like_rate": (likes / views) if (views and likes is not None) else None,
        "comment_conversion": (comments / views) if (views and comments is not None) else None,
        "subscribe_conversion": (subs_gained / views) if (views and subs_gained is not None) else None,
    }
    retention = None
    if ret is not None:
        retention = {
            # Clean ABSOLUTE headline (Analytics): % of the video the average viewer watched.
            "avg_view_pct": (summ or {}).get("averageViewPercentage"),
            # The rest are RELATIVE TO THE OPENING audience (watch ratio can exceed 1.0 on loops).
            "retained_to_end": ret["retained_to_end"],
            "early_leak": ret["early_leak"],
            "biggest_leak": ret["biggest_leak"],
            "mean_relative_performance": ret["mean_relative_performance"],
            "curve": ret["curve"],
        }
        attribution["biggest_leak_scene"] = map_ratio_to_scene(spec, ret["biggest_leak"]["at_ratio"])
    published_ts = public.get("published_at") or post.get("ts")
    age = (now - _parse_ts(published_ts)).days if published_ts else None
    return {
        "video_id": post["video_id"],
        "stem": post.get("stem"),
        "url": post.get("url_or_note"),
        "title": public.get("title"),
        "published_ts": published_ts,
        "collected_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "age_days_at_collection": age,
        "analytics_ready": ret is not None,  # retention is the true "processed" signal
        "design": design,
        "public_metrics": {  # Data API — near-real-time
            "views": public.get("views"),
            "likes": likes,
            "comments": comments,
            "duration_s": public.get("duration_s"),
        },
        "analytics_metrics": summ,  # Analytics API — None until matured (~2-3d)
        "retention": retention,
        "attribution": attribution,
    }


def _write_performance_store(new_records: dict[str, dict]) -> None:
    """Merge new records into analytics/performance.jsonl (latest-wins by video_id)."""
    PERF_STORE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if PERF_STORE.exists():
        for line in PERF_STORE.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[rec.get("video_id")] = rec
    existing.update(new_records)
    ordered = sorted(existing.values(), key=lambda r: r.get("published_ts") or "")
    PERF_STORE.write_text("".join(json.dumps(r) + "\n" for r in ordered))


def collect(only_stem: str | None = None, min_age_days: int = MATURE_DAYS) -> None:
    """Refresh analytics/performance.jsonl for every published YouTube video.

    Public stats (views/likes/comments — Data API, NO lag) are recorded for ALL videos
    immediately; retention + subscribersGained + averageViewPercentage (Analytics API)
    fill in once a video matures (~2-3 days). So the store always reflects the whole
    channel, with retention arriving as it processes.
    """
    now = datetime.now(timezone.utc)
    posts = _read_post_log()
    if only_stem:
        posts = [p for p in posts if p.get("stem") == only_stem]
    if not posts:
        print(f"No matching YouTube rows in {POST_LOG.relative_to(ROOT)} — nothing to collect.")
        return
    public = _public_stats([p["video_id"] for p in posts])  # one batched Data API call
    records: dict[str, dict] = {}
    skipped_nospec = 0
    for p in posts:
        vid = p["video_id"]
        spec = _load_spec(p.get("stem", ""))
        if spec is None:
            print(f"  (skip) no spec for stem={p.get('stem')!r}")
            skipped_nospec += 1
            continue
        pub = public.get(vid, {})
        ts = pub.get("published_at") or p.get("ts")
        age = (now - _parse_ts(ts)).days if ts else 0
        # Always attempt the Analytics API — it's cheap and the lag is uneven (some videos
        # have retention at ~2d, others not), so a fixed age gate wrongly skips real data.
        # It returns None when a video genuinely hasn't processed yet. Public stats are
        # always recorded regardless. (min_age_days kept for callers but no longer gates.)
        summ = summary_data(vid)
        ret = retention_data(vid)
        rec = _build_record(p, spec, pub, summ, ret, now)
        records[vid] = rec
        v = (rec["public_metrics"].get("views"))
        if rec["retention"]:
            leak = rec["attribution"].get("biggest_leak_scene") or {}
            avp = rec["retention"].get("avg_view_pct")
            note = f"avgView={avp}%  leak@scene {leak.get('scene_index')} ({leak.get('graphic_type')})"
        else:
            note = f"retention pending (age {age}d)"
        print(f"  ok  {p.get('stem'):32}  views={v}  {note}")
    if records:
        _write_performance_store(records)
        print(f"\nWrote {len(records)} record(s) -> {PERF_STORE.relative_to(ROOT)}")
    else:
        print("\nNo records written.")
    if skipped_nospec:
        print(f"Skipped {skipped_nospec} missing-spec.")


# ──────────────────────────────────────────────────────────────────────────────
# inventory — discover the WHOLE channel via the Data API (catches videos not in the
# post-log, e.g. published before upload-logging existed) and optionally backfill them.
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_uploads(handle: str) -> list[str]:
    """Resolve a channel @handle to its full list of upload video ids (Data API)."""
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        sys.exit("inventory needs YOUTUBE_API_KEY in .env (Data API).")
    import requests

    base = "https://www.googleapis.com/youtube/v3"
    ch = requests.get(f"{base}/channels", params={
        "part": "contentDetails", "forHandle": handle.lstrip("@"), "key": key}, timeout=20).json()
    items = ch.get("items")
    if not items:
        sys.exit(f"Could not resolve channel @{handle}: {ch}")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, tok = [], ""
    while True:
        pl = requests.get(f"{base}/playlistItems", params={
            "part": "contentDetails", "playlistId": uploads, "maxResults": 50,
            "pageToken": tok, "key": key}, timeout=20).json()
        vids += [it["contentDetails"]["videoId"] for it in pl.get("items", [])]
        tok = pl.get("nextPageToken")
        if not tok:
            break
    return vids


def _norm_tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _match_spec_by_title(title: str) -> tuple[str | None, float]:
    """Best-matching spec stem for a YouTube title, by token overlap with its youtube_title."""
    tt = _norm_tokens(title)
    if not tt:
        return None, 0.0
    best, best_score = None, 0.0
    for sp in sorted(SPECS_DIR.glob("*.json")):
        try:
            spec = json.loads(sp.read_text())
        except Exception:
            continue
        cand = _norm_tokens(spec.get("youtube_title", "") + " " + spec.get("topic", ""))
        if not cand:
            continue
        score = len(tt & cand) / len(tt | cand)  # Jaccard
        if score > best_score:
            best, best_score = sp.stem, score
    return best, best_score


def inventory(backfill: bool = False, handle: str | None = None) -> None:
    """List every channel video with near-real-time public stats; flag any not in the
    post-log. With --backfill, append matched (by title) rows so `collect` picks them up."""
    handle = handle or os.getenv("YT_CHANNEL_HANDLE", "tikitakafootytv")
    vids = _resolve_uploads(handle)
    stats = _public_stats(vids)
    logged = {p["video_id"] for p in _read_post_log()}
    print(f"\n=== CHANNEL INVENTORY — @{handle} ({len(vids)} uploads) ===")
    appended = 0
    for vid in sorted(vids, key=lambda v: (stats.get(v, {}).get("published_at") or ""), reverse=True):
        s = stats.get(vid, {})
        tag = "logged" if vid in logged else "UNLOGGED"
        print(f"  {vid}  {(s.get('published_at') or '')[:10]}  "
              f"views={s.get('views')}  likes={s.get('likes')}  comments={s.get('comments')}  "
              f"[{tag}]  {(s.get('title') or '')[:54]}")
        if backfill and vid not in logged:
            stem, score = _match_spec_by_title(s.get("title", ""))
            if stem and score >= 0.4:
                rec = {"stem": stem, "platform": "youtube", "status": "posted",
                       "url_or_note": f"https://youtu.be/{vid}", "video_id": vid,
                       "ts": s.get("published_at") or "", "note": "backfilled via Data API inventory"}
                with POST_LOG.open("a") as f:
                    f.write(json.dumps(rec) + "\n")
                appended += 1
                print(f"        -> backfilled to post-log as stem={stem!r} (title match {score:.0%})")
            else:
                print(f"        -> NO confident spec match (best {stem!r} {score:.0%}); skipped")
    if backfill:
        print(f"\nBackfilled {appended} row(s) into {POST_LOG.relative_to(ROOT)}.")
    elif any(v not in logged for v in vids):
        print("\nSome videos are UNLOGGED — run `inventory --backfill` to add them, then `collect`.")


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="YouTube Analytics puller (retention/summary)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="One-time OAuth step 1: print the consent URL")
    pf = sub.add_parser("auth-finish", help="One-time OAuth step 2: paste the redirect URL")
    pf.add_argument("response", help="The full http://localhost:8765/?code=... URL (in quotes)")
    for name in ("retention", "summary"):
        p = sub.add_parser(name, help=f"{name} for a video")
        p.add_argument("video", help="YouTube video URL or 11-char id")
    pc = sub.add_parser("collect", help="Refresh analytics/performance.jsonl for all published videos")
    pc.add_argument("--stem", default=None, help="Only collect this spec stem")
    pc.add_argument("--min-age-days", type=int, default=MATURE_DAYS,
                    help=f"Only query the Analytics API for videos at least this old (default {MATURE_DAYS}; it lags ~2-3d)")
    pi = sub.add_parser("inventory", help="List all channel videos (Data API) + flag/backfill any not in the post-log")
    pi.add_argument("--backfill", action="store_true", help="Append matched-by-title rows to the post-log")
    pi.add_argument("--handle", default=None, help="Channel @handle (default $YT_CHANNEL_HANDLE or tikitakafootytv)")
    args = ap.parse_args()
    if args.cmd == "auth":
        do_auth()
    elif args.cmd == "auth-finish":
        do_auth_finish(args.response)
    elif args.cmd == "retention":
        retention(args.video)
    elif args.cmd == "summary":
        summary(args.video)
    elif args.cmd == "collect":
        collect(args.stem, args.min_age_days)
    elif args.cmd == "inventory":
        inventory(args.backfill, args.handle)


if __name__ == "__main__":
    main()
