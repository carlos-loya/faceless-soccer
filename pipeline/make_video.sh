#!/usr/bin/env bash
# One-command end-to-end: a VideoSpec JSON -> a finished MP4.
#   bash pipeline/make_video.sh out/specs/<stem>.json                 # FREE draft (default)
#   TTV_PRODUCTION=1 bash pipeline/make_video.sh out/specs/<stem>.json # real ElevenLabs run
# Run from the repo root. The "brain" (videospec skill, grounded via soccer-news) produces
# the spec; this driver runs all the deterministic stages.
#
# COST GUARDRAIL: draft is the DEFAULT — every run uses FREE local Piper VO and writes a
# "-draft" MP4, so visuals/captions/pacing are ALWAYS previewed for free first. ElevenLabs VO
# costs credits and is reserved for an APPROVED production run (TTV_PRODUCTION=1). Never spend
# ElevenLabs on an unreviewed spec.
#
# For one-off `commons` scenes (specific things not yet curated as KB entities), vision-vet the
# images FIRST so you don't ship a wrong picture:
#   uv run pipeline/fetch_scene_candidates.py <spec.json>   # fetch candidates
#   (run the `pick-images` skill — Claude looks + writes choices.json)
# prepare.mjs then auto-uses those picks. Curated-entity-only videos can skip straight to here.
set -euo pipefail

SPEC="${1:?usage: bash pipeline/make_video.sh <spec.json>}"
STEM="$(basename "$SPEC" .json)"

# Draft is the DEFAULT (free local Piper VO, "-draft" output). ElevenLabs (real VO, costs
# credits) is opt-in ONLY via TTV_PRODUCTION=1 — which wins even if TTV_DRAFT was set.
if [ -n "${TTV_PRODUCTION:-}" ]; then
  export TTV_DRAFT=""        # production: real ElevenLabs VO
  OUT_STEM="$STEM"
  echo "== PRODUCTION RUN: ElevenLabs VO (SPENDS CREDITS) -> out/renders/$OUT_STEM.mp4 =="
else
  export TTV_DRAFT=1         # default: free Piper draft, no credits spent
  OUT_STEM="$STEM-draft"
  echo "== DRAFT (default): free local Piper VO -> out/renders/$OUT_STEM.mp4 (no ElevenLabs credits) =="
  echo "   Visuals approved? Run the real VO with: TTV_PRODUCTION=1 bash pipeline/make_video.sh $SPEC"
fi

echo "== 1/4  ensure assets (auto-fetch images + auto-cutout subject) =="
uv run pipeline/ensure_assets.py "$SPEC"

echo "== 2/4  voiceover ($([ -n "${TTV_DRAFT:-}" ] && echo 'Piper draft' || echo 'ElevenLabs')) =="
TTV_SKIP_IMAGES=1 uv run pipeline/generate_assets.py "$SPEC"

echo "== 3/4  resolve per-scene visuals + sticker =="
( cd pipeline/remotion && node prepare.mjs "out/assets/$STEM" )

echo "== 4/4  render (Remotion) =="
( cd pipeline/remotion \
    && rm -rf node_modules/.cache .remotion \
    && npx remotion render src/index.ts TikiTaka "../../out/renders/$OUT_STEM.mp4" --props=./props.json )

echo "✓ done -> out/renders/$OUT_STEM.mp4"
echo
if [ -z "${TTV_PRODUCTION:-}" ]; then
  echo "  DRAFT preview only (free Piper VO). When the visuals look right, run the real ElevenLabs VO:"
  echo "    TTV_PRODUCTION=1 bash pipeline/make_video.sh $SPEC"
else
  echo "  publish:  uv run pipeline/publish.py publish \"$SPEC\" \"out/renders/$STEM.mp4\" --integration <id> --when now"
  echo "  (channels: uv run pipeline/publish.py channels  |  setup: deploy/postiz/README.md)"
fi
