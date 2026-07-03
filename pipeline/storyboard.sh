#!/usr/bin/env bash
# Storyboard a video BEFORE the slow render — see which image/background every scene gets.
#   bash pipeline/storyboard.sh out/specs/<stem>.json
# Runs the FREE, FAST half of the pipeline: ensure assets (fetch images + cut out the subject) ->
# resolve every scene's visual with the SAME resolver the render uses (no VO) -> build an HTML
# contact sheet at out/storyboards/<stem>.html. No ElevenLabs, no Remotion render, no waiting.
#
# Iterate here for free: open the HTML, fix any wrong visual_source/visual_query in the spec,
# re-run this (seconds), and only run `make_video.sh` (the slow draft render) once it looks right.
# Bonus: the images it downloads are cached, so the eventual draft render is faster too.
set -euo pipefail

# Optional --fresh: wipe cached downloads + stale vision-picks for a guaranteed-clean regen
# (use when a scene's background looks stuck). Accepted before or after the spec path.
FRESH=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--fresh" ]; then FRESH=1; else ARGS+=("$a"); fi
done
set -- "${ARGS[@]}"

SPEC="${1:?usage: bash pipeline/storyboard.sh [--fresh] <spec.json>}"
STEM="$(basename "$SPEC" .json)"

if [ "$FRESH" = "1" ]; then
  echo "== 0/3  --fresh: clearing cached visuals + stale picks for $STEM =="
  rm -rf "pipeline/remotion/public/$STEM"
  rm -f "out/candidates/$STEM/choices.json"
fi

echo "== 1/3  ensure assets (fetch CC images + cut out subject; no VO) =="
uv run pipeline/ensure_assets.py "$SPEC"

echo "== 2/3  resolve per-scene visuals (storyboard mode — no VO, no render) =="
( cd pipeline/remotion && TTV_STORYBOARD=1 node prepare.mjs "$SPEC" )

echo "== 3/3  build storyboard HTML =="
( cd pipeline/remotion && node storyboard.mjs "$STEM" )

echo
echo "✓ open it:  out/storyboards/$STEM.html"
echo "  visuals right? render the free draft:  bash pipeline/make_video.sh $SPEC"
