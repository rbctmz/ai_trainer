#!/usr/bin/env python3
"""
Тест для проверки исправления - имитируем точную структуру данных из логов
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_exact_log_data_structure():
    """Тестируем с точной структурой данных из логов 2025-08-09"""
    print("🔍 Тест с точной структурой данных из логов 2025-08-09...")
    
    # Точная структура данных из логов (у которых все фазы сна были 0)
    real_log_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 34620,    # 577 минут
            'deepSleepSeconds': 3480,     # 58 минут ← ЕСТЬ ДАННЫЕ!
            'lightSleepSeconds': 25260,   # 421 минута ← ЕСТЬ ДАННЫЕ!
            'remSleepSeconds': 5880,      # 98 минут ← ЕСТЬ ДАННЫЕ!
            'awakeCount': 6,
            'sleepStartTimestampLocal': 1755043075000,
            'sleepEndTimestampLocal': 1755069595000
        },
        'sleepMovement': [
            # Движения во сне (реальные данные)
        ]
        # НЕТ sleepScores! Именно поэтому раньше получались нули
    }
    
    print(f"📥 Структура данных (БЕЗ sleepScores):")
    print(f"  - Ключи верхнего уровня: {list(real_log_data.keys())}")
    print(f"  - sleepTimeSeconds: {real_log_data['dailySleepDTO']['sleepTimeSeconds']} сек")
    print(f"  - deepSleepSeconds: {real_log_data['dailySleepDTO']['deepSleepSeconds']} сек")
    print(f"  - lightSleepSeconds: {real_log_data['dailySleepDTO']['lightSleepSeconds']} сек")
    print(f"  - remSleepSeconds: {real_log_data['dailySleepDTO']['remSleepSeconds']} сек")
    print(f"  - ⚠️ sleepScores НЕТ в данных")
    
    print("\\n🔄 Обрабатываем исправленным процессором...")
    
    # Обрабатываем исправленным процессором
    processed = Phase1DataProcessor.process_sleep_data(real_log_data)
    
    if processed:
        total = processed.get('total_sleep_minutes', 0)
        deep = processed.get('deep_sleep_minutes', 0)
        light = processed.get('light_sleep_minutes', 0)
        rem = processed.get('rem_sleep_minutes', 0)
        
        expected_total = 34620 // 60  # 577 минут
        expected_deep = 3480 // 60    # 58 минут
        expected_light = 25260 // 60  # 421 минута
        expected_rem = 5880 // 60     # 98 минут
        
        print(f"📊 Результат обработки:")
        print(f"  - Общий сон: {total} мин (ожидали {expected_total})")
        print(f"  - Глубокий сон: {deep} мин (ожидали {expected_deep})")
        print(f"  - Легкий сон: {light} мин (ожидали {expected_light})")
        print(f"  - REM сон: {rem} мин (ожидали {expected_rem})")
        
        # Проверяем что теперь получаем правильные значения
        if (total == expected_total and 
            deep == expected_deep and 
            light == expected_light and 
            rem == expected_rem):
            print("\\n🎉 ИСПРАВЛЕНИЕ РАБОТАЕТ!")
            print("✅ Процессор теперь правильно извлекает данные из dailySleepDTO БЕЗ sleepScores")
            print("✅ Больше никаких нулей для фаз сна!")
            return True
        else:
            print("\\n❌ Исправление не работает")
            return False
    else:
        print("❌ Процессор вернул None")
        return False

def test_before_after_comparison():
    """Сравниваем старое и новое поведение"""
    print("\\n🔍 Сравнение СТАРОГО и НОВОГО поведения...")
    
    # Данные которые раньше давали нули
    problematic_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 34620,
            'deepSleepSeconds': 3480,     # БЫЛИ данные, но получали 0
            'lightSleepSeconds': 25260,   # БЫЛИ данные, но получали 0  
            'remSleepSeconds': 5880,      # БЫЛИ данные, но получали 0
            'awakeCount': 6
        }
        # НЕТ sleepScores - именно из-за этого были нули
    }
    
    processed = Phase1DataProcessor.process_sleep_data(problematic_data)
    
    if processed:
        deep = processed.get('deep_sleep_minutes', 0)
        light = processed.get('light_sleep_minutes', 0) 
        rem = processed.get('rem_sleep_minutes', 0)
        
        print(f"📊 С исправленным процессором:")
        print(f"  - Глубокий сон: {deep} мин (раньше было 0)")
        print(f"  - Легкий сон: {light} мин (раньше было 0)")
        print(f"  - REM сон: {rem} мин (раньше было 0)")
        
        if deep > 0 and light > 0 and rem > 0:
            print("\\n✅ ПРОБЛЕМА РЕШЕНА! Теперь получаем реальные данные вместо нулей")
            return True
        else:
            print("\\n❌ Проблема не решена")
            return False
    else:
        return False

if __name__ == "__main__":
    print("🚀 Проверка исправления Phase1DataProcessor...")
    
    test1 = test_exact_log_data_structure()
    test2 = test_before_after_comparison()
    
    if test1 and test2:
        print("\\n🏆 ВСЕ ТЕСТЫ ПРОШЛИ!")
        print("🎯 ИСПРАВЛЕНИЕ ПОДТВЕРЖДЕНО:")
        print("  ✅ Процессор теперь правильно обрабатывает реальные данные Garmin")
        print("  ✅ Фазы сна извлекаются напрямую из секунд в dailySleepDTO")
        print("  ✅ Больше не зависим от наличия sleepScores")
        print("  ✅ При следующей синхронизации данные сна будут правильными!")
        print("\\n🔔 РЕКОМЕНДАЦИЯ: Запустите синхронизацию в приложении для обновления базы данных")
    else:
        print("\\n❌ Некоторые тесты не прошли - исправление требует доработки")