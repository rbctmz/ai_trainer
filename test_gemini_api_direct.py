#!/usr/bin/env python3
"""
Прямое тестирование Google Gemini API через curl и requests
"""

import sys
import os
import subprocess
import requests
import json

def test_gemini_curl(api_key: str):
    """Тест Gemini API через curl команду"""
    
    print("🌐 ТЕСТ GEMINI API ЧЕРЕЗ CURL")
    print("=" * 50)
    
    # Подготавливаем curl команду
    curl_command = [
        'curl',
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent',
        '-H', 'Content-Type: application/json',
        '-H', f'X-goog-api-key: {api_key}',
        '-X', 'POST',
        '-d', json.dumps({
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Explain how AI works in a few words"
                        }
                    ]
                }
            ]
        })
    ]
    
    print(f"🔧 Команда curl:")
    masked_command = " ".join(curl_command).replace(api_key, "***API_KEY***")
    print(f"  {masked_command}")
    
    try:
        # Выполняем curl команду
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
        
        print(f"\n📊 Результат curl:")
        print(f"  Return code: {result.returncode}")
        
        if result.returncode == 0:
            # Парсим JSON ответ
            try:
                response_data = json.loads(result.stdout)
                print(f"  ✅ Успешный ответ JSON")
                
                # Извлекаем текст ответа
                if 'candidates' in response_data:
                    text = response_data['candidates'][0]['content']['parts'][0]['text']
                    print(f"  💬 Ответ AI: {text[:200]}...")
                    return True
                else:
                    print(f"  ❌ Неожиданная структура ответа: {response_data}")
                    return False
                    
            except json.JSONDecodeError as e:
                print(f"  ❌ Ошибка парсинга JSON: {e}")
                print(f"  📄 Raw output: {result.stdout[:500]}...")
                return False
        else:
            print(f"  ❌ Ошибка curl")
            print(f"  📄 stdout: {result.stdout}")
            print(f"  📄 stderr: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Таймаут curl команды")
        return False
    except Exception as e:
        print(f"  ❌ Исключение: {e}")
        return False

def test_gemini_requests(api_key: str):
    """Тест Gemini API через Python requests"""
    
    print(f"\n🐍 ТЕСТ GEMINI API ЧЕРЕЗ PYTHON REQUESTS")
    print("=" * 50)
    
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent"
    
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": "Дай краткий совет для восстановления после тренировки"
                    }
                ]
            }
        ]
    }
    
    try:
        print(f"🌐 Отправка запроса к API...")
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        print(f"📊 HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            
            if 'candidates' in response_data:
                text = response_data['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ Успешный ответ!")
                print(f"💬 AI тренер отвечает: {text}")
                return True
            else:
                print(f"❌ Неожиданная структура ответа")
                print(f"📄 Response: {response_data}")
                return False
        else:
            print(f"❌ Ошибка API")
            print(f"📄 Response: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏱️ Таймаут запроса")
        return False
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def test_available_models(api_key: str):
    """Проверяем доступные модели Gemini"""
    
    print(f"\n📋 ПРОВЕРКА ДОСТУПНЫХ МОДЕЛЕЙ GEMINI")
    print("=" * 50)
    
    models_url = "https://generativelanguage.googleapis.com/v1beta/models"
    
    headers = {
        "X-goog-api-key": api_key
    }
    
    try:
        response = requests.get(models_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            models_data = response.json()
            
            if 'models' in models_data:
                print(f"✅ Найдено моделей: {len(models_data['models'])}")
                
                # Фильтруем только Gemini модели
                gemini_models = [
                    model for model in models_data['models']
                    if 'gemini' in model['name'].lower()
                ]
                
                print(f"🤖 Доступные Gemini модели:")
                for model in gemini_models:
                    name = model['name'].split('/')[-1]
                    print(f"  • {name}")
                    
                return len(gemini_models) > 0
            else:
                print(f"❌ Неожиданная структура ответа моделей")
                return False
        else:
            print(f"❌ Ошибка получения списка моделей: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Исключение: {e}")
        return False

def main():
    print("🚀 ПРЯМОЕ ТЕСТИРОВАНИЕ GOOGLE GEMINI API")
    print("=" * 60)
    
    # Получаем API ключ
    api_key = os.getenv('GOOGLE_API_KEY')
    
    if not api_key:
        print("❌ API ключ не найден в переменной окружения GOOGLE_API_KEY")
        print("📝 Инструкции по получению ключа:")
        print("  1. Перейдите на https://aistudio.google.com/app/apikey")
        print("  2. Войдите в Google аккаунт")
        print("  3. Создайте новый API ключ")
        print("  4. Добавьте ключ в .env файл: GOOGLE_API_KEY=ваш_ключ")
        return False
    
    print(f"🔑 API ключ найден: {api_key[:10]}...{api_key[-5:]}")
    
    # Проверяем доступные модели
    models_ok = test_available_models(api_key)
    
    # Тестируем через curl
    curl_ok = test_gemini_curl(api_key)
    
    # Тестируем через requests
    requests_ok = test_gemini_requests(api_key)
    
    print(f"\n📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 30)
    print(f"{'✅' if models_ok else '❌'} Получение списка моделей")
    print(f"{'✅' if curl_ok else '❌'} Тест через curl")
    print(f"{'✅' if requests_ok else '❌'} Тест через Python requests")
    
    if curl_ok or requests_ok:
        print(f"\n🎉 GEMINI API РАБОТАЕТ!")
        print(f"💡 Теперь можно использовать в приложении")
        print(f"🔧 Добавьте GOOGLE_API_KEY в .env файл")
    else:
        print(f"\n❌ Проблемы с Gemini API")
        print(f"🔧 Проверьте:")
        print(f"  • Правильность API ключа")
        print(f"  • Интернет соединение")
        print(f"  • Квоты и лимиты Google AI Studio")
    
    return curl_ok or requests_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)