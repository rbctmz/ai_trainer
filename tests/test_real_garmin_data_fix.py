#!/usr/bin/env python3
"""
Тест с реальными данными Garmin - проверяем исправление проблемы с фазами сна
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_real_garmin_data():
    """Тестируем с реальными данными из логов Garmin"""
    print("🔍 Тестирование с реальными данными Garmin...")
    
    # Данные с реальной структуры из логов (упрощенная версия)
    real_garmin_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,  # 466 минут
            'deepSleepSeconds': 3900,   # 65 минут 
            'lightSleepSeconds': 22200, # 370 минут
            'remSleepSeconds': 1860,    # 31 минут
            'awakeSleepSeconds': 2220,  # 37 минут / 5 = 7 пробуждений
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3
        },
        'sleepScores': {
            'overall': {'value': 66, 'qualifierKey': 'FAIR'}
        },
        # НЕТ sleepLevels - только sleepMovement с float значениями
        'sleepMovement': [
            {'activityLevel': 6.017436038349008},
            {'activityLevel': 0.0},
            {'activityLevel': 1.2345}
            # ... много записей с float значениями
        ]
    }
    
    print(f"📥 Данные содержат:")
    print(f"  - sleepTimeSeconds: {real_garmin_data['dailySleepDTO']['sleepTimeSeconds']} сек")
    print(f"  - deepSleepSeconds: {real_garmin_data['dailySleepDTO']['deepSleepSeconds']} сек")
    print(f"  - lightSleepSeconds: {real_garmin_data['dailySleepDTO']['lightSleepSeconds']} сек")
    print(f"  - remSleepSeconds: {real_garmin_data['dailySleepDTO']['remSleepSeconds']} сек")
    print(f"  - НЕТ sleepLevels массива")
    
    # Обрабатываем данные
    print("🔄 Обработка данных...")
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(real_garmin_data)
        
        if processed_sleep:
            print(f"✅ Данные успешно обработаны!")
            
            # Ожидаемые значения
            expected_total = 27960 // 60  # 466 минут
            expected_deep = 3900 // 60    # 65 минут
            expected_light = 22200 // 60  # 370 минут
            expected_rem = 1860 // 60     # 31 минут
            expected_score = 66
            
            print(f"📊 Результаты обработки:")
            print(f"  - Общий сон: {processed_sleep.get('total_sleep_minutes')} мин (ожидали {expected_total})")
            print(f"  - Глубокий сон: {processed_sleep.get('deep_sleep_minutes')} мин (ожидали {expected_deep})")
            print(f"  - Легкий сон: {processed_sleep.get('light_sleep_minutes')} мин (ожидали {expected_light})")
            print(f"  - REM сон: {processed_sleep.get('rem_sleep_minutes')} мин (ожидали {expected_rem})")
            print(f"  - Sleep Score: {processed_sleep.get('sleep_score')} (ожидали {expected_score})")
            print(f"  - Пробуждения: {processed_sleep.get('awakenings_count')}")
            
            # Проверяем корректность
            success = True
            issues = []
            
            if processed_sleep.get('total_sleep_minutes') != expected_total:
                issues.append(f"Общий сон: получили {processed_sleep.get('total_sleep_minutes')}, ожидали {expected_total}")
                success = False
            
            if processed_sleep.get('deep_sleep_minutes') != expected_deep:
                issues.append(f"Глубокий сон: получили {processed_sleep.get('deep_sleep_minutes')}, ожидали {expected_deep}")
                success = False
                
            if processed_sleep.get('light_sleep_minutes') != expected_light:
                issues.append(f"Легкий сон: получили {processed_sleep.get('light_sleep_minutes')}, ожидали {expected_light}")
                success = False
                
            if processed_sleep.get('rem_sleep_minutes') != expected_rem:
                issues.append(f"REM сон: получили {processed_sleep.get('rem_sleep_minutes')}, ожидали {expected_rem}")
                success = False
                
            if processed_sleep.get('sleep_score') != expected_score:
                issues.append(f"Sleep score: получили {processed_sleep.get('sleep_score')}, ожидали {expected_score}")
                success = False
            
            if success:
                print("🎉 ВСЕ ЗНАЧЕНИЯ КОРРЕКТНЫ!")
                print("✅ Исправление сработало - фазы сна больше не равны 0")
                return True
            else:
                print("❌ Найдены проблемы:")
                for issue in issues:
                    print(f"  - {issue}")
                return False
                
        else:
            print("❌ Обработка вернула None")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Тест исправления проблемы с реальными данными Garmin...")
    success = test_real_garmin_data()
    
    if success:
        print("\n🏆 ПРОБЛЕМА С ФАЗАМИ СНА РЕШЕНА!")
        print("✅ Реальные данные Garmin теперь обрабатываются корректно")
        print("✅ Фазы сна больше не показывают 0")
    else:
        print("\n⚠️ Проблема не полностью решена")