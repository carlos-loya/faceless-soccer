---
name: fact-check
description: Fact-check a generated VideoSpec against the canonical KB (and current sources) BEFORE production. Use after videospec generates a spec and before make_video.sh. Catches false/contradicted/unsupported claims — especially superlatives ("first/only/nobody/most") — and corrects them in place. A wrong fact in a published video destroys credibility.
---

# fact-check — verify a VideoSpec before it ships

Given a spec path (`out/specs/<stem>.json`), check every factual claim in its `voiceover`,
`on_screen_text`, `stat_callout`, hook, captions, and `comment_bait` against the canonical
KB (`kb/entities`, `kb/narratives`) — and where the KB is silent, against `WebSearch`. Then
**correct the spec in place** and report what changed.

This runs on the Claude subscription (judgment). It is the safety net between the brain
(`videospec`) and production (`make_video.sh`).

## What to do

1. **Load the spec** and the KB entities/narratives it references (its `subject` + every
   `entity`/`commons` `visual_query` + any player/club/nation/stadium named in the VO).
2. **Extract every checkable claim** — ages, clubs, nations, records, "this season" stats,
   fitness/availability, dates, and especially **superlatives**.
3. **Verify each claim:**
   - **Ordinary current facts** (age, club, nation, role): the KB is the source of truth (it's
     dated). The claim must match it exactly.
   - **Superlatives / records** — "first / only / nobody / never / most / youngest / oldest /
     record" — **the KB is NOT sufficient; it can be incomplete.** ALWAYS verify these against
     current external sources, and verify **adversarially**: actively search for a COUNTEREXAMPLE
     ("who else has done X", "full list of players who…", "has anyone else ever…"). Treat the
     claim as false until you've seen the complete picture.
     > This is the exact trap that shipped a wrong claim twice: the KB narrative first said
     > "nobody," then "only Messi & Ronaldo," have played six World Cups — but **Guillermo Ochoa
     > does too** (three total, and Ochoa may even be first). The KB missed him; only an external
     > counterexample search catches it. Never trust the KB to *prove* a superlative.
   - If the KB is **silent** on a specific/risky claim → `WebSearch` to confirm; if unconfirmed, cut it.
4. **Correct the spec in place** — edit the offending `voiceover` / `on_screen_text` /
   `comment_bait` so it's accurate, preserving the hook's punch. Keep edits minimal.
5. **Report**: list each claim as ✅ verified / ✏️ corrected (old → new) / ⚠️ removed, then a
   final **PASS** (safe to produce) or **NEEDS REVIEW** (a claim you couldn't resolve).

## Rules

- **Superlatives are guilty until proven, and the KB cannot prove them.** Every "first / only /
  nobody / never / most / best / youngest / oldest / record" claim needs an EXTERNAL, adversarial
  check — search for *who else qualifies*, not just whether the KB agrees (the KB is often
  incomplete). If you can't establish the complete set, reframe to avoid the count ("one of only a
  handful ever") rather than asserting a false "first/only". Most false claims hide here.
- **Don't fabricate a fix** — if you correct a number, the new number must be KB- or
  source-backed. When unsure, go qualitative ("one of the youngest ever") rather than precise.
- **Preserve the brand voice and the format** — fix the fact, not the vibe.
- Time-sensitive facts come from the KB (it's dated); if a KB fact is stale (past its
  freshness policy), refresh it via `soccer-news` first.

## In the pipeline

```
videospec (spec) → fact-check (verify + correct) → make_video.sh (produce)
```
Always fact-check before `make_video.sh`. A video is only as trustworthy as its weakest claim.
