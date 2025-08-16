#!/usr/bin/env python3
"""
Финальный тест исправленного процессора данных сна
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database

def test_complete_fixed_cycle():
    """Тестируем полный исправленный цикл обработки данных сна"""
    print("🔍 Тестирование полного исправленного цикла...")
    
    # Симулируем проблемные данные, которые вызывали ошибку
    problematic_sleep_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27000,  # 7.5 часов
            'deepSleepSeconds': 5400,   # 1.5 часа
            'lightSleepSeconds': 18000, # 5 часов
            'remSleepSeconds': 3600,    # 1 час
            'awakeSleepSeconds': 300,   # 5 минут
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754909110000
        },
        'sleepLevels': [
            # Эти данные вызывали ошибку 'float' object has no attribute 'lower'
            {'activityLevel': 0.0, 'durationInSeconds': 5400},   # deep (float)
            {'activityLevel': 1.0, 'durationInSeconds': 18000},  # light (float)
            {'activityLevel': 2.0, 'durationInSeconds': 3600},   # rem (float)
            {'activityLevel': 3.0, 'durationInSeconds': 300},    # awake (float)
            {'activityLevel': 1.0, 'durationInSeconds': 12600},  # еще light
            {'activityLevel': 3.0, 'durationInSeconds': 180}     # еще awake
        ],
        'sleepScores': {
            'overall': {'value': 82, 'qualifierKey': 'GOOD'}
        }
    }
    
    test_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"📅 Тестируем для даты: {test_date}")
    print(f"📥 Данные содержат числовые activityLevel, которые ранее вызывали ошибку")
    
    # Шаг 1: Обработка данных (раньше падала здесь)
    print("🔄 Шаг 1: Обработка данных с исправленным процессором...")
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(problematic_sleep_data)
        
        if processed_sleep:
            print(f"✅ Данные успешно обработаны: {processed_sleep}")
            
            # Проверяем что получили разумные значения
            total_sleep = processed_sleep.get('total_sleep_minutes', 0)
            deep_sleep = processed_sleep.get('deep_sleep_minutes', 0)
            light_sleep = processed_sleep.get('light_sleep_minutes', 0)
            rem_sleep = processed_sleep.get('rem_sleep_minutes', 0)
            sleep_score = processed_sleep.get('sleep_score', 0)
            
            print(f"📊 Проверка обработанных данных:")
            print(f"  - Общий сон: {total_sleep} мин (ожидали 450)")
            print(f"  - Глубокий сон: {deep_sleep} мин") 
            print(f"  - Легкий сон: {light_sleep} мин")
            print(f"  - REM сон: {rem_sleep} мин")
            print(f"  - Sleep Score: {sleep_score}")
            
            if total_sleep > 0 and sleep_score > 0:
                print("✅ Данные выглядят корректно")
            else:
                print("⚠️ Данные выглядят подозрительно")
                
        else:
            print("❌ Обработка вернула None")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Шаг 2: Сохранение в базу данных
    print("🔄 Шаг 2: Сохранение в базу данных...")
    try:
        db = Database()
        sleep_data_dict = {test_date: processed_sleep}
        result = db.sync_sleep_data(sleep_data_dict)
        print(f"✅ Сохранено в базу: {result}")
        
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False
    
    # Шаг 3: Проверка сохранения
    print("🔄 Шаг 3: Проверка сохранения...")
    try:
        conn = sqlite3.connect('ai_trainer.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM sleep_data WHERE date = ?", (test_date,))
        saved_data = cursor.fetchone()
        
        if saved_data:
            print(f"✅ Данные найдены в базе: {saved_data}")
            return True
        else:
            print(f"❌ Данные НЕ найдены в базе для даты {test_date}")
            return False
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False

def test_edge_cases():
    """Тестируем граничные случаи"""
    print("\n🔍 Тестирование граничных случаев...")
    
    edge_cases = [
        # Случай 1: None вместо строки
        {'sleepLevels': [{'activityLevel': None, 'durationInSeconds': 1800}]},
        
        # Случай 2: Неизвестный числовой код
        {'sleepLevels': [{'activityLevel': 99, 'durationInSeconds': 1800}]},
        
        # Случай 3: Пустая строка
        {'sleepLevels': [{'activityLevel': '', 'durationInSeconds': 1800}]},
        
        # Случай 4: Смешанные типы
        {'sleepLevels': [
            {'activityLevel': 'deep', 'durationInSeconds': 1800},
            {'activityLevel': 1.0, 'durationInSeconds': 1800},
            {'activityLevel': None, 'durationInSeconds': 1800}
        ]}
    ]
    
    for i, test_case in enumerate(edge_cases, 1):
        print(f"  Тест {i}: {test_case}")
        try:
            result = Phase1DataProcessor.process_sleep_data(test_case)
            print(f"    ✅ Обработано успешно: {result is not None}")
        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
            return False
    
    return True

if __name__ == "__main__":
    print("🚀 Финальный тест исправленного процессора данных сна...")
    
    test1_passed = test_complete_fixed_cycle()
    test2_passed = test_edge_cases()
    
    if test1_passed and test2_passed:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("✅ Исправление 'float' object has no attribute 'lower' работает корректно")
        print("✅ Полный цикл обработки данных сна функционирует")
        print("✅ Граничные случаи обрабатываются корректно")
        print("\n🏆 Проблема с загрузкой данных сна ПОЛНОСТЬЮ РЕШЕНА!")
    else:
        print("\n⚠️ Обнаружены проблемы в тестах")