---
name: analytics-review
description: Learn from published-video analytics and refine how videos are made. Use to REVIEW recent YouTube performance (retention curves, swipe-away, subscribe/comment conversion) and distill durable LEARNINGS into kb/learnings.json that the videospec skill auto-applies — closing the loop from "what a video actually did" back into "how the next one is built". Also a BRIEF mode that returns the active learnings videospec should read before scripting. Runs on the Claude subscription; the deterministic data pull is pipeline/youtube_analytics.py collect.
---

# analytics-review — the learning loop for TikiTakaFootyTV

This is the **fourth engine**: outlier = what's viral elsewhere, soccer-news = what's
true now, videospec = grounded × viral → spec, **and this = what actually WORKED on our
channel → how to make the next video better.** It closes the open loop between the
analytics we can measure (`pipeline/youtube_analytics.py`) and the brain that creates
(`videospec`).

The judgment is yours (Claude's): reading a retention curve and naming the craft lesson
is not something naive aggregation can do — especially while N is tiny. The deterministic
glue is `pipeline/youtube_analytics.py collect`, which joins each published video's
analytics with its spec's design levers into `analytics/performance.jsonl`. You interpret
that store and maintain `kb/learnings.json`.

Two modes, chosen from the skill argument:

## Mode: `review` (default)

Refresh the data, interpret it per-video and across videos, and update the learnings.

1. **Collect.** First `uv run pipeline/youtube_analytics.py inventory --backfill` (discovers
   the whole channel via the Data API and logs any videos missing from the post-log), then
   `uv run pipeline/youtube_analytics.py collect` to refresh `analytics/performance.jsonl`.
   Every video gets **near-real-time public stats** (views/likes/comments, no lag);
   **retention + subscribersGained + averageViewPercentage** fill in once a video matures
   (~2–3 days) — `analytics_ready:false` means retention hasn't processed yet. Read the store.

2. **Per-video read.** For each record, interpret the outcome against the design.
   **Metric semantics matter** — `audienceWatchRatio` can exceed 100% (loops), so there is NO
   clean absolute "hook survival %"; use these instead:
   - **Overall hold** — `retention.avg_view_pct` (the clean absolute headline: % of the video
     the average viewer watched). Compare to `channel_baseline.median_avg_view_pct`.
   - **Hook / early body** — `retention.early_leak` = fraction of the OPENING audience lost by
     ~15% elapsed. Small early_leak + low `retained_to_end` ⇒ the hook worked but the body bled.
     Attribute to `design.hook_type` + `design.first_frame_text`.
   - **Biggest leak** — `attribution.biggest_leak_scene` names the scene/beat with the steepest
     drop (mapped from the curve via scene durations). Say it concretely: "the leak is at scene
     N, your <graphic_type> beat — <on_screen_text>".
   - **End / loop** — `retention.retained_to_end` (opening-audience fraction still watching at the
     end) against `design.retention_mechanic`: did the loop/countdown/reveal hold them?
   - **vs comparable videos** — `retention.mean_relative_performance` (>1.0 = retains better than
     similar YouTube videos), when present.
   - **Conversion** — `attribution.subscribe_conversion`, `comment_conversion`, `like_rate`
     (denominator = near-real-time public views). Did the subscribe beat
     (`design.has_subscribe_scene`) and the `comment_bait` convert?

3. **Cross-video patterns.** Group records by design lever (`format`, `hook_type`,
   `retention_mechanic`, the `graphic_type` where leaks cluster, length). Look for
   *directional* signal, not significance ("quizzes ~370 avg views vs ~1000+ for narratives,
   N=2"). Use public views/engagement for ALL videos (no lag) and retention only for the
   matured subset. Down-weight any single view-dominating outlier and say so.

4. **Distill into `kb/learnings.json`** (schema below). ACCUMULATE — don't overwrite
   history: strengthen a learning when a new video agrees (raise `n`, maybe `confidence`),
   weaken/mark `superseded` when it disagrees. Refresh `channel_baseline` (the medians).
   Each learning carries a concrete `proposed_rule_change` — the actual nudge `videospec`
   applies.

5. **Report** what changed: new learnings, strengthened/weakened ones, the current
   baseline, and the 1–2 highest-leverage changes for the next video.

## Mode: `brief`

What `videospec` consumes before scripting (analogous to soccer-news `ground`). Read
`kb/learnings.json` and output ONLY:
- `channel_baseline` (the current medians + conversion) in one line.
- Every `status:"active"` learning as a tight bullet: the `finding`, its
  `proposed_rule_change`, and its `confidence`/`n` — **sorted high → low confidence**.
- A one-line "apply this first": the single highest-confidence change relevant to the
  format/hook about to be made.

Keep it short — this is injected into another skill's context, so no raw data dumps.

## Hard rules — the tiny-N discipline (this is what keeps the loop honest)

The channel started **2026-06-01**; N is in single digits. Overfitting to 1–2 videos
would make the loop actively harmful, so:

- **Every cross-video generalization is a HYPOTHESIS, never a law.** A learning may be
  written at N=1, but it MUST then carry `confidence:"low"` and `n:1`.
- **Confidence graduates `low → med → high`** only as `n` grows AND the direction holds:
  roughly `low` at N≤2, `med` at N 3–4 with a consistent direction, `high` only at **N≥5**
  with a consistent direction. `videospec` hard-applies only `high`; `low`/`med` are
  tie-breakers.
- **Never delete or contradict a standing videospec viral rule on 1–2 videos.** Propose
  ADDITIVE, reversible nudges ("try a question first-frame for news_story"), not "always".
- **Per-video facts are high-confidence; generalizations are not.** "This video held 40% to
  the end" is solid; "narratives beat quizzes" is a low/med hypothesis until N≥5.
- **Don't invent metrics.** Use only what's in the store / the Analytics API. If
  `retention` is null (`analytics_ready:false`), say "retention pending", don't guess — but
  public views/likes/comments are always available, so still read those.
- **Date everything.** `as_of`/`first_seen`/`last_updated` = the harness date (today).
- When a learning is contradicted enough to flip, set the old one's `status:"superseded"`
  (keep it for history) and write the replacement — never silently rewrite.

## `kb/learnings.json` schema

A single JSON file (so `videospec` reads it in one shot). It SUPERSEDES the hand-typed
"video #1" calibration block that used to live in the videospec skill.

```jsonc
{
  "last_updated": "2026-06-13",
  "videos_analyzed": 8,
  "videos_with_retention": 3,
  "channel_baseline": {
    "median_avg_view_pct": 66,            // averageViewPercentage — the clean retention headline
    "median_retained_to_end": 0.19,       // opening-audience fraction still watching at the end
    "subscribe_conversion": 0.0018,
    "comment_conversion": 0.006,
    "like_rate": 0.024,
    "as_of": "2026-06-13",
    "based_on_n": 3
  },
  "learnings": [
    {
      "id": "quiz-underperforms-on-views-and-retention",   // stable kebab id
      "lever": "format",                          // format|hook_type|retention|scene|subscribe|comment|length
      "finding": "quiz_top5 ~370 avg views vs ~1000+ for narratives, and worst retention (13-19% to end).",
      "proposed_rule_change": "Keep quiz_top5 as rare seasoning; if used, <=25s and front-load the payoff.",
      "evidence_video_ids": ["AsVa5jasPCA", "fWhVgNyuGoQ"],
      "n": 2,
      "confidence": "med",                        // low|med|high  (videospec hard-applies only high)
      "direction_holds": true,
      "status": "active",                         // active|superseded|retired
      "first_seen": "2026-06-13",
      "as_of": "2026-06-13"
    }
  ]
}
```

## How videospec uses this

`videospec` reads `kb/learnings.json` before scripting: it applies the `channel_baseline`
and every `status:"active"` learning, **auto-applying `high`-confidence findings as rules**
and treating `low`/`med` as tie-breakers, over its static defaults where they conflict. If
the file is absent/empty it falls back to the founding finding (hook is the bottleneck;
0% subscribe conversion → win the first second and capture the subscribe).

## Scheduling

Run **on-demand** — there is no schedule. Analytics lag ~2–3 days, so trigger
`analytics-review review` when you want a fresh read (e.g. a few days after a batch of
posts). `collect` only ingests videos old enough to have data, so re-running early is safe
(it just skips the young ones).
