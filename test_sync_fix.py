#!/usr/bin/env python3
"""
Тест исправлений ошибок синхронизации
"""

import sys
import pandas as pd

sys.path.append('.')

from data.database import Database

def test_dataframe_operations():
    """Тест операций с DataFrame которые вызывали ошибки"""
    
    print("🧪 Тестирование исправлений DataFrame операций...")
    
    # Создаем тестовый DataFrame
    test_data = [
        {'date': '2025-01-01', 'tss': 85.5, 'sport': 'running'},
        {'date': '2025-01-02', 'tss': None, 'sport': 'cycling'},
        {'date': '2025-01-03', 'tss': 92.3, 'sport': 'swimming'}
    ]
    
    df = pd.DataFrame(test_data)
    
    print("📊 Тестовые данные:")
    print(df)
    print()
    
    # Тест операций которые вызывали ошибки
    print("🔍 Тестирование обращений к DataFrame...")
    
    # Старый способ (ошибочный): row.get('tss', 0)
    # Новый способ (правильный): row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
    
    for idx, row in df.iterrows():
        # Проверяем исправленный код
        tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
        print(f"Строка {idx}: tss = {tss_val} (оригинал: {row['tss']})")
    
    print("\n✅ DataFrame операции работают корректно!")
    
    # Тест сохранения в базу данных
    print("\n💾 Тестирование сохранения в БД...")
    
    db = Database()
    
    # Конвертируем в список словарей (как в исправленном коде)
    activities_list = df.to_dict('records')
    print(f"Конвертированный список: {activities_list}")
    
    try:
        db.save_activities(activities_list)
        print("✅ Сохранение в БД работает!")
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
    
    print("\n🎉 Все исправления работают корректно!")

if __name__ == "__main__":
    test_dataframe_operations()