#!/usr/bin/env python3
"""
Демонстрация новых функций AI провайдеров:
1. Проверка API ключей (test_connection)
2. Получение списка моделей (get_available_models)
"""

from models.ai_providers import AIProviderFactory

def demo_ai_features():
    print("🎯 Демонстрация новых функций AI провайдеров")
    print("=" * 60)
    
    print("\n💡 Новые возможности:")
    print("   1. 🔍 Тест подключения - проверка API ключей")
    print("   2. 📜 Список моделей - получение доступных моделей")
    print("   3. 🛠️ Диагностика - детальная информация о проблемах")
    
    # Демонстрация с Ollama (работающий провайдер)
    print(f"\n{'='*60}")
    print("🦙 Демонстрация с Ollama (локальный провайдер)")
    print('='*60)
    
    try:
        # Создаём Ollama провайдер
        ollama = AIProviderFactory.create_provider("ollama")
        
        print(f"✅ Провайдер: {ollama.get_model_name()}")
        print(f"   Статус: {'🟢 Доступен' if ollama.is_available() else '🔴 Недоступен'}")
        
        # 1. Тест подключения
        print(f"\n🔍 Тест подключения:")
        test_result = ollama.test_connection()
        
        if test_result.get('success'):
            print(f"   ✅ Результат: {test_result.get('message')}")
            print(f"   📊 Модель: {test_result.get('model')}")
            print(f"   🌐 Хост: {test_result.get('host')}")
            print(f"   📏 Длина ответа: {test_result.get('response_length')} символов")
        else:
            print(f"   ❌ Ошибка: {test_result.get('error')}")
        
        # 2. Список моделей  
        print(f"\n📜 Доступные модели:")
        models = ollama.get_available_models()
        
        print(f"   📊 Всего моделей: {len(models)}")
        print("   📋 Топ-10 моделей:")
        for i, model in enumerate(models[:10], 1):
            if model == "gemma3:4b":  # Выделяем текущую модель
                print(f"      {i}. {model} ← 🎯 Текущая")
            else:
                print(f"      {i}. {model}")
        
        if len(models) > 10:
            print(f"      ... и ещё {len(models) - 10} моделей")
            
    except Exception as e:
        print(f"❌ Ошибка демонстрации Ollama: {e}")
    
    # Демонстрация с Mock AI (всегда работает)
    print(f"\n{'='*60}")
    print("🤖 Демонстрация с Mock AI (демо провайдер)")
    print('='*60)
    
    try:
        # Создаём Mock провайдер
        mock = AIProviderFactory.create_provider("mock")
        
        print(f"✅ Провайдер: {mock.get_model_name()}")
        print(f"   Статус: {'🟢 Доступен' if mock.is_available() else '🔴 Недоступен'}")
        
        # 1. Тест подключения
        print(f"\n🔍 Тест подключения:")
        test_result = mock.test_connection()
        
        if test_result.get('success'):
            print(f"   ✅ Результат: {test_result.get('message')}")
            print(f"   📊 Модель: {test_result.get('model')}")
            print(f"   ⏱️ Время ответа: {test_result.get('response_time')}с")
            print(f"   🎯 Особенности: {', '.join(test_result.get('features', []))}")
        
        # 2. Список моделей
        print(f"\n📜 Доступные модели:")
        models = mock.get_available_models()
        
        print(f"   📊 Всего моделей: {len(models)}")
        for i, model in enumerate(models, 1):
            print(f"      {i}. {model}")
            
    except Exception as e:
        print(f"❌ Ошибка демонстрации Mock: {e}")
    
    # Демонстрация с OpenAI (может не работать без ключа)
    print(f"\n{'='*60}")
    print("🚀 Демонстрация с OpenAI (внешний провайдер)")
    print('='*60)
    
    try:
        # Создаём OpenAI провайдер
        openai = AIProviderFactory.create_provider("openai")
        
        print(f"✅ Провайдер: {openai.get_model_name()}")
        print(f"   Статус: {'🟢 Доступен' if openai.is_available() else '🔴 Недоступен'}")
        
        # 1. Тест подключения (может показать ошибку API ключа)
        print(f"\n🔍 Тест подключения:")
        test_result = openai.test_connection()
        
        if test_result.get('success'):
            print(f"   ✅ Результат: {test_result.get('message')}")
            print(f"   📊 Модель: {test_result.get('model')}")
            print(f"   📏 Длина ответа: {test_result.get('response_length')} символов")
        else:
            print(f"   ❌ Ошибка: {test_result.get('error')}")
            print(f"   💡 Это нормально - OpenAI требует действующий API ключ")
        
        # 2. Список моделей (может работать даже без ключа)
        print(f"\n📜 Доступные модели:")
        models = openai.get_available_models()
        
        if models:
            print(f"   📊 Всего моделей: {len(models)}")
            print("   📋 Популярные модели:")
            popular = [m for m in models if any(x in m for x in ['gpt-4', 'gpt-3.5'])]
            for i, model in enumerate(popular[:5], 1):
                print(f"      {i}. {model}")
        else:
            print("   ⚠️  Требуется API ключ для получения списка моделей")
            
    except Exception as e:
        print(f"❌ Ошибка демонстрации OpenAI: {e}")
    
    print(f"\n{'='*60}")
    print("🎉 ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
    print("="*60)
    
    print("\n🚀 Теперь в UI доступно:")
    print("   🔍 Кнопка 'Тест подключения' - проверка API ключей")
    print("   📜 Кнопка 'Показать модели' - список доступных моделей")  
    print("   🛠️ Детальная диагностика проблем")
    print("   📊 Информация о провайдерах")
    
    print("\n💡 Запустите Streamlit для тестирования:")
    print("   streamlit run app.py")
    print("   Перейдите в '🤖 AI Коучинг' → ⚙️ Настройки AI")

if __name__ == "__main__":
    demo_ai_features()