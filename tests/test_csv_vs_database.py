#!/usr/bin/env python3
"""
Тест для диагностики расхождения между данными в базе и CSV экспортом
"""

import sys
import os
import sqlite3
import pytest

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import Database

pytestmark = pytest.mark.debug

def test_database_vs_csv():
    """Проверяем что хранится в базе данных vs что попало в CSV"""
    print("🔍 Диагностика данных: База данных vs CSV экспорт...")
    
    # Проверяем напрямую в базе SQLite
    conn = sqlite3.connect('ai_trainer.db')
    cursor = conn.cursor()
    
    # Получаем все записи о сне за последние дни
    cursor.execute("""
        SELECT date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes, sleep_score
        FROM sleep_data 
        WHERE date >= '2025-08-09' 
        ORDER BY date DESC
    """)
    
    raw_data = cursor.fetchall()
    conn.close()
    
    if raw_data:
        print(f"✅ Найдено {len(raw_data)} записей в базе данных:")
        print("📊 Данные прямо из базы SQLite:")
        for row in raw_data:
            date, total, deep, light, rem, score = row
            print(f"  {date}: total={total}, deep={deep}, light={light}, rem={rem}, score={score}")
            
        # Проверяем все ли нули
        all_zeros = all(row[2] == 0 and row[3] == 0 and row[4] == 0 for row in raw_data)
        
        if all_zeros:
            print("❌ ПРОБЛЕМА НАЙДЕНА: В базе данных тоже все нули!")
            print("🔍 Это означает что проблема НЕ в CSV экспорте, а в сохранении в базу")
            pytest.fail("В базе данных все фазы сна равны нулю")
        else:
            print("✅ В базе есть ненулевые значения - проблема в CSV экспорте")
            assert True
    else:
        print("❌ В базе нет данных о сне")
        pytest.skip("В локальной базе нет данных о сне для диагностики CSV")

def test_database_methods():
    """Тестируем методы Database класса"""
    print("\n🔍 Тестирование методов Database класса...")
    
    db = Database()
    
    # Получаем данные через методы класса
    sleep_data = db.get_sleep_data()
    
    if sleep_data is not None and not sleep_data.empty:
        print(f"✅ Database.get_sleep_data() вернул {len(sleep_data)} записей")
        print("📊 Данные через Database.get_sleep_data():")
        
        # Показываем последние 5 записей
        for _, row in sleep_data.head().iterrows():
            print(f"  {row['date']}: total={row['total_sleep_minutes']}, deep={row['deep_sleep_minutes']}, light={row['light_sleep_minutes']}, rem={row['rem_sleep_minutes']}")
        
        # Проверяем есть ли ненулевые значения
        non_zero_deep = (sleep_data['deep_sleep_minutes'] > 0).any()
        non_zero_light = (sleep_data['light_sleep_minutes'] > 0).any()
        non_zero_rem = (sleep_data['rem_sleep_minutes'] > 0).any()
        
        if non_zero_deep or non_zero_light or non_zero_rem:
            print("✅ Database.get_sleep_data() возвращает ненулевые значения")
            assert True
        else:
            print("❌ Database.get_sleep_data() возвращает только нули")
            pytest.fail("Database.get_sleep_data() возвращает только нулевые фазы сна")
    else:
        print("❌ Database.get_sleep_data() не вернул данных")
        pytest.skip("В локальной базе нет sleep_data для диагностики")

def test_recent_sync():
    """Проверяем что происходило при последней синхронизации"""
    print("\n🔍 Проверка последней синхронизации...")
    
    # Проверяем что было сохранено сегодня
    conn = sqlite3.connect('ai_trainer.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes, created_at
        FROM sleep_data 
        WHERE created_at >= '2025-08-16 12:00:00'
        ORDER BY created_at DESC
    """)
    
    recent_data = cursor.fetchall()
    conn.close()
    
    if recent_data:
        print(f"✅ Найдено {len(recent_data)} записей, сохраненных сегодня после 12:00:")
        for row in recent_data:
            date, total, deep, light, rem, created = row
            print(f"  {date} (сохранено {created}): total={total}, deep={deep}, light={light}, rem={rem}")
            
        # Проверяем фазы сна
        has_phases = any(row[2] > 0 or row[3] > 0 or row[4] > 0 for row in recent_data)
        
        if has_phases:
            print("✅ В недавних записях есть фазы сна!")
            assert True
        else:
            print("❌ В недавних записях все фазы сна равны 0")
            pytest.fail("В недавних записях все фазы сна равны 0")
    else:
        print("❌ Не найдено записей, сохраненных сегодня")
        pytest.skip("В локальной базе нет свежих записей для диагностики")

if __name__ == "__main__":
    print("🚀 Диагностика: База данных vs CSV экспорт...")
    
    test1 = test_database_vs_csv()
    test2 = test_database_methods()  
    test3 = test_recent_sync()
    
    print("\n📊 Результаты диагностики:")
    print(f"  - Прямой доступ к SQLite: {'✅' if test1 else '❌'}")
    print(f"  - Методы Database класса: {'✅' if test2 else '❌'}")
    print(f"  - Недавние записи: {'✅' if test3 else '❌'}")
    
    if not test1 and not test2 and not test3:
        print("\n❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: Данные не сохраняются в базу!")
        print("🔍 ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("1. Процессор возвращает нули из-за неправильного формата данных")
        print("2. Данные не попадают в процессор вообще")
        print("3. Ошибка в логике сохранения в Database.sync_sleep_data()")
        print("4. Реальные данные от Garmin отличаются от тестовых")
    elif test1 and test2 and not test3:
        print("\n⚠️ Старые данные в порядке, но новые записи проблематичны")
    elif test1 and test2 and test3:
        print("\n✅ База данных в порядке - проблема только в CSV экспорте!")
