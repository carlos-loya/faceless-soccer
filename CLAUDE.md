# CLAUDE.md — TikiTakaFootyTV

Context for any Claude working on this project. Read this first.

## What this is

A **faceless soccer theme page** (Instagram / YouTube / TikTok) launching around the **FIFA 2026 World Cup**, then continuing with general soccer content. Brand: **TikiTakaFootyTV** (backup: TikiTakaFootyHQ). The owner wants an **automated content pipeline** so producing posts takes very little of their time.

**Current identity: DAILY WORLD CUP NEWS & STORIES.** The channel tells the day's biggest football moments as fast, cinematic narratives — heroes, upsets, redemption arcs, selection drama, talking points (the Pulisic "redemption" video is the model). Quizzes/stats remain in the toolkit (e.g. the proven `quiz_top5` outlier) but are secondary. The copyright-safe / no-footage rule is unchanged — stories are still told with stat graphics + AI imagery + VO, never broadcast clips.

The repo has a working pipeline (brain skills + deterministic render/publish glue — see the repo map and status below); design docs here capture the strategy behind it.

## The one non-negotiable principle: copyright-safe, no-footage

Soccer is the most aggressively copyright-enforced content online (FIFA/UEFA/PL + Content ID + DMCA). Reposting match footage — **including from FIFA's own YouTube** — gets struck and kills channels. So the entire strategy avoids broadcast footage:

- **Core formats use NO match footage.** Videos are generated **stats graphics + AI imagery + voiceover**. (Stat cards, ranking countdowns, trivia/"did-you-know", season-in-numbers, tactical diagrams.)
- Sanctioned footage paths exist only via **official FIFA 2026 creator programs** — TikTok (Creator Correspondents) and YouTube (now a "Preferred Platform" + a selected creator cohort). Both are **selective/invite-based**, not open to a new page; licensed footage stays with media partners + the chosen cohort. Aspire to / apply, but don't design around having it. (YouTube being a co-equal WC platform raises **YouTube Shorts as a launch priority**.)
- Short fair-use clips (≤~10s, own VO, muted audio) are an *optional, calculated-risk* add-on — **never the foundation**. Content ID can still flag even valid fair use.
- Avoid generating recognizable player **faces** (right-of-publicity + AI mangles them). Lead with stat cards, kits, crests, silhouettes.

If a future request drifts toward "repost highlights," push back and redirect to the no-footage model.

## The pipeline (the mental model)

Claude is the **brain** (judgment), code is the **deterministic glue**:

```
data/news/stats → CLAUDE (structured VideoSpec JSON) → Nano Banana graphics
   + ElevenLabs VO + Remotion assembly + burned-in captions → finished post
```

Two feeder engines surround the brain: the **grounding/news engine** (`soccer-news` skill + `kb/`) tracks what's *true & current* (dated, sourced facts + live narratives), and the **outlier-discovery engine** (YouTube Data API, spec'd) tracks what's *viral*. The brain generates **grounded × viral** specs. Loop: *mine what's true + what's working → rebuild it copyright-safe*.

## Tool stack

| Stage | Tool | Notes |
|---|---|---|
| Ideation / script / captions | **Claude Code** (subscription) via the `videospec` skill | runs on the subscription, NOT the metered API; `VideoSpec` schema is the validation contract |
| Voiceover | **ElevenLabs** | `elevenlabs/skills@text-to-speech` |
| Captions | **ElevenLabs STT** | `@speech-to-text` |
| Graphics / thumbnails | **Nano Banana** (Gemini image API) | free tier ~500 img/day; `banana-claude` skill; Pro tier paid (~$0.13/img) for best text |
| Video assembly | **Remotion** or **FFmpeg** | animates stills + VO + captions |
| B-roll (optional, phase 2) | **Higgsfield** | AI cinematic atmosphere; pricey |
| Outlier discovery | **YouTube Data API v3** | free, 10k units/day |

**API keys (in `.env`, see `.env.example`; obtained + validated ✓):** `GEMINI_API_KEY` (⚠️ **image API needs billing — free tier = 0 for the image model**, despite blog claims), `ELEVENLABS_API_KEY` (works; ⚠️ **free tier has no commercial rights — monetized page needs ≥ Starter $5/mo**), `YOUTUBE_API_KEY` (works, free). All on one Google account except ElevenLabs. **No Anthropic key** — scripting runs on the Claude Code subscription.

