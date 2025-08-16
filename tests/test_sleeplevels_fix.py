#!/usr/bin/env python3
"""
Тест исправления ошибки 'float' object has no attribute 'lower'
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_sleeplevels_with_floats():
    """Тестируем обработку sleepLevels с числовыми activityLevel"""
    print("🔍 Тестирование обработки sleepLevels с числовыми значениями...")
    
    # Данные с числовыми activityLevel (такие как в реальных данных)
    test_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,  # 8 часов
            'deepSleepSeconds': 7200,   # 2 часа
            'lightSleepSeconds': 18000, # 5 часов
            'remSleepSeconds': 3600,    # 1 час
            'awakeSleepSeconds': 300,   # 5 минут
            'sleepStartTimestampLocal': 1754882110000,
            'sleepEndTimestampLocal': 1754910910000
        },
        'sleepLevels': [
            {'activityLevel': 0.0, 'durationInSeconds': 7200},  # deep (float)
            {'activityLevel': 1, 'durationInSeconds': 18000},   # light (int)
            {'activityLevel': 2.0, 'durationInSeconds': 3600}, # rem (float)
            {'activityLevel': 3, 'durationInSeconds': 300}     # awake (int)
        ],
        'sleepScores': {
            'overall': {'value': 85, 'qualifierKey': 'GOOD'}
        }
    }
    
    print(f"📥 Тестовые данные с числовыми activityLevel")
    
    # Обрабатываем данные
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(test_data)
        print(f"✅ Обработанные данные: {processed_sleep}")
        
        if processed_sleep:
            print("✅ Обработка успешна!")
            
            # Проверяем правильность обработки
            expected_deep = 7200 // 60  # 120 минут
            expected_light = 18000 // 60  # 300 минут
            expected_rem = 3600 // 60   # 60 минут
            expected_awake = 1  # 1 пробуждение
            
            print(f"🔢 Ожидаемые значения из sleepLevels:")
            print(f"  - Глубокий сон: {expected_deep} мин")
            print(f"  - Легкий сон: {expected_light} мин")
            print(f"  - REM сон: {expected_rem} мин")
            print(f"  - Пробуждения: {expected_awake}")
            
            print(f"📊 Фактические значения из sleepLevels:")
            print(f"  - Глубокий сон: {processed_sleep.get('deep_sleep_minutes', 'НЕТ')} мин")
            print(f"  - Легкий сон: {processed_sleep.get('light_sleep_minutes', 'НЕТ')} мин")
            print(f"  - REM сон: {processed_sleep.get('rem_sleep_minutes', 'НЕТ')} мин")
            print(f"  - Пробуждения: {processed_sleep.get('awakenings_count', 'НЕТ')}")
            
            # Проверяем на корректность
            success = True
            if processed_sleep.get('deep_sleep_minutes') != expected_deep:
                print(f"❌ Ошибка глубокого сна: ожидали {expected_deep}, получили {processed_sleep.get('deep_sleep_minutes')}")
                success = False
            if processed_sleep.get('light_sleep_minutes') != expected_light:
                print(f"❌ Ошибка легкого сна: ожидали {expected_light}, получили {processed_sleep.get('light_sleep_minutes')}")
                success = False
            if processed_sleep.get('rem_sleep_minutes') != expected_rem:
                print(f"❌ Ошибка REM сна: ожидали {expected_rem}, получили {processed_sleep.get('rem_sleep_minutes')}")
                success = False
            if processed_sleep.get('awakenings_count') != expected_awake:
                print(f"❌ Ошибка пробуждений: ожидали {expected_awake}, получили {processed_sleep.get('awakenings_count')}")
                success = False
                
            return success
        else:
            print("❌ Обработка вернула None")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sleeplevels_with_strings():
    """Тестируем обработку sleepLevels со строковыми activityLevel"""
    print("\n🔍 Тестирование обработки sleepLevels со строковыми значениями...")
    
    # Данные со строковыми activityLevel
    test_data = {
        'sleepLevels': [
            {'activityLevel': 'DEEP', 'durationInSeconds': 5400},  # 90 минут
            {'activityLevel': 'light', 'durationInSeconds': 16200}, # 270 минут
            {'activityLevel': 'REM', 'durationInSeconds': 4500},   # 75 минут
            {'activityLevel': 'AWAKE', 'durationInSeconds': 600}   # 10 минут
        ],
        'sleepScores': {
            'overall': {'value': 78}
        }
    }
    
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(test_data)
        print(f"✅ Обработанные данные: {processed_sleep}")
        
        if processed_sleep:
            print("✅ Обработка строковых activityLevel успешна!")
            return True
        else:
            print("❌ Обработка строковых activityLevel вернула None")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обработки строковых данных: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Запуск тестов исправления sleepLevels...")
    
    test1_passed = test_sleeplevels_with_floats()
    test2_passed = test_sleeplevels_with_strings()
    
    if test1_passed and test2_passed:
        print("\n🎉 Все тесты прошли успешно!")
        print("✅ Исправление 'float' object has no attribute 'lower' работает корректно")
    else:
        print("\n⚠️ Некоторые тесты не прошли")