#!/bin/bash
# Legacy helper для постоянной настройки Google/gRPC runtime default

echo "🚀 Настройка Google/gRPC runtime default"

# Определяем файл конфигурации оболочки
if [[ "$SHELL" == *"zsh"* ]]; then
    CONFIG_FILE="$HOME/.zshrc"
    echo "📝 Обнаружен zsh, используем ~/.zshrc"
elif [[ "$SHELL" == *"bash"* ]]; then
    CONFIG_FILE="$HOME/.bashrc"
    echo "📝 Обнаружен bash, используем ~/.bashrc"
else
    CONFIG_FILE="$HOME/.bashrc"
    echo "📝 Неизвестная оболочка, используем ~/.bashrc по умолчанию"
fi

# Проверяем, есть ли уже настройка
if grep -q "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION" "$CONFIG_FILE" 2>/dev/null; then
    echo "✅ Переменная окружения уже настроена в $CONFIG_FILE"
else
    echo "" >> "$CONFIG_FILE"
    echo "# Google/gRPC runtime default for AI Trainer" >> "$CONFIG_FILE"
    echo "export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python" >> "$CONFIG_FILE"
    echo "✅ Переменная окружения добавлена в $CONFIG_FILE"
fi

# Применяем изменения
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
echo "⚡ Переменная применена к текущей сессии"

echo ""
echo "💡 Для применения к новым терминалам выполните:"
echo "   source $CONFIG_FILE"
echo "   или перезапустите терминал"

echo ""
echo "🧪 Тестируем AI провайдеры..."
python3 -c "
try:
    from models.ai_providers import AIProviderFactory
    available = AIProviderFactory.get_available_providers()
    print('📊 Статус провайдеров:')
    for name, is_available in available.items():
        status = '✅' if is_available else '❌'
        print(f'  {status} {name}')
    print(f'📈 Доступно: {sum(available.values())}/{len(available)}')
except Exception as e:
    print(f'❌ Ошибка: {e}')
"
