#!/usr/bin/env bash
# Cron entry for the schedule-driven match pipeline. No-ops outside the World Cup window and
# uses a lockfile so overlapping runs can't stack. Point cron at THIS file, not the orchestrator.
#
# Install (runs every 30 min; adjust to taste). `crontab -e` and add:
#   */30 * * * * /bin/bash /home/loya/src/github.com/carlos-loya/faceless-soccer/pipeline/auto/wc_cron.sh >> /home/loya/src/github.com/carlos-loya/faceless-soccer/logs/wc_cron.log 2>&1
#
# Requires: `claude`, `uv` on PATH for the cron environment (cron has a minimal PATH — the line
# below sources your profile; adjust if your tools live elsewhere).
set -uo pipefail
[ -f "$HOME/.profile" ] && . "$HOME/.profile" 2>/dev/null || true

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
mkdir -p logs out/auto

# ── only run inside the WC window (from config) ───────────────────────────────
read -r START END < <(python3 -c "import json;w=json.load(open('pipeline/auto/config.json'))['wc_window'];print(w[0],w[1])")
TODAY="$(date '+%Y-%m-%d')"
if [[ "$TODAY" < "$START" || "$TODAY" > "$END" ]]; then
  echo "[$(date '+%F %T')] $TODAY outside WC window [$START..$END] — no-op."
  exit 0
fi

# ── single-flight lock ────────────────────────────────────────────────────────
LOCK="out/auto/.cron.lock"
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "[$(date '+%F %T')] previous run still active (pid $(cat "$LOCK")) — skip."
  exit 0
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

bash pipeline/auto/run_match_pipeline.sh
