#!/usr/bin/env python3
"""
Отладка ListResponse от Ollama
"""

import ollama

def debug_list_response():
    print("🔍 Отладка ListResponse от Ollama")
    print("=" * 50)
    
    try:
        client = ollama.Client(host="http://localhost:11434")
        models = client.list()
        
        print(f"📊 Информация об объекте:")
        print(f"   Тип: {type(models)}")
        print(f"   Атрибуты: {[attr for attr in dir(models) if not attr.startswith('_')]}")
        
        # Проверим, есть ли атрибут models
        if hasattr(models, 'models'):
            models_list = models.models
            print(f"   models атрибут: {type(models_list)}, длина: {len(models_list)}")
            
            if models_list:
                first_model = models_list[0]
                print(f"   Первая модель: {type(first_model)}")
                print(f"   Атрибуты модели: {[attr for attr in dir(first_model) if not attr.startswith('_')]}")
                
                # Пробуем получить имя модели
                if hasattr(first_model, 'name'):
                    print(f"   name: {first_model.name}")
                if hasattr(first_model, 'model'):
                    print(f"   model: {first_model.model}")
                    
                # Показываем все модели
                print(f"\n🦙 Все модели:")
                for i, model in enumerate(models_list[:10]):  # Первые 10
                    name = getattr(model, 'model', 'нет model')
                    print(f"   {i+1}. {name}")
                    
                # Ищем llama3.1:8b
                target = "llama3.1:8b"
                found = any(getattr(model, 'model', '') == target for model in models_list)
                print(f"\n🎯 Поиск '{target}': {'✅ НАЙДЕНА' if found else '❌ НЕ НАЙДЕНА'}")
                
                # Ищем что-то с llama3.1
                llama_models = [getattr(model, 'model', '') for model in models_list if 'llama3.1' in getattr(model, 'model', '')]
                if llama_models:
                    print(f"   Модели с 'llama3.1': {llama_models}")
                else:
                    print(f"   Модели с 'llama3.1': не найдены")
                    
                    # Ищем любые llama
                    any_llama = [getattr(model, 'model', '') for model in models_list if 'llama' in getattr(model, 'model', '').lower()]
                    if any_llama:
                        print(f"   Любые модели с 'llama': {any_llama}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    debug_list_response()