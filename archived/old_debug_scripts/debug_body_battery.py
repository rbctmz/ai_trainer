#!/usr/bin/env python3
"""
Отладка структуры Body Battery данных
"""

import sys
from datetime import datetime, timedelta
import json

sys.path.append('.')

from data.garmin_client import GarminClient

def debug_body_battery():
    """Детальная отладка Body Battery"""
    
    print("🔍 Отладка структуры Body Battery данных")
    print("=" * 50)
    
    client = GarminClient()
    
    # Используем обновленные креды
    email = "greg.kisel@yandex.ru"
    password = "cigNi9-suctem-pasgaj"
    
    if not client.authenticate(email, password):
        print(f"❌ Ошибка аутентификации: {client.auth_error}")
        return False
    
    print("✅ Подключен к Garmin Connect")
    
    # Проверяем структуру Body Battery за вчера
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    print(f"\n🔋 Детальная структура Body Battery за {date_str}:")
    
    battery_data = client.get_body_battery_data(yesterday)
    if battery_data:
        print(f"Тип данных: {type(battery_data)}")
        
        if isinstance(battery_data, list):
            print(f"Количество записей: {len(battery_data)}")
            
            for i, entry in enumerate(battery_data):
                print(f"\n📋 Запись {i+1}:")
                if isinstance(entry, dict):
                    print(f"  Ключи: {list(entry.keys())}")
                    for key, value in entry.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"  Данные: {entry}")
                    
                if i >= 2:  # Показываем только первые 3 записи
                    print(f"  ... (показаны первые 3 из {len(battery_data)})")
                    break
                    
        elif isinstance(battery_data, dict):
            print(f"Структура словаря:")
            for key, value in battery_data.items():
                print(f"  {key}: {value}")
        else:
            print(f"Неожиданный тип данных: {battery_data}")
    else:
        print("📭 Body Battery данные не найдены")
    
    return battery_data is not None

if __name__ == "__main__":
    debug_body_battery()