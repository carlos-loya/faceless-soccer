---
name: post-social
description: Post a finished render to TikTok and/or Instagram via attended browser automation (Playwright MCP). Use when the owner says "post the latest render to TikTok/Instagram", "publish <stem> to TikTok", etc. This is the browser half of the hybrid poster — YouTube goes through the official API (pipeline/upload_youtube.py), NOT this skill. Attended only: the owner is watching and can solve logins/captchas.
---

# post-social — attended TikTok + Instagram posting via the browser

This skill drives a real, logged-in browser (the Playwright MCP) to upload a rendered MP4
to **TikTok** and/or **Instagram**, because their official posting APIs are app-review-gated.
**YouTube is NOT posted here** — it has a reliable official-API path
(`uv run pipeline/upload_youtube.py upload <spec> <video>`). Use that for YouTube.

> ⚠️ **Attended, on-demand only.** TikTok and Instagram detect automated browsers. The owner
> must be present to log in once and to clear any captcha / 2FA / "is this you" challenge.
> Never run this unattended or on a schedule. If a challenge appears, **pause and hand the
> browser to the owner**, then resume — do not try to bypass it.

## Inputs

- A spec stem or paths, e.g. `out/specs/<stem>.json` + `out/renders/<stem>.mp4`
  (or `out/published/<stem>.mp4` if YouTube already moved it there).
- Which platform(s): TikTok, Instagram, or both. If unspecified, ask.

## Playwright MCP tools used

All prefixed `mcp__plugin_playwright_playwright__`:
`browser_navigate`, `browser_snapshot`, `browser_file_upload`, `browser_click`,
`browser_type`, `browser_wait_for`, `browser_take_screenshot`, `browser_tabs`.

**Always drive off `browser_snapshot` (the accessibility tree: roles + text), not guessed CSS
selectors.** Snapshot → find the element by role/name → act on its ref. Re-snapshot after every
navigation or upload, because the DOM changes.

## Step 0 — build the post packet

Run the helper to get the absolute MP4 path + per-platform captions (formatted exactly like
the old Postiz path):

```
uv run pipeline/post_packet.py out/specs/<stem>.json out/renders/<stem>.mp4
```

Keep the JSON. `video_path` is the absolute path the file picker needs. Use
`tiktok.caption` for TikTok and `instagram.caption` for Instagram verbatim.

## Step 1 — confirm the browser is logged in (once per profile)

The `@playwright/mcp` server uses a **persistent profile by default**, so a login done once
survives across sessions. On the **first** ever run:

1. `browser_navigate` to the platform (`https://www.tiktok.com` / `https://www.instagram.com`).
2. `browser_snapshot`. If it shows a logged-out / login state, tell the owner:
   *"Log into <platform> in the browser window now, then tell me to continue."* Wait
   (`browser_wait_for`) and do NOT type credentials yourself.
3. Once logged in, the session persists — later runs skip straight to upload.

If at ANY later step a login wall / captcha / 2FA / "confirm it's you" screen appears, do the
same: stop, ask the owner to clear it in the window, wait, then re-snapshot and continue.

## Step 2 — post to TikTok (if requested)

1. `browser_navigate` → `https://www.tiktok.com/tiktokstudio/upload` (falls back to
   `https://www.tiktok.com/upload`). `browser_snapshot`.
2. Find the file input / "Select video" control. Use `browser_file_upload` with the
   `video_path` from the packet. (If a hidden `<input type=file>` isn't directly actionable,
   click the "Select video" button first — that opens the chooser the upload tool fills.)
3. `browser_wait_for` until the upload + processing finishes (a caption box + a preview
   thumbnail appear). This can take 30–90s for a ~30–60 MB clip; wait on the caption editor
   becoming visible, not a fixed timer.
4. Clear the caption field, then `browser_type` the `tiktok.caption`. Verify via snapshot that
   the text landed (TikTok hashtag autocomplete popups can swallow characters — re-snapshot).
5. Leave default privacy = Public unless the owner said otherwise. Do not toggle "Disclose
   content"/branded-content.
6. Find and `browser_click` the **Post** button. `browser_wait_for` the success state
   (a "your video is being uploaded/posted" toast or redirect to the content list).
7. `browser_take_screenshot` for the record. Confirm to the owner with the resulting state.

## Step 3 — post to Instagram (if requested)

Do this AFTER TikTok is confirmed (one platform at a time).

1. `browser_navigate` → `https://www.instagram.com`. `browser_snapshot`.
2. Click the **Create** ("New post" / "+") control in the left nav. Re-snapshot.
3. In the create dialog, use `browser_file_upload` with `video_path` (Instagram accepts a
   vertical MP4 as a Reel). If it asks to post as a Reel, accept.
4. Step through the dialog's **Next** buttons (crop → edit → caption). Re-snapshot at each
   step; the button label is literally "Next".
5. On the caption step, `browser_type` the `instagram.caption` into the caption field.
6. Click **Share**. `browser_wait_for` the "Your reel has been shared" / post-complete state.
7. `browser_take_screenshot`; confirm to the owner.

## Step 4 — log the result

Append one line to `out/published/post-log.jsonl` per platform posted (use the Bash tool with
a small Python one-liner, or Write to append). Shape:

```json
{"stem": "<stem>", "platform": "tiktok", "status": "posted", "url_or_note": "<url or toast text>", "ts": "<from `date -u +%Y-%m-%dT%H:%M:%SZ`>"}
```

Get the timestamp from the shell (`date -u +%Y-%m-%dT%H:%M:%SZ`) — do not invent one.

## Guardrails

- **One platform at a time; verify each before the next.** Never fire both then walk away.
- **Never auto-clear a captcha/login/2FA.** Hand control to the owner and wait.
- **Don't move/delete the local MP4** here — leave the file management to `upload_youtube.py`
  (YouTube) so a failed browser post doesn't lose the render. The render staying in
  `out/renders/` or `out/published/` is fine.
- If upload processing stalls > ~3 min or the Post/Share button never enables, screenshot,
  stop, and report to the owner rather than retrying blindly.
- We only ever upload our own rendered MP4 — never broadcast footage.
