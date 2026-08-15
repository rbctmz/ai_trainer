#!/usr/bin/env python3
"""
Продвинутый тест всех AI провайдеров с реальными данными
"""

import sys
sys.path.append('.')

import pytest
from models.ai_providers import (
    AnthropicProvider,
    GoogleGeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from data.database import Database
import pandas as pd

pytestmark = pytest.mark.live

# Динамический импорт Mock провайдера
try:
    from models.mock_ai_provider import MockAIProvider
except ImportError:
    MockAIProvider = None

def test_all_providers():
    """Тест всех доступных AI провайдеров"""
    
    print("🤖 ПРОДВИНУТЫЙ ТЕСТ AI ПРОВАЙДЕРОВ")
    print("=" * 60)
    
    # Получаем реальные данные для тестирования
    database = Database()
    activities_df = database.get_activities(7)  # За последние 7 дней
    hrv_df = database.get_hrv_data(7)
    
    # Подготавливаем контекст для AI
    if not activities_df.empty and not hrv_df.empty:
        latest_activity = activities_df.iloc[0]
        latest_hrv = hrv_df.iloc[0]
        
        activity_summary = f"""
Последняя тренировка: {latest_activity['sport']} на {latest_activity['distance_km']:.1f} км
Продолжительность: {latest_activity['duration_minutes']:.0f} минут
TSS: {latest_activity['tss']:.0f}
        """
        
        hrv_summary = f"""
Последние данные HRV:
RMSSD: {latest_hrv['rmssd']:.1f} мс
Стресс: {latest_hrv['stress_score'] if pd.notna(latest_hrv['stress_score']) else 'Н/Д'}
Восстановление: {latest_hrv['recovery_score']:.0f}% если pd.notna(latest_hrv['recovery_score']) else 'Н/Д'
        """
        
        context = activity_summary + hrv_summary
    else:
        context = "Тренировочные данные недоступны для анализа."
    
    # Специализированный prompt для тренировочного анализа
    system_prompt = """Ты - персональный AI тренер по выносливости. 
Анализируй данные тренировок, HRV и физиологические показатели. 
Давай краткие, практичные рекомендации на русском языке.
Ответ должен быть не более 200 слов и включать конкретные советы."""
    
    user_prompt = f"""Проанализируй мои тренировочные данные:

{context}

Дай краткие рекомендации:
1. Оценка текущего состояния (1-2 предложения)
2. Рекомендации на следующую тренировку (1-2 предложения)
3. Общий совет по восстановлению (1 предложение)"""
    
    # Список провайдеров для тестирования
    providers = [
        ('OpenAI GPT-4', OpenAIProvider(model="gpt-4-turbo")),
        ('OpenAI GPT-3.5', OpenAIProvider(model="gpt-3.5-turbo")),
        ('Anthropic Claude', AnthropicProvider(model="claude-3-haiku-20240307")),
        ('Google Gemini 2.5 Flash', GoogleGeminiProvider(model="gemini-2.5-flash")),
        ('Google Gemini 2.5 Pro', GoogleGeminiProvider(model="gemini-2.5-pro")),
        ('Google Gemini 2.0 Flash', GoogleGeminiProvider(model="gemini-2.0-flash")),
        ('Ollama Llama3.1', OllamaProvider(model="llama3.1:8b"))
    ]
    
    # Добавляем Mock провайдер если доступен
    if MockAIProvider:
        providers.append(('Mock AI', MockAIProvider()))
    
    results = {}
    
    for name, provider in providers:
        print(f"\n🧪 Тестирование {name}")
        print("-" * 40)
        
        # Проверяем доступность
        if not provider.is_available():
            print(f"  ❌ {name} недоступен")
            results[name] = {"available": False, "error": "Провайдер не настроен"}
            continue
        
        # Тестируем подключение
        connection_test = provider.test_connection()
        if not connection_test.get('success', False):
            print(f"  ❌ Ошибка подключения: {connection_test.get('error', 'Неизвестная ошибка')}")
            results[name] = {"available": False, "error": connection_test.get('error')}
            continue
        
        print("  ✅ Подключение успешно")
        
        # Генерируем ответ
        try:
            response = provider.generate_response(user_prompt, system_prompt)
            
            if "ошибка" in response.lower() or "error" in response.lower():
                print(f"  ❌ Ошибка в ответе: {response[:100]}...")
                results[name] = {"available": True, "success": False, "error": response}
            else:
                print(f"  ✅ Ответ получен ({len(response)} символов)")
                print(f"  📝 Превью: {response[:150]}...")
                
                results[name] = {
                    "available": True, 
                    "success": True, 
                    "response_length": len(response),
                    "response": response
                }
        except Exception as e:
            print(f"  ❌ Исключение: {str(e)}")
            results[name] = {"available": True, "success": False, "error": str(e)}
    
    # Результаты
    print("\n📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 60)
    
    working_providers = []
    failed_providers = []
    
    for name, result in results.items():
        if result.get("success", False):
            working_providers.append(name)
            print(f"✅ {name}: OK (ответ {result['response_length']} символов)")
        elif result.get("available", False):
            failed_providers.append(name)
            print(f"⚠️ {name}: Доступен, но ошибка генерации")
        else:
            failed_providers.append(name)
            print(f"❌ {name}: Недоступен")
    
    print("\n📈 Статистика:")
    print(f"  Работающих провайдеров: {len(working_providers)}")
    print(f"  Проблемных провайдеров: {len(failed_providers)}")
    
    # Показываем лучшие ответы
    if working_providers:
        print("\n🏆 ПРИМЕРЫ ЛУЧШИХ ОТВЕТОВ:")
        print("=" * 60)
        
        for name in working_providers[:3]:  # Показываем первые 3 работающих
            result = results[name]
            print(f"\n📝 {name}:")
            print("-" * 30)
            print(result['response'])
            print()
    
    assert working_providers, "Ни один AI провайдер не сгенерировал успешный ответ"

def test_provider_switching():
    """Тест автоматического переключения провайдеров"""
    
    print("\n🔄 ТЕСТ АВТОМАТИЧЕСКОГО ПЕРЕКЛЮЧЕНИЯ ПРОВАЙДЕРОВ")
    print("=" * 60)
    
    # Получаем лучший доступный провайдер
    from models.ai_providers import AIProviderFactory
    best_provider = AIProviderFactory.get_first_available()
    
    if best_provider:
        print(f"✅ Лучший провайдер: {best_provider.get_model_name()}")
        
        # Тестируем простой запрос
        response = best_provider.generate_response(
            "Дай один совет для восстановления после тренировки",
            "Ты AI тренер. Отвечай кратко."
        )
        
        print(f"📝 Ответ: {response}")
        assert response
    else:
        print("❌ Ни один провайдер не доступен")
        pytest.skip("Ни один AI провайдер не доступен в текущем окружении")

if __name__ == "__main__":
    print("🚀 Запуск продвинутого теста AI провайдеров...")
    
    # Основной тест провайдеров
    providers_ok = test_all_providers()
    
    # Тест переключения
    switching_ok = test_provider_switching()
    
    if providers_ok:
        print("\n🎉 ТЕСТЫ ЗАВЕРШЕНЫ УСПЕШНО!")
        print("💡 AI провайдеры готовы для персонального тренерского коучинга!")
        print("📱 Запустите приложение: streamlit run app.py")
    else:
        print("\n⚠️ Проблемы с AI провайдерами")
        print("🔧 Проверьте API ключи в .env файле")
