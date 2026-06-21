---
description: Pull the channel's analytics and report what's working / what's wrong, then update the learnings the videospec brain applies
argument-hint: "[optional: a focus, e.g. 'retention' or a stem]"
allowed-tools: Bash, Read, Write, Edit, Skill
---

Run the full TikiTakaFootyTV analytics pipeline and give me a candid read on what we're
doing right and — more importantly — what we're doing wrong. Optional focus: $ARGUMENTS

Do this in order:

1. **Discover + log** every channel video (catches anything published outside the
   auto-logging upload path):
   `uv run pipeline/youtube_analytics.py inventory --backfill`

2. **Collect** the analytics into the performance store (near-real-time public stats for
   ALL videos; retention/avg-view-%/subs for the matured ones — analytics lags ~2–3 days):
   `uv run pipeline/youtube_analytics.py collect`

3. **Interpret + learn** — invoke the **`analytics-review`** skill in `review` mode. It reads
   `analytics/performance.jsonl`, interprets each video and the cross-video patterns, and
   updates `kb/learnings.json` (the file the `videospec` brain auto-applies). Honor its
   tiny-N discipline: findings are hypotheses, confidence `low`/`med` until N≥5.

4. **Report back** to me in plain language, verdict-first:
   - **The numbers** — a compact table: per video, views (no lag) + retention (matured only:
     `avg_view_pct`, `retained_to_end`, biggest-leak scene) + like/comment/subscribe rates.
     Flag which videos are still within the analytics lag (retention pending).
   - **✅ What's working** — the formats / hooks / lengths that over-perform, with the metric.
   - **❌ What's wrong** — the biggest problems, each tied to a specific lever and the scene/
     beat it shows up in (e.g. "quizzes bleed out before the reveal — leak at the quiz_board
     beat"). Be direct; this is the point of the command.
   - **What changed in `kb/learnings.json`** — new/strengthened/weakened learnings.
   - **Do-next** — the 1–2 highest-leverage changes for the next video.

Notes:
- Metric honesty: `audienceWatchRatio` can exceed 100% on loops, so there's no clean absolute
  "hook survival %" — lead with `averageViewPercentage` and the curve shape, not a raw start value.
- Don't spend ElevenLabs/render credits; this is read-only analysis + a learnings-file update.
- If retention is pending for most videos (a fresh batch), say so and lean on public stats —
  re-run in 2–3 days for the retention picture.
