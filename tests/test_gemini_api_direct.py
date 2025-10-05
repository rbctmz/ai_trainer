#!/usr/bin/env python3
"""
Прямое тестирование Google Gemini API через curl и requests
"""

import sys
import subprocess
import requests
import json

import pytest

from config.settings import Settings


@pytest.fixture(scope="module")
def api_key():
    key = Settings.GOOGLE_API_KEY
    if not key:
        pytest.skip("GOOGLE_API_KEY не настроен для интеграционных тестов Gemini")
    return key

def test_gemini_curl(api_key: str):
    """Тест Gemini API через curl команду"""

    print("🌐 ТЕСТ GEMINI API ЧЕРЕЗ CURL")
    print("=" * 50)

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

    print("🔧 Команда curl:")
    masked_command = " ".join(curl_command).replace(api_key, "***API_KEY***")
    print(f"  {masked_command}")

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        pytest.fail("Таймаут curl команды")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Исключение при выполнении curl: {exc}")

    print("\n📊 Результат curl:")
    print(f"  Return code: {result.returncode}")
    print(f"  📄 stdout: {result.stdout[:200]}")
    print(f"  📄 stderr: {result.stderr[:200]}")

    assert result.returncode == 0, "curl не смог получить ответ от Gemini"

    try:
        response_data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Ошибка парсинга JSON: {exc}. Raw output: {result.stdout[:500]}")

    assert 'candidates' in response_data, f"Неожиданная структура ответа: {response_data}"
    text = response_data['candidates'][0]['content']['parts'][0]['text']
    assert text, "Ответ Gemini пуст"
    print(f"  💬 Ответ AI: {text[:200]}...")

def test_gemini_requests(api_key: str):
    """Тест Gemini API через Python requests"""

    print("\n🐍 ТЕСТ GEMINI API ЧЕРЕЗ PYTHON REQUESTS")
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

    print("🌐 Отправка запроса к API...")

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
    except requests.exceptions.Timeout:
        pytest.fail("Таймаут HTTP-запроса к Gemini")
    except requests.RequestException as exc:
        pytest.fail(f"HTTP исключение: {exc}")

    print(f"📊 HTTP Status: {response.status_code}")
    assert response.status_code == 200, f"Gemini API вернул ошибку: {response.text}"

    response_data = response.json()
    assert 'candidates' in response_data, f"Неожиданная структура ответа: {response_data}"
    text = response_data['candidates'][0]['content']['parts'][0]['text']
    assert text, "Ответ Gemini пуст"
    print(f"✅ Успешный ответ!\n💬 AI тренер отвечает: {text}")

def test_available_models(api_key: str):
    """Проверяем доступные модели Gemini"""

    print("\n📋 ПРОВЕРКА ДОСТУПНЫХ МОДЕЛЕЙ GEMINI")
    print("=" * 50)

    models_url = "https://generativelanguage.googleapis.com/v1beta/models"

    headers = {
        "X-goog-api-key": api_key
    }

    try:
        response = requests.get(models_url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        pytest.fail(f"HTTP исключение при получении списка моделей: {exc}")

    assert response.status_code == 200, f"Не удалось получить список моделей: {response.status_code} {response.text}"

    models_data = response.json()
    assert 'models' in models_data, f"Неожиданная структура ответа: {models_data}"

    gemini_models = [
        model for model in models_data['models']
        if 'gemini' in model['name'].lower()
    ]

    assert gemini_models, "Gemini модели не найдены"

    print(f"✅ Найдено моделей: {len(models_data['models'])}")
    print("🤖 Доступные Gemini модели:")
    for model in gemini_models:
        name = model['name'].split('/')[-1]
        print(f"  • {name}")

    # Дополнительная проверка: первая модель должна иметь имя
    assert gemini_models[0]['name'], "Некорректная запись модели"

def main():
    print("🚀 ПРЯМОЕ ТЕСТИРОВАНИЕ GOOGLE GEMINI API")
    print("=" * 60)
    
    # Получаем API ключ
    api_key = Settings.GOOGLE_API_KEY
    
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
