# TikiTakaFootyTV — Content Playbook

How faceless soccer pages actually produce content, and specifically how **Claude** sits at the center of the pipeline. Grounded in the research findings (see the deep-research summary) plus the current Claude API.

---

## 1. The mental model: Claude is the "brain," not the "mouth"

A common misconception is that faceless creators paste a prompt into a chat window and copy out a caption. The ones who scale don't do that. They use Claude as a **structured content engine**: feed it data, get back a machine-readable spec that drives the rest of the pipeline automatically.

```
Match data / news / stats
        │
        ▼
   ┌─────────┐   structured JSON   ┌──────────────┐
   │ CLAUDE  │ ──────────────────▶ │ Video spec    │
   │ (brain) │   (forced schema)   │ scenes + VO   │
   └─────────┘                     │ + captions    │
        │                          │ + title/tags  │
        │                          └──────┬───────┘
        │                                 │
        ▼                                 ▼
  ElevenLabs TTS  ◀──── VO script    Remotion / FFmpeg render
        │                                 │
        └──────────► finished vertical video ◄──── burned-in captions
```

Claude does the **language + judgment** work (what's the story, what's the hook, what words go on screen, what's the caption). Code does the deterministic assembly. That split is what makes "small time investment" real.

---

## 2. The four jobs Claude does in a faceless pipeline

| Job | What Claude produces | Why it matters |
|---|---|---|
| **1. Ideation** | A ranked list of post ideas from match results / trending topics / a data feed | Removes the daily "what do I post?" bottleneck |
| **2. Scripting** | The voiceover script + on-screen text, scene by scene | The core of every faceless video |
| **3. Captions & metadata** | Platform-specific caption, hook line, hashtags, YouTube title + description | Each platform wants different copy; Claude repurposes one idea into all three |
| **4. Repurposing** | One source video → IG Reel caption, TikTok caption, YT Short title/desc | "Make once, post everywhere" without rewriting by hand |

The research confirmed the winning **copyright-safe** formats are stats/data graphics, ranking/countdown videos, trivia/"did-you-know" cards, and player spotlights with stat summaries — **none of which require match footage** (see §5). Short fair-use clips with your own voiceover are an *optional, later, calculated-risk* add-on, never the foundation. All four jobs above feed the no-footage formats directly.

> **Content pivot (2026-06-12): the channel now leads with DAILY WORLD CUP NEWS & STORIES** — the day's biggest moments told as narratives (`news_story` / `player_story` in the `videospec` skill), with the stats/quizzes/rankings above as the secondary toolkit. The no-footage model is unchanged: a story is still told with stat graphics + CC photos + AI imagery + VO, never broadcast clips. The visual-sourcing table in §5 still applies — stories just sequence those same sources around a hook→turn→payoff arc.

---

## 3. The high-leverage pattern: data → structured video spec

> **Implementation note:** the brain runs via the `videospec` **Claude Code skill** on the subscription (not the metered API) — see `.claude/skills/videospec/SKILL.md`. The schema contract lives in `videospec_schema.py`. The metered-API code below is kept only as reference for if you ever switch back to the API.

The single most important technique: **force Claude to return a strict JSON schema** describing the whole video. Don't ask for prose and parse it — define the schema and validate against it so you get valid JSON your renderer can consume.

### Models to use (and when)

| Model | Model ID | Input / Output per 1M | Use it for |
|---|---|---|---|
| **Opus 4.8** | `claude-opus-4-8` | $5 / $25 | The script/spec generation — the creative judgment call. Default here. |
| **Sonnet 4.6** | `claude-sonnet-4-6` | $3 / $15 | High-volume runs once your prompt is dialed in and quality is consistent |
| **Haiku 4.5** | `claude-haiku-4-5` | $1 / $5 | Cheap mechanical bits — hashtag formatting, simple classification |

Default to **Opus 4.8** for the script (quality compounds — a better hook is worth far more than the token cost). Drop to Sonnet/Haiku only for the mechanical stages.

### Example: match result → narrated stats-video spec

```python
import anthropic
from pydantic import BaseModel
from typing import List

client = anthropic.Anthropic()

class Scene(BaseModel):
    on_screen_text: str       # the big text overlay for this beat
    voiceover: str            # what ElevenLabs narrates over it
    stat_callout: str         # e.g. "xG: 2.7 vs 0.9" — drives a graphic
    duration_seconds: float

class VideoSpec(BaseModel):
    title: str                # YouTube title
    hook: str                 # first 2 seconds — make-or-break
    scenes: List[Scene]
    ig_caption: str
    tiktok_caption: str
    hashtags: List[str]

BRAND_SYSTEM = """You are the script engine for TikiTakaFootyTV, a faceless
soccer highlights/stats page. House style: punchy, knowledgeable, hype but not
cringe. Every video is COPYRIGHT-SAFE: original voiceover + stats graphics, no
reposted broadcast footage. Hooks must land in the first 2 seconds. On-screen
text is short (<8 words). Narration is conversational and fast-paced."""

def build_spec(match_data: str) -> VideoSpec:
    resp = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=4000,
        system=[{"type": "text", "text": BRAND_SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],  # cache the brand prompt
        messages=[{"role": "user",
                   "content": f"Make a 30s vertical stats video from:\n{match_data}"}],
        output_format=VideoSpec,
    )
    return resp.parsed_output   # a validated VideoSpec — no parsing, no retries
```

`resp.parsed_output` is a typed object your Remotion/FFmpeg renderer and ElevenLabs call read directly. The whole pipeline downstream is deterministic from here.

---

## 4. Cost engineering — this is what makes it sustainable

> **Mostly moot under the subscription:** the brain runs on the Claude Code subscription, so the LLM stage is flat-cost — the prompt-caching and Batch-API tricks below are **not needed** and apply only if you switch the brain to the metered API. Real marginal cost in v1 is just **ElevenLabs VO** (graphics are free via Remotion; Nano Banana is optional and needs billing). Section retained as API reference.

Two API features turn "expensive to run daily" into "a few cents a video."

### Prompt caching — cache the brand/style prompt
Your `BRAND_SYSTEM` prompt (house style, rules, examples) is identical on every call. Mark it with `cache_control` (as above) and you pay ~0.1× for it on every request after the first. Cache reads are ~90% cheaper than full input. For a long, example-rich style guide this is the difference between viable and not.

- Keep the brand prompt **byte-identical** and **first** in the request (never interpolate the date or a video ID into it — that silently breaks the cache).
- Verify with `resp.usage.cache_read_input_tokens` — if it's 0 across runs, something's invalidating it.

### Batch API — produce a whole week at 50% off
Don't generate one video at a time. When the matchday slate finishes, batch every video spec into **one** Message Batches call:

- **50% cheaper** on all tokens
- Up to 100,000 requests per batch; most finish within an hour
- Combine with the cached brand prompt for compounding savings

```python
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

batch = client.messages.batches.create(requests=[
    Request(custom_id=f"match-{i}",
            params=MessageCreateParamsNonStreaming(
                model="claude-opus-4-8", max_tokens=4000,
                system=[{"type":"text","text":BRAND_SYSTEM,
                         "cache_control":{"type":"ephemeral"}}],
                messages=[{"role":"user","content":f"Video from:\n{m}"}],
                output_config={"format": {"type":"json_schema","schema": VideoSpec.model_json_schema()}},
            ))
    for i, m in enumerate(matchday_data)
])
```

**Rough economics:** a 30s script spec is ~3–4K output tokens. At Opus 4.8 batch pricing (~$12.50/1M output) that's well under **$0.05 per video** on the language side — before caching savings on the input. The expensive part of a faceless page is *your time*, and that's exactly what this removes.

---

## 5. Visual sourcing — the no-footage model (where every pixel comes from)

**The key realization: our core videos use no match footage at all.** The "video" is generated graphics + AI imagery + voiceover, not clips. This is the entire reason the strategy survives copyright. "Official FIFA" footage is **not** a free source — reposting it gets Content-ID'd and struck exactly like a broadcaster's.

| Format | What's on screen | Source | Footage? |
|---|---|---|---|
| Shock Stat | Animated stat card | Nano Banana + Remotion | ❌ |
| Top-5 Countdown | Ranked stat graphics, crests | Nano Banana + Remotion | ❌ |
| This-or-That | Two players, one stat | Nano Banana + stock/licensed photo | ❌ |
| Season in Numbers | Animated stat cards | Nano Banana + Remotion | ❌ |
| Tactical breakdown | Animated pitch + arrows (Tifo-style) | Remotion diagrams | ❌ |
| Atmosphere/story | Cinematic crowd/stadium B-roll | AI (Higgsfield) or stock video | ❌ |

**The footage risk ladder** (know where the line is):
- ✅ **Safe** — generated graphics, AI B-roll, stock. Our whole strategy.
- ✅ **Sanctioned (but selective)** — official FIFA 2026 creator programs on **TikTok** (Creator Correspondents + GamePlan hub) and **YouTube** (now a "Preferred Platform," with a selected creator cohort getting match access). Both are invite/application-based and framed around our exact lane (tactical breakdowns, stories) — a growth goal, not a day-one asset. Licensed footage stays with media partners + the chosen cohort, *not* open to all creators.
- ⚠️ **Calculated risk** — short (≤~10s) clip + your VO, muted original audio, transformative. Legally defensible but *not* strike-proof (Content ID can still flag it).
- 🚫 **The trap** — reposting FIFA/broadcaster footage. What we avoid.

> The public **FIFA Audiovisual Archive** (archives.fifa.com) is *not* a usable source: its license is "visualisation only / private non-commercial," and any commercial use (a monetized page) needs a negotiated paid license. The richer "Digital Archive" access from the YouTube/TikTok deals is tied to the **selective creator cohorts** with unpublished terms — aspirational, not a day-one asset.

Player likeness caveat: generating a recognizable player's *face* raises a right-of-publicity issue separate from broadcast copyright (and AI mangles faces). Lead with **stat-forward cards, kits, crests, silhouettes** — let the numbers be the hero.

---

## 6. Where Claude stops and other tools start

| Stage | Tool | Notes |
|---|---|---|
| Ideation, scripting, captions, metadata | **Claude Code** (subscription) — `videospec` skill | runs on the subscription, not the metered API; emits a validated `VideoSpec` |
| Voiceover from the script | **ElevenLabs** (`elevenlabs/skills@text-to-speech`) | feed `scene.voiceover` |
| Captions/subtitles | **ElevenLabs STT** (`@speech-to-text`) | transcribe the VO → burn-in timing |
| Stats graphics | **Remotion** (React/CSS) — v1 | renders brand stat cards itself, **free**, crisper text than AI; this is the default |
| AI graphics / backgrounds (optional) | **Nano Banana** (Gemini image API — ⚠️ **needs billing**, ~$0.04/img) | richer backgrounds/atmosphere; free tier = 0 for the image model |
| Video assembly | **Remotion** (React→video) | composes graphics + VO + animated captions, driven by `VideoSpec` JSON |
| Cinematic B-roll (optional, phase 2) | **Higgsfield** (AI video) | AI stadium/atmosphere; credit-priced, reserve for hero/launch pieces |
| Posting (DEFAULT) | **Hybrid:** `pipeline/upload_youtube.py` (YouTube, official Data API) + the attended **`post-social`** skill (TikTok/IG, Playwright-MCP browser automation) | YT is API-direct; TikTok/IG are attended browser posts (owner clears captcha/login). Postiz is the legacy fallback. |

Claude is the only stage that needs *judgment*; everything else is deterministic glue. That's why the pipeline can run on a few minutes of your review per batch.

> **Static-post shortcut:** Nano Banana also makes single-image stat cards / carousels viable on day one — Claude writes the stat → Nano Banana renders the graphic → post. No video render, no TTS. The fastest path to shipping daily while the video pipeline is built.

---

## 7. Build order (so you don't boil the ocean)

1. **Nail the `BRAND_SYSTEM` prompt + `VideoSpec` schema** by hand in a notebook. Generate 5 specs, read them, tune the prompt. This is the highest-leverage hour you'll spend.
2. **Wire one spec → ElevenLabs VO → a single Remotion template.** One end-to-end video, fully automated, even if ugly.
3. **Add auto-captions** (ElevenLabs STT → burned-in).
4. **Batch it** — generate a whole matchday's specs in one Batches call.
5. **Add a scheduler.** Posting is last; the content engine has to work first.

You stay in the loop at step 1's prompt and a quick review of each batch — that's the "small time investment" target.
