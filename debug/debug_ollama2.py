#!/usr/bin/env python3
"""
Детальная отладка ответа Ollama
"""

import ollama
import json

def debug_ollama_response():
    print("🔍 Детальная отладка ответа Ollama")
    print("=" * 50)
    
    try:
        client = ollama.Client(host="http://localhost:11434")
        models = client.list()
        
        print("📋 Полный ответ от client.list():")
        print(json.dumps(models, indent=2)[:1000] + "..." if len(str(models)) > 1000 else str(models))
        
        print(f"\n📊 Структура ответа:")
        print(f"   Тип: {type(models)}")
        if isinstance(models, dict):
            print(f"   Ключи: {list(models.keys())}")
            
            models_list = models.get('models', [])
            print(f"   models список: {len(models_list)} элементов")
            
            if models_list:
                first_model = models_list[0]
                print(f"   Первая модель:")
                print(f"     Тип: {type(first_model)}")
                print(f"     Ключи: {list(first_model.keys()) if isinstance(first_model, dict) else 'не dict'}")
                print(f"     name: {first_model.get('name', 'НЕТ КЛЮЧА name')}")
                print(f"     model: {first_model.get('model', 'НЕТ КЛЮЧА model')}")
        
        # Пробуем разные способы получения имен
        print(f"\n🎯 Попытки извлечения имен моделей:")
        
        # Способ 1: по ключу name
        names1 = [m.get('name', '') for m in models.get('models', [])]
        print(f"   По ключу 'name': {names1[:3]}...")
        
        # Способ 2: по ключу model
        names2 = [m.get('model', '') for m in models.get('models', [])]
        print(f"   По ключу 'model': {names2[:3]}...")
        
        # Способ 3: все ключи каждой модели
        if models.get('models'):
            print(f"   Все ключи первой модели: {list(models['models'][0].keys())}")
            
        # Проверим, есть ли наша модель
        target_model = "llama3.1:8b"
        found_in_names1 = any(target_model in str(name) for name in names1)
        found_in_names2 = any(target_model in str(name) for name in names2)
        
        print(f"\n🔍 Поиск '{target_model}':")
        print(f"   В 'name': {found_in_names1}")
        print(f"   В 'model': {found_in_names2}")
        
        # Попробуем найти что-то похожее на llama
        llama_names1 = [name for name in names1 if 'llama' in str(name).lower()]
        llama_names2 = [name for name in names2 if 'llama' in str(name).lower()]
        
        print(f"\n🦙 Модели с 'llama':")
        print(f"   В 'name': {llama_names1}")
        print(f"   В 'model': {llama_names2}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    debug_ollama_response()