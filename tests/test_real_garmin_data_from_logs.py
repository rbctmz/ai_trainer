#!/usr/bin/env python3
"""
Тест с реальными данными из логов для диагностики проблемы с обработкой
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_real_log_data_2025_08_13():
    """Тестируем с реальными данными за 2025-08-13 из логов"""
    print("🔍 Тестируем реальные данные за 2025-08-13 из логов...")
    
    # Реальные данные из логов (упрощенная версия, только самое важное)
    real_garmin_data_20250813 = {
        'dailySleepDTO': {
            'id': 1755032275000,
            'calendarDate': '2025-08-13',
            'sleepTimeSeconds': 26100,  # 435 минут
            'deepSleepSeconds': 3360,   # 56 минут
            'lightSleepSeconds': 17520, # 292 минуты
            'remSleepSeconds': 5220,    # 87 минут
            'awakeSleepSeconds': 420,
            'awakeCount': 1,
            'sleepStartTimestampLocal': 1755043075000,
            'sleepEndTimestampLocal': 1755069595000
        },
        'sleepScores': {
            'overall': {'value': 82, 'qualifierKey': 'GOOD'},
            'remPercentage': {'value': 20, 'qualifierKey': 'FAIR'},
            'lightPercentage': {'value': 67, 'qualifierKey': 'FAIR'},
            'deepPercentage': {'value': 13, 'qualifierKey': 'FAIR'}
        }
    }
    
    print("📥 Реальные данные из логов за 2025-08-13:")
    print(f"  - sleepTimeSeconds: {real_garmin_data_20250813['dailySleepDTO']['sleepTimeSeconds']} сек (435 мин)")
    print(f"  - deepSleepSeconds: {real_garmin_data_20250813['dailySleepDTO']['deepSleepSeconds']} сек (56 мин)")
    print(f"  - lightSleepSeconds: {real_garmin_data_20250813['dailySleepDTO']['lightSleepSeconds']} сек (292 мин)")
    print(f"  - remSleepSeconds: {real_garmin_data_20250813['dailySleepDTO']['remSleepSeconds']} сек (87 мин)")
    print(f"  - deepPercentage: {real_garmin_data_20250813['sleepScores']['deepPercentage']['value']}%")
    print(f"  - lightPercentage: {real_garmin_data_20250813['sleepScores']['lightPercentage']['value']}%")
    print(f"  - remPercentage: {real_garmin_data_20250813['sleepScores']['remPercentage']['value']}%")
    print(f"  - overall: {real_garmin_data_20250813['sleepScores']['overall']['value']}")
    
    print("\n🔄 Тестируем обработку...")
    
    # Обрабатываем данные
    try:
        processed = Phase1DataProcessor.process_sleep_data(real_garmin_data_20250813)
        
        if processed:
            print("✅ Данные успешно обработаны!")
            
            # Ожидаемые значения из секунд (должны быть приоритетными)
            expected_total = 26100 // 60  # 435 минут
            expected_deep = 3360 // 60    # 56 минут
            expected_light = 17520 // 60  # 292 минуты
            expected_rem = 5220 // 60     # 87 минут
            expected_score = 82
            expected_awakenings = 1
            
            actual_total = processed.get('total_sleep_minutes')
            actual_deep = processed.get('deep_sleep_minutes')
            actual_light = processed.get('light_sleep_minutes')
            actual_rem = processed.get('rem_sleep_minutes')
            actual_score = processed.get('sleep_score')
            actual_awakenings = processed.get('awakenings_count')
            
            print("📊 Результаты обработки:")
            print(f"  - Общий сон: {actual_total} мин (ожидали {expected_total})")
            print(f"  - Глубокий сон: {actual_deep} мин (ожидали {expected_deep})")
            print(f"  - Легкий сон: {actual_light} мин (ожидали {expected_light})")
            print(f"  - REM сон: {actual_rem} мин (ожидали {expected_rem})")
            print(f"  - Sleep Score: {actual_score} (ожидали {expected_score})")
            print(f"  - Пробуждения: {actual_awakenings} (ожидали {expected_awakenings})")
            
            # Проверяем что используются секунды, а НЕ проценты
            success = True
            
            if actual_total != expected_total:
                print(f"❌ Общий сон: получили {actual_total}, ожидали {expected_total}")
                success = False
            
            if actual_deep != expected_deep:
                print(f"❌ Глубокий сон: получили {actual_deep}, ожидали {expected_deep}")
                success = False
            
            if actual_light != expected_light:
                print(f"❌ Легкий сон: получили {actual_light}, ожидали {expected_light}")
                success = False
            
            if actual_rem != expected_rem:
                print(f"❌ REM сон: получили {actual_rem}, ожидали {expected_rem}")
                success = False
            
            if actual_score != expected_score:
                print(f"❌ Sleep score: получили {actual_score}, ожидали {expected_score}")
                success = False
            
            if actual_awakenings != expected_awakenings:
                print(f"❌ Пробуждения: получили {actual_awakenings}, ожидали {expected_awakenings}")
                success = False
            
            if success:
                print("🎉 ВСЕ ЗНАЧЕНИЯ ТОЧНО СОВПАДАЮТ!")
                print("✅ Процессор правильно использует СЕКУНДЫ из dailySleepDTO")
                return True
            else:
                print("⚠️ Некоторые значения не совпадают")
                return False
                
        else:
            print("❌ Обработка вернула None")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_without_seconds():
    """Тестируем случай когда нет секунд, только проценты"""
    print("\n🔍 Тест случая без секунд, только проценты...")
    
    # Данные без секунд (как может быть в некоторых случаях)
    no_seconds_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 26100,  # Только общее время
            'sleepStartTimestampLocal': 1755043075000,
            'sleepEndTimestampLocal': 1755069595000,
            'awakeCount': 1
            # НЕТ deepSleepSeconds, lightSleepSeconds, remSleepSeconds
        },
        'sleepScores': {
            'overall': {'value': 82, 'qualifierKey': 'GOOD'},
            'remPercentage': {'value': 20, 'qualifierKey': 'FAIR'},
            'lightPercentage': {'value': 67, 'qualifierKey': 'FAIR'},
            'deepPercentage': {'value': 13, 'qualifierKey': 'FAIR'}
        }
    }
    
    print("📥 Данные без секунд фаз сна, только проценты")
    
    processed = Phase1DataProcessor.process_sleep_data(no_seconds_data)
    
    if processed:
        total_minutes = 435
        expected_deep_from_percent = round(total_minutes * 13 / 100)   # 57 минут
        expected_light_from_percent = round(total_minutes * 67 / 100)  # 291 минута
        expected_rem_from_percent = round(total_minutes * 20 / 100)    # 87 минут
        
        actual_deep = processed.get('deep_sleep_minutes', 0)
        actual_light = processed.get('light_sleep_minutes', 0)
        actual_rem = processed.get('rem_sleep_minutes', 0)
        
        print(f"📊 Результат: глуб={actual_deep}, легк={actual_light}, REM={actual_rem}")
        print(f"📊 Ожидали из %: глуб={expected_deep_from_percent}, легк={expected_light_from_percent}, REM={expected_rem_from_percent}")
        
        if (actual_deep == expected_deep_from_percent and 
            actual_light == expected_light_from_percent and 
            actual_rem == expected_rem_from_percent):
            print("✅ Процентный fallback работает правильно!")
            return True
        else:
            print("❌ Процентный fallback не работает")
            return False
    else:
        print("❌ Обработка вернула None")
        return False

if __name__ == "__main__":
    print("🚀 Диагностика реальных данных из логов...")
    
    test1 = test_real_log_data_2025_08_13()
    test2 = test_data_without_seconds()
    
    if test1 and test2:
        print("\n🏆 ВСЕ ТЕСТЫ ПРОШЛИ!")
        print("✅ Процессор правильно обрабатывает реальные данные Garmin")
        print("✅ И секунды (приоритет), и проценты (fallback) работают")
        print("\n🔍 ВЫВОД: Проблема НЕ в процессоре, а в:")
        print("  1. Данные не достигают процессора")
        print("  2. Данные попадают в процессор в неправильном формате")
        print("  3. Ошибка в передаче данных от Garmin к процессору")
    else:
        print("\n⚠️ Некоторые тесты не прошли")
        if not test1:
            print("❌ Проблема с обработкой данных с секундами")
        if not test2:
            print("❌ Проблема с процентным fallback")