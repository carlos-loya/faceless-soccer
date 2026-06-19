---
name: soccer-news
description: Maintain and query the canonical soccer knowledge base (kb/) — the grounding engine. Use to REFRESH current facts/narratives for players, clubs, nations (so videos aren't built on stale training memory), or to GROUND a topic before scripting (returns current, dated, sourced facts + active narratives for the videospec skill). Runs on the Claude subscription via web research; writes dated, sourced JSON to kb/.
---

# soccer-news — grounding engine for TikiTakaFootyTV

Maintains `kb/` (see `kb/schema.md`): a **dated, sourced** store of soccer **facts** and **narratives** so generated videos are grounded in *current reality*, not the model's training cutoff. This is engine #2 of three (outlier = what's viral, **this = what's true now**, videospec = grounded × viral → spec).

Two modes, chosen from the skill argument:

## Mode: `refresh <target>`
`target` = an entity slug (`lamine-yamal`), `narratives`, `watchlist` (everything), or `stale` (only entries past their freshness policy).

For each entity/narrative:
1. **Research** — `WebSearch` for the current state ("<name> latest 2026", "<name> world cup 2026", "<name> injury/transfer/form"). `WebFetch` the 1–3 best, most recent, most reputable sources.
2. **Extract** the time-sensitive facts (age, club, nation, position, fitness, current form, WC role, fresh records) and any **active narratives** (storylines, debates, quotes, injury/transfer sagas).
3. **Verify** — cross-check contested facts against ≥2 sources. If sources disagree, take the most recent/reputable and set `confidence: "low"|"med"`. Prefer official/major outlets; treat aggregators/blogs as weak.
4. **Write** to `kb/entities/<slug>.json` / `kb/narratives/<slug>.json` per `kb/schema.md`:
   - every fact gets `value`, `as_of` (the date it was true/reported), `source` (URL), `confidence`;
   - set `last_verified` to today;
   - link entities ↔ narratives (`active_narratives` / `entities`).
5. **Report** what changed (new facts, corrections, new/cooled narratives).

**Hard rules:**
- Never write a time-sensitive fact without a dated source URL. No source → leave it out.
- **Never fabricate** a source or an image URL. Leave `image: null` + an `image_todo` if no verified Creative-Commons/public-domain image is found.
- Freshness beats completeness — a confidently wrong "now" fact is worse than a gap.
- Today's date is the harness date; use it for `as_of`/`last_verified` (convert any relative "yesterday/last week" to absolute).

## Mode: `ground <topic-or-entity>`
Produce the grounding brief `videospec` consumes before scripting:
1. Resolve the topic to entity slug(s).
2. Read `kb/entities/<slug>.json` + linked `kb/narratives/*`. If **missing or stale** (per `watchlist.json` `refresh_policy`), run `refresh` on it first.
3. Output a concise brief:
   - **Current facts** (with `as_of` dates) — especially the ones that go stale: age, club, fitness, form, WC role.
   - **Active narratives** (hottest first) + their ready-to-use **angles**.
   - **Sources**.
   - **A one-line "currency check"**: the single most important way reality differs from a naive/old take (e.g. "He is 18 now and leads Spain — NOT a 16-year-old prospect").

## Image layer (optional, connects to the no-footage rule)
During refresh, you *may* look for a **Creative-Commons / public-domain** portrait (Wikimedia Commons) and record `{url, license, attribution, as_of}` on the entity — free + legal with attribution. Do **not** record agency photos (Getty/AP — copyrighted) or iconic match-moment shots (almost always agency-owned). No verified CC image → leave it null.

## Scheduling
During the WC window (`watchlist.json` → `wc_window`), the user can `/schedule` `soccer-news refresh stale` (or `watchlist`) **daily** so the KB stays current.

## How videospec uses this
`videospec` calls `ground <subject>` first and bases every time-sensitive claim on the returned brief (its ACCURACY rule). The KB's hot narratives are also a prime **idea source** — grounded *and* topical.
