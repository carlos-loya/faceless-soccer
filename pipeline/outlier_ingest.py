# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "python-dotenv"]
# ///
"""
Outlier-discovery engine — MVP ingest (the viral engine, deterministic stage).

seeds.json -> resolve channels -> pull recent uploads + stats -> per-channel median
baseline (Shorts vs long-form) -> rank outliers (views / baseline) -> print "what's hot".

Quota-aware by design (see OUTLIER-ENGINE-SPEC.md): NO search.list (100 units). Uses
channels.list + playlistItems.list + videos.list (~1 unit each). ~7 channels ≈ ~21 units
of the 10k/day budget. Persists to SQLite so later runs can track velocity.

Run:  uv run pipeline/outlier_ingest.py
Key:  YOUTUBE_API_KEY from .env
"""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

load_dotenv()
API = "https://www.googleapis.com/youtube/v3"
KEY = os.environ["YOUTUBE_API_KEY"]
DB = Path("out/outliers/outliers.db")
RECENT = 50            # uploads to pull per channel
MATURITY_DAYS = 2      # ignore videos younger than this (views unstable)
RECENT_DAYS = 45       # an outlier must be this recent to be "hot"
MIN_BUCKET = 4         # need >= this many videos to trust a baseline
OUTLIER_X = 3.0        # views >= X * channel median = outlier
_quota = {"units": 0}


