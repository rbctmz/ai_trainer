#!/usr/bin/env python3
"""
Тест специализированных prompts с Google Gemini
"""

import sys
sys.path.append('.')

import pytest
from models.training_prompts import TrainingPrompts, get_analysis_prompt
from models.ai_providers import GoogleGeminiProvider
from data.database import Database

pytestmark = pytest.mark.live

def test_gemini_with_training_data():
    """Тест Gemini с реальными тренировочными данными"""
    
    print("🤖 ТЕСТ GEMINI С СПЕЦИАЛИЗИРОВАННЫМИ PROMPTS")
    print("=" * 60)
    
    # Создаем Google Gemini провайдер
    gemini = GoogleGeminiProvider(model="gemini-2.0-flash-exp")
    
    if not gemini.is_available():
        print("❌ Google Gemini недоступен")
        pytest.skip("Google Gemini недоступен в текущем окружении")
    
    print(f"✅ Используем: {gemini.get_model_name()}")
    
    # Получаем реальные данные
    database = Database()
    activities_df = database.get_activities(7)
    hrv_df = database.get_hrv_data(7)
    
    print(f"📊 Данные: {len(activities_df)} активностей, {len(hrv_df)} HRV записей")
    
    # Тестируем разные типы анализа
    test_cases = [
        {
            'name': '📈 Анализ недавних тренировок (7 дней)',
            'type': 'recent_training',
            'params': {'activities_df': activities_df, 'hrv_df': hrv_df, 'days': 7}
        },
        {
            'name': '💓 Экспертный анализ HRV',
            'type': 'hrv',
            'params': {'hrv_df': hrv_df, 'period_days': 14}
        }
    ]
    
    # Если есть активности, добавляем анализ конкретной тренировки
    if not activities_df.empty:
        latest_activity = activities_df.iloc[0].to_dict()
        test_cases.append({
            'name': '🏃 Анализ конкретной тренировки',
            'type': 'workout',
            'params': {'activity': latest_activity}
        })
    
    results = []
    
    for test_case in test_cases:
        print(f"\n{test_case['name']}")
        print("-" * 50)
        
        try:
            # Получаем специализированный prompt
            system_prompt, user_prompt = get_analysis_prompt(
                test_case['type'], 
                **test_case['params']
            )
            
            print(f"📝 Размер user prompt: {len(user_prompt)} символов")
            
            # Генерируем ответ через Gemini
            response = gemini.generate_response(user_prompt, system_prompt)
            
            if response and not ("ошибка" in response.lower() or "error" in response.lower()):
                print(f"✅ Ответ получен ({len(response)} символов)")
                print(f"🎯 AI Тренер отвечает:")
                print("-" * 30)
                print(response)
                print()
                
                results.append({
                    'test': test_case['name'],
                    'success': True,
                    'response': response
                })
            else:
                print(f"❌ Проблема с ответом: {response[:100]}...")
                results.append({
                    'test': test_case['name'],
                    'success': False,
                    'error': response
                })
                
        except Exception as e:
            print(f"❌ Исключение: {str(e)}")
            results.append({
                'test': test_case['name'],
                'success': False,
                'error': str(e)
            })
    
    # Итоги
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\n📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 40)
    print(f"✅ Успешных тестов: {len(successful)}")
    print(f"❌ Неудачных тестов: {len(failed)}")
    
    if successful:
        print(f"\n🎉 GEMINI УСПЕШНО РАБОТАЕТ КАК AI ТРЕНЕР!")
        print(f"💡 Специализированные prompts дают качественные ответы")
    else:
        print(f"\n⚠️ Проблемы с тестированием")
    assert successful, "Gemini не вернул успешных ответов для training prompts"

def test_simple_gemini():
    """Простой тест Gemini"""
    
    print(f"\n🧪 ПРОСТОЙ ТЕСТ GEMINI")
    print("-" * 30)
    
    gemini = GoogleGeminiProvider(model="gemini-2.0-flash-exp")
    
    if not gemini.is_available():
        print("❌ Gemini недоступен")
        pytest.skip("Google Gemini недоступен в текущем окружении")
    
    # Простой вопрос
    response = gemini.generate_response(
        "Дай один совет по тренировкам на выносливость в 2-3 предложения",
        "Ты AI тренер по выносливости. Отвечай кратко и практично."
    )
    
    print(f"🎯 Простой вопрос -> ответ:")
    print(f"💬 {response}")
    
    assert response

if __name__ == "__main__":
    print("🚀 Тестирование Google Gemini как AI тренера...")
    
    # Простой тест
    simple_ok = test_simple_gemini()
    
    # Продвинутый тест с данными
    advanced_ok = test_gemini_with_training_data()
    
    if simple_ok and advanced_ok:
        print(f"\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ!")
        print(f"🤖 Google Gemini 2.0 готов быть AI тренером!")
        print(f"📱 Запустите приложение: streamlit run app.py")
    else:
        print(f"\n⚠️ Некоторые тесты не прошли")
