#!/usr/bin/env python3
"""
Тест интеграции синхронизации в приложении
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_database_sleep_data():
    """Проверяем что в базе данных есть данные сна"""
    print("🔍 Проверяем содержимое базы данных...")
    
    try:
        conn = sqlite3.connect('ai_trainer.db')
        cursor = conn.cursor()
        
        # Проверяем все данные сна за последние 30 дней
        cursor.execute("""
            SELECT date, total_sleep_minutes, deep_sleep_minutes, sleep_score, bedtime, wakeup_time
            FROM sleep_data 
            WHERE date >= date('now', '-30 days')
            ORDER BY date DESC
        """)
        
        sleep_records = cursor.fetchall()
        
        if sleep_records:
            print(f"✅ Найдено {len(sleep_records)} записей данных сна:")
            for record in sleep_records[:10]:  # Показываем первые 10
                date, total_sleep, deep_sleep, sleep_score, bedtime, wakeup = record
                print(f"  📅 {date}: {total_sleep} мин сна, {deep_sleep} мин глубокий, score: {sleep_score}, {bedtime}-{wakeup}")
        else:
            print("❌ Данные сна в базе НЕ найдены")
        
        # Также проверим HRV данные для сравнения
        cursor.execute("""
            SELECT date, rmssd 
            FROM hrv_data 
            WHERE date >= date('now', '-30 days')
            ORDER BY date DESC
            LIMIT 5
        """)
        
        hrv_records = cursor.fetchall()
        if hrv_records:
            print("\n📊 Для сравнения - HRV данные (последние 5):")
            for record in hrv_records:
                print(f"  📅 {record[0]}: RMSSD {record[1]}")
        else:
            print("\n⚠️ HRV данные тоже отсутствуют")
            
        conn.close()
        return len(sleep_records)
        
    except Exception as e:
        print(f"❌ Ошибка проверки базы данных: {e}")
        return 0

def simulate_manual_sync():
    """Симулируем ручную синхронизацию данных"""
    print("🔄 Симулируем ручную синхронизацию данных...")
    
    from data.garmin_client import GarminClient
    from data.data_processor_phase1 import Phase1DataProcessor
    from data.database import Database
    
    # Инициализируем компоненты
    GarminClient()
    db = Database()
    
    # Симулируем получение данных от garth
    # Используем структуру данных, которую мы видели в логах
    test_sleep_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 25200,  # 7 часов
            'deepSleepSeconds': 1800,   # 30 минут
            'lightSleepSeconds': 20400, # 5.67 часов
            'remSleepSeconds': 3000,    # 50 минут
            'awakeSleepSeconds': 600,   # 10 минут
            'sleepStartTimestampLocal': int((datetime.now() - timedelta(days=1, hours=15)).timestamp() * 1000),
            'sleepEndTimestampLocal': int((datetime.now() - timedelta(hours=8)).timestamp() * 1000)
        },
        'sleepScores': {
            'overall': {'value': 75, 'qualifierKey': 'GOOD'}
        }
    }
    
    test_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    print(f"📅 Обрабатываем данные для {test_date}")
    
    # Обрабатываем данные
    processed_sleep = Phase1DataProcessor.process_sleep_data(test_sleep_data)
    
    if processed_sleep:
        print(f"✅ Данные обработаны: {processed_sleep}")
        
        # Сохраняем в базу
        sleep_data_dict = {test_date: processed_sleep}
        result = db.sync_sleep_data(sleep_data_dict)
        print(f"✅ Сохранено в базу: {result}")
        
        return True
    else:
        print("❌ Ошибка обработки данных")
        return False

def main():
    """Основная функция теста"""
    print("🚀 Тест интеграции синхронизации приложения...")
    
    # Сначала проверим что есть в базе
    initial_count = check_database_sleep_data()
    
    # Попробуем добавить тестовые данные
    print("\n" + "="*50)
    sync_success = simulate_manual_sync()
    
    # Проверим результат
    print("\n" + "="*50)
    final_count = check_database_sleep_data()
    
    if sync_success and final_count > initial_count:
        print("\n🎉 Тест синхронизации прошел успешно!")
        print(f"📈 Добавлено записей: {final_count - initial_count}")
    elif final_count > 0:
        print(f"\n✅ В базе уже есть {final_count} записей данных сна")
    else:
        print("\n⚠️ Данные сна по-прежнему отсутствуют в базе")
    
    # Финальные рекомендации
    print("\n📋 Следующие шаги:")
    print("1. Запустить приложение Streamlit: streamlit run app.py")
    print("2. Перейти в раздел 'Анализ сна' для проверки отображения")
    print("3. Попробовать синхронизацию с реальным Garmin аккаунтом")
    print("4. Проверить логи синхронизации в разделе 'Логи'")

if __name__ == "__main__":
    main()