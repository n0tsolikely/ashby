#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/webapp/stuart_frontend/stuart_app"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

BACKEND_HOST="${STUART_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${STUART_WEB_PORT:-8844}"
FRONTEND_HOST="${STUART_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${STUART_FRONTEND_PORT:-4173}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing $VENV_PYTHON. Run ./Stuart once to create/install runtime dependencies." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found on PATH." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

echo "Starting Stuart backend on http://${BACKEND_HOST}:${BACKEND_PORT}"
(
  cd "$ROOT_DIR"
  PYTHONPATH="$ROOT_DIR" STUART_WEB_PORT="$BACKEND_PORT" "$VENV_PYTHON" scripts/stuart_web.py
) \
  > >(sed 's/^/[backend] /') \
  2> >(sed 's/^/[backend] /' >&2) &
BACKEND_PID=$!

cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "Stopping backend (pid=$BACKEND_PID)"
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Wait briefly for backend readiness.
for _ in $(seq 1 40); do
  if curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/api/sessions" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "Starting Stuart frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT}"
cd "$FRONTEND_DIR"
VITE_API_PROXY_TARGET="http://${BACKEND_HOST}:${BACKEND_PORT}" \
  npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
