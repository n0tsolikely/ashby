#!/usr/bin/env bash
set -euo pipefail

STUART_ROOT="${STUART_ROOT:-$HOME/ashby_runtime/stuart}"
LOG_DIR="${STUART_ROOT}/realtime_log"
DOCTOR_LINES="${1:-300}"

mkdir -p "${LOG_DIR}"
for f in events.jsonl alerts.jsonl ui.jsonl llm.jsonl; do
  touch "${LOG_DIR}/${f}"
done

echo "[runtime-audit] STUART_ROOT=${STUART_ROOT}"
echo "[runtime-audit] LOG_DIR=${LOG_DIR}"
echo "[runtime-audit] tailing events/ui/llm/alerts (Ctrl+C to stop)"

tail -n 0 -F \
  "${LOG_DIR}/events.jsonl" \
  "${LOG_DIR}/alerts.jsonl" \
  "${LOG_DIR}/ui.jsonl" \
  "${LOG_DIR}/llm.jsonl"

echo
echo "[runtime-audit] doctor summary"
python3 tools/realtime_log_doctor.py --stuart-root "${STUART_ROOT}" --lines "${DOCTOR_LINES}"
