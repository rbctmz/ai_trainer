#!/usr/bin/env python3
"""
Тест обработки данных сна от garth
"""

import sys
import os

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor

def test_garth_sleep_data():
    """Тестируем обработку данных сна от garth"""
    print("🧪 Тестирование обработки данных сна...")
    
    # Симуляция данных как они приходят от garth (конвертированные)
    garth_converted_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 25200,  # 7 часов
            'deepSleepSeconds': 5400,
            'lightSleepSeconds': 14400,
            'remSleepSeconds': 5400,
            'awakeSleepSeconds': 600,
            'sleepStartTimestampLocal': 1755297000000,
            'sleepEndTimestampLocal': 1755322200000,
        },
        'sleepScores': {
            'overall': {'value': 85}
        }
    }
    
    print(f"📥 Входные данные garth: {garth_converted_data}")
    
    # Обрабатываем данные
    result = Phase1DataProcessor.process_sleep_data(garth_converted_data)
    
    if result:
        print(f"✅ Обработка успешна: {result}")
        
        # Проверяем корректность
        expected_total = 25200 // 60  # 420 минут = 7 часов
        if result.get('total_sleep_minutes') == expected_total:
            print(f"✅ Общее время сна корректно: {expected_total} минут")
        else:
            print(f"❌ Ошибка времени сна: ожидали {expected_total}, получили {result.get('total_sleep_minutes')}")
        
        if result.get('sleep_score') == 85:
            print("✅ Sleep score сохранен корректно")
        else:
            print(f"❌ Ошибка sleep score: ожидали 85, получили {result.get('sleep_score')}")
            
        print(f"🏆 Финальный результат: {result}")
        
    else:
        print("❌ Обработка не удалась")
    assert result is not None
    assert result.get('total_sleep_minutes') == 25200 // 60
    assert result.get('sleep_score') == 85

def test_direct_garth_data():
    """Тестируем прямые данные garth"""
    print("\n🧪 Тестирование прямых данных garth...")
    
    direct_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 28800,  # 8 часов
            'deepSleepSeconds': 7200,   # 2 часа
            'lightSleepSeconds': 14400, # 4 часа
            'remSleepSeconds': 7200,    # 2 часа
            'sleepStartTimestampLocal': 1755295200000,
            'sleepEndTimestampLocal': 1755324000000,
        },
        'sleepScores': {
            'overall': {'value': 90}
        }
    }
    
    print(f"📥 Прямые данные garth: {direct_data}")
    
    result = Phase1DataProcessor.process_sleep_data(direct_data)
    
    if result:
        print(f"✅ Обработка прямых данных успешна: {result}")
    else:
        print("❌ Обработка прямых данных не удалась")
    assert result is not None

if __name__ == "__main__":
    print("🚀 Запуск тестов обработки данных сна...")
    
    # Тест 1: Конвертированные данные garth
    test1_result = test_garth_sleep_data()
    
    # Тест 2: Прямые данные garth  
    test2_result = test_direct_garth_data()
    
    if test1_result and test2_result:
        print("\n🎉 Все тесты прошли успешно!")
    else:
        print("\n⚠️ Некоторые тесты не прошли")
