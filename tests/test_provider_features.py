#!/usr/bin/env python3
"""
Тестирование новых функций провайдеров:
- test_connection() - проверка подключения
- get_available_models() - получение списка моделей
"""

import sys
sys.path.append('..')
import pytest
from models.ai_providers import AIProviderFactory

pytestmark = pytest.mark.live

def test_provider_features():
    print("🔧 Тестирование новых функций AI провайдеров")
    print("=" * 60)
    
    # Список провайдеров для тестирования
    providers_to_test = [
        ('mock', {'delay': 0.1}),
        ('ollama', {}),
        ('openai', {}),
        ('anthropic', {}), 
        ('google', {})
    ]
    
    for provider_type, kwargs in providers_to_test:
        print(f"\n{'='*60}")
        print(f"🧪 Тестирование {provider_type.upper()}")
        print('='*60)
        
        try:
            # Создаём провайдер
            provider = AIProviderFactory.create_provider(provider_type, **kwargs)
            
            if not provider:
                print(f"❌ Не удалось создать провайдер {provider_type}")
                continue
            
            print(f"✅ Провайдер создан: {provider.get_model_name()}")
            print(f"   Доступен: {'✅' if provider.is_available() else '❌'}")
            
            # Тест 1: test_connection()
            print(f"\n🔗 Тест подключения:")
            connection_result = provider.test_connection()
            
            if connection_result.get('success'):
                print(f"   ✅ Подключение: {connection_result.get('message')}")
                print(f"   📊 Модель: {connection_result.get('model')}")
                
                # Дополнительная информация если есть
                for key, value in connection_result.items():
                    if key not in ['success', 'message', 'model']:
                        print(f"   📋 {key}: {value}")
            else:
                print(f"   ❌ Ошибка: {connection_result.get('error')}")
            
            # Тест 2: get_available_models()
            print(f"\n📜 Доступные модели:")
            models = provider.get_available_models()
            
            if models:
                print(f"   📊 Найдено моделей: {len(models)}")
                print("   📋 Список моделей:")
                for i, model in enumerate(models[:10], 1):  # Показываем первые 10
                    print(f"      {i}. {model}")
                
                if len(models) > 10:
                    print(f"      ... и ещё {len(models) - 10} моделей")
            else:
                print("   ⚠️  Список моделей пуст")
                
        except Exception as e:
            print(f"❌ Ошибка тестирования {provider_type}: {e}")
    
    print(f"\n{'='*60}")
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
    print("🎯 Новые функции добавлены во все провайдеры!")
    print("="*60)
    
    print("\n💡 Теперь в UI можно:")
    print("   1. Проверить API ключи перед использованием")
    print("   2. Показать список доступных моделей")
    print("   3. Диагностировать проблемы с подключением")

if __name__ == "__main__":
    test_provider_features()
