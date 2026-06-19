# Outlier-Discovery Engine — Technical Spec

The hardest part of Subscribr to replicate, and the most valuable. This engine continuously finds soccer videos that **massively overperformed their channel's baseline** — the outliers that reveal *what's working right now* — and feeds them into Claude for formula extraction (see VIRAL-FORMULA.md) and ideation (PLAYBOOK.md job #1).

This is a spec, not an implementation. It defines the concept, data source, architecture, data model, scoring, and build phases.

---

## 1. The core concept: what is an "outlier"?

A video is an outlier when its views vastly exceed **its own channel's typical performance** — not when it has high absolute views. A 300k-view Short on a 15k-follower page is a far stronger signal than 300k on a 5M page.

```
outlier_score = video_views / channel_baseline
```

Where `channel_baseline` = the **median** views of that channel's recent videos (median, not mean — robust to the very outliers we're hunting). Score ≥ ~3× on a recent video = worth analyzing.

This normalizes for channel size, which is exactly why outlier analysis beats "most-viewed" lists.

---

## 2. Data source: YouTube Data API v3 (the sanctioned path)

- **Free**, default quota **10,000 units/day**. No scraping, no ToS risk.
- Scope **YouTube first** (Shorts are the World Cup battleground anyway). Instagram/TikTok have **no free official API** for this — they'd need paid third-party data providers (Phase 5, optional).

### The quota math is the whole architecture

Endpoint costs are wildly uneven — design around the cheap ones:

| Endpoint | Cost | Use |
|---|---|---|
| `search.list` | **100 units** | Avoid for routine work — only ~100 calls/day. Discovery only. |
| `playlistItems.list` | **1 unit** / 50 items | **Primary ingestion** — list a channel's recent uploads |
| `videos.list` | **1 unit** / 50 IDs | Batch-fetch stats (views, likes, comments), duration, tags |
| `channels.list` | **1 unit** | Get subscriber count + the channel's "uploads" playlist ID |

**Key insight:** never use `search` to monitor known channels. Every channel exposes an "uploads" playlist; pull it via `playlistItems.list` (1 unit per 50 videos) → batch the IDs into `videos.list` (1 unit per 50). Monitoring **hundreds of channels/day costs only a few hundred units** — a fraction of the 10k budget, leaving room for velocity polling.

---

## 3. Architecture

```
┌─ Seed list (config) ─┐   curated soccer channels to monitor
│  faceless pages,     │   (the VIRAL-FORMULA.md accounts + competitors)
│  competitors, lanes  │
└──────────┬───────────┘
           ▼
   ┌───────────────┐   playlistItems.list + videos.list (cheap)
   │  Ingestion    │ ─────────────────────────────────────────►  raw video stats
   └──────┬────────┘
          ▼
   ┌───────────────┐   median per channel, per duration bucket
   │  Baseline     │ ─────────────────────────────────────────►  channel_baseline
   └──────┬────────┘
          ▼
   ┌───────────────┐   outlier_score + velocity + recency filter
   │  Scoring      │ ─────────────────────────────────────────►  flagged outliers
   └──────┬────────┘
          ▼
   ┌───────────────┐   dedup vs already-analyzed
   │  Outlier feed │ ─────────────────────────────────────────►  ranked fresh outliers
   └──────┬────────┘
          ▼
   ┌───────────────┐   Claude dissects vs VIRAL-FORMULA rubric
   │  Analysis     │ ─────────────────────────────────────────►  structured formula records
   └──────┬────────┘
          ▼
     Ideation context  ──►  VideoSpec generation  ──►  production pipeline
```

Periodically (every few hours), a lightweight **velocity poll** re-fetches stats for recent videos to catch outliers *while they're still rising* — this is what lets you ride a trend, not just autopsy it.

---

## 4. Data model (SQLite to start → Postgres at scale)

```sql
channels(
  channel_id PK, handle, name, subscriber_count,
  uploads_playlist_id, lane,          -- 'stats' | 'banter' | 'edits' | ...
  added_at
)

videos(
  video_id PK, channel_id FK, title, description,
  published_at, duration_s, is_short, -- is_short = duration_s <= 60
  thumbnail_url, tags
)

video_stats(                          -- time series (one row per poll)
  video_id FK, captured_at,
  view_count, like_count, comment_count
)

outliers(
  video_id FK, detected_at,
  outlier_score, velocity, baseline, status  -- 'new' | 'analyzed'
)

formulas(                             -- Claude's dissection output
  video_id FK, analyzed_at,
  hook_type, format_archetype, emotional_trigger,
  retention_mechanic, comment_driver, raw_json
)
```

