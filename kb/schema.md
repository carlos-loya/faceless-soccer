# Canonical Knowledge Base — schema & conventions

The grounding engine (#2 of three: outlier = what's viral, **KB = what's true now**, videospec = grounded × viral → spec). A dated, sourced store of soccer-verse **facts** and **narratives** that `videospec` reads so generated videos are grounded in current reality — not the model's stale training memory.

Maintained by the **`soccer-news` skill** (refresh + ground). Everything here is JSON on disk so both the skill and a human can read/edit it.

## Layout
```
kb/
  watchlist.json            # canonical scope: which entities/narratives to track + refresh policy
  entities/<slug>.json      # one player / club / nation
  narratives/<slug>.json    # one active storyline
  schema.md                 # this file
```

## The non-negotiables
1. **Every time-sensitive fact carries a date (`as_of`) and a `source` URL.** No dated source → don't write it.
2. **Freshness over completeness.** A confidently *wrong* current fact is worse than a missing one — it destroys credibility.
3. **Cross-check contested facts** (≥2 sources) before writing; lower `confidence` if sources disagree.
4. **Never fabricate** a source URL or an image URL. Leave the field null + a `*_todo` note instead.

## Entity record (`entities/<slug>.json`)
```jsonc
{
  "slug": "lamine-yamal",
  "type": "player",                 // player | club | nation
  "name": "Lamine Yamal",
  "aliases": ["Yamal"],
  "facts": {                        // each fact is dated + sourced
    "age":  { "value": 18, "as_of": "2026-06-09", "source": "https://…", "confidence": "high" },
    "club": { "value": "Barcelona", "as_of": "2026-06-09", "source": "https://…", "confidence": "high" }
    // position, nation, fitness, form, wc_role, records … as relevant
  },
  "image": null,                    // { url, license, attribution, as_of } once a CC/PD image is verified
  "image_todo": "fetch + verify a Creative-Commons portrait; no fabricated URLs",
  "active_narratives": ["yamal-next-messi"],
  "last_verified": "2026-06-09"
}
```
`confidence`: `high | med | low`. `as_of`: YYYY-MM-DD the fact was true/reported.

## Narrative record (`narratives/<slug>.json`)
Storylines are what make content resonate — and they're exactly what's in today's news.
```jsonc
{
  "slug": "yamal-next-messi",
  "headline": "Yamal anointed the next Messi heading into WC 2026",
  "summary": "1–3 sentences, plain and current.",
  "entities": ["lamine-yamal", "spain"],   // links to entity slugs
  "heat": "hot",                            // hot | warm | cool  (how live the story is)
  "as_of": "2026-06-08",
  "sources": ["https://…", "https://…"],
  "angles": ["ready-to-use content angles / debate questions"],
  "last_verified": "2026-06-09"
}
```

## Freshness policy (in `watchlist.json`)
- `facts_days`: re-verify entity facts older than N days.
- `narratives_days`: re-verify narratives older than N days.
- `wc_mode: "daily"`: during the World Cup window, refresh everything daily.
An entry is **stale** when `last_verified` is older than its policy → `soccer-news refresh` should re-check it before `videospec` grounds on it.
