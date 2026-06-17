#!/bin/bash
# Изолированный acceptance launch для безопасного browser clickthrough

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$SCRIPT_DIR/ai_trainer_env/bin"
SYSTEM_PYTHON_BIN="${PYTHON_BIN:-python3}"
SYSTEM_STREAMLIT_BIN="${STREAMLIT_BIN:-streamlit}"

function use_virtualenv_runtime() {
    PYTHON_BIN="$VENV_BIN/python"
    STREAMLIT_BIN="$VENV_BIN/streamlit"
}

function use_system_runtime() {
    PYTHON_BIN="$SYSTEM_PYTHON_BIN"
    STREAMLIT_BIN="$SYSTEM_STREAMLIT_BIN"
}

function run_streamlit() {
    if "$PYTHON_BIN" -m streamlit --version >/dev/null 2>&1; then
        "$PYTHON_BIN" -m streamlit "$@"
        return
    fi
    "$STREAMLIT_BIN" "$@"
}

if [[ -x "$VENV_BIN/python" && -x "$VENV_BIN/streamlit" ]]; then
    use_virtualenv_runtime
else
    use_system_runtime
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

if [[ "${ACCEPTANCE_SKIP_DOCTOR:-0}" != "1" ]]; then
    echo "🩺 Проверка runtime-зависимостей..."
    if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
        if [[ "$PYTHON_BIN" == "$VENV_BIN/python" ]]; then
            echo "🔧 Пытаюсь автоматически восстановить runtime virtualenv..."
            "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" repair --runtime || true
            if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
                if command -v "$SYSTEM_PYTHON_BIN" >/dev/null 2>&1 && command -v "$SYSTEM_STREAMLIT_BIN" >/dev/null 2>&1; then
                    echo "↪️  Virtualenv runtime всё ещё неисправен, переключаюсь на system Python runtime."
                    use_system_runtime
                fi
            fi
        fi
    fi

    if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
        echo "❌ Runtime-зависимости повреждены."
        echo "💡 Выполните одноразовое восстановление:"
        echo "   $PYTHON_BIN $SCRIPT_DIR/scripts/doctor_env.py repair --runtime"
        echo "💡 Или временно пропустите preflight:"
        echo "   ACCEPTANCE_SKIP_DOCTOR=1 ./run_acceptance.sh"
        exit 1
    fi

    echo "📁 Проверка локальной доступности workspace..."
    if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --workspace; then
        echo "❌ Workspace не полностью доступен локально."
        echo "💡 Для acceptance mode держите репозиторий полностью скачанным: Download Now / Keep Downloaded."
        echo "💡 Надежный вариант: переместите репозиторий в локальную папку вроде ~/Code или ~/GitHub."
        exit 1
    fi
fi

echo "🏃 Запуск Streamlit acceptance instance..."
run_streamlit run "$SCRIPT_DIR/app.py" --server.fileWatcherType none --server.port "$ACCEPTANCE_PORT"

echo "👋 Acceptance instance остановлен"
