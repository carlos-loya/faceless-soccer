---
description: Post an APPROVED render to YouTube (official API) + TikTok/Instagram (attended browser), then log it — the pipeline's last mile
argument-hint: "<stem> [youtube|tiktok|instagram|all] [public|unlisted]"
allowed-tools: Bash, Read, Skill, AskUserQuestion
---

Publish a finished, owner-approved render across platforms and record it. Input: $ARGUMENTS
(a spec stem, optional platform list, optional YouTube visibility).

This is the back-half poster of the hybrid model: **YouTube via the official API**, **TikTok
+ Instagram via the attended `post-social` browser flow**. Posting is **public and hard to
undo**, so confirm before firing.

1. **Resolve the render.** From the stem, the spec is `out/specs/<stem>.json` and the MP4 is
   `out/renders/<stem>.mp4` (fall back to `out/published/<stem>.mp4` if YouTube already moved
   it). **Refuse to post a `-draft` file** — drafts use free Piper VO, not the real ElevenLabs
   production audio. If only a `-draft` exists, stop and tell the owner to run the production
   render first: `TTV_PRODUCTION=1 bash pipeline/make_video.sh out/specs/<stem>.json`.

2. **Confirm before posting.** Use **AskUserQuestion** to confirm: which platforms (default
   **all** — YouTube + TikTok + Instagram) and the **YouTube visibility** (default `public`;
   offer `unlisted` for a first/cautious post). Show the title (`youtube_title`) and the
   resolved MP4 path so the owner sees exactly what ships. Do not proceed without confirmation.

3. **YouTube (do this FIRST).** `uv run pipeline/upload_youtube.py upload out/specs/<stem>.json
   out/renders/<stem>.mp4 --visibility <public|unlisted>`. The official Data API uploads it,
   appends a row to `out/published/post-log.jsonl`, and **moves the render to
   `out/published/<stem>.mp4`** — so use that moved path for the next step.

4. **TikTok + Instagram (attended).** Build the handoff packet:
   `uv run pipeline/post_packet.py out/specs/<stem>.json out/published/<stem>.mp4`, then invoke
   the **`post-social`** skill for the chosen platform(s). **Attended only** — the owner watches
   the browser and clears any login / captcha / 2FA; if a challenge appears, pause and hand the
   browser over, then resume. Never try to bypass it. (post-social logs each platform to
   `post-log.jsonl`.)

5. **Report.** Summarize what posted where: the YouTube URL, the TikTok/IG status, the
   visibility, and the `post-log.jsonl` rows written. Note anything skipped or pending.

Guardrails:
- **Never auto-confirm.** Publishing is outward-facing — the AskUserQuestion gate is required.
- **YouTube only** rides the official API; TikTok/IG stay attended (shadowban risk) — never
  schedule or run this command unattended.
- After publishing, remind the owner that `/analyze-channel` (in ~2–3 days, after the analytics
  lag) will read the results back into `kb/learnings.json`.
