#!/usr/bin/env python3
"""
Диагностика проблемы с фазами сна - почему все показывают 0
"""

import sys
import os
import sqlite3

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def diagnose_zero_sleep_phases():
    """Диагностируем почему все фазы сна равны 0"""
    print("🔍 Диагностика проблемы с фазами сна...")
    
    # Проверим последние записи в базе данных
    print("\n📊 Проверяем данные в базе:")
    try:
        conn = sqlite3.connect('ai_trainer.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes
            FROM sleep_data 
            ORDER BY date DESC 
            LIMIT 5
        """)
        
        recent_data = cursor.fetchall()
        for record in recent_data:
            date, total, deep, light, rem = record
            print(f"  {date}: {total}мин общий, {deep}мин глуб, {light}мин легк, {rem}мин REM")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка чтения БД: {e}")
    
    # Тестируем обработку данных с dailySleepDTO (откуда берется общее время)
    print("\n🧪 Тест 1: Данные только с dailySleepDTO (как в реальности)")
    test_data_dto_only = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,  # 8 часов
            'deepSleepSeconds': 7200,   # 2 часа (из DTO)
            'lightSleepSeconds': 18000, # 5 часов (из DTO)
            'remSleepSeconds': 3600,    # 1 час (из DTO)
            'awakeSleepSeconds': 300,   # 5 минут
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754910910000
        },
        'sleepScores': {
            'overall': {'value': 85}
        }
    }
    
    result1 = Phase1DataProcessor.process_sleep_data(test_data_dto_only)
    print(f"Результат: {result1}")
    print(f"Глубокий сон: {result1.get('deep_sleep_minutes', 'НЕТ')}")
    print(f"Легкий сон: {result1.get('light_sleep_minutes', 'НЕТ')}")
    print(f"REM сон: {result1.get('rem_sleep_minutes', 'НЕТ')}")
    
    # Тестируем обработку данных с sleepLevels (дополнительные данные)
    print("\n🧪 Тест 2: Данные с sleepLevels (детальные фазы)")
    test_data_with_levels = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754910910000
        },
        'sleepLevels': [
            {'activityLevel': 0, 'durationInSeconds': 7200},   # deep
            {'activityLevel': 1, 'durationInSeconds': 18000},  # light  
            {'activityLevel': 2, 'durationInSeconds': 3600},   # rem
            {'activityLevel': 3, 'durationInSeconds': 300}     # awake
        ],
        'sleepScores': {
            'overall': {'value': 85}
        }
    }
    
    result2 = Phase1DataProcessor.process_sleep_data(test_data_with_levels)
    print(f"Результат: {result2}")
    print(f"Глубокий сон: {result2.get('deep_sleep_minutes', 'НЕТ')}")
    print(f"Легкий сон: {result2.get('light_sleep_minutes', 'НЕТ')}")
    print(f"REM сон: {result2.get('rem_sleep_minutes', 'НЕТ')}")
    
    # Проверим приоритет обработки
    print("\n🧪 Тест 3: Конфликт между dailySleepDTO и sleepLevels")
    test_data_conflict = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,
            'deepSleepSeconds': 1800,    # Из DTO: 30 минут
            'lightSleepSeconds': 23400,  # Из DTO: 390 минут
            'remSleepSeconds': 3600,     # Из DTO: 60 минут
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754910910000
        },
        'sleepLevels': [
            {'activityLevel': 0, 'durationInSeconds': 7200},   # Из levels: 120 минут
            {'activityLevel': 1, 'durationInSeconds': 18000},  # Из levels: 300 минут
            {'activityLevel': 2, 'durationInSeconds': 3600}    # Из levels: 60 минут
        ],
        'sleepScores': {
            'overall': {'value': 85}
        }
    }
    
    result3 = Phase1DataProcessor.process_sleep_data(test_data_conflict)
    print(f"Результат: {result3}")
    print(f"Глубокий сон: {result3.get('deep_sleep_minutes', 'НЕТ')} (DTO: 30, Levels: 120)")
    print(f"Легкий сон: {result3.get('light_sleep_minutes', 'НЕТ')} (DTO: 390, Levels: 300)")
    print(f"REM сон: {result3.get('rem_sleep_minutes', 'НЕТ')} (DTO: 60, Levels: 60)")
    
    print("\n🔍 Анализ проблемы:")
    if result1 and result1.get('deep_sleep_minutes', 0) > 0:
        print("✅ dailySleepDTO содержит фазы сна и они обрабатываются")
    else:
        print("❌ Проблема: dailySleepDTO не содержит фазы или они не обрабатываются")
        
    if result2 and result2.get('deep_sleep_minutes', 0) > 0:
        print("✅ sleepLevels обрабатываются корректно")
    else:
        print("❌ Проблема: sleepLevels не обрабатываются или данные неправильные")

if __name__ == "__main__":
    diagnose_zero_sleep_phases()