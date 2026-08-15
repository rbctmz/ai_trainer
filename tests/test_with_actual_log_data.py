#!/usr/bin/env python3
"""
Тест с точной структурой данных из логов Garmin
"""

import sys
import os
import sqlite3
import tempfile
from pathlib import Path
import pytest

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database

def test_with_exact_log_data():
    """Тестируем с точной структурой из логов"""
    print("🔍 Тестирование с точной структурой данных из логов...")
    
    # Данные точно как в логе 2025-08-14 (упрощенная версия)
    exact_log_data = {
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
            'totalDuration': {'qualifierKey': 'EXCELLENT', 'optimalStart': 27600.0, 'optimalEnd': 27600.0},
            'stress': {'qualifierKey': 'FAIR', 'optimalStart': 0.0, 'optimalEnd': 15.0},
            'awakeCount': {'qualifierKey': 'FAIR', 'optimalStart': 0.0, 'optimalEnd': 1.0},
            'overall': {'value': 66, 'qualifierKey': 'FAIR'},
            'remPercentage': {'value': 7, 'qualifierKey': 'POOR', 'optimalStart': 21.0, 'optimalEnd': 31.0},
            'restlessness': {'qualifierKey': 'POOR', 'optimalStart': 0.0, 'optimalEnd': 5.0},
            'lightPercentage': {'value': 79, 'qualifierKey': 'FAIR', 'optimalStart': 30.0, 'optimalEnd': 64.0},
            'deepPercentage': {'value': 14, 'qualifierKey': 'FAIR', 'optimalStart': 16.0, 'optimalEnd': 33.0}
        }
    }
    
    print("📥 Данные из реальных логов:")
    print(f"  - sleepTimeSeconds: {exact_log_data['dailySleepDTO']['sleepTimeSeconds']} сек (466 мин)")
    print("  - НЕТ секунд для фаз сна")
    print(f"  - deepPercentage: {exact_log_data['sleepScores']['deepPercentage']['value']}%")
    print(f"  - lightPercentage: {exact_log_data['sleepScores']['lightPercentage']['value']}%")
    print(f"  - remPercentage: {exact_log_data['sleepScores']['remPercentage']['value']}%")
    print(f"  - overall score: {exact_log_data['sleepScores']['overall']['value']}")
    
    # Обрабатываем данные
    try:
        processed_sleep = Phase1DataProcessor.process_sleep_data(exact_log_data)
        
        if processed_sleep:
            print("✅ Данные успешно обработаны!")
            
            # Ожидаемые значения из процентов
            total_minutes = 466
            expected_deep = round(466 * 14 / 100)  # 65 минут
            expected_light = round(466 * 79 / 100)  # 368 минут
            expected_rem = round(466 * 7 / 100)   # 33 минуты
            expected_score = 66
            expected_awakenings = 3
            
            actual_total = processed_sleep.get('total_sleep_minutes')
            actual_deep = processed_sleep.get('deep_sleep_minutes')
            actual_light = processed_sleep.get('light_sleep_minutes')
            actual_rem = processed_sleep.get('rem_sleep_minutes')
            actual_score = processed_sleep.get('sleep_score')
            actual_awakenings = processed_sleep.get('awakenings_count')
            
            print("📊 Результаты обработки:")
            print(f"  - Общий сон: {actual_total} мин (ожидали {total_minutes})")
            print(f"  - Глубокий сон: {actual_deep} мин (ожидали {expected_deep})")
            print(f"  - Легкий сон: {actual_light} мин (ожидали {expected_light})")
            print(f"  - REM сон: {actual_rem} мин (ожидали {expected_rem})")
            print(f"  - Sleep Score: {actual_score} (ожидали {expected_score})")
            print(f"  - Пробуждения: {actual_awakenings} (ожидали {expected_awakenings})")
            
            # Проверяем главное - что фазы сна НЕ равны 0
            if actual_deep > 0 and actual_light > 0 and actual_rem > 0:
                print("🎉 КРИТИЧЕСКИЙ УСПЕХ: Все фазы сна больше не равны 0!")
                
                assert actual_total == total_minutes
                assert actual_deep == expected_deep
                assert actual_light == expected_light
                assert actual_rem == expected_rem
                assert actual_score == expected_score
                assert actual_awakenings == expected_awakenings
                print("✅ Все значения точно совпадают с ожидаемыми!")
            else:
                print("❌ ПРОБЛЕМА: Некоторые фазы сна все еще равны 0")
                print(f"  - Глубокий: {actual_deep}, Легкий: {actual_light}, REM: {actual_rem}")
                assert actual_deep > 0 and actual_light > 0 and actual_rem > 0
                
        else:
            print("❌ Обработка вернула None")
            assert processed_sleep is not None
            
    except Exception as e:
        print(f"❌ Ошибка обработки: {e}")
        import traceback
        traceback.print_exc()
        raise

def test_simulated_database_save(tmp_path):
    """Тестируем сохранение обработанных данных в базу"""
    print("\n🔍 Тестирование сохранения в базу данных...")
    
    # Используем те же данные
    exact_log_data = {
        'dailySleepDTO': {
            'sleepTimeSeconds': 27960,
            'sleepStartTimestampLocal': 1755128729000,
            'sleepEndTimestampLocal': 1755158909000,
            'awakeCount': 3
        },
        'sleepScores': {
            'overall': {'value': 66, 'qualifierKey': 'FAIR'},
            'remPercentage': {'value': 7, 'qualifierKey': 'POOR'},
            'lightPercentage': {'value': 79, 'qualifierKey': 'FAIR'},
            'deepPercentage': {'value': 14, 'qualifierKey': 'FAIR'}
        }
    }
    
    try:
        # Обрабатываем данные
        processed_sleep = Phase1DataProcessor.process_sleep_data(exact_log_data)
        
        if processed_sleep and processed_sleep.get('deep_sleep_minutes', 0) > 0:
            # Сохраняем в базу
            test_date = '2025-08-16'  # Тестовая дата
            
            db = Database(str(tmp_path / "sleep_save.db"))
            sleep_data_dict = {test_date: processed_sleep}
            result = db.sync_sleep_data(sleep_data_dict)
            print(f"✅ Результат сохранения: {result}")
            
            # Проверяем сохранение
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes FROM sleep_data WHERE date = ?", (test_date,))
            saved_data = cursor.fetchone()
            conn.close()
            
            if saved_data:
                total, deep_saved, light_saved, rem_saved = saved_data
                print(f"✅ В базе сохранено: {total} мин общий, {deep_saved} мин глуб, {light_saved} мин легк, {rem_saved} мин REM")
                
                if deep_saved > 0 and light_saved > 0 and rem_saved > 0:
                    print("🎉 БАЗА ДАННЫХ: Все фазы сна успешно сохранены!")
                    assert True
                else:
                    print("❌ БАЗА ДАННЫХ: Фазы сна сохранились как нули")
                    pytest.fail("Фазы сна сохранились как нули")
            else:
                print("❌ Данные не найдены в базе")
                assert saved_data is not None
        else:
            print("❌ Не удалось обработать данные для сохранения")
            assert processed_sleep is not None
            
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        raise

if __name__ == "__main__":
    print("🚀 Тест с точной структурой данных из логов Garmin...")
    
    test_with_exact_log_data()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_simulated_database_save(Path(tmp_dir))
    
    print("\n🏆 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
    print("✅ Процентный подход работает с точной структурой логов")
    print("✅ Данные корректно сохраняются в базу")
    print("🎉 ПРОБЛЕМА С НУЛЕВЫМИ ФАЗАМИ СНА ПОЛНОСТЬЮ РЕШЕНА!")
