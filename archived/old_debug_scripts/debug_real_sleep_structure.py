#!/usr/bin/env python3
"""
Диагностика реальной структуры данных сна из логов
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def debug_real_garmin_structure():
    """Проверяем что происходит с реальными данными"""
    print("🔍 Диагностика реальной структуры данных Garmin...")
    
    # Создаем данные максимально близкие к реальным (из логов)
    real_garmin_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,  # 466 минут
            'napTimeSeconds': 0,
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3,
            'avgSleepStress': 23.0
            # НЕТ deepSleepSeconds, lightSleepSeconds, remSleepSeconds
        },
        'sleepScores': {
            'totalDuration': {'qualifierKey': 'EXCELLENT'},
            'stress': {'qualifierKey': 'FAIR'},
            'awakeCount': {'qualifierKey': 'FAIR'},
            'overall': {'value': 66, 'qualifierKey': 'FAIR'},
            'remPercentage': {'value': 7, 'qualifierKey': 'POOR'},
            'restlessness': {'qualifierKey': 'POOR'},
            'lightPercentage': {'value': 79, 'qualifierKey': 'FAIR'},
            'deepPercentage': {'value': 14, 'qualifierKey': 'FAIR'}
        }
    }
    
    print("📥 Структура данных:")
    print(f"  - sleepTimeSeconds: {real_garmin_data['dailySleepDTO']['sleepTimeSeconds']}")
    print(f"  - НЕТ секунд фаз сна в dailySleepDTO")
    print(f"  - deepPercentage в sleepScores: {real_garmin_data['sleepScores']['deepPercentage']['value']}%")
    print(f"  - lightPercentage в sleepScores: {real_garmin_data['sleepScores']['lightPercentage']['value']}%")
    print(f"  - remPercentage в sleepScores: {real_garmin_data['sleepScores']['remPercentage']['value']}%")
    
    print("\n🔄 Тестируем обработку...")
    
    # Добавляем детальное логирование в процессор
    processed = Phase1DataProcessor.process_sleep_data(real_garmin_data)
    
    if processed:
        print(f"✅ Обработка успешна:")
        print(f"  - total_sleep_minutes: {processed.get('total_sleep_minutes')}")
        print(f"  - deep_sleep_minutes: {processed.get('deep_sleep_minutes')}")
        print(f"  - light_sleep_minutes: {processed.get('light_sleep_minutes')}")
        print(f"  - rem_sleep_minutes: {processed.get('rem_sleep_minutes')}")
        print(f"  - sleep_score: {processed.get('sleep_score')}")
        
        # Проверяем критические условия
        total_minutes = processed.get('total_sleep_minutes', 0)
        deep_minutes = processed.get('deep_sleep_minutes', 0)
        light_minutes = processed.get('light_sleep_minutes', 0)
        rem_minutes = processed.get('rem_sleep_minutes', 0)
        
        print(f"\n🔍 Диагностика логики:")
        print(f"  - Общее время > 0: {total_minutes > 0}")
        print(f"  - sleepScores присутствует: {'sleepScores' in real_garmin_data}")
        print(f"  - deepPercentage найден: {'deepPercentage' in real_garmin_data.get('sleepScores', {})}")
        
        if total_minutes > 0 and 'sleepScores' in real_garmin_data:
            scores = real_garmin_data['sleepScores']
            deep_percent = scores.get('deepPercentage', {}).get('value', 0)
            light_percent = scores.get('lightPercentage', {}).get('value', 0)
            rem_percent = scores.get('remPercentage', {}).get('value', 0)
            
            expected_deep = round(total_minutes * deep_percent / 100)
            expected_light = round(total_minutes * light_percent / 100)
            expected_rem = round(total_minutes * rem_percent / 100)
            
            print(f"  - Ожидаемый глубокий сон: {expected_deep} мин")
            print(f"  - Ожидаемый легкий сон: {expected_light} мин")
            print(f"  - Ожидаемый REM сон: {expected_rem} мин")
            
            if deep_minutes == expected_deep and light_minutes == expected_light and rem_minutes == expected_rem:
                print("✅ Процентный подход работает корректно!")
                return True
            else:
                print("❌ Процентный подход не работает!")
                print(f"  Получили: глуб={deep_minutes}, легк={light_minutes}, REM={rem_minutes}")
                print(f"  Ожидали: глуб={expected_deep}, легк={expected_light}, REM={expected_rem}")
                return False
        else:
            print("❌ Условия для процентного подхода не выполнены")
            return False
    else:
        print("❌ Обработка вернула None")
        return False

def test_missing_percentages():
    """Тестируем случай когда процентов нет"""
    print("\n🔍 Тест случая без процентов...")
    
    # Данные без процентов (как может быть в реальности)
    no_percentages_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3
        },
        'sleepScores': {
            'overall': {'value': 66, 'qualifierKey': 'FAIR'}
            # НЕТ процентов фаз сна
        }
    }
    
    print("📥 Данные без процентов фаз сна")
    
    processed = Phase1DataProcessor.process_sleep_data(no_percentages_data)
    
    if processed:
        deep = processed.get('deep_sleep_minutes', 0)
        light = processed.get('light_sleep_minutes', 0)
        rem = processed.get('rem_sleep_minutes', 0)
        
        print(f"📊 Результат: глуб={deep}, легк={light}, REM={rem}")
        
        if deep == 0 and light == 0 and rem == 0:
            print("✅ Корректно возвращает нули когда нет данных")
            return True
        else:
            print("❌ Неожиданные значения при отсутствии данных")
            return False
    else:
        print("❌ Обработка вернула None")
        return False

if __name__ == "__main__":
    print("🚀 Диагностика реальной структуры данных сна...")
    
    test1 = debug_real_garmin_structure()
    test2 = test_missing_percentages()
    
    if test1:
        print("\n✅ ПРОЦЕНТНЫЙ ПОДХОД РАБОТАЕТ - проблема в другом!")
    else:
        print("\n❌ ПРОЦЕНТНЫЙ ПОДХОД НЕ РАБОТАЕТ - нужна отладка!")
        
    if not test1 and not test2:
        print("\n🔍 ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("1. Реальные данные имеют другую структуру")
        print("2. Проценты не содержатся в sleepScores")  
        print("3. Логика условий в процессоре неправильная")
        print("4. Данные не достигают процессора из-за ошибки выше")