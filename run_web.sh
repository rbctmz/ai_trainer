#!/usr/bin/env bash
# Launch the web stack: FastAPI backend (:8000) + Next.js dev server (:3000).
# Streamlit (./run.sh) remains the fallback surface.
set -euo pipefail

cd "$(dirname "$0")"

# Same Google/gRPC runtime default as run.sh.
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

# Activate the project venv if present.
if [ -d "ai_trainer_env" ]; then
  # shellcheck disable=SC1091
  source ai_trainer_env/bin/activate
fi

cleanup() {
  echo ""
  echo "Stopping web stack..."
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Ensure backend web deps (FastAPI/uvicorn/pydantic) are present in the active
# environment. uvicorn alone isn't enough — api.main imports fastapi.
if ! python -c "import fastapi" >/dev/null 2>&1; then
  echo "→ Installing backend web dependencies (requirements-web.txt)…"
  pip install -r requirements-web.txt
fi

echo "→ Starting FastAPI on :$API_PORT"
uvicorn api.main:app --reload --port "$API_PORT" &
API_PID=$!

# Always reconcile deps to package-lock.json. npm is idempotent when the tree
# is already up to date, and this also repairs a partial/cross-platform
# node_modules (e.g. if it was populated on another OS).
echo "→ Installing/юстируем web dependencies…"
(cd web && npm install --no-audit --no-fund)

echo "→ Starting Next.js on :$WEB_PORT"
(cd web && API_BASE_URL="http://127.0.0.1:$API_PORT" npm run dev -- -p "$WEB_PORT") &
WEB_PID=$!

echo ""
echo "AI Trainer web:  http://localhost:$WEB_PORT"
echo "API docs:        http://localhost:$API_PORT/docs"
echo "Press Ctrl+C to stop."
wait
