# Mission Control — the dashboard

A local, **token-free control room** for the pipeline. One screen to see where every video
is and to fire the **deterministic** stages with a click — no Claude/brain steps run from
here, so no surprise token spend and no autonomous-agent surface.

## Run it

```bash
bash pipeline/dashboard/run.sh        # → http://localhost:8770
```

Stdlib Python only (no `uv`, no install). It binds to `127.0.0.1` (local only).
Override the port with `TTV_DASHBOARD_PORT=9000`.

## What the buttons do

Every action just shells out to the scripts that already exist and streams their output to
the **TRANSMISSION LOG** dock at the bottom:

| Button | Runs | Cost |
|---|---|---|
| **◱ STORYBOARD** | `bash pipeline/storyboard.sh out/specs/<stem>.json` | free |
| **▣ DRAFT** | `bash pipeline/make_video.sh out/specs/<stem>.json` (Piper VO) | free |
| **● PRODUCTION** | `TTV_PRODUCTION=1 bash pipeline/make_video.sh …` | **ElevenLabs credits** — confirm dialog |
| **▲ PUBLISH YT** | `uv run pipeline/upload_youtube.py upload <spec> <mp4> --visibility …` | **public, irreversible** — confirm dialog (refuses drafts) |
| **⚡ RUN OUTLIER FEED** | `uv run pipeline/outlier_ingest.py` → `out/topics/outlier-feed-*.md` | free (YT Data API quota ~21u) |

View buttons (`◱ BOARD`, `▷ DRAFT`, `▷ MASTER`) open the storyboard contact sheet / play the
rendered MP4 in-page. Published rows link out to YouTube/TikTok.

## The brain steps stay in Claude (by design)

Ideation and scripting — `/find-topics`, `videospec`, `/daily`, `fact-check` — are **not**
buttons here (they need judgment + spend tokens). Run them in your Claude Code session as
usual. Anything you save under `out/topics/*.md` (e.g. a `/find-topics` brief) shows up in the
**CACHED BRIEFS** list automatically, and any new `out/specs/*.json` appears on the board.

So the loop is: *Claude makes the spec → dashboard storyboards, drafts, masters, and
publishes it without spending another token.*

## Files

- `server.py` — stdlib HTTP server: aggregates `out/` state, runs the scripts as background
  jobs with live log tailing, serves storyboards/renders (with MP4 range requests). No Claude.
- `index.html` — the single-file UI (broadcast control-room theme).
- `run.sh` — launcher.
