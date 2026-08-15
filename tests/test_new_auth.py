#!/usr/bin/env python3
"""
Тест с обновленными учетными данными Garmin
"""

import sys
import os
from datetime import datetime, timedelta
import pytest

sys.path.append('.')

from data.garmin_client import GarminClient

pytestmark = pytest.mark.live

def test_new_auth():
    """Тест с новыми учетными данными"""
    
    print("🧪 Тест подключения с обновленными учетными данными")
    print("=" * 60)
    
    client = GarminClient()
    
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        pytest.skip("GARMIN_EMAIL/GARMIN_PASSWORD не заданы для live Garmin auth test")
    
    print(f"🔐 Подключаемся к Garmin Connect как {email}...")
    
    if not client.authenticate(email, password):
        print(f"❌ Ошибка аутентификации: {client.auth_error}")
        pytest.fail(f"Ошибка аутентификации Garmin: {client.auth_error}")
    
    print("✅ Успешно подключен к Garmin Connect!")
    
    # Проверяем доступность данных за последние 2 дня
    end_date = datetime.now()
    start_date = end_date - timedelta(days=2)
    
    print(f"\n📊 Проверка данных за период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    current_date = start_date
    data_found = {"hrv": 0, "stress": 0, "recovery": 0, "activities": 0}
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Дата: {date_str}")
        
        # 1. HRV данные
        hrv_data = client.get_hrv_data(current_date)
        if hrv_data:
            data_found["hrv"] += 1
            if 'hrvSummary' in hrv_data:
                rmssd = hrv_data['hrvSummary'].get('lastNightAvg')
                print(f"  💓 HRV: RMSSD = {rmssd}")
            else:
                print(f"  💓 HRV данные найдены (структура: {type(hrv_data)})")
        else:
            print("  📭 Нет HRV данных")
        
        # 2. Стресс данные
        stress_data = client.get_stress_data(current_date)
        if stress_data:
            data_found["stress"] += 1
            print(f"  😰 Стресс данные найдены (тип: {type(stress_data)})")
            if isinstance(stress_data, dict):
                stress_keys = [k for k in stress_data.keys() if 'stress' in k.lower() or 'level' in k.lower()]
                if stress_keys:
                    print(f"    Ключи стресса: {stress_keys[:3]}")
                    for key in stress_keys[:2]:
                        print(f"    {key}: {stress_data[key]}")
        else:
            print("  📭 Нет стресс данных")
        
        # 3. Body Battery данные
        battery_data = client.get_body_battery_data(current_date)
        if battery_data:
            data_found["recovery"] += 1
            print(f"  🔋 Body Battery найден (тип: {type(battery_data)})")
            if isinstance(battery_data, list) and len(battery_data) > 0:
                first_entry = battery_data[0]
                last_entry = battery_data[-1]
                print(f"    Записей: {len(battery_data)}")
                print(f"    Начало дня: {first_entry.get('batteryLevelStart', 'Н/Д')}")
                print(f"    Конец дня: {last_entry.get('batteryLevelEnd', 'Н/Д')}")
        else:
            print("  📭 Нет Body Battery данных")
        
        current_date += timedelta(days=1)
    
    # 4. Проверим активности
    print("\n🏃 Проверка активностей...")
    activities = client.get_activities(start_date, end_date)
    if activities:
        data_found["activities"] = len(activities)
        print(f"  ✅ Найдено активностей: {len(activities)}")
        for i, activity in enumerate(activities[:3]):
            print(f"    {i+1}. {activity.get('activityName', 'Без названия')} - {activity.get('distance', 0):.1f}км")
    else:
        print("  📭 Нет активностей")
    
    print("\n📊 Итоговая статистика:")
    print(f"  💓 HRV данных: {data_found['hrv']} дней")
    print(f"  😰 Стресс данных: {data_found['stress']} дней")
    print(f"  🔋 Recovery данных: {data_found['recovery']} дней")
    print(f"  🏃 Активностей: {data_found['activities']}")
    
    total_data = sum(data_found.values())
    if total_data > 0:
        print("\n🎉 Подключение успешно! Найдены данные.")
        assert True
    else:
        print("\n⚠️  Подключение успешно, но данные не найдены.")
        pytest.fail("Garmin auth успешен, но данные за проверяемый период не найдены")

if __name__ == "__main__":
    success = test_new_auth()
    if success:
        print("\n✅ Тест пройден! Данные доступны.")
        print("💡 Можно обновить переменные окружения и протестировать синхронизацию.")
    else:
        print("\n❓ Возможно, устройство не синхронизировано или данные недоступны.")
