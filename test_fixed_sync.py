#!/usr/bin/env python3
"""
Тест исправленной синхронизации HRV, стресс и Body Battery
"""

import sys
from datetime import datetime, timedelta

sys.path.append('.')

from data.garmin_client import GarminClient
from data.database import Database

def test_fixed_sync():
    """Тест исправленной синхронизации"""
    
    print("🧪 Тест исправленной синхронизации с правильной структурой данных")
    print("=" * 70)
    
    # Инициализация
    client = GarminClient() 
    database = Database()
    
    # Используем обновленные креды
    email = "greg.kisel@yandex.ru"
    password = "cigNi9-suctem-pasgaj"
    
    if not client.authenticate(email, password):
        print(f"❌ Ошибка аутентификации: {client.auth_error}")
        return False
    
    print("✅ Подключен к Garmin Connect")
    
    # Тестируем за последние 2 дня
    end_date = datetime.now()
    start_date = end_date - timedelta(days=2)
    
    print(f"\n💓 Синхронизация за период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    hrv_data = {}
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"\n📅 Обработка даты: {date_str}")
        
        # HRV данные
        hrv_day_data = client.get_hrv_data(current_date)
        rmssd_value = None
        if hrv_day_data and 'hrvSummary' in hrv_day_data:
            hrv_summary = hrv_day_data['hrvSummary']
            rmssd_value = hrv_summary.get('lastNightAvg')
            print(f"  💓 HRV: RMSSD = {rmssd_value}")
        else:
            print(f"  📭 HRV данные не найдены")
        
        # Стресс данные (исправленная логика)
        stress_score = None
        stress_data = client.get_stress_data(current_date)
        if stress_data:
            stress_score = stress_data.get('avgStressLevel') or stress_data.get('overallStressLevel')
            print(f"  😰 Стресс: {stress_score}")
        else:
            print(f"  📭 Стресс данные не найдены")
        
        # Body Battery данные (исправленная логика)
        recovery_score = None
        body_battery_data = client.get_body_battery_data(current_date)
        if body_battery_data and isinstance(body_battery_data, list) and len(body_battery_data) > 0:
            entry = body_battery_data[0]
            print(f"  🔋 Body Battery найден")
            
            if 'bodyBatteryValuesArray' in entry and entry['bodyBatteryValuesArray']:
                battery_values = entry['bodyBatteryValuesArray']
                print(f"    Значений в массиве: {len(battery_values)}")
                if battery_values:
                    # Показываем первое и последнее значение
                    first_value = battery_values[0][1]
                    last_value = battery_values[-1][1]
                    recovery_score = last_value
                    print(f"    Начало дня: {first_value}%, конец дня: {last_value}%")
        else:
            print(f"  📭 Body Battery данные не найдены")
        
        # Сохраняем данные
        if rmssd_value is not None or stress_score is not None or recovery_score is not None:
            hrv_data[date_str] = {
                'rmssd': rmssd_value,
                'stress_score': stress_score,
                'recovery_score': recovery_score
            }
            print(f"  ✅ Данные подготовлены для сохранения")
        else:
            print(f"  ❌ Нет данных для сохранения")
        
        current_date += timedelta(days=1)
    
    # Сохранение в базу данных
    if hrv_data:
        print(f"\n💾 Сохранение {len(hrv_data)} записей в базу данных...")
        hrv_result = database.sync_hrv_data(hrv_data)
        print(f"  🆕 Новых: {hrv_result['new']}")
        print(f"  🔄 Обновлено: {hrv_result['updated']}")
        
        # Проверяем статистику по типам данных
        hrv_count = sum(1 for data in hrv_data.values() if data.get('rmssd') is not None)
        stress_count = sum(1 for data in hrv_data.values() if data.get('stress_score') is not None)
        recovery_count = sum(1 for data in hrv_data.values() if data.get('recovery_score') is not None)
        
        print(f"\n📊 Статистика синхронизированных данных:")
        print(f"  💓 RMSSD: {hrv_count} дней")
        print(f"  😰 Стресс: {stress_count} дней") 
        print(f"  🔋 Восстановление: {recovery_count} дней")
        
        # Проверяем результат в базе
        saved_hrv = database.get_hrv_data(30)
        print(f"\n📋 Последние записи в базе данных:")
        import pandas as pd
        for _, row in saved_hrv.head(5).iterrows():
            rmssd = row['rmssd'] if row['rmssd'] is not None and not pd.isna(row['rmssd']) else 'Н/Д'
            stress = row['stress_score'] if row['stress_score'] is not None else 'Н/Д'
            recovery = row['recovery_score'] if row['recovery_score'] is not None else 'Н/Д'
            print(f"  {row['date'].strftime('%Y-%m-%d')}: RMSSD={rmssd}, Стресс={stress}, Восст.={recovery}%")
        
        return True
    else:
        print("\n📭 Нет данных для синхронизации")
        return False

if __name__ == "__main__":
    success = test_fixed_sync()
    if success:
        print("\n🎉 Исправленная синхронизация работает!")
        print("📱 Запустите: streamlit run app.py")
        print("💡 Теперь стресс-индекс и восстановление должны показывать реальные значения!")
    else:
        print("\n❌ Проблемы с синхронизацией")