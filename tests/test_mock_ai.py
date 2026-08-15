#!/usr/bin/env python3
"""
Тест Mock AI провайдера для демонстрации системы AI коучинга
"""

import sys
sys.path.append('..')
from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

def test_mock_ai():
    print("🤖 Тестирование Mock AI провайдера")
    print("=" * 60)
    
    # Проверяем доступные провайдеры
    print("\n📊 Доступные провайдеры:")
    available = AIProviderFactory.get_available_providers()
    
    for name, is_available in available.items():
        status = "✅" if is_available else "❌"
        print(f"{status} {name}")
    
    # Создаём Mock провайдер
    print("\n🎯 Создаём Mock провайдер...")
    try:
        provider = AIProviderFactory.create_provider("mock", delay=0.5)  # Быстрый режим
        if provider and provider.is_available():
            print(f"✅ Подключено к: {provider.get_model_name()}")
        else:
            print("❌ Mock провайдер недоступен")
            return
    except Exception as e:
        print(f"❌ Ошибка создания Mock провайдера: {e}")
        return
    
    # Создаём AI коуча
    coach = UniversalAICoach(provider)
    
    # Тестовые метрики
    test_metrics = {
        'ctl': 45.2,
        'atl': 42.1,
        'tsb': 3.1,
        'form': 'Хорошая форма',
        'week_activities': 4,
        'week_tss': 320,
        'avg_tss': 80,
        'primary_sport': 'бег'
    }
    
    print(f"\n{'='*60}")
    print("🧪 ТЕСТИРОВАНИЕ ФУНКЦИЙ AI КОУЧИНГА")
    print('='*60)
    
    # Тест 1: Анализ состояния
    print("\n📊 Тест 1: Анализ текущего состояния")
    print("-" * 50)
    analysis = coach.analyze_current_state(test_metrics)
    print(analysis)
    
    # Тест 2: Недельный план
    print("\n📅 Тест 2: Генерация недельного плана")
    print("-" * 50)
    goals = "подготовка к полумарафону через 8 недель"
    plan = coach.generate_weekly_plan(test_metrics, goals)
    print(plan)
    
    # Тест 3: Анализ тренировки
    print("\n🏃 Тест 3: Анализ тренировки")
    print("-" * 50)
    workout_data = {
        'sport': 'бег',
        'duration_minutes': 60,
        'distance_km': 8.5,
        'tss': 85,
        'avg_hr': 165,
        'max_hr': 178,
        'avg_power': None,
        'elevation_gain': 120
    }
    feeling = "чувствовал себя хорошо, но под конец немного устал"
    workout_analysis = coach.analyze_workout(workout_data, feeling)
    print(workout_analysis)
    
    # Тест 4: Объяснение метрик
    print("\n📚 Тест 4: Объяснение метрик")
    print("-" * 50)
    explanation = coach.explain_metrics("CTL (Chronic Training Load)")
    print(explanation)
    
    # Тест 5: Ответ на вопрос
    print("\n❓ Тест 5: Ответ на произвольный вопрос")
    print("-" * 50)
    question = "Как часто нужно делать интервальные тренировки?"
    answer = coach.answer_question(question, test_metrics)
    print(answer)
    
    print(f"\n{'='*60}")
    print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ!")
    print("📱 Теперь можете протестировать в Streamlit приложении:")
    print("   streamlit run app.py")
    print("="*60)

if __name__ == "__main__":
    test_mock_ai()