## Repo map

| File | What it is |
|---|---|
| `CLAUDE.md` | This file — project context |
| `README.md` | Public-facing overview: what the project is, the pipeline, setup, and usage. Start here. |
| `docs/PLAYBOOK.md` | How the Claude content engine works: VideoSpec schema, cost engineering, visual sourcing, tool stack, build order |
| `docs/VIRAL-FORMULA.md` | Reverse-engineered viral formula from real faceless soccer pages + 5 starter templates |
| `docs/OUTLIER-ENGINE-SPEC.md` | Spec for the outlier-discovery engine (replicates Subscribr's hardest feature) |
| `seeds.json` | Seed list of ~22 soccer YouTube channels (by lane/priority) for the outlier engine |
| `pipeline/videospec_schema.py` | The `VideoSpec` Pydantic contract the downstream pipeline validates against (no API call) |
| `.claude/skills/videospec/` | **The brain** — generates a VideoSpec from a topic (grounds first), on the subscription |
| `kb/` | **Canonical knowledge base** — dated, sourced facts + narratives for grounding (schema: `kb/schema.md`, scope: `kb/watchlist.json`) |
| `kb/fixtures.json` | **WC2026 match schedule** — the trigger source for schedule-driven recaps. Per-match `stage`/`date`/`kickoff_et`/`home`/`away`/`status`/`result` (team `*_slug` align to `kb/entities/`). Focuses on the knockout stage (the coverage target). Maintained by `soccer-news` (`refresh fixtures`); queried by `pipeline/fixtures.py` |
| `.claude/skills/soccer-news/` | **Grounding engine** — refreshes the KB + grounds a topic before scripting |
| `.claude/skills/fact-check/` | **Fact-check stage** — verifies a spec's claims (esp. superlatives) vs the KB before production |
| `.claude/skills/pick-images/` | **Vision image selection** — Claude looks at candidates + picks the correct one per `commons` scene |
| `.claude/skills/analytics-review/` | **The learning loop** — reviews each published video's analytics (retention/swipe-away/conversion), distills durable LEARNINGS into `kb/learnings.json` that `videospec` auto-applies. `review` mode (interpret + update) / `brief` mode (what videospec reads). On-demand; the deterministic data pull is `youtube_analytics.py collect` |
| `analytics/performance.jsonl` | **Performance store** — one record per published video joining its spec's design levers (format/hook_type/retention_mechanic/scenes) with its YouTube analytics (retention curve, swipe-away, conversion) + scene-leak attribution. Written by `youtube_analytics.py collect`, read by `analytics-review` |
| `kb/learnings.json` | **Distilled learnings** — dated, evidenced findings (`n`/`confidence`/`proposed_rule_change`) + `channel_baseline`, maintained by `analytics-review`, read by `videospec` (auto-applies `high`-confidence, weights `low`/`med`). Supersedes the old hand-typed "video #1" calibration block |
| `pipeline/generate_assets.py` | ElevenLabs VO (+ optional Nano Banana) asset generation, via `uv` |
| `pipeline/remotion/` | Remotion project — composes graphics + VO + captions → MP4 |
| `pipeline/outlier_ingest.py` | **Viral engine MVP** — YouTube outlier discovery (deterministic), ranks `seeds.json` channels |
| `pipeline/commons.py` | **Shared Wikimedia helpers** — the one copy of the Commons fetch/validate/download logic (UA, `strip_html`, `is_image`, 429-backoff `get_image`, `commons_search`, `download_candidates`) imported by every `fetch_*` script (was duplicated 5×) |
| `pipeline/ytcommon.py` | **Shared YouTube-script helpers** — the one copy of the two-step headless OAuth flow (`YTOAuth`) + `video_id` parser, imported by `upload_youtube.py` / `youtube_analytics.py` / `youtube_comments.py` (the OAuth flow was byte-duplicated between the first two) |
| `pipeline/fetch_images.py` | CC/Wikimedia **free** image fetcher (players/stadiums/nations) → KB `image` field |
| `pipeline/cutout.py` | Background removal (`rembg`) → transparent-PNG **cutout** for the iPhone-sticker corner element (`out/cutouts/<slug>.png`) |
| `pipeline/ensure_assets.py` | **Auto-fetch + auto-cutout** — creates stub entities, fetches CC images, cuts out the subject for any spec (hands-off) |
| `pipeline/fetch_candidates.py` | Fetch several Commons options for one query → vision-vet → curate a KB entity |
| `pipeline/fetch_player_candidates_plus.py` | **Expanded-source player photos** — when Commons/Openverse give only club shots or low-res, this casts wider: Wikidata P18 (preferred image) + per-language Wikipedia LEADS (en/ko/cs/de/es/tr — a Korean/Czech player's ko/cs page lead is often the NATIONAL-kit shot Commons search misses). Free-licensed Commons-hosted files only. Usage: `fetch_player_candidates_plus.py <slug>:"<Full Name>" …` → `out/candidates/<slug>/plus-N`. |
| `pipeline/fetch_player_candidates.py` | **Wider-net player photos** — gathers many free candidates (Commons search + Commons *category* + Openverse/Flickr-CC) so you can vision-pick a NATIONAL-kit shot. Note: national-kit photos are usually crowded match shots → rembg grabs the group; crop to the lone player first, or use a clean club/training portrait |
| `pipeline/fetch_scene_candidates.py` | Per-spec candidate fetch for one-off `commons` scenes (feeds `pick-images`) |
| `pipeline/make_video.sh` | **One-command driver:** `spec.json → finished MP4` (ensure → VO → visuals → render). **Draft is the DEFAULT** (free Piper VO, `-draft` output, no ElevenLabs credits); real ElevenLabs VO is opt-in via `TTV_PRODUCTION=1`. |
| `pipeline/storyboard.sh` | **Pre-render preview driver:** `spec.json → out/storyboards/<stem>.html` (ensure → resolve visuals → HTML). Runs only the FREE/FAST half — **no VO, no Remotion render** — so the owner sees which image/background each scene will get BEFORE the slow draft. Iterate the spec here for free; the images it downloads are cached so the eventual draft renders faster. Driven by `/storyboard`. |
| `pipeline/remotion/storyboard.mjs` | **Storyboard HTML generator** — reads `storyboard-props.json` + the spec, emits a 9:16-card-per-scene contact sheet: resolved background + caption + VO line + `visual_source:visual_query` + per-scene WARNINGS (image didn't resolve → plain graphic, `ai` not wired, `stock_video` ≥~6s freeze risk). Uses the same resolver as the render (`prepare.mjs` `TTV_STORYBOARD` branch). Also writes `<stem>.summary.json`. |
| `pipeline/upload_youtube.py` | **YouTube posting (DEFAULT)** — uploads a rendered MP4 straight to the channel via the official YouTube Data API (`videos.insert`); no Docker. Title/description/tags from the spec; vertical 1080×1920 auto-classifies as a Short. Owner OAuth (`youtube.upload` scope) in `pipeline/.secrets/yt_upload_token.json` (reuses the analytics Desktop client). `auth` / `auth-finish` / `upload <spec> <mp4> [--visibility]`. Moves the render to `out/published/` on success |
| `pipeline/post_packet.py` | **TikTok/IG handoff** — `post_packet.py <spec> <mp4>` prints a per-platform JSON packet (absolute mp4 path + tiktok/instagram captions, formatted exactly like `publish._caption_for`) consumed by the **`post-social`** skill |
| `pipeline/regen_scene.py` | **Single-clip VO re-record** — `regen_scene.py <spec_stem> <scene_index>` regenerates ONE scene's mp3 (applies `pronunciations.json`) + patches `out/assets/<stem>/props.json`, so a one-line VO edit doesn't re-spend ElevenLabs credits on the whole video (then re-run `prepare.mjs` + render) |
| `pipeline/youtube_analytics.py` | **Real retention diagnostic + collector** — `summary` / `retention <video>` via the YouTube Analytics API (owner OAuth in `pipeline/.secrets/`), plus `collect [--stem --min-age-days]` which joins every matured published video's analytics with its spec's design levers + scene-leak mapping → `analytics/performance.jsonl` (feeds the `analytics-review` learning loop). ⚠️ Analytics API lags ~2–3 days; a fresh video returns zeros until processed (`collect` skips it as no-data) |
| `out/published/`, `logs/` | `out/published/` = published renders (moved by `upload_youtube.py`); `out/renders/` = unpublished drafts; `logs/` = build/render logs. `out/published/post-log.jsonl` = TikTok/IG browser-post log (written by the `post-social` skill) |
| `.claude/skills/post-social/` | **TikTok + Instagram posting (DEFAULT)** — attended Playwright-MCP browser runbook: drives a logged-in browser to upload the MP4 + caption. Owner watches/clears any captcha/login. YouTube does NOT go through here (use `upload_youtube.py`) |
| `pipeline/youtube_comments.py` | **Comment fetcher (read-only)** — lists the channel's top-level comments we haven't replied to (public `YOUTUBE_API_KEY`, no OAuth/write scope) → JSON the brain drafts replies from. `fetch [--video <id>] [--days N] [--min-likes N]`. Never posts; the owner replies by hand |
| `.claude/commands/reply-comments.md` | **`/reply-comments` slash command** — fetch un-answered comments (`youtube_comments.py`) → draft a reply for each for the owner to copy-paste. Never posts |
| `logo-icon.svg`, `logo-wordmark.svg` | Brand assets (gold/black; "TT" monogram + wordmark) |
| `.claude/commands/find-topics.md` | **`/find-topics` slash command** — ideation: what's TRUE now (`soccer-news`) × what's VIRAL (`outlier_ingest.py`) × what WORKS for us (`kb/learnings.json`) → a ranked shortlist of ~5 grounded, copyright-safe video ideas. Feeds `/daily`; does not script/render/post |
| `.claude/commands/daily.md` | **`/daily` slash command** — front of the pipeline: ground today's news (`soccer-news`) → pick an angle → `videospec` → `fact-check` → `make_video.sh` FREE draft → stop for owner review. Never spends ElevenLabs or posts (production + posting are owner-approved separately) |
| `pipeline/fixtures.py` | **Fixture query CLI** — reads `kb/fixtures.json`: `today` / `upcoming` / `next` / `recent [--hours N]` (finished-recently, what the cron polls), `--notable` = the coverage rule (knockouts + watchlist-nation matches), `--json` for the orchestrator. Pure stdlib |
| `.claude/commands/match-recap.md` | **`/match-recap` slash command** — the per-match unit of the automated pipeline: resolve a finished fixture → ground the game report (`soccer-news`) → `videospec` (`post_match`) → **`fact-check` HARD GATE** → render (FREE draft by default; `--produce`/`--publish` spend credits). Writes `out/auto/receipts/<id>.json`. Runs by hand or via the orchestrator (`claude -p`) |
| `pipeline/auto/` | **Schedule-driven match pipeline** — `run_match_pipeline.sh` (for each recent finished notable match not in the `processed.jsonl` ledger, up to `daily_cap`: `claude -p "/match-recap …"` → if `mode:publish` + fact-check passed + render exists, `upload_youtube.py` + a `post_packet.py` handoff), `wc_cron.sh` (window-gated, single-flight cron entry — every 30 min), `config.json` (`mode` draft/produce/publish, cap, visibility). **YouTube-only auto-publish; TikTok/IG never auto-posted** |
| `.claude/commands/publish.md` | **`/publish` slash command** — last mile: confirm → YouTube via `upload_youtube.py` (official API, auto-logs + moves to `out/published/`) → TikTok/IG via `post_packet.py` + the attended `post-social` skill. Refuses `-draft` files; AskUserQuestion gate before posting (outward-facing) |
| `.claude/commands/analyze-channel.md` | **`/analyze-channel` slash command** — back of the pipeline: `inventory --backfill` → `collect` → `analytics-review` → report what's working/wrong + update `kb/learnings.json` |
| `.claude/commands/storyboard.md` | **`/storyboard` slash command** — pre-render preview: runs `storyboard.sh` (no VO/render) → reports the per-scene visual table + warnings + the HTML path. Slots into `/daily` between `fact-check` and `make_video.sh` so the draft is right the first time. Never spends credits, never renders, never posts |
| `pipeline/dashboard/` | **Mission Control dashboard** — a local, **token-free** control room (`bash pipeline/dashboard/run.sh` → http://localhost:8770; stdlib-only Python, binds 127.0.0.1). `server.py` aggregates `out/` state (specs → storyboard → draft → production → published, joined with `post-log.jsonl`) and fires the **deterministic** stages as background jobs with a live-streaming transmission log: **storyboard** (`storyboard.sh`), **draft** (`make_video.sh`), **production** (`TTV_PRODUCTION=1`, confirm-gated — spends credits), **publish YT** (`upload_youtube.py`, confirm-gated, refuses `-draft`), **outlier feed** (`outlier_ingest.py`). Serves storyboard contact-sheets + plays renders in-page (MP4 range). **No Claude is invoked from the server** (no token spend, no autonomous-agent surface) — brain steps (`/find-topics`, `videospec`, `/daily`) stay in the Claude session; briefs saved to `out/topics/*.md` + new `out/specs/*.json` auto-appear. Broadcast control-room UI (`index.html`, built with the frontend-design skill). |

## Status & decisions

- ✅ **Pipeline fully operational end-to-end:** all stages built (grounding → videospec → fact-check → storyboard → make_video.sh → upload_youtube.py / post-social). See repo map for individual components.
- ⬜ **Handles NOT yet registered.** Owner should register `@tikitakafootytv` on IG + YouTube + TikTok (confirm TikTok at signup; fall back to `…hq`), same day, + grab the `.com`.
- ⚠️ **Nano Banana image API needs billing** (free tier = 0). v1 uses free Remotion CSS graphics; enable billing later for AI backgrounds (~$0.04/img).
- ⚠️ **Remotion component:** `TikiTakaVideo.tsx` (with the 'i'); composition id `TikiTaka`.
- **Visual source routing:** `entity` (KB) → `commons` (specific Wikimedia search) → `stock` (Pexels generic) → `ai` (needs billing) → `graphic`. `videospec` plans the routing per scene (`visual_source`/`visual_query`).
- ⬜ **AI imagery (`ai` source) not wired in `prepare.mjs`** — needs Google billing enabled; until then `ai` scenes render with no background.
- ✅ **Corner stickers DISABLED** (owner directive) — no subject cutout, no per-scene flag chip. `subject` is metadata/thumbnail identity only; `sticker_entity` is deprecated. Don't reintroduce.
- ✅ **Running scoreboard** — match summaries use a TV scoreboard (lower-middle, ticks with the narrative). ⚠️ Needs FLAG images on BOTH `matchup` nations — if a nation entity has `image:null`, the scoreboard silently won't render. Scoreboard auto-hides on `group_table` scenes and the end card. ⚠️ Crowded match shots → crop to the lone player BEFORE `cutout.py` (rembg grabs every foreground body). Always eyeball owner-supplied photos for the right person.
- **Group-table scene conventions:** (a) use `night-stadium` `stock_video` background; (b) VO karaoke renders under the table; keep table-scene VO ≤ ~6s. Use `on_screen_text` as the gold heading (e.g. `"GROUP E"`).
- ⚠️ **`stock_video` b-roll FREEZES if a scene outlasts its clip** (~6s). Keep `stock_video` scene VO under ~6s (the VO drives scene length). Not reliably detectable by frame-diffing (karaoke captions change every frame); eyeball it.
- ✅ **Schedule-driven match automation (2026-07-03):** the WC schedule (`kb/fixtures.json`) drives per-match recaps. `pipeline/auto/wc_cron.sh` (local cron, every 30 min, window-gated) → `run_match_pipeline.sh` → `/match-recap` per recent finished **notable** match (knockouts + watchlist nations, `fixtures.py --notable`). Owner chose **full auto incl. YouTube publish**, so the auto path overrides the manual draft-first default — but with hard rails: **fact-check is a blocking gate** (a match that can't be verified produces no render, so it can't publish), a **`daily_cap`**, an **each-match-once ledger** (`out/auto/processed.jsonl`), and **YouTube-only** auto-publish (official API). **TikTok/IG are NEVER auto-posted** — a `post_packet.py` handoff is written for the attended `post-social` run. Flip `pipeline/auto/config.json` `mode` to `draft` to fall back to review-first. `/daily` remains the primary owner-driven path. Also fixed: editing a scene's background now re-resolves in `/storyboard` (stale vision-picks auto-invalidate; `--fresh` forces a clean rebuild).
- ✅ **Deterministic result gate (2026-07-08):** the auto path no longer relies on a manual KB refresh (or LLM judgment) to know a match finished or what the score was. `run_match_pipeline.sh` gates each match on `pipeline/auto/fetch_result.py <id> --write`, which pulls the authoritative score + scorers from ESPN's free `fifa.world` scoreboard (no key) and writes them into `kb/fixtures.json` **only when ESPN reports the match `post` (final)** — else it fails safe (skip, retry next run, nothing published). `/match-recap` treats the `result` block (`source:"espn"`/`verified:true`) as ground truth; `soccer-news` grounding is narrative-only and must not change the score/scorers. This fixes the earlier failure mode where grounding hallucinated a scorer ("Zico scored both Egypt goals") and fact-check missed it. First autonomous QF (qf-01) publishes **unlisted** as a safety net — flip `youtube_visibility` back to `public` after verifying.
- ✅ **Subscribe chip + scene-2 escalation (2026-06-21):** `Scene.subscribe_chip: true` marks ONE climax beat where a gold "SUBSCRIBE" pill pops for ~2s, paired with a subject-tied subscribe line in that beat's VO. `videospec` rule 5 + rule 1b enforce this. Scene 2 must ESCALATE the hook (raise the subject's specific quantified deprivation) — never open on a chronological timeline, opponent scoring, or abstract frame. ⬜ Measure A/B in next `/analyze-channel`.
- ⚠️ **TikTok/IG posting is attended-only** — never run unattended/scheduled (bot detection + shadowban risk). YouTube stays on the safe official API.
- ⚠️ **Analytics metric nuance:** `audienceWatchRatio` can exceed 100% (loops) — use `averageViewPercentage` as the clean headline retention stat. The "68% swiped away" Studio impression stat is a different measurement from the Analytics curve.

## Working conventions

- **LLM/scripting runs on the Claude Code subscription** (the `videospec` skill, or headless `claude -p`) — NOT the metered Anthropic API. Keys are only for Nano Banana, ElevenLabs, YouTube Data API. The `VideoSpec` Pydantic schema is the validation contract, not an API caller.
- **Tooling:** Python deps via **`uv`** (system `python3` has no pip). **Node + Remotion** for the video render stage. Secrets live in `.env` (see `.env.example`), never committed.
- **ElevenLabs credits = money — ALWAYS draft first.** `make_video.sh` defaults to a FREE Piper draft; only run `TTV_PRODUCTION=1` (real ElevenLabs VO) on a spec whose visuals/captions/pacing have been reviewed and approved. Caption/layout/image fixes are free to iterate in draft. If only the caption text (not audio) is wrong on an already-produced video, patch the words in `out/assets/<stem>/props.json` and re-run `prepare.mjs` + Remotion render — never re-run TTS just to fix on-screen text.
- **Grounding:** time-sensitive facts (age, club, fitness, form, records) MUST come from the `kb/` via the `soccer-news` skill — never from model memory (it's stale). Every KB fact is dated + sourced; verify freshness before grounding.
- **Superlatives need EXTERNAL, adversarial verification — never trust the KB to prove them.** Any "first/only/nobody/record/most/youngest" claim must be checked against current sources by actively searching for a counterexample (the `fact-check` skill), because the KB is always incomplete. Real example: the KB said only Messi & Ronaldo reach a 6th World Cup — it missed **Guillermo Ochoa** (three total). If the full set can't be established, reframe ("one of only a handful ever"), don't assert a false "first/only".
- **Claude/Anthropic API questions:** consult the `claude-api` skill — don't answer model IDs/pricing/caching from memory.
- Keep docs current when decisions change (this file + PLAYBOOK especially).
- Default model for the content engine is **Opus 4.8** (`claude-opus-4-8`); drop to Sonnet/Haiku only for mechanical stages.
- Verify any memory/recalled fact (handles, file names) before acting — handle availability was checked, not registered.
