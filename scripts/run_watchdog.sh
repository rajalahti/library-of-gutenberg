#!/usr/bin/env bash
set -euo pipefail

# Generic watchdog: runs a python scraper script; if it exits, restarts.
# Usage:
#   ./scripts/run_watchdog.sh <name> <out_dir> <python_script> [-- extra args]

NAME="${1:?name}"
OUT_DIR="${2:?out_dir}"
SCRIPT="${3:?python_script}"
shift 3 || true
EXTRA_ARGS=("$@")

RESTART_DELAY="${RESTART_DELAY:-3}"
LOG_FILE="${LOG_FILE:-${OUT_DIR}/${NAME}.watchdog.log}"

mkdir -p "$OUT_DIR"

ts() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }

echo "[$(ts)] Starting watchdog: $NAME script=$SCRIPT out=$OUT_DIR" | tee -a "$LOG_FILE"

i=0
while true; do
  i=$((i+1))
  echo "[$(ts)] Run #$i" | tee -a "$LOG_FILE"
  python3 "$SCRIPT" --out "$OUT_DIR" "${EXTRA_ARGS[@]}" >>"$LOG_FILE" 2>&1 || true
  echo "[$(ts)] $NAME exited. Restarting in ${RESTART_DELAY}s" | tee -a "$LOG_FILE"
  sleep "$RESTART_DELAY"
done
