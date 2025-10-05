#!/usr/bin/env python3
"""
Отладка получения HRV данных из Garmin Connect
"""

import sys
from datetime import datetime, timedelta
import json

sys.path.append('.')

from data.garmin_client import GarminClient
from config.settings import Settings

def debug_hrv_data():
    """Отладка получения HRV данных"""
    
    print("🔍 Отладка получения HRV данных из Garmin Connect")
    print("=" * 60)
    
    # Инициализация клиента
    client = GarminClient()
    
    # Получаем креды из централизованных настроек или вводим вручную
    email = Settings.GARMIN_EMAIL
    password = Settings.GARMIN_PASSWORD
    
    if not email or not password:
        print("📧 Введите данные для входа в Garmin Connect:")
        email = input("Email: ")
        password = input("Password: ")
    
    print(f"🔐 Подключаемся к Garmin Connect как {email}...")
    
    # Аутентификация
    if not client.authenticate(email, password):
        print(f"❌ Ошибка аутентификации: {client.auth_error}")
        return False
    
    print("✅ Успешно подключен к Garmin Connect!")
    
    # Проверяем HRV данные за последние несколько дней
    print("\n💓 Проверка HRV данных за последние 7 дней:")
    print("-" * 50)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    current_date = start_date
    hrv_found = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Дата: {date_str}")
        
        try:
            hrv_data = client.get_hrv_data(current_date)
            
            if hrv_data:
                hrv_found += 1
                print(f"  ✅ HRV данные найдены!")
                print(f"  📊 Тип данных: {type(hrv_data)}")
                print(f"  🔧 Структура данных:")
                
                if isinstance(hrv_data, dict):
                    for key, value in hrv_data.items():
                        print(f"    {key}: {value} ({type(value).__name__})")
                else:
                    print(f"    Данные: {hrv_data}")
                    
                # Пытаемся найти RMSSD в разных возможных ключах
                possible_keys = ['rmssd', 'RMSSD', 'weeklyAvg', 'lastNightAvg', 
                               'hrvValue', 'hrv_value', 'value']
                
                print(f"  🔍 Поиск RMSSD в возможных ключах:")
                for key in possible_keys:
                    if isinstance(hrv_data, dict) and key in hrv_data:
                        print(f"    ✅ {key}: {hrv_data[key]}")
                
            else:
                print(f"  📭 Нет HRV данных")
                
        except Exception as e:
            print(f"  ❌ Ошибка получения HRV: {e}")
        
        current_date += timedelta(days=1)
    
    print(f"\n📊 Итого найдено HRV данных: {hrv_found} из 7 дней")
    
    if hrv_found == 0:
        print("\n🤔 Возможные причины отсутствия HRV данных:")
        print("  1. Устройство не поддерживает HRV или не носилось ночью")
        print("  2. Данные еще не синхронизированы с Garmin Connect")
        print("  3. API метод работает по-другому")
        print("  4. Нужны специальные настройки в Garmin Connect")
        
        # Пробуем альтернативные методы получения данных
        print("\n🔧 Попытка альтернативных методов получения данных:")
        
        try:
            # Попробуем получить данные о сне (там часто есть HRV)
            sleep_data = client.client.get_sleep_data(end_date.strftime('%Y-%m-%d'))
            if sleep_data:
                print("  ✅ Найдены данные о сне:")
                print(f"    Структура: {type(sleep_data)}")
                if isinstance(sleep_data, dict):
                    for key in sleep_data.keys():
                        print(f"    Ключ: {key}")
        except Exception as e:
            print(f"  ❌ Данные о сне недоступны: {e}")
            
        try:
            # Попробуем получить wellness данные
            wellness = client.client.get_user_summary(end_date.strftime('%Y-%m-%d'))
            if wellness:
                print("  ✅ Найдены wellness данные:")
                print(f"    Структура: {type(wellness)}")
                if isinstance(wellness, dict):
                    for key in wellness.keys():
                        if 'hrv' in key.lower() or 'stress' in key.lower():
                            print(f"    HRV-ключ: {key} = {wellness[key]}")
        except Exception as e:
            print(f"  ❌ Wellness данные недоступны: {e}")
    
    return hrv_found > 0

if __name__ == "__main__":
    success = debug_hrv_data()
    if success:
        print("\n🎉 HRV данные найдены! Проблема может быть в обработке.")
    else:
        print("\n🚨 HRV данные не найдены в Garmin Connect.")
        print("📱 Убедитесь, что устройство поддерживает HRV и данные синхронизированы.")
