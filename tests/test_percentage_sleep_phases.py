#!/usr/bin/env python3
"""
Тест нового подхода к фазам сна через проценты
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_percentage_based_sleep_phases():
    """Тестируем новый подход через проценты sleepScores"""
    print("🔍 Тестирование фаз сна через проценты...")
    
    # Данные как в реальных логах - без deepSleepSeconds, но с процентами
    real_structure_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,  # 466 минут
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3
            # НЕТ deepSleepSeconds, lightSleepSeconds, remSleepSeconds
        },
        'sleepScores': {
            'overall': {'value': 66, 'qualifierKey': 'FAIR'},
            'deepPercentage': {'value': 14, 'qualifierKey': 'FAIR'},      # 14% = 65 минут
            'lightPercentage': {'value': 79, 'qualifierKey': 'FAIR'},     # 79% = 368 минут
            'remPercentage': {'value': 7, 'qualifierKey': 'POOR'},        # 7% = 33 минуты
            'restlessness': {'qualifierKey': 'POOR'}
        }
    }
    
    print(f"📥 Тестовые данные:")
    print(f"  - sleepTimeSeconds: {real_structure_data['dailySleepDTO']['sleepTimeSeconds']} (466 мин)")
    print(f"  - deepPercentage: {real_structure_data['sleepScores']['deepPercentage']['value']}%")
    print(f"  - lightPercentage: {real_structure_data['sleepScores']['lightPercentage']['value']}%")
    print(f"  - remPercentage: {real_structure_data['sleepScores']['remPercentage']['value']}%")
    print(f"  - НЕТ deepSleepSeconds/lightSleepSeconds/remSleepSeconds")
    
    # Обрабатываем данные
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(real_structure_data)
        
        if processed_sleep:
            print(f"✅ Данные успешно обработаны!")
            
            # Ожидаемые значения
            expected_total = 466
            expected_deep = round(466 * 14 / 100)  # 65 минут
            expected_light = round(466 * 79 / 100)  # 368 минут
            expected_rem = round(466 * 7 / 100)   # 33 минуты
            expected_score = 66
            expected_awakenings = 3
            
            print(f"📊 Результаты обработки:")
            print(f"  - Общий сон: {processed_sleep.get('total_sleep_minutes')} мин (ожидали {expected_total})")
            print(f"  - Глубокий сон: {processed_sleep.get('deep_sleep_minutes')} мин (ожидали {expected_deep})")
            print(f"  - Легкий сон: {processed_sleep.get('light_sleep_minutes')} мин (ожидали {expected_light})")
            print(f"  - REM сон: {processed_sleep.get('rem_sleep_minutes')} мин (ожидали {expected_rem})")
            print(f"  - Sleep Score: {processed_sleep.get('sleep_score')} (ожидали {expected_score})")
            print(f"  - Пробуждения: {processed_sleep.get('awakenings_count')} (ожидали {expected_awakenings})")
            
            assert processed_sleep.get('total_sleep_minutes') == expected_total
            assert processed_sleep.get('deep_sleep_minutes') == expected_deep
            assert processed_sleep.get('light_sleep_minutes') == expected_light
            assert processed_sleep.get('rem_sleep_minutes') == expected_rem
            assert processed_sleep.get('sleep_score') == expected_score
            assert processed_sleep.get('awakenings_count') == expected_awakenings
            print("🎉 ПРОЦЕНТНЫЙ ПОДХОД РАБОТАЕТ ИДЕАЛЬНО!")
            print("✅ Все значения корректны")
                
        else:
            print("❌ Обработка вернула None")
            assert processed_sleep is not None
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        raise

def test_fallback_to_seconds():
    """Тестируем что старый подход через секунды тоже работает"""
    print("\n🔍 Тестирование fallback к секундам...")
    
    # Данные со старой структурой (с секундами)
    old_structure_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,  # 480 минут
            'deepSleepSeconds': 7200,   # 120 минут
            'lightSleepSeconds': 18000, # 300 минут
            'remSleepSeconds': 3600,    # 60 минут
            'awakeSleepSeconds': 300,   # 5 минут
            'awakeCount': 2
        },
        'sleepScores': {
            'overall': {'value': 85}
            # НЕТ процентов, но есть секунды
        }
    }
    
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(old_structure_data)
        
        if processed_sleep:
            expected_deep = 120
            expected_light = 300 
            expected_rem = 60
            
            actual_deep = processed_sleep.get('deep_sleep_minutes')
            actual_light = processed_sleep.get('light_sleep_minutes')
            actual_rem = processed_sleep.get('rem_sleep_minutes')
            
            print(f"  - Глубокий сон: {actual_deep} мин (ожидали {expected_deep})")
            print(f"  - Легкий сон: {actual_light} мин (ожидали {expected_light})")
            print(f"  - REM сон: {actual_rem} мин (ожидали {expected_rem})")
            
            assert actual_deep == expected_deep
            assert actual_light == expected_light
            assert actual_rem == expected_rem
            print("✅ Fallback к секундам работает корректно")
        else:
            print("❌ Обработка fallback вернула None")
            assert processed_sleep is not None
    except Exception as e:
        print(f"❌ Ошибка fallback: {e}")
        raise

if __name__ == "__main__":
    print("🚀 Тестирование нового подхода к фазам сна...")
    
    test1_passed = test_percentage_based_sleep_phases()
    test2_passed = test_fallback_to_seconds()
    
    if test1_passed and test2_passed:
        print("\n🏆 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("✅ Процентный подход работает для реальных данных Garmin")
        print("✅ Fallback к секундам сохранен для старых данных")
        print("🎉 ПРОБЛЕМА С НУЛЕВЫМИ ФАЗАМИ СНА РЕШЕНА!")
    else:
        print("\n⚠️ Некоторые тесты не прошли")
