#!/usr/bin/env python3
"""
Тест специализированных training prompts
"""

import sys
sys.path.append('.')

import pytest
from models.training_prompts import TrainingPrompts, get_analysis_prompt
from models.ai_providers import AIProviderFactory
from data.database import Database

@pytest.mark.live
def test_specialized_prompts():
    """Тест специализированных prompts для анализа тренировок"""
    
    print("🎯 ТЕСТ СПЕЦИАЛИЗИРОВАННЫХ AI PROMPTS")
    print("=" * 60)
    
    # Получаем реальные данные
    database = Database()
    activities_df = database.get_activities(14)
    hrv_df = database.get_hrv_data(14)
    
    print("📊 Данные для тестирования:")
    print(f"  • Активностей: {len(activities_df)}")
    print(f"  • HRV записей: {len(hrv_df)}")
    
    # Получаем лучший доступный AI провайдер
    ai_provider = AIProviderFactory.get_first_available()
    if not ai_provider:
        print("❌ Ни один AI провайдер недоступен")
        pytest.skip("Ни один AI провайдер не доступен в текущем окружении")
    
    print(f"🤖 Используем: {ai_provider.get_model_name()}")
    
    # Тестируем различные типы анализа
    test_cases = [
        {
            'name': '📈 Анализ недавних тренировок',
            'type': 'recent_training',
            'params': {'activities_df': activities_df, 'hrv_df': hrv_df, 'days': 7}
        },
        {
            'name': '💓 Анализ HRV',
            'type': 'hrv',
            'params': {'hrv_df': hrv_df, 'period_days': 14}
        },
        {
            'name': '📅 Планирование недели',
            'type': 'weekly_plan',
            'params': {
                'activities_df': activities_df, 
                'hrv_df': hrv_df,
                'goals': 'Подготовка к полумарафону'
            }
        }
    ]
    
    # Добавляем анализ конкретной тренировки если есть данные
    if not activities_df.empty:
        latest_activity = activities_df.iloc[0].to_dict()
        test_cases.append({
            'name': '🏃 Анализ конкретной тренировки',
            'type': 'workout',
            'params': {'activity': latest_activity}
        })
    
    results = {}
    
    for test_case in test_cases:
        print(f"\n{test_case['name']}")
        print("-" * 50)
        
        try:
            # Получаем специализированный prompt
            system_prompt, user_prompt = get_analysis_prompt(
                test_case['type'], 
                **test_case['params']
            )
            
            print(f"📝 Размер prompt: {len(user_prompt)} символов")
            print(f"🔍 Превью prompt:\n{user_prompt[:200]}...")
            
            # Генерируем ответ AI
            response = ai_provider.generate_response(user_prompt, system_prompt)
            
            if response and not ("ошибка" in response.lower() or "error" in response.lower()):
                print(f"✅ Ответ получен ({len(response)} символов)")
                results[test_case['name']] = {
                    'success': True,
                    'response': response,
                    'prompt_length': len(user_prompt)
                }
            else:
                print(f"❌ Ошибка в ответе: {response[:100]}...")
                results[test_case['name']] = {'success': False, 'error': response}
                
        except Exception as e:
            print(f"❌ Исключение: {str(e)}")
            results[test_case['name']] = {'success': False, 'error': str(e)}
    
    # Показываем результаты
    print("\n🏆 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ PROMPTS")
    print("=" * 60)
    
    successful_tests = [name for name, result in results.items() if result.get('success', False)]
    failed_tests = [name for name, result in results.items() if not result.get('success', False)]
    
    print(f"✅ Успешных тестов: {len(successful_tests)}")
    print(f"❌ Неудачных тестов: {len(failed_tests)}")
    
    # Показываем примеры ответов
    if successful_tests:
        print("\n📋 ПРИМЕРЫ ОТВЕТОВ AI ТРЕНЕРА:")
        print("=" * 60)
        
        for test_name in successful_tests[:2]:  # Показываем первые 2
            result = results[test_name]
            print(f"\n{test_name}:")
            print("-" * 30)
            print(result['response'])
            print()
    
    assert successful_tests, "Ни один specialized prompt не получил успешный AI ответ"

def test_prompt_components():
    """Тест компонентов prompt системы"""
    
    print("\n🔧 ТЕСТ КОМПОНЕНТОВ PROMPT СИСТЕМЫ")
    print("=" * 60)
    
    # Тестируем системный prompt
    system_prompt = TrainingPrompts.get_system_prompt()
    print(f"📝 Системный prompt: {len(system_prompt)} символов")
    print("🔍 Содержит ключевые слова:")
    
    keywords = ['TSS', 'HRV', 'тренер', 'физиология', 'восстановление']
    for keyword in keywords:
        found = keyword.lower() in system_prompt.lower()
        print(f"  {'✅' if found else '❌'} {keyword}")
    
    # Тестируем статистические функции
    database = Database()
    activities_df = database.get_activities(7)
    hrv_df = database.get_hrv_data(7)
    
    if not activities_df.empty:
        stats = TrainingPrompts._get_training_stats(activities_df, hrv_df, 7)
        print("\n📊 Статистика тренировок:")
        print(stats)
    
    if not hrv_df.empty:
        hrv_stats = TrainingPrompts._get_hrv_stats(hrv_df, 7)
        print("\n💓 Статистика HRV:")
        print(hrv_stats)
    
    print("\n✅ Компоненты prompt системы работают корректно")
    required_keywords = ['TSS', 'HRV', 'тренер']
    assert all(keyword.lower() in system_prompt.lower() for keyword in required_keywords)

if __name__ == "__main__":
    print("🚀 Запуск тестирования специализированных prompts...")
    
    # Тест компонентов
    components_ok = test_prompt_components()
    
    # Основной тест prompts
    prompts_ok = test_specialized_prompts()
    
    if prompts_ok and components_ok:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("🧠 Специализированные AI prompts готовы!")
        print("💡 Теперь AI может давать экспертные советы по:")
        print("  • Анализу тренировок с учетом TSS и HRV")
        print("  • Планированию восстановления")
        print("  • Оптимизации тренировочного процесса")
        print("  • Персонализированным рекомендациям")
    else:
        print("\n⚠️ Некоторые тесты не прошли")
        print("🔧 Проверьте настройки AI провайдеров")
