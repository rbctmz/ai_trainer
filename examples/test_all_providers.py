#!/usr/bin/env python3
"""
Демонстрация всех доступных AI провайдеров
"""

import os
import sys
import time
from dotenv import load_dotenv

# Добавляем корневую папку в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.ai_providers import AIProviderFactory
from models.ai_coach_universal import UniversalAICoach

# Загружаем переменные окружения
load_dotenv()

def test_provider(provider_name: str, **kwargs):
    """Тестирование конкретного провайдера"""
    print(f"\n{'='*60}")
    print(f"🧪 Тестирование {provider_name.upper()}")
    print('='*60)
    
    try:
        # Создаём провайдера
        provider = AIProviderFactory.create_provider(provider_name, **kwargs)
        
        if not provider.is_available():
            print(f"❌ {provider_name} недоступен")
            return None
            
        print(f"✅ Подключено к: {provider.get_model_name()}")
        
        # Создаём коуча
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
        
        # Тест 1: Анализ состояния
        print(f"\n📊 Тест 1: Анализ состояния")
        print("-" * 40)
        start_time = time.time()
        
        analysis = coach.analyze_current_state(test_metrics)
        
        elapsed = time.time() - start_time
        print(f"⏱️  Время ответа: {elapsed:.1f}с")
        print(f"💬 Ответ ({len(analysis)} символов):")
        print(analysis[:200] + "..." if len(analysis) > 200 else analysis)
        
        # Тест 2: Объяснение метрики
        print(f"\n📚 Тест 2: Объяснение TSS")
        print("-" * 40)
        start_time = time.time()
        
        explanation = coach.explain_metrics("TSS (Training Stress Score)")
        
        elapsed = time.time() - start_time
        print(f"⏱️  Время ответа: {elapsed:.1f}с")
        print(f"💬 Ответ ({len(explanation)} символов):")
        print(explanation[:200] + "..." if len(explanation) > 200 else explanation)
        
        return provider
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def main():
    print("🤖 Тестирование всех AI провайдеров")
    print("=" * 60)
    
    # Проверяем доступные провайдеры
    print("\n📋 Статус провайдеров:")
    available = AIProviderFactory.get_available_providers()
    
    working_providers = []
    
    for name, is_available in available.items():
        status = "✅" if is_available else "❌"
        print(f"{status} {name}")
        
        if is_available:
            provider_key = name.lower().replace(" ", "_")
            working_providers.append(provider_key)
    
    if not working_providers:
        print("\n❌ Нет доступных провайдеров!")
        print("Настройте API ключи в .env файле:")
        print("- OPENAI_API_KEY")
        print("- ANTHROPIC_API_KEY")  
        print("- GOOGLE_API_KEY")
        print("- OLLAMA_HOST (для локальных моделей)")
        return
    
    print(f"\n🚀 Найдено {len(working_providers)} доступных провайдера(ов)")
    
    # Тестируем каждый провайдер
    results = {}
    
    # OpenAI
    if "openai" in working_providers:
        provider = test_provider(
            "openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        )
        if provider:
            results["OpenAI"] = provider
    
    # Anthropic
    if "anthropic" in working_providers:
        provider = test_provider(
            "anthropic", 
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
        )
        if provider:
            results["Anthropic"] = provider
    
    # Google
    if "google" in working_providers:
        provider = test_provider(
            "google",
            api_key=os.getenv("GOOGLE_API_KEY"),
            model=os.getenv("GOOGLE_MODEL", "gemini-pro")
        )
        if provider:
            results["Google"] = provider
    
    # Ollama
    if "ollama" in working_providers:
        provider = test_provider(
            "ollama",
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "llama2")
        )
        if provider:
            results["Ollama"] = provider
    
    # Итоговый отчёт
    print(f"\n{'='*60}")
    print("📈 ИТОГОВЫЙ ОТЧЁТ")
    print('='*60)
    
    if results:
        print(f"✅ Успешно протестировано: {len(results)} провайдера(ов)")
        for name, provider in results.items():
            print(f"   • {name}: {provider.get_model_name()}")
        
        print(f"\n💡 Рекомендации:")
        if "OpenAI" in results:
            print("   • OpenAI GPT-3.5: быстрый и недорогой для ежедневного использования")
        if "Anthropic" in results:
            print("   • Anthropic Claude: отличное качество анализа")
        if "Google" in results:
            print("   • Google Gemini: хороший баланс скорости и качества")
        if "Ollama" in results:
            print("   • Ollama: конфиденциальность, работает без интернета")
    else:
        print("❌ Ни один провайдер не работает")
        
    print(f"\n🎯 Для использования в приложении:")
    print("   1. Запустите: streamlit run app.py")
    print("   2. Перейдите в раздел '🤖 AI Коучинг'")
    print("   3. Выберите любого доступного провайдера")

if __name__ == "__main__":
    main()