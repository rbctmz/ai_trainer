#!/usr/bin/env python3
"""
Тест умной синхронизации без дублей
"""

import sys
from datetime import date
import tempfile
from pathlib import Path

sys.path.append('.')

from data.database import Database
from tests.sync_fixtures import legacy_upsert_activities

def test_unique_sync(tmp_path):
    """Тест синхронизации с контролем уникальности"""
    
    print("🧪 Тестирование умной синхронизации без дублей")
    print("=" * 50)
    
    db = Database(str(tmp_path / "sync_unique.db"))
    
    # Очищаем базу для чистого теста
    db.clear_all_data()
    print("🧹 База данных очищена для теста")
    
    # Создаем тестовые активности
    test_activities_1 = [
        {
            'activity_id': 'test_sync_1',
            'date': date(2025, 1, 1),
            'sport': 'running',
            'duration_minutes': 60,
            'distance_km': 10.0,
            'tss': 85
        },
        {
            'activity_id': 'test_sync_2', 
            'date': date(2025, 1, 2),
            'sport': 'cycling',
            'duration_minutes': 90,
            'distance_km': 25.0,
            'tss': 120
        }
    ]
    
    print("\n📊 Первая синхронизация (новые данные):")
    result1 = legacy_upsert_activities(db, test_activities_1)
    print(f"  🆕 Новых: {result1['new']}")
    print(f"  🔄 Обновлено: {result1['updated']}")
    print(f"  ⏭️ Пропущено: {result1['skipped']}")
    
    # Проверяем количество записей (используем большое окно для тестовых данных)
    activities_df = db.get_activities(1000)
    print(f"  📋 Всего активностей в БД: {len(activities_df)}")
    assert result1 == {'new': 2, 'updated': 0, 'skipped': 0}
    assert len(activities_df) == 2
    
    # Вторая синхронизация - те же данные (не должны дублироваться)
    print("\n📊 Повторная синхронизация (те же данные):")
    result2 = legacy_upsert_activities(db, test_activities_1)
    print(f"  🆕 Новых: {result2['new']}")
    print(f"  🔄 Обновлено: {result2['updated']}")
    print(f"  ⏭️ Пропущено: {result2['skipped']}")
    
    activities_df = db.get_activities(1000)
    print(f"  📋 Всего активностей в БД: {len(activities_df)}")
    assert result2 == {'new': 0, 'updated': 2, 'skipped': 0}
    assert len(activities_df) == 2
    
    # Третья синхронизация - обновляем существующие + добавляем новые
    test_activities_2 = [
        {
            'activity_id': 'test_sync_1',  # Существующая - обновляем TSS
            'date': date(2025, 1, 1),
            'sport': 'running',
            'duration_minutes': 60,
            'distance_km': 10.0,
            'tss': 95  # Изменили TSS
        },
        {
            'activity_id': 'test_sync_3',  # Новая активность
            'date': date(2025, 1, 3),
            'sport': 'swimming',
            'duration_minutes': 45,
            'distance_km': 2.0,
            'tss': 60
        }
    ]
    
    print("\n📊 Смешанная синхронизация (обновления + новые):")
    result3 = legacy_upsert_activities(db, test_activities_2)
    print(f"  🆕 Новых: {result3['new']}")
    print(f"  🔄 Обновлено: {result3['updated']}")
    print(f"  ⏭️ Пропущено: {result3['skipped']}")
    
    activities_df = db.get_activities(1000)
    print(f"  📋 Всего активностей в БД: {len(activities_df)}")
    assert result3 == {'new': 1, 'updated': 1, 'skipped': 0}
    assert len(activities_df) == 3
    updated_row = activities_df[activities_df['activity_id'] == 'test_sync_1'].iloc[0]
    assert updated_row['tss'] == 95
    
    # Показываем итоговые данные
    print("\n📋 Итоговые данные в базе:")
    for _, row in activities_df.iterrows():
        print(f"  {row['activity_id']}: {row['date'].strftime('%Y-%m-%d')} - {row['sport']} (TSS: {row['tss']})")
    
    # Тест HRV синхронизации
    print("\n💓 Тестирование HRV синхронизации:")
    
    hrv_data_1 = {
        '2025-01-01': {'rmssd': 35.0, 'stress_score': 45, 'recovery_score': 75},
        '2025-01-02': {'rmssd': 32.0, 'stress_score': 50, 'recovery_score': 70}
    }
    
    result_hrv1 = db.sync_hrv_data(hrv_data_1)
    print(f"  🆕 Новых HRV: {result_hrv1['new']}")
    print(f"  🔄 Обновлено HRV: {result_hrv1['updated']}")
    assert result_hrv1 == {'new': 2, 'updated': 0}
    
    # Повторная синхронизация HRV
    hrv_data_2 = {
        '2025-01-01': {'rmssd': 38.0, 'stress_score': 40, 'recovery_score': 80},  # Обновляем
        '2025-01-03': {'rmssd': 33.0, 'stress_score': 48, 'recovery_score': 72}   # Новая
    }
    
    result_hrv2 = db.sync_hrv_data(hrv_data_2)
    print(f"  🆕 Новых HRV: {result_hrv2['new']}")
    print(f"  🔄 Обновлено HRV: {result_hrv2['updated']}")
    assert result_hrv2 == {'new': 1, 'updated': 1}
    
    hrv_df = db.get_hrv_data(1000)
    print(f"  📋 Всего HRV записей: {len(hrv_df)}")
    assert len(hrv_df) == 3
    
    print("\n🎉 Тест умной синхронизации завершен успешно!")
    print("✅ Дубли больше не создаются!")

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_unique_sync(Path(tmp_dir))
    print("\n✅ Все тесты прошли! Синхронизация теперь работает корректно.")
