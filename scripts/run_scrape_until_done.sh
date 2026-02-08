#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-data/theme-map}"
SLEEP_SECS="${SLEEP_SECS:-0.25}"
RESTART_DELAY="${RESTART_DELAY:-3}"
LOG_FILE="${LOG_FILE:-${OUT_DIR}/scrape.log}"

mkdir -p "$OUT_DIR"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }

echo "[$(ts)] Starting watchdog. out=$OUT_DIR sleep=$SLEEP_SECS" | tee -a "$LOG_FILE"

while true; do
  echo "[$(ts)] Launching scrape" | tee -a "$LOG_FILE"
  python3 scripts/generate_theme_map.py --max-books 70000 --out "$OUT_DIR" --sleep "$SLEEP_SECS" >>"$LOG_FILE" 2>&1 || true

  # Check completion (no missing)
  if [[ -f "$OUT_DIR/themeByBookId.v1.json" ]]; then
    MISSING=$(python3 - <<'PY'
import json
from pathlib import Path
arr=json.loads(Path("data/theme-map/themeByBookId.v1.json").read_text('utf-8'))
missing=sum(1 for x in arr[1:] if x is None)
print(missing)
PY
)
    echo "[$(ts)] Missing=$MISSING" | tee -a "$LOG_FILE"
    if [[ "$MISSING" == "0" ]]; then
      echo "[$(ts)] DONE" | tee -a "$LOG_FILE"
      exit 0
    fi
  fi

  echo "[$(ts)] Scrape exited (or was killed). Restarting in ${RESTART_DELAY}s" | tee -a "$LOG_FILE"
  sleep "$RESTART_DELAY"
done
