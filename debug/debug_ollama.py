#!/usr/bin/env python3
"""
Отладка Ollama провайдера
"""

def debug_ollama():
    print("🔍 Отладка Ollama провайдера")
    print("=" * 50)
    
    # Проверка 1: Прямой запрос к Ollama API
    print("\n1️⃣ Прямая проверка Ollama API:")
    import requests
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"✅ API доступно, найдено моделей: {len(models)}")
            for model in models[:5]:  # Показываем первые 5
                print(f"   - {model.get('name', 'unknown')}")
        else:
            print(f"❌ API недоступно, статус: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Ошибка подключения к API: {e}")
        return
    
    # Проверка 2: Ollama библиотека
    print("\n2️⃣ Проверка Ollama Python библиотеки:")
    try:
        import ollama
        print("✅ Библиотека ollama импортирована")
        
        # Создаём клиент
        client = ollama.Client(host="http://localhost:11434")
        print("✅ Клиент создан")
        
        # Получаем список моделей
        models = client.list()
        model_names = [m.get('name', '') for m in models.get('models', [])]
        print(f"✅ Получен список моделей: {len(model_names)}")
        
        target_model = "llama3.1:8b"
        found = any(target_model == name or target_model in name for name in model_names)
        
        print(f"\n🎯 Поиск модели '{target_model}':")
        print(f"   Доступные модели:")
        for name in model_names[:10]:  # Показываем первые 10
            status = "✅" if (target_model == name or target_model in name) else "   "
            print(f"   {status} {name}")
        
        print(f"\n   Результат поиска: {'✅ НАЙДЕНА' if found else '❌ НЕ НАЙДЕНА'}")
        
        if not found:
            print(f"\n💡 Попробуем найти похожие модели:")
            similar = [name for name in model_names if 'llama3' in name.lower()]
            if similar:
                print("   Найдены похожие модели:")
                for name in similar:
                    print(f"     - {name}")
                    
                print(f"\n🔧 Попробуйте изменить модель в .env файле на одну из:")
                for name in similar[:3]:
                    print(f"   OLLAMA_MODEL={name}")
        
    except ImportError:
        print("❌ Библиотека ollama не установлена")
        print("   Установите: pip install ollama")
        return
    except Exception as e:
        print(f"❌ Ошибка работы с библиотекой: {e}")
        return
    
    # Проверка 3: Тест простого запроса
    if found:
        print(f"\n3️⃣ Тест простого запроса к модели:")
        try:
            response = client.chat(
                model=target_model,
                messages=[{"role": "user", "content": "Привет! Ответь кратко."}]
            )
            answer = response['message']['content']
            print(f"✅ Модель ответила: {answer[:100]}...")
        except Exception as e:
            print(f"❌ Ошибка запроса к модели: {e}")
    
    # Проверка 4: AI провайдер
    print(f"\n4️⃣ Проверка AI провайдера:")
    try:
        from models.ai_providers import AIProviderFactory
        
        provider = AIProviderFactory.create_provider(
            "ollama",
            host="http://localhost:11434", 
            model=target_model
        )
        
        if provider:
            print("✅ Провайдер создан")
            available = provider.is_available()
            print(f"   is_available(): {'✅ True' if available else '❌ False'}")
            
            if available:
                print(f"   Модель: {provider.get_model_name()}")
        else:
            print("❌ Не удалось создать провайдер")
            
    except Exception as e:
        print(f"❌ Ошибка создания провайдера: {e}")

if __name__ == "__main__":
    debug_ollama()