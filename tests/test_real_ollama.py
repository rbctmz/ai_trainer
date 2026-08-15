#!/usr/bin/env python3
"""
Тест реального Ollama AI коучинга с gemma3:4b
"""

import sys
sys.path.append('..')
from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

def test_real_ollama():
    print("🦙 Тестирование реального Ollama AI коучинга (gemma3:4b)")
    print("=" * 60)
    
    # Создаём Ollama провайдер (использует настройки из .env)
    provider = AIProviderFactory.create_provider("ollama")
    
    if not provider or not provider.is_available():
        print("❌ Ollama недоступен")
        return
        
    print(f"✅ Подключено к: {provider.get_model_name()}")
    
    # Создаём AI коуча
    coach = UniversalAICoach(provider)
    
    # Тестовые метрики
    test_metrics = {
        'ctl': 52.3,
        'atl': 41.8,
        'tsb': 10.5,
        'form': 'Отличная форма',
        'week_activities': 5,
        'week_tss': 380,
        'avg_tss': 76,
        'primary_sport': 'велосипед'
    }
    
    print(f"\n{'='*60}")
    print("🧪 ТЕСТИРОВАНИЕ РЕАЛЬНОГО OLLAMA AI КОУЧИНГА")
    print('='*60)
    
    # Тест 1: Простой вопрос
    print("\n❓ Тест 1: Простой вопрос")
    print("-" * 40)
    question = "Что означает TSB +10.5? Хорошо это или плохо для спортсмена?"
    print(f"Вопрос: {question}")
    print("Ответ Ollama:")
    answer = coach.answer_question(question, test_metrics)
    print(answer)
    
    # Тест 2: Анализ состояния (короткий)
    print("\n📊 Тест 2: Краткий анализ состояния")
    print("-" * 40)
    analysis = coach.analyze_current_state(test_metrics)
    print(analysis)
    
    print(f"\n{'='*60}")
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
    print("🎯 Ollama работает как локальный AI коуч!")
    print("="*60)

if __name__ == "__main__":
    test_real_ollama()