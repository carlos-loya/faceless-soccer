# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dotenv", "requests"]
# ///
"""
Fetch comments on the channel's videos that WE HAVEN'T REPLIED TO yet.

Read-only: uses the public Data API key (YOUTUBE_API_KEY) — no OAuth, no new scope —
because the owner replies manually. We never post anything from here.

A top-level comment counts as "unreplied" when none of its replies were authored by our
own channel. We also drop comments we authored ourselves. The Data API returns up to 5
inline replies per thread; if a busy thread has more, we page `comments.list` for it so we
don't miss an existing owner reply.

Usage:
  uv run pipeline/youtube_comments.py fetch [--video <url|id>] [--days N]
                                            [--min-likes N] [--max N] [--out PATH]
    --video     only this video (default: every video on the channel)
    --days      only comments newer than N days (default: all)
    --min-likes only comments with >= N likes (default: 0)
    --max       stop after collecting N unreplied comments (default: 200)
    --out       where to write the JSON (default: out/comments/unreplied.json)

Writes a JSON array of unreplied comments (with video context) to --out and prints a
summary. The `reply-comments` slash command reads that file and drafts replies.

Env (.env):
  YOUTUBE_API_KEY    public Data API key (required)
  YT_CHANNEL_HANDLE  channel @handle (default: tikitakafootytv)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_OUT = ROOT / "out" / "comments" / "unreplied.json"
API = "https://www.googleapis.com/youtube/v3"


def _key() -> str:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        sys.exit("Missing YOUTUBE_API_KEY in .env (read-only Data API key).")
    return key


def _video_id(s: str) -> str:
    s = s.strip()
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    sys.exit(f"Could not parse a video id from: {s!r}")


def _get(path: str, **params) -> dict:
    params["key"] = _key()
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    if r.status_code != 200:
        # surface the API's own error (e.g. commentsDisabled, quotaExceeded)
        try:
            err = r.json().get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason", "")
            sys.exit(f"Data API {path} -> {r.status_code} {reason}: {err.get('message','')}")
        except ValueError:
            r.raise_for_status()
    return r.json()


def _channel(handle: str) -> tuple[str, str]:
    """Resolve an @handle to (channel_id, title)."""
    j = _get("channels", part="snippet", forHandle=handle.lstrip("@"))
    items = j.get("items")
    if not items:
        sys.exit(f"Could not resolve channel @{handle}.")
    return items[0]["id"], items[0]["snippet"]["title"]


def _video_titles(vids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(vids), 50):
        j = _get("videos", part="snippet", id=",".join(vids[i : i + 50]))
        for it in j.get("items", []):
            out[it["id"]] = it["snippet"]["title"]
    return out


def _all_replies_have_us(parent_id: str, our_id: str) -> bool:
    """Page comments.list for a thread with >5 replies; True if we already replied."""
    tok = ""
    while True:
        j = _get("comments", part="snippet", parentId=parent_id, maxResults=100, pageToken=tok)
        for c in j.get("items", []):
            if (c["snippet"].get("authorChannelId") or {}).get("value") == our_id:
                return True
        tok = j.get("nextPageToken", "")
        if not tok:
            return False


def _replied_by_us(thread: dict, our_id: str) -> bool:
    inline = (thread.get("replies") or {}).get("comments", [])
    for c in inline:
        if (c["snippet"].get("authorChannelId") or {}).get("value") == our_id:
            return True
    total = thread["snippet"].get("totalReplyCount", 0)
    if total > len(inline):  # more replies than came back inline — check them all
        return _all_replies_have_us(thread["snippet"]["topLevelComment"]["id"], our_id)
    return False


def _threads(channel_id: str, video: str | None):
    """Yield comment threads, newest first, across the channel or one video."""
    tok = ""
    while True:
        params = dict(part="snippet,replies", maxResults=100, order="time",
                      textFormat="plainText", pageToken=tok)
        if video:
            params["videoId"] = video
        else:
            params["allThreadsRelatedToChannelId"] = channel_id
        j = _get("commentThreads", **params)
        for t in j.get("items", []):
            yield t
        tok = j.get("nextPageToken", "")
        if not tok:
            break


def fetch(video: str | None, days: int | None, min_likes: int, max_n: int, out: Path) -> None:
    handle = os.getenv("YT_CHANNEL_HANDLE", "tikitakafootytv")
    channel_id, channel_title = _channel(handle)
    print(f"Channel: {channel_title} ({channel_id})")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)) if days else None

    collected: list[dict] = []
    scanned = 0
    for t in _threads(channel_id, video):
        scanned += 1
        top = t["snippet"]["topLevelComment"]["snippet"]
        # skip our own comments and anything we've already answered
        if (top.get("authorChannelId") or {}).get("value") == channel_id:
            continue
        if _replied_by_us(t, channel_id):
            continue
        published = top.get("publishedAt", "")
        if cutoff and published:
            when = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if when < cutoff:
                # threads are time-ordered newest-first; everything after is older too
                if not video:
                    pass  # allThreads ordering is per-video, keep scanning other videos
                continue
        if int(top.get("likeCount", 0)) < min_likes:
            continue
        collected.append({
            "comment_id": t["snippet"]["topLevelComment"]["id"],
            "video_id": t["snippet"].get("videoId"),
            "author": top.get("authorDisplayName"),
            "text": top.get("textDisplay", "").strip(),
            "like_count": int(top.get("likeCount", 0)),
            "published_at": published,
            "reply_count": t["snippet"].get("totalReplyCount", 0),
        })
        if len(collected) >= max_n:
            break

    titles = _video_titles(sorted({c["video_id"] for c in collected if c["video_id"]}))
    for c in collected:
        c["video_title"] = titles.get(c["video_id"], "")
        c["video_url"] = f"https://youtu.be/{c['video_id']}" if c["video_id"] else ""
    # most-liked first, then newest — surfaces the comments worth answering
    collected.sort(key=lambda c: (c["like_count"], c["published_at"]), reverse=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collected, indent=2, ensure_ascii=False))
    print(f"Scanned {scanned} threads -> {len(collected)} unreplied comment(s).")
    print(f"Wrote {out.relative_to(ROOT)}")
    for c in collected[:15]:
        likes = f"♥{c['like_count']}" if c["like_count"] else "  "
        print(f"  {likes:>5}  {c['author'][:18]:18}  {c['text'][:60]!r}  [{c['video_title'][:30]}]")
    if len(collected) > 15:
        print(f"  … and {len(collected) - 15} more in the file.")


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Fetch unreplied YouTube comments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fetch", help="Fetch comments we haven't replied to")
    pf.add_argument("--video", default=None, help="Only this video (URL or id)")
    pf.add_argument("--days", type=int, default=None, help="Only comments newer than N days")
    pf.add_argument("--min-likes", type=int, default=0, help="Only comments with >= N likes")
    pf.add_argument("--max", type=int, default=200, help="Stop after N unreplied comments")
    pf.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    args = ap.parse_args()
    if args.cmd == "fetch":
        fetch(_video_id(args.video) if args.video else None,
              args.days, args.min_likes, args.max, Path(args.out))


if __name__ == "__main__":
    main()
