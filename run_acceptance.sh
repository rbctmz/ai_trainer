#!/bin/bash
# Изолированный acceptance launch для безопасного browser clickthrough

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$SCRIPT_DIR/ai_trainer_env/bin"

if [[ -x "$VENV_BIN/python" && -x "$VENV_BIN/streamlit" ]]; then
    PYTHON_BIN="$VENV_BIN/python"
    STREAMLIT_BIN="$VENV_BIN/streamlit"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
    STREAMLIT_BIN="${STREAMLIT_BIN:-streamlit}"
fi

ACCEPTANCE_PORT="${ACCEPTANCE_PORT:-8510}"
ACCEPTANCE_ROOT="${ACCEPTANCE_ROOT:-${TMPDIR:-/tmp}/ai_trainer_acceptance}"
mkdir -p "$ACCEPTANCE_ROOT"
ACCEPTANCE_DIR="$(mktemp -d "$ACCEPTANCE_ROOT/session_XXXXXX")"
ACCEPTANCE_DB_PATH="${ACCEPTANCE_DB_PATH:-$ACCEPTANCE_DIR/ai_trainer_acceptance.db}"

export DATABASE_PATH="$ACCEPTANCE_DB_PATH"
export ACCEPTANCE_MODE=1
export ACCEPTANCE_AUTO_DEMO="${ACCEPTANCE_AUTO_DEMO:-1}"
export ACCEPTANCE_DISABLE_GARMIN="${ACCEPTANCE_DISABLE_GARMIN:-1}"
export ACCEPTANCE_LABEL="${ACCEPTANCE_LABEL:-Acceptance Mode}"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

echo "🧪 Запуск AI Trainer в acceptance mode..."
echo "📁 Isolated acceptance dir: $ACCEPTANCE_DIR"
echo "🗃️  Isolated database: $DATABASE_PATH"
echo "🌐 Port: $ACCEPTANCE_PORT"
echo "⚠️  Этот runtime не затрагивает основную ai_trainer.db"

echo "🩺 Проверка runtime-зависимостей..."
if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
    echo "❌ Runtime-зависимости повреждены."
    echo "💡 Выполните одноразовое восстановление:"
    echo "   $PYTHON_BIN $SCRIPT_DIR/scripts/doctor_env.py repair --runtime"
    exit 1
fi

echo "🏃 Запуск Streamlit acceptance instance..."
"$STREAMLIT_BIN" run "$SCRIPT_DIR/app.py" --server.fileWatcherType none --server.port "$ACCEPTANCE_PORT"

echo "👋 Acceptance instance остановлен"
