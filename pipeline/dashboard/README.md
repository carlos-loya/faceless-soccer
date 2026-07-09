# Mission Control — the dashboard

A local, SaaS-style control room for the whole pipeline: one place to see channel health and to
drive every stage from ideation to publish. Bound to `127.0.0.1` (local, single-owner). Stdlib
Python + a single self-contained `index.html` — no build step, no install.

## Run it

```bash
bash pipeline/dashboard/run.sh        # → http://localhost:8770
```

Override the port with `TTV_DASHBOARD_PORT=9000`.

## Tabs

- **Overview** — channel KPIs (views, retention, swipe-away, subscribe conversion), the pipeline
  funnel (specs → boards → drafts → masters → live), recent video performance, auto-pipeline status,
  next fixtures, and live VoiceBox / comments indicators.
- **Pipeline** — the video board. Each card runs storyboard → draft → production → publish, plus a
  TikTok/IG handoff and delete menu. Filters (All / Needs work / Ready to post / Live) come from one
  server-computed `stage` where **published is authoritative from the post-log** (a live video never
  shows under "Needs work" even after its local files are cleaned up).
- **Analytics** — performance table + a "Collect data" refresh (`youtube_analytics.py collect`).
- **Comments** — unreplied-comment queue (`youtube_comments.py fetch`) with a copy-to-Claude reply
  handoff. Read-only; you reply by hand.
- **Automation** — the auto match pipeline: edit `config.json` (mode / cap / visibility / window),
  see run history + live cron status, run the deterministic ESPN result gate, and a gated "Run now".
- **Schedule** — scheduled-upload queue (reschedule / unschedule / post now).
- **Ideation** — topic briefs + the outlier feed, plus the gated Claude brain buttons.
- **Entities** — the KB entity grid with editable images.

## Draft voice

The **Build draft** dialog picks the voice: **Carlos** (your VoiceBox clone, default; the topbar
chip shows whether the VoiceBox app is reachable) or **Piper** (fast offline fallback). Draft never
spends ElevenLabs credits.

## Deterministic vs token-spending

Most actions are deterministic glue (storyboard, draft, publish, analytics collect, comments fetch,
result gate, config edit) and stream to the **transmission log** dock. A few **spend Claude
subscription tokens** and are clearly tagged + confirm-gated:

- **Ideation → Run find-topics / Run daily** — fire `claude -p /find-topics` / `/daily`.
- **Automation → Run now** — shells `run_match_pipeline.sh` (fires `claude -p /match-recap` and, in
  publish mode, uploads to YouTube).

Every side-effecting or token-spending action requires an explicit confirm. The server binds
localhost only.

## Files

- `server.py` — stdlib HTTP server: aggregates `out/` state, computes `/api/overview`, runs scripts
  as background jobs with live log tailing, serves storyboards/renders (MP4 range). Reads raw repo
  JSON directly for the lighter tabs.
- `index.html` — the single-file UI (broadcast control-room theme, vanilla HTML/CSS/JS).
- `run.sh` — launcher.
