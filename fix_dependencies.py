#!/usr/bin/env python3
"""
Скрипт для исправления проблем с зависимостями AI провайдеров
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Выполнить команду с описанием"""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} - успешно")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - ошибка: {e.stderr}")
        return False

def main():
    print("🚀 Исправление зависимостей AI провайдеров")
    print("=" * 50)
    
    # Список исправлений
    fixes = [
        {
            "cmd": "pip3 install 'protobuf>=4.25.0,<5.0.0' 'grpcio-status>=1.49.1,<1.63.0'",
            "desc": "Обновление Google/gRPC runtime stack"
        },
        {
            "cmd": "pip3 install --upgrade anthropic",
            "desc": "Обновление Anthropic библиотеки"
        },
        {
            "cmd": "pip3 install --upgrade google-genai",
            "desc": "Обновление Google Gen AI SDK"
        },
        {
            "cmd": "pip3 install --upgrade ollama",
            "desc": "Обновление Ollama библиотеки"
        },
        {
            "cmd": "pip3 install --upgrade openai",
            "desc": "Обновление OpenAI библиотеки"
        }
    ]
    
    success_count = 0
    
    for fix in fixes:
        if run_command(fix["cmd"], fix["desc"]):
            success_count += 1
        print()
    
    # Установка переменной окружения для Google Gemini
    print("🔧 Настройка переменной окружения для Google Gemini...")
    os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
    print("✅ Переменная окружения установлена")
    
    print(f"\n{'='*50}")
    print(f"📊 РЕЗУЛЬТАТЫ:")
    print(f"✅ Успешно: {success_count}/{len(fixes)}")
    
    if success_count == len(fixes):
        print("🎉 Все зависимости исправлены!")
    else:
        print("⚠️  Некоторые исправления не удались")
    
    print(f"\n💡 Рекомендации:")
    print("1. Перезапустите терминал для применения изменений")
    print("2. Запустите тест: python3 test_mock_ai.py")
    print("3. Для постоянного решения добавьте в ~/.bashrc или ~/.zshrc:")
    print("   export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python")
    
    # Тест провайдеров
    print(f"\n🧪 Тестирование провайдеров...")
    try:
        from models.ai_providers import AIProviderFactory
        available = AIProviderFactory.get_available_providers()
        
        print("📊 Статус провайдеров:")
        for name, is_available in available.items():
            status = "✅" if is_available else "❌"
            print(f"  {status} {name}")
            
        available_count = sum(available.values())
        print(f"\n📈 Доступно провайдеров: {available_count}/{len(available)}")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")

if __name__ == "__main__":
    main()
