#!/usr/bin/env python3
"""
Тест исправления ошибки 'Error binding parameter 1 - probably unsupported type'
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, date

sys.path.append('.')

from data.database import Database

def test_sqlite_binding():
    """Тест исправления проблем с типами данных в SQLite"""
    
    print("🧪 Тестирование исправлений SQLite binding...")
    
    # Создаем проблематичные данные с разными типами
    problematic_data = [
        {
            'activity_id': 'test_1',
            'date': date.today(),
            'sport': 'running',
            'duration_minutes': np.float64(65.5),  # numpy float
            'distance_km': np.float32(10.2),       # numpy float32
            'avg_hr': np.int64(155),               # numpy int64
            'max_hr': np.int32(175),               # numpy int32
            'avg_power': None,                     # None
            'max_power': pd.NA,                   # pandas NaN
            'elevation_gain': float('nan'),        # Python NaN
            'calories': 450,                       # обычный int
            'tss': 85.7                           # обычный float
        },
        {
            'activity_id': 'test_2',
            'date': '2025-01-02',                 # строка даты
            'sport': 'cycling',
            'duration_minutes': pd.NA,            # pandas NA
            'distance_km': np.nan,                # numpy nan
            'avg_hr': 0,
            'max_hr': 0,
            'avg_power': np.int64(250),
            'max_power': np.int64(400),
            'elevation_gain': np.float64(125.8),
            'calories': np.int32(600),
            'tss': np.float32(102.3)
        }
    ]
    
    print("📊 Проблематичные типы данных:")
    for i, activity in enumerate(problematic_data):
        print(f"\nАктивность {i+1}:")
        for key, value in activity.items():
            print(f"  {key}: {value} ({type(value)})")
    
    # Тест функции clean_value
    print("\n🔧 Тестирование функции clean_value...")
    
    db = Database()
    
    test_values = [
        np.float64(65.5),
        np.int32(155),
        None,
        pd.NA,
        float('nan'),
        'normal_string',
        123,
        45.6
    ]
    
    for value in test_values:
        cleaned = db.clean_value(value)
        print(f"  {value} ({type(value)}) -> {cleaned} ({type(cleaned)})")
    
    # Тест сохранения в базу данных
    print("\n💾 Тестирование сохранения в БД...")
    
    try:
        db.save_activities(problematic_data)
        print("✅ Сохранение активностей прошло успешно!")
    except Exception as e:
        print(f"❌ Ошибка сохранения активностей: {e}")
        return False
    
    # Тест HRV данных с проблематичными типами
    print("\n💓 Тестирование HRV данных...")
    
    hrv_data = {
        '2025-01-01': {
            'rmssd': np.float64(35.5),
            'stress_score': np.int32(45),
            'recovery_score': pd.NA
        },
        '2025-01-02': {
            'rmssd': float('nan'),
            'stress_score': None,
            'recovery_score': np.float32(78.2)
        }
    }
    
    try:
        db.save_hrv_data(hrv_data)
        print("✅ Сохранение HRV данных прошло успешно!")
    except Exception as e:
        print(f"❌ Ошибка сохранения HRV: {e}")
        return False
    
    # Проверка загрузки данных обратно
    print("\n📖 Тестирование загрузки данных...")
    
    try:
        activities_df = db.get_activities(30)
        print(f"✅ Загружено {len(activities_df)} активностей")
        
        hrv_df = db.get_hrv_data(30)
        print(f"✅ Загружено {len(hrv_df)} записей HRV")
        
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        return False
    
    print("\n🎉 Все тесты прошли успешно! SQLite binding исправлен!")
    return True

if __name__ == "__main__":
    success = test_sqlite_binding()
    if success:
        print("\n✅ Исправление работает корректно!")
    else:
        print("\n❌ Требуются дополнительные исправления!")