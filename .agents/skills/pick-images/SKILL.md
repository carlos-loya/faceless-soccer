---
name: pick-images
description: Vision-select the correct background image for a video's one-off `commons` scenes. Use after fetch_scene_candidates.py has downloaded candidates and before make_video.sh. Claude looks at each candidate and picks the one that actually depicts the scene's subject (keyword search returns plausible-but-wrong images, e.g. "World Cup trophy" → Germany lifting it). Writes choices.json the renderer consumes.
---

# pick-images — choose the right image with your eyes

Keyword image search returns *plausibly-related but wrong* images. This step fixes that by
**looking** at the candidates and picking the correct one. Runs on the subscription (vision
judgment) between `fetch_scene_candidates.py` and `make_video.sh`.

## What to do

1. Read `out/candidates/<stem>/candidates.json` — a map of `sceneIndex →
   { query, on_screen_text, voiceover, candidates: [{ index, file, title, credit }] }`.
2. For each scene, **`Read` every candidate image file** (the Read tool shows you the image).
3. Pick the single best candidate against the rubric below — or **none**.
4. Write `out/candidates/<stem>/choices.json`: `{ "<sceneIndex>": "<chosen file path>" | null }`.
   `null` = no candidate is good enough → the scene falls back to a clean brand graphic
   (better than shipping a wrong image).
5. Report each pick with one line of reasoning (what it shows, why it fits / why others were rejected).

## Rubric — pick the image that…

- **Depicts EXACTLY the subject** the scene's VO/text is about (the thing itself).
- **Has NO conflicting branding** — for a generic subject (the trophy, a stadium type), reject
  shots dominated by a *specific* team/player/nation that isn't this video's subject. A
  Germany-celebrating-with-the-trophy shot is WRONG for an Argentina/Messi video.
- **Works in 9:16** — prefer portrait or square; reject wide landscape group shots (they crop badly).
- **Clean & clear** — the subject is the focus, well-lit, uncluttered, not a tiny detail in a busy frame.
- When in doubt between two, pick the cleaner/more iconic one. If NONE qualify, choose `null`.

## Curate recurring subjects

If a scene's subject is something that will recur (the World Cup trophy, a major stadium, the
Ballon d'Or), don't just pick for this video — **promote the chosen image to a curated KB entity**
(`kb/entities/<slug>.json` with the image url/license/attribution + `"curated": true`) so future
videos reference it via `visual_source: "entity"` and never re-search. Then they're correct by
construction. (This is how `fifa-world-cup-trophy` was created.)

## In the pipeline
```
videospec → fact-check → fetch_scene_candidates.py → pick-images (you) → make_video.sh
```
`prepare.mjs` reads `choices.json`: a chosen file is used as that scene's background; absent/`null`
falls back to the existing search (or a brand graphic).
