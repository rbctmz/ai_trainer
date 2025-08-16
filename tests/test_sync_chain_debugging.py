#!/usr/bin/env python3
"""
Тест для диагностики цепочки передачи данных garth -> app.py -> процессор
"""

import sys
import os
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.garmin_client import GarminClient
from data.data_processor_phase1 import Phase1DataProcessor

def test_sync_chain():
    """Тестируем полную цепочку как в app.py"""
    print("🔍 Диагностика полной цепочки синхронизации...")
    
    # Инициализируем GarminClient
    try:
        garmin_client = GarminClient()
        print(f"✅ GarminClient инициализирован")
        
        # Проверяем авторизацию
        if not garmin_client.is_authenticated:
            print("❌ GarminClient не авторизован - пропускаем тест")
            return False
        
        print(f"✅ GarminClient авторизован")
        
        # Тестируем получение данных сна за последние несколько дней
        test_dates = []
        current_date = datetime.now()
        for i in range(3):  # Последние 3 дня
            test_date = current_date - timedelta(days=i)
            test_dates.append(test_date)
        
        for date in test_dates:
            date_str = date.strftime('%Y-%m-%d')
            print(f"\n📅 Тестируем дату: {date_str}")
            
            try:
                # Получаем данные сна через GarminClient (как в app.py)
                sleep_raw = garmin_client.get_sleep_data(date)
                print(f"DEBUG CHAIN: Получены данные сна для {date_str}: {type(sleep_raw)}")
                
                if sleep_raw:
                    print(f"DEBUG CHAIN: === ДАННЫЕ ОТ GARMIN CLIENT ===")
                    
                    if isinstance(sleep_raw, dict):
                        print(f"DEBUG CHAIN: Ключи верхнего уровня: {list(sleep_raw.keys())}")
                        
                        # Анализируем содержимое
                        if 'dailySleepDTO' in sleep_raw:
                            dto = sleep_raw['dailySleepDTO']
                            if isinstance(dto, dict):
                                print(f"DEBUG CHAIN: dailySleepDTO.sleepTimeSeconds: {dto.get('sleepTimeSeconds', 'НЕТ')}")
                                print(f"DEBUG CHAIN: dailySleepDTO.deepSleepSeconds: {dto.get('deepSleepSeconds', 'НЕТ')}")
                                print(f"DEBUG CHAIN: dailySleepDTO.lightSleepSeconds: {dto.get('lightSleepSeconds', 'НЕТ')}")
                                print(f"DEBUG CHAIN: dailySleepDTO.remSleepSeconds: {dto.get('remSleepSeconds', 'НЕТ')}")
                        
                        if 'sleepScores' in sleep_raw:
                            scores = sleep_raw['sleepScores']
                            if isinstance(scores, dict):
                                if 'deepPercentage' in scores:
                                    deep_val = scores['deepPercentage'].get('value') if isinstance(scores['deepPercentage'], dict) else scores['deepPercentage']
                                    print(f"DEBUG CHAIN: sleepScores.deepPercentage: {deep_val}")
                                if 'lightPercentage' in scores:
                                    light_val = scores['lightPercentage'].get('value') if isinstance(scores['lightPercentage'], dict) else scores['lightPercentage']
                                    print(f"DEBUG CHAIN: sleepScores.lightPercentage: {light_val}")
                                if 'remPercentage' in scores:
                                    rem_val = scores['remPercentage'].get('value') if isinstance(scores['remPercentage'], dict) else scores['remPercentage']
                                    print(f"DEBUG CHAIN: sleepScores.remPercentage: {rem_val}")
                    
                    print(f"DEBUG CHAIN: === ПЕРЕДАЕМ В ПРОЦЕССОР ===")
                    
                    # Передаем в процессор (как в app.py)
                    processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw)
                    
                    if processed_sleep:
                        total = processed_sleep.get('total_sleep_minutes', 0)
                        deep = processed_sleep.get('deep_sleep_minutes', 0)
                        light = processed_sleep.get('light_sleep_minutes', 0)
                        rem = processed_sleep.get('rem_sleep_minutes', 0)
                        score = processed_sleep.get('sleep_score', 0)
                        
                        print(f"DEBUG CHAIN: ✅ Результат процессора: total={total}, deep={deep}, light={light}, rem={rem}, score={score}")
                        
                        if deep == 0 and light == 0 and rem == 0:
                            print(f"DEBUG CHAIN: ⚠️ ПРОБЛЕМА: Все фазы сна равны 0 после обработки!")
                        else:
                            print(f"DEBUG CHAIN: ✅ Фазы сна обработаны правильно!")
                            
                        return True
                    else:
                        print(f"DEBUG CHAIN: ❌ Процессор вернул None")
                else:
                    print(f"DEBUG CHAIN: Нет данных сна для {date_str}")
                    
            except Exception as e:
                print(f"DEBUG CHAIN: ❌ Ошибка для {date_str}: {e}")
                import traceback
                traceback.print_exc()
        
        return False
        
    except Exception as e:
        print(f"❌ Ошибка инициализации GarminClient: {e}")
        return False

def test_garth_vs_garminconnect():
    """Сравниваем что возвращает garth vs garminconnect"""
    print("\n🔍 Сравнение garth vs garminconnect...")
    
    try:
        garmin_client = GarminClient()
        
        if not garmin_client.is_authenticated:
            print("❌ GarminClient не авторизован")
            return False
        
        test_date = datetime.now() - timedelta(days=1)  # Вчера
        date_str = test_date.strftime('%Y-%m-%d')
        
        print(f"📅 Тестируем дату: {date_str}")
        
        # Получаем данные
        sleep_data = garmin_client.get_sleep_data(test_date)
        
        if sleep_data:
            print(f"📊 Получены данные сна, тип: {type(sleep_data)}")
            
            # Проверяем источник данных
            if hasattr(garmin_client, 'garth_client') and garmin_client.garth_client:
                print("🔄 Данные получены через garth")
            else:
                print("🔄 Данные получены через garminconnect")
            
            return True
        else:
            print("❌ Нет данных сна")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Диагностика цепочки синхронизации...")
    
    test1 = test_sync_chain()
    test2 = test_garth_vs_garminconnect()
    
    if test1:
        print("\n✅ ЦЕПОЧКА СИНХРОНИЗАЦИИ РАБОТАЕТ")
    else:
        print("\n❌ ПРОБЛЕМА В ЦЕПОЧКЕ СИНХРОНИЗАЦИИ")
        print("🔍 Возможные причины:")
        print("1. Авторизация Garmin")
        print("2. Формат данных от garth/garminconnect отличается от ожидаемого")
        print("3. Ошибка в конвертации данных в garth_client.py")
        print("4. Данные сна недоступны для тестируемых дат")