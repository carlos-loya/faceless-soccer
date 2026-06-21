# TikiTakaFootyTV

An **automated, copyright-safe content pipeline** for a faceless soccer theme page
(YouTube Shorts · TikTok · Instagram Reels), built around the FIFA 2026 World Cup and
general football content. The channel tells the day's biggest football moments as fast,
cinematic short-form **news & stories** — heroes, upsets, redemption arcs, selection
drama — produced with almost no hands-on time.

The design principle: **Claude is the brain (judgment), code is the deterministic glue.**
Claude turns a topic into a structured video spec; a deterministic toolchain renders that
spec into a finished, captioned vertical video and posts it.

> This is a personal project. It is shared publicly as a reference for how an LLM-centered,
> copyright-safe content pipeline can be assembled. See **License** below.

---

## The one non-negotiable: copyright-safe, no footage

Soccer is the most aggressively copyright-enforced content online (FIFA/UEFA/leagues +
Content ID + DMCA). Reposting match footage — even from official channels — gets videos
struck and kills accounts. So the entire pipeline **avoids broadcast footage**:

- Videos are **generated stat graphics + AI/CC imagery + original voiceover** — never
  match clips.
- It avoids generating recognizable player **faces** (right-of-publicity + AI artifacts);
  it leads with stat cards, kits, crests, silhouettes, and licensed Creative-Commons
  photos used as backgrounds.
- Every fact is grounded in a dated, sourced knowledge base, then fact-checked before
  production.

If a change drifts toward "repost highlights," it doesn't belong here.

---

## How it works

```
data / news / stats
   → CLAUDE  (structured VideoSpec JSON: hook, scenes, VO, captions, comment-bait)
   → graphics (Nano Banana / brand CSS cards) + ElevenLabs voiceover
   → Remotion assembly + burned-in karaoke captions
   → finished 1080×1920 short  → YouTube / TikTok / Instagram
```

Two feeder engines surround the brain:

- **Grounding engine** — tracks what's *true and current* (a dated, sourced knowledge base
  refreshed by web research) so videos aren't built on stale model memory.
- **Outlier-discovery engine** — tracks what's *viral* (YouTube Data API; finds videos that
  massively overperformed their channel baseline) to inform format choices.

A **learning loop** closes the cycle: each published video's analytics (retention curve,
swipe-away, subscribe/comment conversion) are distilled into durable "learnings" that the
spec generator automatically applies to the next video.

---

## Tool stack

| Stage | Tool | Notes |
|---|---|---|
| Ideation / script / captions | **Claude Code** (subscription) | runs on the subscription, not a metered API |
| Voiceover | **ElevenLabs** | text-to-speech (commercial plan for monetized use) |
| Captions | **ElevenLabs STT** | word-level timings → karaoke captions |
| Graphics / thumbnails | **Nano Banana** (Gemini image API) | optional; free brand CSS cards otherwise |
| Video assembly | **Remotion** / FFmpeg | animates stills + VO + captions |
| Outlier discovery | **YouTube Data API v3** | free quota |
| Analytics | **YouTube Analytics API** | retention + conversion, feeds the learning loop |

The scripting "brain" runs on the **Claude Code subscription** — there is **no Anthropic API
key**. API keys are only needed for image generation, voiceover, and the YouTube APIs.

---

## Repository layout

| Path | What it is |
|---|---|
| `CLAUDE.md` | Project context & working conventions for any AI agent (also bridged to `AGENTS.md`) |
| `docs/` | Strategy & design docs — **start with [`docs/PLAYBOOK.md`](docs/PLAYBOOK.md)** |
| `.claude/skills/` | The **brain**: skills for spec generation, grounding, fact-checking, analytics review, posting |
| `.claude/commands/` | Slash-command workflows (`/find-topics`, `/daily`, `/storyboard`, `/publish`, `/analyze-channel`) |
| `pipeline/` | The deterministic glue: asset generation, Remotion render, image fetching, posting, analytics |
| `pipeline/remotion/` | The Remotion project that composes graphics + VO + captions → MP4 |
| `pipeline/dashboard/` | Local, token-free "Mission Control" web dashboard for driving the pipeline |
| `kb/` | Canonical knowledge base — dated, sourced facts + narratives for grounding |
| `videospec_schema.py` | The `VideoSpec` Pydantic contract the pipeline validates against |
| `seeds.json` | Seed channels for the outlier-discovery engine |
| `.agents/`, `.opencode/` | Generated copies of skills/commands for other agent harnesses (see [harness portability](docs/HARNESS-PORTABILITY.md)) |

The brain (`.claude/`) is the single source of truth; `pipeline/sync_harness.py` regenerates
the `.opencode/` and `.agents/` copies for OpenCode and Antigravity.

---

## Setup

Prerequisites: **Python** (via [`uv`](https://github.com/astral-sh/uv)), **Node.js** (for
Remotion), and the [Claude Code](https://claude.com/claude-code) CLI for the brain stage.

```bash
# 1. API keys — copy the template and fill in what you have
cp .env.example .env        # GEMINI / ELEVENLABS / YOUTUBE keys (all optional to start)

# 2. Python deps run on demand via uv (no global install needed)
#    Node deps for the renderer:
cd pipeline/remotion && npm install
```

`.env`, OAuth tokens (`pipeline/.secrets/`), and other secrets are **git-ignored** and never
committed. See `.env.example` for where to obtain each key.

---

## Usage

The day-to-day flow runs through slash commands inside Claude Code:

```
/find-topics      # what's TRUE now × what's VIRAL × what WORKS for us → ranked ideas
/daily            # ground today's news → script → fact-check → FREE draft render → review
/storyboard       # preview each scene's visuals as an HTML contact sheet before rendering
/publish          # post an APPROVED render to YouTube (API) + TikTok/IG (attended browser)
/analyze-channel  # pull analytics → report what's working/wrong → update the learnings
```

Or drive the deterministic stages directly:

```bash
# spec.json → finished MP4 (free Piper draft by default; real ElevenLabs VO is opt-in)
bash pipeline/make_video.sh out/specs/<stem>.json

# local control room (no tokens, binds 127.0.0.1)
bash pipeline/dashboard/run.sh        # → http://localhost:8770
```

**Cost discipline:** ElevenLabs voiceover costs money, so `make_video.sh` defaults to a free
draft. Real voiceover is opt-in (`TTV_PRODUCTION=1`) only after the visuals and pacing are
reviewed.

---

## Documentation

- **[docs/PLAYBOOK.md](docs/PLAYBOOK.md)** — how the content engine works: the VideoSpec
  schema, cost engineering, visual sourcing, tool stack, build order.
- **[docs/VIRAL-FORMULA.md](docs/VIRAL-FORMULA.md)** — the reverse-engineered viral formula
  and starter format templates.
- **[docs/OUTLIER-ENGINE-SPEC.md](docs/OUTLIER-ENGINE-SPEC.md)** — technical spec for the
  outlier-discovery engine.
- **[docs/HARNESS-PORTABILITY.md](docs/HARNESS-PORTABILITY.md)** — running the skills and
  commands outside Claude Code (OpenCode, Antigravity).
- **[CLAUDE.md](CLAUDE.md)** — full project context and working conventions.

---

## License

No open-source license is granted. This repository is published for reference; all rights
reserved by the owner. Brand assets and channel content are not licensed for reuse.
