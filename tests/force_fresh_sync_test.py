#!/usr/bin/env python3
"""
Принудительная синхронизация одного дня для тестирования нового подхода
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Добавляем путь к корневой папке проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from config.settings import Settings
from data.garmin_client import GarminClient
from data.data_processor_phase1 import Phase1DataProcessor
from data.database import Database

def force_sync_yesterday():
    """Принудительно синхронизируем данные за вчера с новым процессором"""
    print("🔄 Принудительная синхронизация данных сна за вчера...")
    
    GARMIN_EMAIL = Settings.GARMIN_EMAIL
    GARMIN_PASSWORD = Settings.GARMIN_PASSWORD

    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        print("❌ ОШИБКА: Учетные данные Garmin не найдены.")
        print("Пожалуйста, создайте файл .env в корневой папке проекта и добавьте в него:")
        print("GARMIN_EMAIL=your_email@example.com")
        print("GARMIN_PASSWORD=your_password")
        return False

    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    print(f"📅 Синхронизируем данные за {date_str}")
    
    try:
        # Инициализируем и аутентифицируем клиент Garmin
        garmin_client = GarminClient()
        print("🔐 Попытка аутентификации...")
        if not garmin_client.authenticate(GARMIN_EMAIL, GARMIN_PASSWORD):
            print(f"❌ ОШИБКА АУТЕНТИФИКАЦИИ: {garmin_client.auth_error}")
            print("Пожалуйста, проверьте правильность логина и пароля в вашем .env файле.")
            return False
        
        print("✅ Аутентификация прошла успешно!")
        
        # Получаем данные сна
        print(f"📥 Получаем данные сна за {date_str}...")
        sleep_raw_data = garmin_client.get_sleep_data(yesterday) # Передаем объект datetime
        
        if sleep_raw_data:
            print(f"✅ Данные получены: {type(sleep_raw_data)}")
            print(f"📝 Структура данных: dailySleepDTO={bool('dailySleepDTO' in sleep_raw_data)}, sleepScores={bool('sleepScores' in sleep_raw_data)}")
            
            # Обрабатываем данные НОВЫМ процессором
            print("🔄 Обрабатываем данные новым процессором...")
            processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw_data)
            
            if processed_sleep:
                print("✅ Данные успешно обработаны новым процессором:")
                print(f"  - Общий сон: {processed_sleep.get('total_sleep_minutes')} мин")
                print(f"  - Глубокий сон: {processed_sleep.get('deep_sleep_minutes')} мин")
                print(f"  - Легкий сон: {processed_sleep.get('light_sleep_minutes')} мин")
                print(f"  - REM сон: {processed_sleep.get('rem_sleep_minutes')} мин")
                print(f"  - Sleep Score: {processed_sleep.get('sleep_score')}")
                print(f"  - Пробуждения: {processed_sleep.get('awakenings_count')}")
                
                # Проверяем что фазы сна больше не равны 0
                deep = processed_sleep.get('deep_sleep_minutes', 0)
                light = processed_sleep.get('light_sleep_minutes', 0)
                rem = processed_sleep.get('rem_sleep_minutes', 0)
                
                if deep > 0 or light > 0 or rem > 0:
                    print("🎉 УСПЕХ: Фазы сна больше не равны 0!")
                    
                    # Сохраняем в базу данных
                    print("💾 Сохраняем в базу данных...")
                    db = Database()
                    sleep_data_dict = {date_str: processed_sleep}
                    result = db.sync_sleep_data(sleep_data_dict)
                    print(f"✅ Результат сохранения: {result}")
                    
                    # Проверяем сохранение
                    print("🔍 Проверяем сохранение в базе...")
                    conn = sqlite3.connect('ai_trainer.db')
                    cursor = conn.cursor()
                    cursor.execute("SELECT total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes, rem_sleep_minutes FROM sleep_data WHERE date = ?", (date_str,))
                    saved_data = cursor.fetchone()
                    conn.close()
                    
                    if saved_data:
                        total, deep_saved, light_saved, rem_saved = saved_data
                        print("✅ В базе сохранено:")
                        print(f"  - Общий сон: {total} мин")
                        print(f"  - Глубокий сон: {deep_saved} мин")
                        print(f"  - Легкий сон: {light_saved} мин")
                        print(f"  - REM сон: {rem_saved} мин")
                        
                        if deep_saved > 0 or light_saved > 0 or rem_saved > 0:
                            print("🏆 ПОЛНЫЙ УСПЕХ: Новый подход работает с реальными данными!")
                            return True
                        else:
                            print("❌ Проблема: В базе все еще нули")
                            return False
                    else:
                        print("❌ Данные не найдены в базе")
                        return False
                else:
                    print("❌ Проблема: Новый процессор все еще возвращает нули")
                    return False
            else:
                print("❌ Новый процессор вернул None")
                return False
        else:
            print("❌ Данные сна не получены")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Принудительная синхронизация для тестирования нового подхода...")
    success = force_sync_yesterday()
    
    if success:
        print("\n🎉 ПРОБЛЕМА С ФАЗАМИ СНА ПОЛНОСТЬЮ РЕШЕНА!")
        print("✅ Новый процентный подход работает с реальными данными Garmin")
        print("✅ Данные корректно сохраняются в базу")
    else:
        print("\n⚠️ Требуется дополнительная отладка")
