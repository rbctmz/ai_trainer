#!/usr/bin/env python3
"""
Диагностика структуры реальных данных сна от Garmin
"""

import sys
import os
import sqlite3
import json
from datetime import datetime, timedelta

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.garth_client import GarthClient
from utils.logger import GarminLogger

def debug_real_sleep_data():
    """Исследуем структуру реальных данных сна"""
    print("🔍 Исследование структуры реальных данных сна от Garmin...")
    
    logger = GarminLogger()
    
    try:
        # Инициализируем GarthClient
        garth_client = GarthClient()
        print("✅ GarthClient инициализирован")
        
        # Получаем данные сна за вчера
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')
        
        print(f"📅 Получаем данные сна за {date_str}...")
        
        sleep_data = garth_client.get_sleep_data(date_str)
        
        if sleep_data:
            print(f"✅ Данные получены: {type(sleep_data)}")
            
            # Логируем полную структуру в красивом формате
            print("\n📊 ПОЛНАЯ СТРУКТУРА ДАННЫХ:")
            print("=" * 60)
            
            # Если это словарь, выводим красиво
            if isinstance(sleep_data, dict):
                formatted_data = json.dumps(sleep_data, indent=2, ensure_ascii=False, default=str)
                print(formatted_data)
                
                # Анализируем наличие ключевых полей
                print("\n🔎 АНАЛИЗ КЛЮЧЕВЫХ ПОЛЕЙ:")
                print("=" * 40)
                
                if 'dailySleepDTO' in sleep_data:
                    dto = sleep_data['dailySleepDTO']
                    print("✅ dailySleepDTO найден:")
                    
                    key_fields = [
                        'sleepTimeSeconds', 'deepSleepSeconds', 'lightSleepSeconds', 
                        'remSleepSeconds', 'awakeSleepSeconds', 'awakeCount'
                    ]
                    
                    for field in key_fields:
                        if field in dto:
                            print(f"  ✅ {field}: {dto[field]}")
                        else:
                            print(f"  ❌ {field}: НЕТ")
                else:
                    print("❌ dailySleepDTO НЕ найден")
                
                if 'sleepLevels' in sleep_data:
                    levels = sleep_data['sleepLevels']
                    print(f"✅ sleepLevels найден: {len(levels)} записей")
                    if levels:
                        print(f"  Пример: {levels[0]}")
                else:
                    print("❌ sleepLevels НЕ найден")
                
                if 'sleepMovement' in sleep_data:
                    movement = sleep_data['sleepMovement']
                    print(f"✅ sleepMovement найден: {len(movement)} записей")
                    if movement:
                        print(f"  Пример: {movement[0]}")
                else:
                    print("❌ sleepMovement НЕ найден")
                
                if 'sleepScores' in sleep_data:
                    scores = sleep_data['sleepScores']
                    print(f"✅ sleepScores найден:")
                    if 'overall' in scores:
                        print(f"  Общий балл: {scores['overall'].get('value', 'НЕТ')}")
                    if 'deepPercentage' in scores:
                        print(f"  Глубокий сон %: {scores['deepPercentage'].get('value', 'НЕТ')}")
                    if 'lightPercentage' in scores:
                        print(f"  Легкий сон %: {scores['lightPercentage'].get('value', 'НЕТ')}")
                    if 'remPercentage' in scores:
                        print(f"  REM сон %: {scores['remPercentage'].get('value', 'НЕТ')}")
                else:
                    print("❌ sleepScores НЕ найден")
            else:
                print(f"Тип данных: {type(sleep_data)}")
                print(f"Содержимое: {sleep_data}")
                
        else:
            print("❌ Данные сна не получены")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

def analyze_percentage_approach():
    """Анализируем можно ли получить фазы сна из процентов"""
    print("\n🔍 Анализ подхода через проценты...")
    
    # Симулируем данные с процентами, как в реальных данных
    sample_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,  # 466 минут = 7 часов 46 минут
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3
        },
        'sleepScores': {
            'overall': {'value': 66},
            'deepPercentage': {'value': 14},      # 14% глубокого сна
            'lightPercentage': {'value': 79},     # 79% легкого сна  
            'remPercentage': {'value': 7},        # 7% REM сна
            'restlessness': {'qualifierKey': 'POOR'}
        }
    }
    
    total_sleep_minutes = sample_data['dailySleepDTO']['sleepTimeSeconds'] // 60
    deep_percent = sample_data['sleepScores']['deepPercentage']['value']
    light_percent = sample_data['sleepScores']['lightPercentage']['value']
    rem_percent = sample_data['sleepScores']['remPercentage']['value']
    
    print(f"📊 Общее время сна: {total_sleep_minutes} минут")
    print(f"📊 Проценты фаз:")
    print(f"  - Глубокий сон: {deep_percent}%")
    print(f"  - Легкий сон: {light_percent}%")
    print(f"  - REM сон: {rem_percent}%")
    
    # Рассчитываем минуты из процентов
    deep_minutes = round(total_sleep_minutes * deep_percent / 100)
    light_minutes = round(total_sleep_minutes * light_percent / 100)  
    rem_minutes = round(total_sleep_minutes * rem_percent / 100)
    
    print(f"📊 Рассчитанные минуты:")
    print(f"  - Глубокий сон: {deep_minutes} мин")
    print(f"  - Легкий сон: {light_minutes} мин")
    print(f"  - REM сон: {rem_minutes} мин")
    print(f"  - Сумма: {deep_minutes + light_minutes + rem_minutes} мин (должно быть ~{total_sleep_minutes})")
    
    total_calculated = deep_minutes + light_minutes + rem_minutes
    if abs(total_calculated - total_sleep_minutes) <= 5:  # Небольшая погрешность из-за округления
        print("✅ Подход через проценты работает!")
        return True
    else:
        print("❌ Подход через проценты дает большую погрешность")
        return False

if __name__ == "__main__":
    print("🚀 Диагностика структуры реальных данных сна...")
    
    debug_real_sleep_data()
    
    percentage_works = analyze_percentage_approach()
    
    if percentage_works:
        print("\n💡 РЕШЕНИЕ: Использовать проценты из sleepScores для расчета фаз сна!")
    else:
        print("\n⚠️ Необходимо найти другой подход...")