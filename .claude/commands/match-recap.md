---
description: Turn one finished World Cup match into a copyright-safe recap video — ground the game report, script, fact-check, and render (draft by default; production/publish only when told)
argument-hint: "[fixture id like r16-05, or blank to auto-pick the most recent finished notable match] [--produce] [--publish]"
allowed-tools: Bash, Read, Write, Edit, Skill, AskUserQuestion
---

Make a post-match recap for one WC2026 fixture. Arguments: $ARGUMENTS

This is the per-match unit the automated pipeline (`pipeline/auto/run_match_pipeline.sh`) drives,
and it also runs by hand. **The fact-check in step 4 is a HARD GATE**: if a claim can't be
verified, STOP — do not render, do not publish. A wrong fact in an auto-published video is worse
than a missed match.

**Flags** (default = free draft, stop for review):
- `--produce` → render real ElevenLabs VO after fact-check passes (spends credits).
- `--publish` → `--produce`, and the caller (the orchestrator) will upload to YouTube. TikTok/IG
  are **never** auto-posted here — a handoff packet is written for the owner's attended run.

1. **Resolve the fixture.** If `$ARGUMENTS` names a fixture id, use it; otherwise pick the most
   recent finished notable match: `uv run pipeline/fixtures.py recent --notable --json`. Read the
   match (teams, stage, date, result) from `kb/fixtures.json`. If the match has no `result`, it is
   **not confirmed final** — STOP (the auto orchestrator gates on this via `fetch_result.py`, so a
   missing result means the match isn't over). For a manual run you can fetch it deterministically
   first: `uv run pipeline/auto/fetch_result.py <id> --write`.

   **The `result` block is AUTHORITATIVE ground truth.** When it carries `"source":"espn"` /
   `"verified":true`, its `home`/`away` score and `scorers` (player + minute) are what actually
   happened — use them **verbatim** in the script and scoreboard. Never override them from model
   memory or a web source.

2. **Ground the game report.** Invoke the **`soccer-news`** skill in `ground` mode on the match
   ("<Home> vs <Away>, WC2026 <stage> — key moments and storylines"). Use it for **narrative and
   context only** — the turning point, cards/VAR, the standout performer, the one talking point.
   **It MUST NOT change the score or scorers**: those come from the verified `result` block above.
   If web sources disagree with the KB score, trust the KB (ESPN) and never invent a scorer (a real
   past miss: "Zico scored both Egypt goals"). Grounded, dated, sourced — never from memory.

3. **Script it.** Invoke the **`videospec`** skill on that report in the **`post_match`** format:
   a running TV scoreboard that ticks with the real score (both nations need flag images — see the
   scoreboard convention), a hook that wins the first second, a real subscribe beat, a seamless
   loop. It grounds via `soccer-news` and applies `kb/learnings.json` automatically, and writes
   `out/specs/<stem>.json`.

4. **Fact-check — HARD GATE.** Invoke the **`fact-check`** skill on the spec, especially any
   superlative ("first/only/most/youngest/fastest"). Correct in place. **If a claim can't be
   verified even after reframing, halt: do not proceed to render.** Record the outcome for step 7.

5. **Vision-vet one-off images (only if needed).** For any `commons` scenes, run
   `uv run pipeline/fetch_scene_candidates.py out/specs/<stem>.json` then the **`pick-images`**
   skill so the renderer uses the right picture.

6. **Render.**
   - Default: `bash pipeline/make_video.sh out/specs/<stem>.json` — FREE draft, then STOP and hand
     off for review (same as `/daily`).
   - `--produce` / `--publish`: `TTV_PRODUCTION=1 bash pipeline/make_video.sh out/specs/<stem>.json`
     (spends ElevenLabs) — only after step 4 passed.

7. **Write the receipt** so the orchestrator knows what happened. Save
   `out/auto/receipts/<fixture-id>.json`:
   ```json
   {"fixture_id":"<id>","stem":"<stem>","spec":"out/specs/<stem>.json",
    "render":"<path or null>","factcheck":"pass|halt","mode":"draft|produce|publish","as_of":"<date>"}
   ```
   The orchestrator publishes **only** when `factcheck` is `pass` and the production render exists.

8. **Report:** the fixture, the angle/hook, the format, fact-check corrections, the render path,
   and — for a manual draft run — the exact owner next steps (produce → publish), never run by you.

Guardrails:
- **Draft-first for manual runs.** Only `--produce`/`--publish` (the orchestrator, or the owner)
  spends credits.
- **Fact-check is non-negotiable** — the auto path halts silently-safe (no render → no publish).
- **TikTok/IG stay attended** — this command never posts to them; it leaves a `post_packet.py`
  handoff for the `post-social` skill.
