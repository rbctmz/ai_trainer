#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы AI коучинга
"""

import sys
sys.path.append('..')
from dotenv import load_dotenv
from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

# Загружаем переменные окружения
load_dotenv()

def test_ai_coach():
    print("🤖 Тестирование AI коучинга")
    print("=" * 60)
    
    # Проверяем доступные провайдеры
    print("\n📊 Доступные AI провайдеры:")
    available = AIProviderFactory.get_available_providers()
    
    available_providers = []
    for name, is_available in available.items():
        status = "✅" if is_available else "❌"
        print(f"{status} {name}")
        if is_available:
            available_providers.append(name.lower().replace(" ", "_"))
    
    if not available_providers:
        print("\n❌ Нет доступных провайдеров. Настройте API ключи в .env файле")
        return
    
    # Выбираем первый доступный провайдер
    print("\n🎯 Используем первый доступный провайдер...")
    provider = AIProviderFactory.get_first_available()
    
    if not provider:
        print("❌ Не удалось инициализировать провайдер")
        return
    
    print(f"✅ Подключено к: {provider.get_model_name()}")
    
    # Создаём AI коуча
    coach = UniversalAICoach(provider)
    
    # Тестовые метрики
    test_metrics = {
        'ctl': 42.5,
        'atl': 38.2,
        'tsb': 4.3,
        'form': 'Хорошая форма',
        'week_activities': 5,
        'week_tss': 380,
        'avg_tss': 76,
        'primary_sport': 'бег'
    }
    
    print("\n" + "=" * 60)
    print("📝 Тестируем анализ состояния спортсмена...")
    print("-" * 60)
    
    analysis = coach.analyze_current_state(test_metrics)
    print(analysis)
    
    print("\n" + "=" * 60)
    print("❓ Тестируем объяснение метрики TSS...")
    print("-" * 60)
    
    explanation = coach.explain_metrics("TSS (Training Stress Score)")
    print(explanation)
    
    print("\n" + "=" * 60)
    print("✅ Тестирование завершено!")

if __name__ == "__main__":
    test_ai_coach()