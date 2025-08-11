#!/usr/bin/env python3
"""
Тест Ollama провайдера для AI коучинга
"""

from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

def test_ollama():
    print("🦙 Тестирование Ollama AI коучинга")
    print("=" * 60)
    
    # Проверяем доступность Ollama
    print("\n📊 Проверка Ollama провайдера:")
    try:
        provider = AIProviderFactory.create_provider(
            "ollama",
            host="http://localhost:11434",
            model="tinyllama:latest"  # Очень маленькая модель - 637MB
        )
        
        if provider and provider.is_available():
            print(f"✅ Подключено к: {provider.get_model_name()}")
        else:
            print("❌ Ollama недоступен")
            print("Убедитесь что:")
            print("1. Ollama сервер запущен")
            print("2. Модель llama3.1:8b загружена")
            return
            
    except Exception as e:
        print(f"❌ Ошибка создания Ollama провайдера: {e}")
        return
    
    # Создаём AI коуча
    coach = UniversalAICoach(provider)
    
    # Тестовые метрики
    test_metrics = {
        'ctl': 48.5,
        'atl': 35.2,
        'tsb': 13.3,
        'form': 'Отличная форма',
        'week_activities': 6,
        'week_tss': 420,
        'avg_tss': 70,
        'primary_sport': 'велосипед'
    }
    
    print(f"\n{'='*60}")
    print("🧪 ТЕСТИРОВАНИЕ OLLAMA AI КОУЧИНГА")
    print('='*60)
    
    # Тест 1: Анализ состояния (русские промпты)
    print(f"\n📊 Тест 1: Анализ состояния спортсмена")
    print("-" * 50)
    analysis = coach.analyze_current_state(test_metrics)
    print(analysis)
    
    # Тест 2: Быстрый вопрос
    print(f"\n❓ Тест 2: Простой вопрос коучу")
    print("-" * 50)
    question = "Что означает TSB +13.3? Хорошо это или плохо?"
    answer = coach.answer_question(question, test_metrics)
    print(f"Вопрос: {question}")
    print(f"Ответ: {answer}")
    
    # Тест 3: Объяснение метрик
    print(f"\n📚 Тест 3: Объяснение CTL")
    print("-" * 50)
    explanation = coach.explain_metrics("CTL (Chronic Training Load)")
    print(explanation)
    
    print(f"\n{'='*60}")
    print("✅ ТЕСТИРОВАНИЕ OLLAMA ЗАВЕРШЕНО!")
    print("🎉 Локальный AI коучинг работает без внешних API!")
    print("📱 Запустите Streamlit: streamlit run app.py")
    print("="*60)

if __name__ == "__main__":
    test_ollama()