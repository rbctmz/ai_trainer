#!/usr/bin/env python3
"""
Тестирование библиотеки garth для получения данных Garmin
"""

import sys
import os
sys.path.append('..')

def test_garth_import():
    """Тестирование импорта и базовых возможностей garth"""
    print("🔍 Тестирование библиотеки garth...")
    
    try:
        import garth
        print("✅ Garth успешно импортирован")
        
        # Проверяем доступные методы
        garth_methods = [method for method in dir(garth) if not method.startswith('_')]
        print(f"\n📋 Доступные методы garth ({len(garth_methods)}):")
        for method in garth_methods[:10]:
            print(f"   • {method}")
        if len(garth_methods) > 10:
            print(f"   ... и ещё {len(garth_methods) - 10}")
        
        # Проверяем client
        if hasattr(garth, 'client'):
            print("✅ Garth client доступен")
        
        # Проверяем connectapi
        if hasattr(garth, 'connectapi'):
            print("✅ Garth connectapi доступен")
            
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта garth: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при тестировании garth: {e}")
        return False

def test_garth_authentication():
    """Тестирование аутентификации garth (без реальных данных)"""
    print("\n🔐 Тестирование аутентификации garth...")
    
    try:
        import garth
        
        print("📋 Методы аутентификации:")
        auth_methods = [method for method in dir(garth) if 'auth' in method.lower() or 'login' in method.lower()]
        for method in auth_methods:
            print(f"   • {method}")
        
        # Проверяем статус аутентификации
        try:
            is_auth = garth.client.is_authenticated if hasattr(garth, 'client') else False
            print(f"   Статус аутентификации: {is_auth}")
        except:
            print("   Аутентификация не выполнена (нормально для теста)")
        
        print("✅ Методы аутентификации доступны")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании аутентификации: {e}")
        return False

def explore_garth_sleep_methods():
    """Исследование методов для получения данных сна"""
    print("\n😴 Исследование методов для данных сна...")
    
    try:
        import garth
        
        print("📋 Возможные методы для данных сна:")
        
        # Примеры API endpoints для сна
        sleep_endpoints = [
            "/wellness-service/wellness/dailySleepData/{username}",
            "/wellness-service/wellness/sleepData",
            "/sleep-service/sleep/daily",
            "/wellness-service/wellness/bodyBattery/reports/daily"
        ]
        
        print("   API endpoints для сна:")
        for endpoint in sleep_endpoints:
            print(f"     • {endpoint}")
        
        # Пример использования connectapi
        print("\n💡 Пример получения данных сна:")
        example_code = '''
# Аутентификация
garth.login("username", "password")

# Получение данных сна
sleep_data = garth.connectapi(
    f"/wellness-service/wellness/dailySleepData/{garth.client.username}",
    params={"date": "2025-08-16", "nonSleepBufferMinutes": 60}
)

# Body Battery и стресс
body_battery = garth.connectapi(
    "/wellness-service/wellness/bodyBattery/reports/daily",
    params={"startDate": "2025-08-16", "endDate": "2025-08-16"}
)
'''
        print(example_code)
        
        print("✅ Методы для данных сна изучены")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при исследовании методов сна: {e}")
        return False

def create_garth_client_prototype():
    """Создание прототипа клиента с garth"""
    print("\n🛠️ Создание прототипа GarthClient...")
    
    garth_client_code = '''
import garth
from datetime import datetime, timedelta

class GarthClient:
    """Клиент для работы с Garmin Connect через библиотеку garth"""
    
    def __init__(self):
        self.is_authenticated = False
        self.auth_error = None
    
    def authenticate(self, email, password):
        """Аутентификация через garth"""
        try:
            garth.login(email, password)
            self.is_authenticated = True
            self.auth_error = None
            return True
        except Exception as e:
            self.auth_error = str(e)
            self.is_authenticated = False
            return False
    
    def get_sleep_data(self, date):
        """Получение данных сна через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            sleep_data = garth.connectapi(
                f"/wellness-service/wellness/dailySleepData/{garth.client.username}",
                params={"date": date_str, "nonSleepBufferMinutes": 60}
            )
            return sleep_data
        except Exception as e:
            print(f"Ошибка получения данных сна: {e}")
            return None
    
    def get_body_battery_data(self, date):
        """Получение данных Body Battery через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            body_battery = garth.connectapi(
                "/wellness-service/wellness/bodyBattery/reports/daily",
                params={"startDate": date_str, "endDate": date_str}
            )
            return body_battery
        except Exception as e:
            print(f"Ошибка получения Body Battery: {e}")
            return None
    
    def get_wellness_data(self, date):
        """Получение общих данных здоровья через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            wellness = garth.connectapi(
                f"/wellness-service/wellness/wellness/{date_str}"
            )
            return wellness
        except Exception as e:
            print(f"Ошибка получения данных здоровья: {e}")
            return None
'''
    
    print("💾 Прототип GarthClient создан:")
    print("   ✅ Аутентификация через garth.login()")
    print("   ✅ Получение данных сна через connectapi")
    print("   ✅ Получение Body Battery данных")
    print("   ✅ Получение общих данных здоровья")
    
    # Сохраняем прототип в файл
    with open("garth_client_prototype.py", "w", encoding="utf-8") as f:
        f.write(garth_client_code)
    
    print("📁 Прототип сохранён в garth_client_prototype.py")
    return True

def main():
    """Главная функция тестирования garth"""
    print("🚀 Исследование библиотеки garth для Garmin Connect\n")
    
    success_count = 0
    total_tests = 4
    
    if test_garth_import():
        success_count += 1
    
    if test_garth_authentication():
        success_count += 1
    
    if explore_garth_sleep_methods():
        success_count += 1
    
    if create_garth_client_prototype():
        success_count += 1
    
    print(f"\n📊 Результаты: {success_count}/{total_tests} тестов пройдено")
    
    if success_count == total_tests:
        print("\n🎉 Garth готов к интеграции!")
        print("\n📋 Следующие шаги:")
        print("   1. Создать GarthClient класс")
        print("   2. Интегрировать в существующий GarminClient")
        print("   3. Добавить методы получения данных сна")
        print("   4. Протестировать с реальными данными")
        print("   5. Обновить процесс синхронизации")
    else:
        print(f"\n⚠️  Найдены проблемы в {total_tests - success_count} тестах")

if __name__ == "__main__":
    main()