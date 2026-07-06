#!/usr/bin/env bash
# Launch the web stack: FastAPI backend (:8000) + Next.js dev server (:3000).
# Streamlit (./run.sh) remains the fallback surface.
set -euo pipefail

cd "$(dirname "$0")"

# Same Google/gRPC runtime default as run.sh.
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

validate_port() {
  local name="$1"
  local port="$2"

  if ! [[ "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
    echo "✖ $name must be a TCP port between 1 and 65535, got '$port'."
    exit 1
  fi
}

port_is_busy() {
  python - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.2)
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

next_free_port() {
  python - "$1" <<'PY'
import socket
import sys

start = int(sys.argv[1])
for port in range(start, 65536):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        sys.exit(0)
sys.exit(1)
PY
}

suggest_override_command() {
  local api_start="$(( API_PORT < 8010 ? 8010 : API_PORT + 1 ))"
  local web_start="$(( WEB_PORT < 3010 ? 3010 : WEB_PORT + 1 ))"
  local suggested_api
  local suggested_web

  suggested_api="$(next_free_port "$api_start" 2>/dev/null || true)"
  suggested_web="$(next_free_port "$web_start" 2>/dev/null || true)"

  if [ -n "$suggested_api" ] && [ "$suggested_api" = "$suggested_web" ]; then
    suggested_web="$(next_free_port "$((suggested_web + 1))" 2>/dev/null || true)"
  fi

  if [ -z "$suggested_api" ] || [ -z "$suggested_web" ]; then
    echo "API_PORT=8010 WEB_PORT=3010 ./run_web.sh"
  else
    echo "API_PORT=$suggested_api WEB_PORT=$suggested_web ./run_web.sh"
  fi
}

require_free_port() {
  local name="$1"
  local port="$2"

  if port_is_busy "$port"; then
    echo "✖ $name port :$port is already in use."
    echo "  Stop the process using it or choose another port, for example:"
    echo "  $(suggest_override_command)"
    exit 1
  fi
}

wait_for_api() {
  local port="$1"
  local attempts=40

  for _ in $(seq 1 "$attempts"); do
    if python - "$port" <<'PY'
import json
import sys
import urllib.error
import urllib.request

port = int(sys.argv[1])
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    sys.exit(0 if payload.get("status") == "ok" else 1)
except (OSError, urllib.error.URLError, json.JSONDecodeError):
    sys.exit(1)
PY
    then
      return 0
    fi

    if ! kill -0 "$API_PID" 2>/dev/null; then
      echo "✖ FastAPI process exited before becoming healthy."
      exit 1
    fi

    sleep 0.5
  done

  echo "✖ FastAPI did not become healthy on :$port."
  echo "  Check the log above, or try a different port:"
  echo "  $(suggest_override_command)"
  exit 1
}

# Activate the project venv if present.
if [ -d "ai_trainer_env" ]; then
  # shellcheck disable=SC1091
  source ai_trainer_env/bin/activate
fi

validate_port "API_PORT" "$API_PORT"
validate_port "WEB_PORT" "$WEB_PORT"

if [ "$API_PORT" = "$WEB_PORT" ]; then
  echo "✖ API_PORT and WEB_PORT must be different (both are :$API_PORT)."
  echo "  Example: $(suggest_override_command)"
  exit 1
fi

require_free_port "API" "$API_PORT"
require_free_port "Web" "$WEB_PORT"

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

echo "→ Waiting for FastAPI health check…"
wait_for_api "$API_PORT"

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
