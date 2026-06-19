# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dotenv", "requests"]
# ///
"""
Fetch comments from the channel's videos — read-only, uses the public YOUTUBE_API_KEY
(no OAuth needed for reading). Lists every top-level comment and whether it already has
a reply FROM THE CHANNEL OWNER, so we can draft replies only for the un-answered ones.

Posting replies is NOT done here (that needs OAuth write scope) — output is JSON the
brain drafts replies from; the owner posts manually.

Usage:
  uv run pipeline/fetch_comments.py                 # all videos, un-replied comments -> JSON
  uv run pipeline/fetch_comments.py --all-comments  # include already-replied too
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

API = "https://www.googleapis.com/youtube/v3"
HANDLE = "tikitakafootytv"


def _key() -> str:
    k = os.getenv("YOUTUBE_API_KEY")
    if not k:
        sys.exit("YOUTUBE_API_KEY missing from .env")
    return k


def _get(path: str, **params):
    params["key"] = _key()
    r = requests.get(f"{API}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def channel_meta() -> tuple[str, str]:
    """Return (channelId, uploadsPlaylistId)."""
    d = _get("channels", part="contentDetails", forHandle=HANDLE)
    item = d["items"][0]
    return item["id"], item["contentDetails"]["relatedPlaylists"]["uploads"]


def list_videos(uploads_playlist: str) -> list[dict]:
    vids, page = [], None
    while True:
        d = _get("playlistItems", part="snippet,contentDetails",
                 playlistId=uploads_playlist, maxResults=50, pageToken=page)
        for it in d.get("items", []):
            vids.append({
                "videoId": it["contentDetails"]["videoId"],
                "title": it["snippet"]["title"],
            })
        page = d.get("nextPageToken")
        if not page:
            break
    return vids


def comment_threads(video_id: str, channel_id: str) -> list[dict]:
    """Top-level comments + whether the OWNER already replied."""
    out, page = [], None
    while True:
        try:
            d = _get("commentThreads", part="snippet,replies",
                     videoId=video_id, maxResults=100, order="relevance",
                     pageToken=page, textFormat="plainText")
        except requests.HTTPError as e:
            # commentsDisabled (403) or similar — skip this video
            if e.response is not None and e.response.status_code in (403, 404):
                return out
            raise
        for th in d.get("items", []):
            top = th["snippet"]["topLevelComment"]["snippet"]
            replies = th.get("replies", {}).get("comments", [])
            owner_replied = any(
                r["snippet"].get("authorChannelId", {}).get("value") == channel_id
                for r in replies
            )
            out.append({
                "commentId": th["snippet"]["topLevelComment"]["id"],
                "author": top.get("authorDisplayName", ""),
                "text": top.get("textDisplay", ""),
                "likeCount": top.get("likeCount", 0),
                "publishedAt": top.get("publishedAt", ""),
                "totalReplies": th["snippet"].get("totalReplyCount", 0),
                "ownerReplied": owner_replied,
            })
        page = d.get("nextPageToken")
        if not page:
            break
    return out


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-comments", action="store_true",
                    help="include comments the owner has already replied to")
    args = ap.parse_args()

    channel_id, uploads = channel_meta()
    videos = list_videos(uploads)
    report = []
    for v in videos:
        threads = comment_threads(v["videoId"], channel_id)
        if not args.all_comments:
            threads = [t for t in threads if not t["ownerReplied"]]
        report.append({**v, "comments": threads})

    total = sum(len(v["comments"]) for v in report)
    print(json.dumps({"channelId": channel_id, "videos": report, "totalComments": total}, indent=2))


if __name__ == "__main__":
    main()
