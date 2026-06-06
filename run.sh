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

echo "🚀 Запуск AI Trainer..."
echo "📌 Применение исправления для Google Gemini API..."

# Устанавливаем переменную окружения для исправления protobuf
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

echo "🩺 Проверка runtime-зависимостей..."
if ! "$PYTHON_BIN" "$SCRIPT_DIR/scripts/doctor_env.py" check --runtime; then
    echo "❌ Runtime-зависимости повреждены."
    echo "💡 Выполните одноразовое восстановление:"
    echo "   $PYTHON_BIN $SCRIPT_DIR/scripts/doctor_env.py repair --runtime"
    exit 1
fi

# Запускаем приложение
echo "🏃 Запуск Streamlit..."
"$STREAMLIT_BIN" run "$SCRIPT_DIR/app.py" --server.fileWatcherType none

echo "👋 Приложение остановлено"
