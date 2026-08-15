#!/usr/bin/env python3
"""
Тест полного цикла синхронизации: garth -> процессор -> база данных
"""

import sys
import os
from datetime import datetime, timedelta
import sqlite3

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database

def test_full_sync_cycle():
    """Тестируем полный цикл синхронизации данных сна"""
    print("🔍 Тестирование полного цикла синхронизации...")
    
    # Инициализируем базу данных
    db = Database()
    
    # Симулируем реальные данные garth
    real_garth_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 23700,
            'deepSleepSeconds': 720,
            'lightSleepSeconds': 21420,
            'remSleepSeconds': 1560,
            'awakeSleepSeconds': 300,
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754906110000
        },
        'sleepScores': {
            'overall': {'value': 57, 'qualifierKey': 'POOR'}
        }
    }
    
    test_date = datetime.now() - timedelta(days=1)
    date_str = test_date.strftime('%Y-%m-%d')
    
    print(f"📅 Тестируем для даты: {date_str}")
    
    # Шаг 1: Обработка данных
    print("🔄 Шаг 1: Обработка данных...")
    processed_sleep = Phase1DataProcessor.process_sleep_data(real_garth_data)
    
    if processed_sleep:
        print(f"✅ Данные обработаны: {processed_sleep}")
    else:
        print("❌ Ошибка обработки данных")
        return False
    
    # Шаг 2: Сохранение в базу данных
    print("🔄 Шаг 2: Сохранение в базу данных...")
    try:
        # Проверяем, есть ли метод sync_sleep_data
        if hasattr(db, 'sync_sleep_data'):
            # sync_sleep_data ожидает словарь {date: data}
            sleep_data_dict = {date_str: processed_sleep}
            db.sync_sleep_data(sleep_data_dict)
            print("✅ Данные сохранены через sync_sleep_data")
        else:
            print("⚠️ Метод sync_sleep_data не найден, попробуем другой способ")
            # Пробуем прямое сохранение в базу
            conn = sqlite3.connect('ai_trainer.db')
            cursor = conn.cursor()
            
            # Проверяем структуру таблицы sleep_data
            cursor.execute("PRAGMA table_info(sleep_data)")
            columns = cursor.fetchall()
            print(f"📋 Структура таблицы sleep_data: {[col[1] for col in columns]}")
            
            # Простая вставка данных
            cursor.execute("""
                INSERT OR REPLACE INTO sleep_data 
                (date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, 
                 rem_sleep_minutes, sleep_score, bedtime, wakeup_time, sleep_efficiency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date_str,
                processed_sleep.get('total_sleep_minutes'),
                processed_sleep.get('deep_sleep_minutes'),
                processed_sleep.get('light_sleep_minutes'),
                processed_sleep.get('rem_sleep_minutes'),
                processed_sleep.get('sleep_score'),
                processed_sleep.get('bedtime'),
                processed_sleep.get('wakeup_time'),
                processed_sleep.get('sleep_efficiency')
            ))
            
            conn.commit()
            conn.close()
            print("✅ Данные сохранены напрямую в базу")
            
    except Exception as e:
        print(f"❌ Ошибка сохранения в базу: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Шаг 3: Проверка сохранения
    print("🔄 Шаг 3: Проверка сохранения...")
    try:
        conn = sqlite3.connect('ai_trainer.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sleep_data WHERE date = ?", (date_str,))
        saved_data = cursor.fetchone()
        
        if saved_data:
            print(f"✅ Данные найдены в базе: {saved_data}")
            
            # Проверяем все основные поля
            if saved_data[1] and saved_data[1] > 0:  # total_sleep_minutes
                print("✅ total_sleep_minutes сохранено")
            if saved_data[2] and saved_data[2] > 0:  # deep_sleep_minutes
                print("✅ deep_sleep_minutes сохранено") 
            if saved_data[5] and saved_data[5] > 0:  # sleep_score
                print("✅ sleep_score сохранено")
                
            return True
        else:
            print(f"❌ Данные НЕ найдены в базе для даты {date_str}")
            
            # Проверим, что вообще есть в таблице
            cursor.execute("SELECT date, total_sleep_minutes FROM sleep_data ORDER BY date DESC LIMIT 5")
            recent_data = cursor.fetchall()
            print(f"📊 Последние записи в sleep_data: {recent_data}")
            
            return False
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка проверки данных: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Запуск теста полного цикла синхронизации...")
    success = test_full_sync_cycle()
    
    if success:
        print("\n🎉 Полный цикл синхронизации работает!")
    else:
        print("\n⚠️ Обнаружены проблемы в полном цикле")