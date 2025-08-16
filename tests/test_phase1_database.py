#!/usr/bin/env python3
"""
Тест создания новых таблиц базы данных для Фазы 1
"""

import sys
import os
sys.path.append('..')

try:
    from data.database import Database
except ImportError:
    sys.path.append('.')
    from data.database import Database

import sqlite3

def test_new_tables_creation():
    """Тестирование создания новых таблиц"""
    print("🧪 Тестирование создания новых таблиц для Фазы 1...")
    
    # Создаем тестовую БД
    test_db_path = "test_phase1_tables.db"
    db = Database(test_db_path)
    
    # Проверяем, что новые таблицы созданы
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    
    # Получаем список всех таблиц
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"📊 Найденные таблицы: {tables}")
    
    # Проверяем наличие всех необходимых таблиц
    expected_tables = [
        'activities', 'hrv_data', 'user_settings',  # Существующие
        'sleep_data', 'daily_health', 'training_status'  # Новые
    ]
    
    for table in expected_tables:
        assert table in tables, f"Таблица {table} не найдена"
        print(f"   ✅ Таблица {table} создана")
    
    # Проверяем структуру новых таблиц
    print("\n🔍 Проверяем структуру новых таблиц:")
    
    # Таблица sleep_data
    cursor.execute("PRAGMA table_info(sleep_data)")
    sleep_columns = [row[1] for row in cursor.fetchall()]
    expected_sleep_columns = [
        'date', 'total_sleep_minutes', 'deep_sleep_minutes', 
        'light_sleep_minutes', 'rem_sleep_minutes', 'awakenings_count',
        'sleep_score', 'bedtime', 'wakeup_time', 'sleep_efficiency', 'created_at'
    ]
    
    for col in expected_sleep_columns:
        assert col in sleep_columns, f"Колонка {col} не найдена в sleep_data"
    print(f"   ✅ sleep_data: {len(sleep_columns)} колонок")
    
    # Таблица daily_health
    cursor.execute("PRAGMA table_info(daily_health)")
    health_columns = [row[1] for row in cursor.fetchall()]
    expected_health_columns = [
        'date', 'resting_hr', 'steps', 'floors_climbed',
        'calories_active', 'calories_bmr', 'distance_meters',
        'active_minutes', 'intensity_minutes', 'created_at'
    ]
    
    for col in expected_health_columns:
        assert col in health_columns, f"Колонка {col} не найдена в daily_health"
    print(f"   ✅ daily_health: {len(health_columns)} колонок")
    
    # Таблица training_status
    cursor.execute("PRAGMA table_info(training_status)")
    training_columns = [row[1] for row in cursor.fetchall()]
    expected_training_columns = [
        'date', 'vo2_max', 'fitness_age', 'training_load_7d',
        'training_status', 'training_readiness', 'recovery_time_hours',
        'load_ratio', 'created_at'
    ]
    
    for col in expected_training_columns:
        assert col in training_columns, f"Колонка {col} не найдена в training_status"
    print(f"   ✅ training_status: {len(training_columns)} колонок")
    
    conn.close()
    
    # Тестируем обновленную статистику БД
    print("\n📈 Тестирование статистики БД:")
    stats = db.get_database_stats()
    print(f"   Статистика: {stats}")
    
    # Проверяем, что новые таблицы включены в статистику
    assert 'sleep_data' in stats, "sleep_data не в статистике"
    assert 'daily_health' in stats, "daily_health не в статистике"
    assert 'training_status' in stats, "training_status не в статистике"
    
    # Все новые таблицы должны быть пустыми
    assert stats['sleep_data'] == 0, "sleep_data должна быть пустой"
    assert stats['daily_health'] == 0, "daily_health должна быть пустой"
    assert stats['training_status'] == 0, "training_status должна быть пустой"
    
    print("   ✅ Статистика включает все новые таблицы")
    
    # Тестируем очистку БД
    print("\n🗑️ Тестирование очистки БД:")
    db.clear_all_data()
    stats_after_clear = db.get_database_stats()
    print(f"   Статистика после очистки: {stats_after_clear}")
    
    for table, count in stats_after_clear.items():
        assert count == 0, f"Таблица {table} не очищена полностью"
    
    print("   ✅ Очистка БД работает для всех таблиц")
    
    # Очистка тестового файла
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    print("\n✅ Все тесты новых таблиц прошли успешно!")
    return True

def main():
    """Основная функция тестирования"""
    print("🚀 Тестирование структуры БД для Фазы 1\n")
    
    try:
        if test_new_tables_creation():
            print("\n🎉 Структура БД успешно обновлена!")
            print("\n📋 Созданные таблицы:")
            print("   ✅ sleep_data - данные сна (время, фазы, качество)")
            print("   ✅ daily_health - ежедневные показатели (пульс покоя, шаги)")
            print("   ✅ training_status - статус тренированности (VO2 max, готовность)")
            print("\n🔧 Обновленные методы:")
            print("   ✅ get_database_stats() - включает новые таблицы")
            print("   ✅ clear_all_data() - очищает все таблицы")
        
    except Exception as e:
        print(f"\n❌ Ошибка в тестах: {e}")
        raise

if __name__ == "__main__":
    main()