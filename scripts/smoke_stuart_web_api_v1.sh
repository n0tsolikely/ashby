#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${STUART_SMOKE_BASE_URL:-http://127.0.0.1:8844}"
PORT="${STUART_WEB_PORT:-8844}"

TMP_ROOT="$(mktemp -d -t stuart_smoke_root_XXXXXX)"
cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[smoke] STUART_ROOT=$TMP_ROOT"
cd "$ROOT_DIR"
STUART_ROOT="$TMP_ROOT" PYTHONPATH="$ROOT_DIR" python3 scripts/stuart_web.py >/tmp/stuart_smoke_server.log 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 50); do
  if curl -fsS "$BASE_URL/api/registry" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 0.2
done

if [[ "${READY:-0}" != "1" ]]; then
  echo "[smoke] server did not become ready at $BASE_URL within timeout" >&2
  if [[ -f /tmp/stuart_smoke_server.log ]]; then
    echo "[smoke] server log tail:" >&2
    tail -n 60 /tmp/stuart_smoke_server.log >&2 || true
  fi
  exit 1
fi

echo "[smoke] 1) POST /api/sessions"
CREATE_JSON="$(curl -fsS -X POST "$BASE_URL/api/sessions" -H 'Content-Type: application/json' -d '{"mode":"meeting","title":"Smoke Session"}')"
echo "$CREATE_JSON"
SESSION_ID="$(python3 - <<'PY' "$CREATE_JSON"
import json,sys
print(json.loads(sys.argv[1]).get("session_id",""))
PY
)"
if [[ -z "$SESSION_ID" ]]; then
  echo "[smoke] failed: missing session_id" >&2
  exit 1
fi

echo "[smoke] 2) POST /api/upload (bytes path)"
UPLOAD_JSON="$(curl -fsS -X POST "$BASE_URL/api/upload?session_id=$SESSION_ID" \
  -H 'Content-Type: audio/wav' \
  -H 'X-Filename: smoke.wav' \
  --data-binary 'FAKE_WAV_BYTES')"
echo "$UPLOAD_JSON"

echo "[smoke] 3) POST /api/run"
RUN_JSON="$(curl -fsS -X POST "$BASE_URL/api/run" -H 'Content-Type: application/json' -d "{\"session_id\":\"$SESSION_ID\",\"ui\":{\"mode\":\"meeting\",\"template_id\":\"default\",\"retention\":\"MED\",\"speakers\":\"auto\"}}")"
echo "$RUN_JSON"

echo "[smoke] 4) GET /api/sessions"
curl -fsS "$BASE_URL/api/sessions" | head -c 400; echo

echo "[smoke] 5) GET /api/sessions/{id}"
curl -fsS "$BASE_URL/api/sessions/$SESSION_ID" | head -c 400; echo

echo "[smoke] 6) GET /api/sessions/{id}/runs"
curl -fsS "$BASE_URL/api/sessions/$SESSION_ID/runs" | head -c 400; echo

echo "[smoke] 7) GET /api/sessions/{id}/transcripts"
curl -fsS "$BASE_URL/api/sessions/$SESSION_ID/transcripts" | head -c 400; echo

echo "[smoke] 8) GET /api/sessions/{id}/formalizations"
curl -fsS "$BASE_URL/api/sessions/$SESSION_ID/formalizations" | head -c 400; echo

echo "[smoke] 9) GET /api/sessions/{id}/export?export_type=full_bundle"
curl -fsS "$BASE_URL/api/sessions/$SESSION_ID/export?export_type=full_bundle" | head -c 400; echo

echo "[smoke] complete"
