#!/bin/bash
# Скрипт запуска AI Trainer с исправлением для Google Gemini

echo "🚀 Запуск AI Trainer..."
echo "📌 Применение исправления для Google Gemini API..."

# Устанавливаем переменную окружения для исправления protobuf
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# Запускаем приложение
echo "🏃 Запуск Streamlit..."
streamlit run app.py

echo "👋 Приложение остановлено"