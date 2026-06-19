# AI b-roll prompt pack — TikiTakaFootyTV atmosphere library

Ready-to-paste prompts for generating the reusable **texture-lane** b-roll (Higgsfield / Kling / Veo /
Runway). These are CONNECTIVE atmosphere clips reused across many videos — generate once, reuse all
tournament. Each drops into this folder as `assets/broll/<slug>.mp4` + a `credits.json` line.

## Rules baked into every prompt
- On-brand by birth: deep black + warm gold/amber light (needs almost no grading; reinforces identity).
- Copyright/face-safe: NO recognizable faces, NO real kits/crests, **NO FIFA/World Cup logos, emblem or
  trophy** (IP — use the curated CC trophy image instead). Humans stay distant / silhouetted / blurred.
- Text-safe + loopable: vertical 9:16, slow motion, calm dark empty space in the CENTER (captions land
  there), seamless loop, slow/smooth camera only (fast motion = AI artifacts + fights captions).

## Settings (set in the tool, not the prompt)
Aspect **9:16 vertical** · **slow motion** · ~6–10s · seamless loop if available · highest quality.

## Negative prompt (paste where the tool supports it)
`faces, close-up people, text, captions, watermark, logo, brand mark, jersey, crest, scoreboard, fast
motion, camera shake, jitter, warping, distortion, extra limbs, daylight, oversaturated, cartoon`

## Shared STYLE SUFFIX — append to EVERY prompt below (this is what makes the set cohere)
> `Cinematic premium broadcast quality, deep near-black background, warm gold and amber stadium light,
> high contrast, volumetric haze, shallow depth of field, slow motion, smooth subtle camera move, calm
> dark empty space in the centre of the frame, moody, vertical 9:16. No visible faces, no text, no logos.`

## Generate these 5 FIRST (cover hook + tension + triumph + neutral)
`gold-confetti` → `night-stadium` → `empty-net-rain` → `floodlight-bokeh` → `crowd-erupt`

## Generate NEXT for match summaries (the ACTION-IMPLIED lane, §9–12 below)
`net-ripple` → `knee-slide` → `ball-to-net` → `wheel-away` — these DEPICT a goal/celebration
(faceless) so recap goal beats stop relying on a static portrait or generic crowd.

---

### 1. `gold-confetti`  — winner / hook / celebration / subscribe outro (most reused)
> Gold and amber confetti and ticker-tape drifting and falling slowly through the air against a deep
> black background, particles catching glints of warm stadium light, soft out-of-focus pieces in the
> foreground, gentle downward drift, the centre of the frame mostly empty and dark. [+ STYLE SUFFIX]

### 2. `crowd-erupt`  — energy / celebration without identifiable people
> A massive stadium crowd from a low angle, entirely in silhouette, backlit by intense gold floodlight
> glare and haze, arms rising as the crowd erupts in slow motion, no faces visible, dark foreground,
> warm rim light, very slow push-in. [+ STYLE SUFFIX]

### 3. `pyro-rim`  — opening-ceremony grandeur / big hooks / WC launch
> Golden pyrotechnic fountains and sparks erupting along the dark rim of a stadium at night, embers
> raining down slowly through volumetric haze, deep black sky, warm gold light, distant and abstract,
> no people, slow drift. [+ STYLE SUFFIX]

### 4. `empty-net-rain`  — tension / VAR / offside / "so close" / the save
> An empty football goal net under bright floodlights at night, fine drifting mist and light rain
> catching the light, moody and still, deep shadows, desaturated except warm light on the net, slow
> subtle push-in, no people. [+ STYLE SUFFIX]

### 5. `ball-on-spot`  — tense beat / penalty / dramatic pause
> A single football resting on the penalty spot under a shaft of floodlight in a dark empty stadium at
> night, a volumetric beam of light, deep black surroundings, dramatic and tense, slow cinematic
> push-in toward the ball, no people. [+ STYLE SUFFIX]

### 6. `night-stadium`  — default establishing / neutral connective / hook backdrop
> Slow aerial drone push-in toward a packed floodlit football stadium bowl at night, warm gold lights
> glowing against a deep black sky, the crowd an abstract field of tiny twinkling lights, no individual
> faces, atmospheric haze, smooth slow motion. [+ STYLE SUFFIX]

### 7. `floodlight-bokeh`  — pure texture behind stat cards / numbers
> Defocused golden floodlight orbs and lens flares drifting slowly across a deep black frame, soft warm
> bokeh, gentle bloom and haze, abstract stadium lights at night, no subjects, pure atmospheric texture,
> slow drift. [+ STYLE SUFFIX]

### 8. `stadium-dusk`  — World Cup "summer tournament" grandeur (IP-safe)
> A vast modern football stadium exterior glowing warm gold at dusk, deep blue-black sky, generic
> blurred flags fluttering out of focus in the foreground, atmospheric and grand, slow rising crane
> move, no recognizable national flags or logos, no people in focus. [+ STYLE SUFFIX]

## ACTION-IMPLIED lane — "a goal happened" without footage or faces (highest-leverage for match summaries)
The atmosphere clips above set MOOD; these DEPICT the action a goal beat needs, copyright- and
face-safe. Generate these next — they upgrade every match recap/story (goals, assists, celebrations).

### 9. `net-ripple`  — THE GOAL moment / "he scores" / brace beats (most useful for recaps)
> The white netting of a football goal billowing and rippling outward in slow motion as a ball strikes
> the back of the net, fine net strands catching warm gold floodlight, deep black surroundings behind,
> droplets and dust shaking loose into the light, shot from behind the goal, no people, no logos, calm
> dark space above the net for captions, slow cinematic push-in. [+ STYLE SUFFIX]

### 10. `ball-to-net`  — alt goal angle / "buries it" (pairs with `net-ripple`)
> A football flying into the top corner of an empty goal and rippling the white net in slow motion,
> seen from a low side angle under intense gold floodlight, volumetric haze, deep black background, the
> ball and net the only lit subjects, no goalkeeper, no people, no logos, slow motion. [+ STYLE SUFFIX]

### 11. `knee-slide`  — celebration / redemption peak / the brace payoff
> A lone footballer in silhouette sliding on his knees in celebration with both arms thrown wide,
> fully backlit by intense gold floodlight glare and haze so NO face or kit detail is visible, dark
> empty pitch around him, warm rim light tracing the silhouette, slow motion, low hero angle, generic
> plain kit with no crest or number, no logos. [+ STYLE SUFFIX]

### 12. `wheel-away`  — alt celebration / "off he runs" (pairs with `knee-slide`)
> A single footballer in full silhouette wheeling away and running toward camera with arms spread in
> celebration, backlit by gold floodlights and stadium haze, no visible face, plain unmarked kit, dark
> blurred crowd far behind, slow motion, shallow depth of field, no logos, no text. [+ STYLE SUFFIX]

---

## Wiring a finished clip into the pipeline
1. Drop the file at `assets/broll/<slug>.mp4` (e.g. `assets/broll/gold-confetti.mp4`).
2. Add a credit line to `assets/broll/credits.json`, e.g. `"gold-confetti": "AI generated — TikiTakaFootyTV"`.
3. It's now a routable `stock_video` category: a spec scene with `visual_source: "stock_video"`,
   `visual_query: "gold-confetti"` uses it. The global grade still applies on top.
4. Vision-vet a few candidates per concept and keep the best (same discipline as the image pipeline).
