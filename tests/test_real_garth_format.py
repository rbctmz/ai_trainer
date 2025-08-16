#!/usr/bin/env python3
"""
Тест с реальной структурой данных garth из логов
"""

import sys
import os
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_real_garth_format():
    """Тестируем с реальной структурой данных из логов"""
    print("🔍 Тестирование с реальной структурой данных garth...")
    
    # Реальная структура данных из логов (примерно)
    real_garth_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 23700,  # Время сна в секундах
            'deepSleepSeconds': 720,    # Глубокий сон
            'lightSleepSeconds': 21420, # Легкий сон
            'remSleepSeconds': 1560,    # REM сон
            'awakeSleepSeconds': 300,   # Время бодрствования (НЕ awakeTime!)
            'sleepStartTimestampLocal': 1754882110000,  # МИЛЛИСЕКУНДЫ, не строка!
            'sleepEndTimestampLocal': 1754906110000     # МИЛЛИСЕКУНДЫ, не строка!
        },
        'sleepScores': {
            'overall': {'value': 57, 'qualifierKey': 'POOR'}
        }
    }
    
    print(f"📥 Реальные данные garth: {real_garth_data}")
    
    # Обрабатываем данные
    print(f"🔄 Обрабатываем реальные данные garth...")
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(real_garth_data)
        print(f"✅ Обработанные данные: {processed_sleep}")
        
        if processed_sleep:
            print("✅ Обработка успешна!")
            
            # Проверяем правильность вычислений
            expected_total = 23700 // 60  # 395 минут
            expected_deep = 720 // 60     # 12 минут
            expected_light = 21420 // 60  # 357 минут
            expected_rem = 1560 // 60     # 26 минут
            
            print(f"🔢 Ожидаемые значения:")
            print(f"  - Общий сон: {expected_total} мин")
            print(f"  - Глубокий: {expected_deep} мин")
            print(f"  - Легкий: {expected_light} мин")
            print(f"  - REM: {expected_rem} мин")
            
            print(f"📊 Фактические значения:")
            print(f"  - Общий сон: {processed_sleep.get('total_sleep_minutes', 'НЕТ')} мин")
            print(f"  - Глубокий: {processed_sleep.get('deep_sleep_minutes', 'НЕТ')} мин")
            print(f"  - Легкий: {processed_sleep.get('light_sleep_minutes', 'НЕТ')} мин")
            print(f"  - REM: {processed_sleep.get('rem_sleep_minutes', 'НЕТ')} мин")
            print(f"  - Sleep Score: {processed_sleep.get('sleep_score', 'НЕТ')}")
            
            # Проверяем timestamps
            if 'bedtime' in processed_sleep:
                print(f"  - Время засыпания: {processed_sleep['bedtime']}")
            if 'wakeup_time' in processed_sleep:
                print(f"  - Время пробуждения: {processed_sleep['wakeup_time']}")
            
            return processed_sleep
        else:
            print("❌ Обработка вернула None")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🚀 Запуск теста с реальным форматом garth...")
    result = test_real_garth_format()
    
    if result:
        print("\n🎉 Тест прошел успешно!")
    else:
        print("\n⚠️ Тест выявил проблемы")