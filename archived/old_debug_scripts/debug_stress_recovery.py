#!/usr/bin/env python3
"""
Отладка получения данных о стрессе и восстановлении из Garmin Connect
"""

import sys
from datetime import datetime, timedelta
import json

sys.path.append('.')

from config.settings import Settings
from data.garmin_client import GarminClient

def debug_stress_recovery():
    """Отладка получения данных о стрессе и восстановлении"""
    
    print("🔍 Отладка данных о стрессе и восстановлении из Garmin Connect")
    print("=" * 70)
    
    # Инициализация клиента
    client = GarminClient()
    
    # Получаем креды из централизованных настроек
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
    
    # Проверяем данные за последние 3 дня
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)
    
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Дата: {date_str}")
        print("-" * 40)
        
        # 1. Проверяем user summary (может содержать стресс данные)
        try:
            print("🔍 Попытка получить user summary...")
            summary = client.client.get_user_summary(date_str)
            if summary:
                print(f"  ✅ User summary найден, тип: {type(summary)}")
                
                # Ищем стресс-данные
                stress_keys = [k for k in summary.keys() if 'stress' in k.lower()]
                if stress_keys:
                    print(f"  🎯 Найдены ключи со стрессом: {stress_keys}")
                    for key in stress_keys:
                        print(f"    {key}: {summary[key]}")
                else:
                    print("  📭 Нет ключей со стрессом")
                
                # Ищем recovery-данные
                recovery_keys = [k for k in summary.keys() if any(word in k.lower() for word in ['recovery', 'body', 'battery'])]
                if recovery_keys:
                    print(f"  🎯 Найдены ключи восстановления: {recovery_keys}")
                    for key in recovery_keys:
                        print(f"    {key}: {summary[key]}")
                else:
                    print("  📭 Нет ключей восстановления")
                    
            else:
                print("  📭 User summary не найден")
        except Exception as e:
            print(f"  ❌ Ошибка user summary: {e}")
        
        # 2. Проверяем daily stress data
        try:
            print("\n🔍 Попытка получить stress data...")
            stress_data = client.client.get_stress_data(date_str)
            if stress_data:
                print(f"  ✅ Stress data найдены!")
                print(f"  📊 Тип данных: {type(stress_data)}")
                if isinstance(stress_data, dict):
                    print(f"  🔧 Ключи: {list(stress_data.keys())}")
                    
                    # Показываем основные данные о стрессе
                    for key, value in stress_data.items():
                        if key in ['overallStressLevel', 'restStressLevel', 'activityStressLevel', 
                                  'stressLevelAvg', 'maxStressLevel', 'stressDuration']:
                            print(f"    {key}: {value}")
                else:
                    print(f"  📊 Данные: {stress_data}")
            else:
                print("  📭 Stress data не найдены")
        except Exception as e:
            print(f"  ❌ Ошибка stress data: {e}")
        
        # 3. Проверяем body battery (восстановление)
        try:
            print("\n🔍 Попытка получить body battery...")
            body_battery = client.client.get_body_battery(date_str, date_str)
            if body_battery:
                print(f"  ✅ Body battery найден!")
                print(f"  📊 Тип данных: {type(body_battery)}")
                if isinstance(body_battery, list) and len(body_battery) > 0:
                    print(f"  📊 Количество записей: {len(body_battery)}")
                    first_entry = body_battery[0]
                    print(f"  🔧 Структура первой записи:")
                    for key, value in first_entry.items():
                        print(f"    {key}: {value}")
                elif isinstance(body_battery, dict):
                    print(f"  🔧 Ключи: {list(body_battery.keys())}")
                else:
                    print(f"  📊 Данные: {body_battery}")
            else:
                print("  📭 Body battery не найден")
        except Exception as e:
            print(f"  ❌ Ошибка body battery: {e}")
        
        # 4. Проверяем sleep data (может содержать восстановление)
        try:
            print("\n🔍 Попытка получить sleep data...")
            sleep_data = client.client.get_sleep_data(date_str)
            if sleep_data:
                print(f"  ✅ Sleep data найдены!")
                print(f"  📊 Тип данных: {type(sleep_data)}")
                if isinstance(sleep_data, dict):
                    recovery_keys = [k for k in sleep_data.keys() if any(word in k.lower() for word in ['recovery', 'restful', 'quality'])]
                    if recovery_keys:
                        print(f"  🎯 Ключи восстановления в сне: {recovery_keys}")
                        for key in recovery_keys:
                            print(f"    {key}: {sleep_data[key]}")
            else:
                print("  📭 Sleep data не найдены")
        except Exception as e:
            print(f"  ❌ Ошибка sleep data: {e}")
        
        current_date += timedelta(days=1)
    
    print(f"\n📋 Резюме:")
    print("✅ HRV данные (RMSSD) - доступны через get_hrv_data()")
    print("❓ Стресс данные - проверить get_stress_data() или user_summary")
    print("❓ Восстановление - проверить get_body_battery() или sleep_data")
    
    return True

if __name__ == "__main__":
    debug_stress_recovery()