`video_stats` as a time series is what enables **velocity** (views-per-hour between polls) — the early-warning signal.

---

## 5. Scoring algorithm

```python
# Per channel, per duration bucket (Shorts vs long-form scale very differently)
def baseline(channel, bucket):
    vids = videos(channel, bucket, aged_more_than="7d", within="6 months")
    return median(v.view_count for v in vids)   # median ignores the outliers

def score(video):
    base      = baseline(video.channel, video.bucket)
    age_days  = (now - video.published_at).days
    o_score   = video.view_count / base
    velocity  = view_count_delta / hours_delta      # from video_stats snapshots
    is_outlier = o_score >= 3.0 and age_days <= 30  # tunable thresholds
    return o_score, velocity, is_outlier
```

**Critical nuances:**
- **Median, not mean** for the baseline — the mean gets dragged up by the very hits we're chasing.
- **Bucket by duration** — Shorts (≤60s) and long-form have totally different view scales; never pool them.
- **Age maturity** — fresh videos haven't accumulated views. Either only *score* videos older than ~72h, or rank by **velocity** (views/day) to catch rising ones early.
- **Exclude immature videos from the baseline** (aged > 7d) so the denominator is stable.

---

## 6. Integration with our pipeline — closing the loop

```
Outlier engine ──► fresh outliers ──► Claude dissection (VIRAL-FORMULA rubric)
   ──► formula records ──► ideation prompt context ──► VideoSpec (PLAYBOOK)
   ──► Nano Banana graphics + ElevenLabs VO + Remotion ──► finished post
```

This is the payoff: we stop *guessing* what's viral and start **mining what overperformed this week**, then rebuild it copyright-safe under TikiTakaFootyTV. The `formulas` table directly enriches the `BRAND_SYSTEM` prompt's examples over time — the system learns what works in *our* niche.

---

## 7. Build phases

| Phase | Deliverable | Effort |
|---|---|---|
| **0** | Seed list (config of ~50–200 soccer channels by lane) | trivial |
| **1 — MVP** | Daily ingest (playlistItems + videos.list) → baseline → outlier scoring → ranked feed | small |
| **2** | Velocity snapshots (periodic re-poll) for early detection of rising outliers | small |
| **3** | Claude auto-dissection → `formulas` records | small (we have the rubric) |
| **4** | Discovery — find *new* channels via `search.list` / related-channel crawl (quota-managed) | medium |
| **5** | IG/TikTok via paid third-party data providers | medium (paid, optional) |

Phases 1–3 are the whole value and are cheap to build. Phase 4+ is expansion.

---

## 8. Scope, risks, and decisions

- **Quota is the binding constraint, and we're well within it.** ~200 channels × ~2 units/day ≈ 400 units, vs 10k budget. Plenty of headroom for velocity polls. Only `search`-based *discovery* (Phase 4) eats quota.
- **YouTube only, by design.** The Data API is the only free, sanctioned, reliable source. IG/TikTok lack an equivalent — defer to paid providers and don't scrape (fragile + ToS violation).
- **The moat is the data + the baselines**, not the code. Subscribr's edge is its accumulated channel database; ours grows the same way — every day of ingestion makes the baselines and formula library better. Start the seed list now so the history compounds.
- **Tech stack:** Python or Node, SQLite → Postgres, a scheduler (cron / our `/schedule`) for daily ingest + periodic velocity polls, Claude API for the analysis stage.
- **Get a YouTube Data API key** (free, Google Cloud console) — same account as the Nano Banana / AI Studio key.

---

## 9. The MVP, concretely

1. Hand-build the **seed list** (~50 soccer channels across stats/banter/edits lanes — start with the VIRAL-FORMULA.md accounts' YouTube channels + obvious competitors).
2. Script the **daily ingest**: for each channel → `channels.list` (uploads playlist + subs) → `playlistItems.list` (recent 50) → `videos.list` (stats + duration). Store in SQLite.
3. Compute **per-channel median baselines** (bucketed by Shorts/long-form).
4. Flag + rank **outliers** (`score ≥ 3×`, `age ≤ 30d`).
5. Output a **daily ranked feed** of fresh outliers (title, thumbnail, score, link).
6. (Phase 3) Pipe each into **Claude** → structured formula record → ideation context.

That MVP — seed list + daily ingest + median baseline + outlier ranking — is the core of Subscribr's hardest feature, soccer-tuned and owned by us.
