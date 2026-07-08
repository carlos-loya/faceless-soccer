#!/usr/bin/env bash
# Schedule-driven match pipeline — the deterministic glue that turns "a WC match just finished"
# into a recap video. The cron (wc_cron.sh) calls this; you can also run it by hand.
#
# For each recently-finished NOTABLE match (fixtures.py) not already handled (processed.jsonl),
# up to the daily cap, it:
#   1. runs the brain headless — `claude -p "/match-recap <id> [--produce|--publish]"`
#      (ground the game report -> videospec -> FACT-CHECK HARD GATE -> render)
#   2. reads the receipt the command wrote (out/auto/receipts/<id>.json)
#   3. if mode=publish AND fact-check passed AND the production render exists:
#        - uploads to YouTube via the official API (upload_youtube.py)
#        - writes a TikTok/IG handoff packet (post_packet.py) — NEVER auto-posts those
#   4. appends an outcome to out/auto/processed.jsonl and prints a summary line
#
# Safety rails: fact-check gate (a failed match produces no render, so it can't publish),
# daily cap, each-match-once ledger, YouTube-only auto-publish. Config: pipeline/auto/config.json.
set -uo pipefail

cd "$(dirname "$0")/../.."               # repo root
AUTO="pipeline/auto"
CFG="$AUTO/config.json"
LEDGER="out/auto/processed.jsonl"
RECEIPTS="out/auto/receipts"
mkdir -p out/auto "$RECEIPTS"

# ── read config (stdlib python3 — no deps) ────────────────────────────────────
cfg() { python3 -c "import json,sys;print(json.load(open('$CFG')).get('$1',''))"; }
MODE="$(cfg mode)";                 MODE="${MODE:-draft}"
DAILY_CAP="$(cfg daily_cap)";       DAILY_CAP="${DAILY_CAP:-3}"
RECENT_HOURS="$(cfg recent_hours)"; RECENT_HOURS="${RECENT_HOURS:-36}"
VIS="$(cfg youtube_visibility)";    VIS="${VIS:-unlisted}"
NOTABLE_FLAG=""; [ "$(cfg notable_only)" = "True" ] && NOTABLE_FLAG="--notable"

case "$MODE" in
  draft)   RECAP_FLAG="" ;;         # free draft, no posting
  produce) RECAP_FLAG="--produce" ;;
  publish) RECAP_FLAG="--publish" ;;
  *) echo "!! unknown mode '$MODE' in $CFG (use draft|produce|publish)"; exit 2 ;;
esac
echo "[$(date '+%F %T')] match pipeline — mode=$MODE cap=$DAILY_CAP recent=${RECENT_HOURS}h $NOTABLE_FLAG"

# already handled? (ledger holds one JSON line per fixture id)
handled() { [ -f "$LEDGER" ] && grep -q "\"fixture_id\": \"$1\"" "$LEDGER"; }
# how many did we already publish/produce TODAY (cap is per calendar day, ET)
today_count() {
  [ -f "$LEDGER" ] || { echo 0; return; }
  local d n; d="$(date '+%Y-%m-%d')"
  n="$(grep -c "\"day\": \"$d\"" "$LEDGER" 2>/dev/null)"   # grep -c exits 1 on 0 matches; sub still captures "0"
  echo "${n:-0}"
}

MATCHES_JSON="$(uv run pipeline/fixtures.py recent --hours "$RECENT_HOURS" $NOTABLE_FLAG --json)"
IDS="$(printf '%s' "$MATCHES_JSON" | python3 -c "import json,sys;print(' '.join(m['id'] for m in json.load(sys.stdin)))")"
[ -z "$IDS" ] && { echo "  no recently-finished notable matches — nothing to do."; exit 0; }

for id in $IDS; do
  if handled "$id"; then echo "  · $id already handled — skip"; continue; fi
  if [ "$(today_count)" -ge "$DAILY_CAP" ]; then echo "  · daily cap ($DAILY_CAP) reached — stopping"; break; fi

  # Deterministic finality gate: only proceed once ESPN confirms the match is FINAL, which also
  # writes the authoritative score+scorers into kb/fixtures.json (so the brain can't invent them,
  # and /match-recap's "result present?" gate then passes). Fails safe — not final => skip, retry.
  if ! uv run pipeline/auto/fetch_result.py "$id" --write >>"logs/fetch-result-$id.log" 2>&1; then
    echo "  · $id not final on ESPN yet — skip (retry next run)"; continue
  fi

  echo "  ▸ $id — running /match-recap $RECAP_FLAG"
  rc_file="$RECEIPTS/$id.json"; rm -f "$rc_file"
  claude -p "/match-recap $id $RECAP_FLAG" >"logs/match-recap-$id.log" 2>&1 || echo "    (claude -p exited non-zero — check logs/match-recap-$id.log)"

  if [ ! -f "$rc_file" ]; then
    echo "    ✗ no receipt written — treating as HALTED (likely fact-check gate). Logged, will retry next run."
    continue
  fi

  read -r stem spec render factcheck < <(python3 -c "
import json
r=json.load(open('$rc_file'))
print(r.get('stem',''), r.get('spec',''), r.get('render') or 'none', r.get('factcheck',''))")

  status="drafted"
  if [ "$MODE" = "publish" ] && [ "$factcheck" = "pass" ] && [ "$render" != "none" ] && [ -f "$render" ]; then
    echo "    ↑ uploading to YouTube ($VIS): $render"
    if uv run pipeline/upload_youtube.py upload "$spec" "$render" --visibility "$VIS" >>"logs/match-recap-$id.log" 2>&1; then
      status="published-youtube"
      # TikTok/IG handoff — attended only, never auto-posted
      uv run pipeline/post_packet.py "$spec" "$render" >"out/auto/post-packet-$id.json" 2>/dev/null \
        && echo "    ✎ TikTok/IG handoff → out/auto/post-packet-$id.json (attended: run post-social)"
    else
      status="youtube-upload-failed"; echo "    ✗ YouTube upload failed — see logs/match-recap-$id.log"
    fi
  elif [ "$factcheck" != "pass" ]; then
    status="halted-factcheck"; echo "    ⏸ fact-check did not pass — not published."
  fi

  python3 -c "
import json,datetime
rec={'fixture_id':'$id','stem':'$stem','spec':'$spec','render':'$render',
     'factcheck':'$factcheck','mode':'$MODE','status':'$status',
     'day':datetime.date.today().isoformat(),'at':datetime.datetime.now().isoformat(timespec='seconds')}
open('$LEDGER','a').write(json.dumps(rec)+'\n')
print('    ✓ '+'$id'+' -> '+'$status')"
done

echo "[$(date '+%F %T')] done."
