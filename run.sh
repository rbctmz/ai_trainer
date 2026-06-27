#!/bin/bash
# Скрипт запуска AI Trainer с исправлением для Google Gemini

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$SCRIPT_DIR/ai_trainer_env/bin"

if [[ -x "$VENV_BIN/python" && -x "$VENV_BIN/streamlit" ]]; then
    PYTHON_BIN="$VENV_BIN/python"
    STREAMLIT_BIN="$VENV_BIN/streamlit"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
    STREAMLIT_BIN="${STREAMLIT_BIN:-streamlit}"
fi

function run_streamlit() {
    if "$PYTHON_BIN" -m streamlit --version >/dev/null 2>&1; then
        "$PYTHON_BIN" -m streamlit "$@"
        return
    fi
    "$STREAMLIT_BIN" "$@"
}

echo "🚀 Запуск AI Trainer..."
echo "📌 Применение исправления для Google Gemini API..."

# Консервативный runtime default для Google/gRPC stack
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

echo "🩺 Проверка runtime-зависимостей..."
if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
    echo "❌ Runtime-зависимости повреждены."
    echo "💡 Выполните одноразовое восстановление:"
    echo "   $PYTHON_BIN $SCRIPT_DIR/scripts/doctor_env.py repair --runtime"
    exit 1
fi

echo "📁 Проверка локальной доступности workspace..."
if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --workspace; then
    echo "❌ Workspace не полностью доступен локально."
    echo "💡 Если проект находится в iCloud/~/Documents, выполните Download Now или Keep Downloaded."
    echo "💡 Надежный вариант: переместите репозиторий в локальную папку вроде ~/Code или ~/GitHub."
    exit 1
fi

# Запускаем приложение
echo "🏃 Запуск Streamlit..."
run_streamlit run "$SCRIPT_DIR/app.py" --server.fileWatcherType none

echo "👋 Приложение остановлено"
