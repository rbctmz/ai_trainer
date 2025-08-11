#!/usr/bin/env python3
"""
Детальная отладка проблемы с Ollama
"""

import os
import sys
sys.path.append('..')
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

def debug_ollama_issue():
    print("🔍 Детальная отладка проблемы с Ollama")
    print("=" * 50)
    
    # Проверяем переменные окружения
    print("\n📋 Переменные окружения:")
    print(f"   OLLAMA_HOST: {os.getenv('OLLAMA_HOST')}")
    print(f"   OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL')}")
    print(f"   DEFAULT_AI_PROVIDER: {os.getenv('DEFAULT_AI_PROVIDER')}")
    
    # Проверяем settings
    from config.settings import Settings
    print(f"\n⚙️ Settings:")
    print(f"   Settings.OLLAMA_HOST: {Settings.OLLAMA_HOST}")
    print(f"   Settings.OLLAMA_MODEL: {Settings.OLLAMA_MODEL}")
    print(f"   Settings.DEFAULT_AI_PROVIDER: {Settings.DEFAULT_AI_PROVIDER}")
    
    # Пробуем создать провайдер напрямую
    print(f"\n🏭 Создание провайдера напрямую:")
    from models.ai_providers import OllamaProvider
    
    try:
        provider = OllamaProvider(
            host=Settings.OLLAMA_HOST,
            model=Settings.OLLAMA_MODEL
        )
        print(f"   ✅ Провайдер создан")
        
        # Проверяем is_available()
        available = provider.is_available()
        print(f"   is_available(): {available}")
        
        if not available:
            print(f"   🔍 Отладка is_available():")
            
            # Проверяем клиент
            print(f"   client: {provider.client}")
            
            if provider.client:
                try:
                    models_response = provider.client.list()
                    print(f"   models_response type: {type(models_response)}")
                    
                    if hasattr(models_response, 'models'):
                        models_list = models_response.models
                        print(f"   models count: {len(models_list)}")
                        
                        model_names = [getattr(m, 'model', '') for m in models_list]
                        print(f"   model names: {model_names[:5]}...")
                        
                        target_model = Settings.OLLAMA_MODEL
                        found = any(target_model == name or target_model in name for name in model_names)
                        print(f"   Target model '{target_model}' found: {found}")
                        
                        if not found:
                            print(f"   🔍 Поиск похожих:")
                            similar = [name for name in model_names if any(part in name.lower() for part in target_model.lower().split(':'))]
                            print(f"   Похожие модели: {similar}")
                            
                except Exception as e:
                    print(f"   ❌ Ошибка проверки моделей: {e}")
        else:
            print(f"   ✅ Провайдер доступен!")
            
    except Exception as e:
        print(f"   ❌ Ошибка создания провайдера: {e}")
    
    # Тестируем Factory
    print(f"\n🏭 Тестирование Factory:")
    from models.ai_providers import AIProviderFactory
    
    try:
        factory_provider = AIProviderFactory.create_provider("ollama")
        print(f"   ✅ Factory создал провайдер: {type(factory_provider)}")
        print(f"   Factory provider host: {factory_provider.host}")
        print(f"   Factory provider model: {factory_provider.model}")
        print(f"   Factory provider client: {factory_provider.client}")
        
        if factory_provider:
            factory_available = factory_provider.is_available()
            print(f"   Factory is_available(): {factory_available}")
    except Exception as e:
        print(f"   ❌ Ошибка Factory: {e}")

if __name__ == "__main__":
    debug_ollama_issue()