def yt(endpoint: str, **params) -> dict:
    params["key"] = KEY
    _quota["units"] += 100 if endpoint == "search" else 1
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def iso_seconds(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def db_init() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
      CREATE TABLE IF NOT EXISTS channels(
        channel_id TEXT PRIMARY KEY, name TEXT, handle TEXT, subs INTEGER,
        uploads TEXT, lane TEXT, resolved_at TEXT);
      CREATE TABLE IF NOT EXISTS videos(
        video_id TEXT PRIMARY KEY, channel_id TEXT, title TEXT,
        published_at TEXT, duration_s INTEGER, is_short INTEGER);
      CREATE TABLE IF NOT EXISTS video_stats(
        video_id TEXT, captured_at TEXT, views INTEGER, likes INTEGER, comments INTEGER,
        PRIMARY KEY(video_id, captured_at));
    """)
    return c


def resolve(seed: dict) -> dict | None:
    """seeds entry -> channel record (by id, else handle). Name-only is skipped (would need search)."""
    part = "snippet,statistics,contentDetails"
    if seed.get("channel_id"):
        data = yt("channels", part=part, id=seed["channel_id"])
    elif seed.get("handle"):
        data = yt("channels", part=part, forHandle=seed["handle"].lstrip("@"))
    else:
        return None
    items = data.get("items") or []
    if not items:
        return None
    it = items[0]
    return {
        "channel_id": it["id"],
        "name": it["snippet"]["title"],
        "handle": seed.get("handle"),
        "subs": int(it["statistics"].get("subscriberCount", 0)),
        "uploads": it["contentDetails"]["relatedPlaylists"]["uploads"],
        "lane": seed.get("lane", ""),
    }


def recent_video_ids(uploads: str) -> list[str]:
    data = yt("playlistItems", part="contentDetails", playlistId=uploads, maxResults=RECENT)
    return [i["contentDetails"]["videoId"] for i in data.get("items", [])]


def video_details(ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        data = yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        for it in data.get("items", []):
            dur = iso_seconds(it["contentDetails"]["duration"])
            st = it["statistics"]
            out.append({
                "video_id": it["id"],
                "title": it["snippet"]["title"],
                "published_at": it["snippet"]["publishedAt"],
                "duration_s": dur,
                "is_short": 1 if dur <= 60 else 0,
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            })
    return out


def age_days(published_at: str, now: datetime) -> float:
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return (now - dt).total_seconds() / 86400


def resolve_by_search(name: str) -> tuple[str, str] | None:
    """One-time name -> channel_id via search.list (100 units). NOT used in routine ingest."""
    data = yt("search", part="snippet", q=name, type="channel", maxResults=1)
    items = data.get("items") or []
    if not items:
        return None
    cid = items[0]["id"]["channelId"]
    return cid, items[0]["snippet"]["title"]


def cmd_resolve() -> None:
    """Fill channel_id for name-only seeds and write seeds.json back. Run once after adding seeds."""
    path = Path("seeds.json")
    doc = json.loads(path.read_text())
    changed = 0
    print("Resolving name-only seeds (search.list, 100 units each)…")
    for s in doc["channels"]:
        if s.get("channel_id") or s.get("handle"):
            continue
        try:
            res = resolve_by_search(s["name"])
        except Exception as e:
            print(f"  ✗ {s['name']}: {str(e).splitlines()[0][:60]}"); continue
        if not res:
            print(f"  · {s['name']}: no channel match"); continue
        cid, title = res
        s["channel_id"] = cid
        flag = "" if title.lower().replace(" ", "")[:6] in s["name"].lower().replace(" ", "") \
            or s["name"].lower().replace(" ", "")[:6] in title.lower().replace(" ", "") else "  ⚠ verify"
        print(f"  ✓ {s['name']:22} -> {title[:28]:28} ({cid}){flag}")
        changed += 1
    path.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nResolved {changed}; wrote seeds.json (~{_quota['units']} units). "
          f"⚠ = name/title mismatch, eyeball it.")


def main() -> None:
    seeds = json.loads(Path("seeds.json").read_text())["channels"]
    now = datetime.now(timezone.utc)
    con = db_init()
    cur = con.cursor()

    resolved, skipped = [], []
    for s in seeds:
        try:
            ch = resolve(s)
        except Exception as e:
            skipped.append((s.get("name"), str(e).split("\n")[0][:60])); continue
        if not ch:
            skipped.append((s.get("name"), "no id/handle (needs resolution)")); continue
        cur.execute("INSERT OR REPLACE INTO channels VALUES (?,?,?,?,?,?,?)",
                    (ch["channel_id"], ch["name"], ch["handle"], ch["subs"], ch["uploads"], ch["lane"],
                     now.isoformat()))
        resolved.append(ch)

    captured = now.isoformat()
    all_vids = []  # (channel, video)
    for ch in resolved:
        try:
            vids = video_details(recent_video_ids(ch["uploads"]))
        except Exception as e:
            print(f"  ingest failed {ch['name']}: {str(e).split(chr(10))[0][:60]}"); continue
        for v in vids:
            cur.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?)",
                        (v["video_id"], ch["channel_id"], v["title"], v["published_at"],
                         v["duration_s"], v["is_short"]))
            cur.execute("INSERT OR REPLACE INTO video_stats VALUES (?,?,?,?,?)",
                        (v["video_id"], captured, v["views"], v["likes"], v["comments"]))
            all_vids.append((ch, v))
    con.commit()

    # baselines per channel per bucket (mature videos only), then score
    outliers = []
    by_ch_bucket: dict[tuple, list[int]] = {}
    for ch, v in all_vids:
        if age_days(v["published_at"], now) >= MATURITY_DAYS:
            by_ch_bucket.setdefault((ch["channel_id"], v["is_short"]), []).append(v["views"])
    for ch, v in all_vids:
        a = age_days(v["published_at"], now)
        base_list = by_ch_bucket.get((ch["channel_id"], v["is_short"]), [])
        if len(base_list) < MIN_BUCKET or a < MATURITY_DAYS:
            continue
        base = statistics.median(base_list)
        if base <= 0:
            continue
        score = v["views"] / base
        if score >= OUTLIER_X and a <= RECENT_DAYS:
            outliers.append({
                "score": score, "views": v["views"], "base": base, "age": a,
                "channel": ch["name"], "is_short": v["is_short"], "title": v["title"],
                "url": f"https://youtube.com/watch?v={v['video_id']}",
            })

    outliers.sort(key=lambda o: o["score"], reverse=True)

    print(f"\nResolved {len(resolved)} channels, ingested {len(all_vids)} videos "
          f"(~{_quota['units']} quota units used of 10,000/day)")
    if skipped:
        print(f"Skipped {len(skipped)} (need channel_id/handle in seeds.json): "
              + ", ".join(n for n, _ in skipped[:8]) + ("…" if len(skipped) > 8 else ""))
    print(f"\n=== OUTLIERS (views ≥ {OUTLIER_X}× channel median, ≤ {RECENT_DAYS}d) ===")
    if not outliers:
        print("  none yet — baselines need more history, or no recent breakouts. Re-run over days.")
    for o in outliers[:15]:
        kind = "Short" if o["is_short"] else "Long "
        print(f"  {o['score']:4.1f}×  {o['views']:>9,}v  {int(o['age']):>2}d  [{kind}] "
              f"{o['channel'][:18]:18} | {o['title'][:54]}")
        print(f"        {o['url']}")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        cmd_resolve()
    else:
        main()
