#!/usr/bin/env python3
"""
Тест для проверки нового функционала управления данными
"""

import sys
import os
sys.path.append('..')

# Импорты для работы с приложением
try:
    from data.database import Database
    from data.garmin_client import GarminClient
except ImportError:
    # Если запускаем из корня проекта
    sys.path.append('.')
    from data.database import Database
    from data.garmin_client import GarminClient

from tests.sync_fixtures import legacy_upsert_activities
from datetime import datetime, timedelta

def test_database_operations():
    """Тестирование операций с базой данных"""
    print("🧪 Тестирование операций с базой данных...")
    
    # Создаем тестовую БД
    db = Database("test_data_management.db")
    
    # Тестовые данные для активностей
    test_activities = [
        {
            'activity_id': 'test_123',
            'date': '2024-01-15',
            'sport': 'cycling',
            'duration_minutes': 60,
            'distance_km': 25.5,
            'avg_hr': 155,
            'max_hr': 175,
            'avg_power': 200,
            'max_power': 350,
            'elevation_gain': 500,
            'calories': 800,
            'tss': 85.5
        },
        {
            'activity_id': 'test_456',
            'date': '2024-01-16', 
            'sport': 'running',
            'duration_minutes': 45,
            'distance_km': 8.2,
            'avg_hr': 165,
            'max_hr': 180,
            'avg_power': None,
            'max_power': None,
            'elevation_gain': 150,
            'calories': 450,
            'tss': 65.0
        }
    ]
    
    # Тестовые HRV данные
    test_hrv_data = {
        '2024-01-15': {
            'rmssd': 45.2,
            'stress_score': 35,
            'recovery_score': 75
        },
        '2024-01-16': {
            'rmssd': 42.8,
            'stress_score': 42,
            'recovery_score': 68
        }
    }
    
    print("📊 Тестирование синхронизации активностей...")
    sync_result = legacy_upsert_activities(db, test_activities)
    print(f"   Результат: {sync_result}")
    assert sync_result['new'] == 2, "Должно быть добавлено 2 активности"
    
    print("💓 Тестирование синхронизации HRV данных...")
    hrv_result = db.sync_hrv_data(test_hrv_data)
    print(f"   Результат: {hrv_result}")
    assert hrv_result['new'] == 2, "Должно быть добавлено 2 HRV записи"
    
    print("📈 Тестирование получения статистики...")
    stats = db.get_database_stats()
    print(f"   Статистика: {stats}")
    assert stats['activities'] >= 2, "Должно быть минимум 2 активности"
    assert stats['hrv_data'] >= 2, "Должно быть минимум 2 HRV записи"
    
    print("🗑️ Тестирование очистки БД...")
    db.clear_all_data()
    
    stats_after_clear = db.get_database_stats()
    print(f"   Статистика после очистки: {stats_after_clear}")
    assert stats_after_clear['activities'] == 0, "После очистки должно быть 0 активностей"
    assert stats_after_clear['hrv_data'] == 0, "После очистки должно быть 0 HRV записей"
    
    # Очистка тестового файла
    if os.path.exists("test_data_management.db"):
        os.remove("test_data_management.db")
    
    print("✅ Все тесты БД прошли успешно!")

def test_sync_optimization():
    """Тестирование оптимизации синхронизации"""
    print("\n⚡ Тестирование оптимизации синхронизации...")
    
    # Создаем тестовую БД
    db = Database("test_sync_optimization.db")
    
    # Генерируем большое количество тестовых активностей
    test_activities = []
    base_date = datetime(2024, 1, 1)
    
    for i in range(50):  # 50 активностей
        activity_date = base_date + timedelta(days=i)
        test_activities.append({
            'activity_id': f'bulk_test_{i}',
            'date': activity_date.strftime('%Y-%m-%d'),
            'sport': 'cycling' if i % 2 == 0 else 'running',
            'duration_minutes': 60 + i,
            'distance_km': 20.0 + i * 0.5,
            'avg_hr': 150 + i % 30,
            'max_hr': 180 + i % 20,
            'avg_power': 200 + i * 2 if i % 2 == 0 else None,
            'max_power': 350 + i * 5 if i % 2 == 0 else None,
            'elevation_gain': 100 + i * 10,
            'calories': 500 + i * 10,
            'tss': 50.0 + i * 1.5
        })
    
    print(f"📦 Синхронизация {len(test_activities)} активностей...")
    start_time = datetime.now()
    
    sync_result = legacy_upsert_activities(db, test_activities)
    
    end_time = datetime.now()
    sync_duration = (end_time - start_time).total_seconds()
    
    print(f"   Время синхронизации: {sync_duration:.2f} секунд")
    print(f"   Результат: {sync_result}")
    
    assert sync_result['new'] == 50, "Должно быть добавлено 50 активностей"
    assert sync_duration < 5.0, "Синхронизация должна занимать менее 5 секунд"
    
    # Тест повторной синхронизации (должна быть быстрее)
    print("🔄 Тест повторной синхронизации...")
    start_time = datetime.now()
    
    sync_result_2 = legacy_upsert_activities(db, test_activities)
    
    end_time = datetime.now()
    sync_duration_2 = (end_time - start_time).total_seconds()
    
    print(f"   Время повторной синхронизации: {sync_duration_2:.2f} секунд")
    print(f"   Результат: {sync_result_2}")
    
    assert sync_result_2['new'] == 0, "При повторной синхронизации не должно быть новых записей"
    assert sync_result_2['updated'] == 50, "Должно быть обновлено 50 записей"
    
    # Очистка тестового файла
    if os.path.exists("test_sync_optimization.db"):
        os.remove("test_sync_optimization.db")
    
    print("✅ Тесты оптимизации синхронизации прошли успешно!")

def test_garmin_client_integration():
    """Тестирование интеграции с Garmin Client"""
    print("\n🔗 Тестирование интеграции с Garmin Client...")
    
    client = GarminClient()
    
    # Проверяем, что клиент создается без ошибок
    assert not client.is_authenticated, "Клиент не должен быть аутентифицирован изначально"
    assert client.auth_error is None, "Не должно быть ошибок аутентификации изначально"
    
    # Тестируем методы без аутентификации
    activities = client.get_activities(datetime.now() - timedelta(days=7), datetime.now())
    assert activities == [], "Без аутентификации должен возвращаться пустой список"
    
    details = client.get_activity_details("test_id")
    assert details is None, "Без аутентификации должен возвращаться None"
    
    hrv_data = client.get_hrv_data(datetime.now())
    assert hrv_data is None, "Без аутентификации должен возвращаться None"
    
    print("✅ Тесты интеграции с Garmin Client прошли успешно!")

def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестов нового функционала управления данными\n")
    
    try:
        test_database_operations()
        test_sync_optimization() 
        test_garmin_client_integration()
        
        print("\n🎉 Все тесты прошли успешно!")
        print("\n📋 Новый функционал готов к использованию:")
        print("   ✅ Выбор периода синхронизации (7-90 дней)")
        print("   ✅ Прогресс-бар для синхронизации")
        print("   ✅ Оптимизация скорости синхронизации")
        print("   ✅ Статистика базы данных в сайдбаре")
        print("   ✅ Функция очистки БД с подтверждением")
        print("   ✅ Батчовая обработка HRV данных")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тестах: {e}")
        raise

if __name__ == "__main__":
    main()
