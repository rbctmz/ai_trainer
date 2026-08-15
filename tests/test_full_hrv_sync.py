#!/usr/bin/env python3
"""
Тест полной синхронизации HRV, стресс и восстановление данных
"""

import sys
from datetime import datetime, timedelta

import pandas as pd
import pytest

sys.path.append('.')

from data.garmin_client import GarminClient
from data.database import Database
from config.settings import Settings

def test_full_hrv_sync():
    """Тест полной синхронизации HRV, стресс и восстановление"""
    
    print("🧪 Тест полной синхронизации HRV + стресс + восстановление")
    print("=" * 60)
    
    # Инициализация
    client = GarminClient() 
    database = Database()
    
    # Подключение к Garmin через централизованные настройки
    email = Settings.GARMIN_EMAIL
    password = Settings.GARMIN_PASSWORD
    
    if not email or not password:
        pytest.skip("Не найдены переменные окружения GARMIN_EMAIL и GARMIN_PASSWORD")

    if not client.authenticate(email, password):
        pytest.fail(f"Ошибка аутентификации: {client.auth_error}")
    
    print("✅ Подключен к Garmin Connect")
    
    # Тестируем новые методы за последние 2 дня
    end_date = datetime.now()
    start_date = end_date - timedelta(days=2)
    
    print(f"\n💓 Тест данных за период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
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
            print("  📭 HRV данные не найдены")
        
        # Стресс данные
        stress_score = None
        stress_data = client.get_stress_data(current_date)
        if stress_data:
            print(f"  🔧 Стресс данные найдены, тип: {type(stress_data)}")
            if isinstance(stress_data, dict):
                print(f"    Ключи: {list(stress_data.keys())}")
                stress_score = (stress_data.get('overallStressLevel') or 
                              stress_data.get('stressLevelAvg') or 
                              stress_data.get('restStressLevel'))
                print(f"  😰 Стресс: {stress_score}")
            else:
                print(f"    Данные: {stress_data}")
        else:
            print("  📭 Стресс данные не найдены")
        
        # Body Battery данные
        recovery_score = None
        body_battery_data = client.get_body_battery_data(current_date)
        if body_battery_data:
            print(f"  🔧 Body Battery найдены, тип: {type(body_battery_data)}")
            if isinstance(body_battery_data, list) and len(body_battery_data) > 0:
                print(f"    Количество записей: {len(body_battery_data)}")
                last_entry = body_battery_data[-1]
                recovery_score = last_entry.get('batteryLevelEnd') or last_entry.get('endLevel')
                print(f"  🔋 Восстановление: {recovery_score}%")
            elif isinstance(body_battery_data, dict):
                print(f"    Ключи: {list(body_battery_data.keys())}")
                recovery_score = body_battery_data.get('batteryLevelEnd') or body_battery_data.get('endLevel')
                print(f"  🔋 Восстановление: {recovery_score}%")
        else:
            print("  📭 Body Battery данные не найдены")
        
        # Сохраняем данные если есть хотя бы один показатель
        if rmssd_value is not None or stress_score is not None or recovery_score is not None:
            hrv_data[date_str] = {
                'rmssd': rmssd_value,
                'stress_score': stress_score,
                'recovery_score': recovery_score
            }
            print("  ✅ Данные сохранены")
        else:
            print("  ❌ Нет данных для сохранения")
        
        current_date += timedelta(days=1)
    
    # Сохранение в базу данных
    if hrv_data:
        print(f"\n💾 Сохранение {len(hrv_data)} записей...")
        hrv_result = database.sync_hrv_data(hrv_data)
        print(f"  🆕 Новых: {hrv_result['new']}")
        print(f"  🔄 Обновлено: {hrv_result['updated']}")
        
        # Проверяем результат
        saved_hrv = database.get_hrv_data(30)
        print(f"\n📊 Всего HRV записей в БД: {len(saved_hrv)}")
        
        if len(saved_hrv) > 0:
            print("📋 Последние записи с полными данными:")
            for _, row in saved_hrv.head(5).iterrows():
                rmssd = row['rmssd'] if row['rmssd'] is not None and not pd.isna(row['rmssd']) else 'Н/Д'
                stress = row['stress_score'] if row['stress_score'] is not None else 'Н/Д'
                recovery = row['recovery_score'] if row['recovery_score'] is not None else 'Н/Д'
                print(f"  {row['date'].strftime('%Y-%m-%d')}: RMSSD={rmssd}, Стресс={stress}, Восст.={recovery}")
        
        assert len(saved_hrv) > 0, "Должны быть сохраненные HRV данные"
    else:
        pytest.fail("Нет данных для синхронизации")

if __name__ == "__main__":
    import pandas as pd  # нужен для проверки isna
    
    success = test_full_hrv_sync()
    if success:
        print("\n🎉 Полная HRV синхронизация работает!")
        print("📱 Попробуйте: streamlit run app.py")
        print("💡 Теперь стресс-индекс и восстановление должны отображаться")
    else:
        print("\n❌ Проблемы с полной HRV синхронизацией")
