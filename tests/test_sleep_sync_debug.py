#!/usr/bin/env python3
"""
Тест отладки синхронизации данных сна
"""

import sys
import os
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.garmin_client import GarminClient
from data.data_processor_phase1 import Phase1DataProcessor

def test_sleep_sync_with_debug():
    """Тестируем синхронизацию данных сна с отладочными сообщениями"""
    print("🔍 Тестирование синхронизации данных сна...")
    
    # Инициализируем клиент
    GarminClient()
    
    # Здесь нужно будет авторизоваться, но для теста мы симулируем данные
    # client.authenticate("email", "password")
    
    # Симулируем данные как они приходят от garth
    test_date = datetime.now() - timedelta(days=1)
    date_str = test_date.strftime('%Y-%m-%d')
    
    # Имитируем данные от garth с корректным форматом времени
    current_timestamp = int(datetime.now().timestamp())
    sleep_start_ts = current_timestamp - 28800  # 8 часов назад
    sleep_end_ts = current_timestamp - 1800  # 30 минут назад
    
    mock_garth_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 26400,  # 7.3 часа
            'sleepStartTimestampLocal': sleep_start_ts * 1000,  # в миллисекундах
            'sleepEndTimestampLocal': sleep_end_ts * 1000,     # в миллисекундах
            'deepSleepSeconds': 3600,   # 1 час
            'lightSleepSeconds': 19800, # 5.5 часов
            'remSleepSeconds': 3000,    # 50 минут
            'awakeTime': 600            # 10 минут
        },
        'sleepScores': {
            'overall': {'value': 78}
        }
    }
    
    print(f"📥 Тестовые данные сна для {date_str}: {mock_garth_data}")
    
    # Обрабатываем данные
    print(f"🔄 Обрабатываем данные сна для {date_str}")
    processed_sleep = Phase1DataProcessor.process_sleep_data(mock_garth_data)
    print(f"✅ Обработанные данные сна для {date_str}: {processed_sleep}")
    
    if processed_sleep:
        print("✅ Обработка успешна")
        # Проверяем структуру
        expected_fields = ['total_sleep_minutes', 'deep_sleep_minutes', 'light_sleep_minutes', 'rem_sleep_minutes']
        missing_fields = [field for field in expected_fields if field not in processed_sleep]
        
        if missing_fields:
            print(f"⚠️ Отсутствуют поля: {missing_fields}")
        else:
            print("✅ Все необходимые поля присутствуют")
            
        return processed_sleep
    else:
        print("❌ Обработка данных сна вернула None")
        return None

if __name__ == "__main__":
    print("🚀 Запуск теста отладки синхронизации сна...")
    result = test_sleep_sync_with_debug()
    
    if result:
        print("\n🎉 Тест прошел успешно!")
        print(f"📊 Результат: {result}")
    else:
        print("\n⚠️ Тест показал проблемы в обработке данных")