#!/usr/bin/env bash
# Launch the TikiTakaFootyTV Mission Control dashboard.
#   bash pipeline/dashboard/run.sh            # http://localhost:8770
#   TTV_DASHBOARD_PORT=9000 bash pipeline/dashboard/run.sh
# Stdlib-only Python — no deps to install. Run from anywhere; it finds the repo root itself.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/server.py"
