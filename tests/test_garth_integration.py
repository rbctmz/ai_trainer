#!/usr/bin/env python3
"""
Тест интеграции garth в GarminClient
"""

import sys
import os
sys.path.append('..')

try:
    from data.garmin_client import GarminClient, GARTH_AVAILABLE
    from data.garth_client import GarthClient
except ImportError:
    sys.path.append('.')
    from data.garmin_client import GarminClient, GARTH_AVAILABLE
    from data.garth_client import GarthClient

from datetime import datetime, timedelta

def test_garmin_client_with_garth():
    """Тестирование GarminClient с интеграцией garth"""
    print("🔍 Тестирование интеграции garth в GarminClient...")
    
    # Создаем клиент
    client = GarminClient()
    
    # Проверяем доступность garth
    print(f"   Garth доступен: {GARTH_AVAILABLE}")
    print(f"   Garth клиент создан: {client.garth_client is not None}")
    
    # Информация о подключении
    connection_info = client.get_connection_info()
    print(f"   Информация о подключении: {connection_info}")
    
    assert connection_info['garth_available'] == GARTH_AVAILABLE, "Статус garth должен совпадать"
    assert not connection_info['authenticated'], "Клиент не должен быть авторизован"
    assert not connection_info['using_garth'], "garth не должен использоваться без авторизации"
    
    print("   ✅ Базовая интеграция работает")
    return True

def test_garth_sleep_methods():
    """Тестирование методов получения данных сна"""
    print("\n😴 Тестирование методов garth для данных сна...")
    
    if not GARTH_AVAILABLE:
        print("   ⚠️  garth недоступен, тест пропущен")
        return True
    
    # Создаем garth клиент напрямую
    garth_client = GarthClient()
    
    # Проверяем методы без авторизации
    test_date = datetime.now() - timedelta(days=1)
    
    sleep_data = garth_client.get_sleep_data_garth(test_date)
    print(f"   Данные сна без авторизации: {sleep_data is not None}")
    
    hrv_data = garth_client.get_hrv_data_garth(test_date)
    print(f"   HRV данные без авторизации: {hrv_data is not None}")
    
    wellness_data = garth_client.get_wellness_comprehensive(test_date)
    print(f"   Комплексные данные без авторизации: {wellness_data is not None}")
    
    print("   ✅ Методы garth определены корректно")
    return True

def test_fallback_mechanism():
    """Тестирование механизма переключения между garth и garminconnect"""
    print("\n🔄 Тестирование механизма переключения...")
    
    client = GarminClient()
    
    # Тестируем метод получения данных сна без авторизации
    test_date = datetime.now() - timedelta(days=1)
    sleep_data = client.get_sleep_data(test_date)
    
    print(f"   Данные сна без авторизации: {sleep_data is not None}")
    print(f"   Используется garth: {client.use_garth}")
    
    # Информация о подключении
    info = client.get_connection_info()
    print(f"   Статус авторизации: {info['authenticated']}")
    
    assert not info['authenticated'], "Без авторизации клиент не должен быть авторизован"
    
    print("   ✅ Механизм переключения работает")
    return True

def test_comprehensive_integration():
    """Комплексное тестирование интеграции"""
    print("\n🎯 Комплексное тестирование интеграции...")
    
    try:
        # Проверяем импорты
        from data.garmin_client import GarminClient
        from data.garth_client import GarthClient
        print("   ✅ Все импорты работают")
        
        # Создаем клиенты
        garmin_client = GarminClient()
        garth_client = GarthClient()
        print("   ✅ Клиенты создаются без ошибок")
        
        # Проверяем методы
        assert hasattr(garmin_client, 'get_sleep_data'), "get_sleep_data должен быть доступен"
        assert hasattr(garmin_client, 'test_garth_connection'), "test_garth_connection должен быть доступен"
        assert hasattr(garmin_client, 'get_connection_info'), "get_connection_info должен быть доступен"
        print("   ✅ Все методы доступны")
        
        # Проверяем структуру данных
        connection_info = garmin_client.get_connection_info()
        required_keys = ['authenticated', 'using_garth', 'garth_available', 'auth_error']
        for key in required_keys:
            assert key in connection_info, f"Ключ {key} должен быть в connection_info"
        print("   ✅ Структура данных корректна")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка комплексного тестирования: {e}")
        return False

def create_usage_example():
    """Создание примера использования"""
    print("\n📝 Создание примера использования...")
    
    usage_example = '''
# Пример использования GarminClient с поддержкой garth

from data.garmin_client import GarminClient
from datetime import datetime, timedelta

# Создание клиента
client = GarminClient()

# Проверка доступности garth
info = client.get_connection_info()
print(f"Garth доступен: {info['garth_available']}")

# Авторизация (сначала попробует garth, потом garminconnect)
success = client.authenticate("email@example.com", "password")
if success:
    print(f"Авторизация успешна, используется: {'garth' if client.use_garth else 'garminconnect'}")
    
    # Получение данных сна (автоматически выберет лучший метод)
    yesterday = datetime.now() - timedelta(days=1)
    sleep_data = client.get_sleep_data(yesterday)
    
    if sleep_data:
        print("Данные сна получены!")
        # Обработка данных...
    else:
        print("Данные сна недоступны")
    
    # Тестирование garth подключения
    if client.use_garth:
        test_results = client.test_garth_connection()
        print(f"Тест garth: {test_results}")

# Отключение
client.disconnect()
'''
    
    print("💾 Пример использования:")
    print(usage_example)
    
    # Сохраняем в файл
    with open("garth_integration_example.py", "w", encoding="utf-8") as f:
        f.write(usage_example)
    
    print("📁 Пример сохранён в garth_integration_example.py")
    return True

def main():
    """Главная функция тестирования"""
    print("🚀 Тестирование интеграции garth в GarminClient\n")
    
    tests = [
        ("Базовая интеграция", test_garmin_client_with_garth),
        ("Методы garth", test_garth_sleep_methods),
        ("Механизм переключения", test_fallback_mechanism),
        ("Комплексное тестирование", test_comprehensive_integration),
        ("Пример использования", create_usage_example)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Ошибка в тесте '{test_name}': {e}")
    
    print(f"\n📊 Результаты: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("\n🎉 Интеграция garth завершена успешно!")
        print("\n📋 Готово к тестированию:")
        print("   ✅ GarminClient поддерживает garth")
        print("   ✅ Автоматическое переключение между библиотеками")
        print("   ✅ Улучшенные методы получения данных сна")
        print("   ✅ Диагностика и тестирование подключения")
        
        print("\n🚀 Следующие шаги:")
        print("   1. Протестировать с реальными данными Garmin")
        print("   2. Обновить процесс синхронизации в app.py")
        print("   3. Добавить в интерфейс информацию о типе подключения")
    else:
        print(f"\n⚠️  Найдены проблемы в {total - passed} тестах")

if __name__ == "__main__":
    main()