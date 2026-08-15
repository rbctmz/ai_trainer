#!/usr/bin/env python3
"""
Тест синхронизации HRV данных с корректной структурой
"""

import sys
from datetime import datetime, timedelta

sys.path.append('.')

from data.garmin_client import GarminClient
from data.database import Database
from config.settings import Settings

def test_hrv_sync():
    """Тест синхронизации HRV данных"""
    
    print("🧪 Тест синхронизации HRV данных")
    print("=" * 40)
    
    # Инициализация
    client = GarminClient() 
    database = Database()
    
    # Подключение к Garmin
    email = Settings.GARMIN_EMAIL
    password = Settings.GARMIN_PASSWORD
    
    if not email or not password:
        print("📧 Введите данные для входа в Garmin Connect:")
        email = input("Email: ")
        password = input("Password: ")
    
    if not client.authenticate(email, password):
        print(f"❌ Ошибка аутентификации: {client.auth_error}")
        return False
    
    print("✅ Подключен к Garmin Connect")
    
    # Получаем HRV данные за последние 3 дня
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)
    
    print(f"\n💓 Синхронизация HRV за период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    hrv_data = {}
    current_date = start_date
    
    while current_date <= end_date:
        print(f"\n📅 Обработка даты: {current_date.strftime('%Y-%m-%d')}")
        
        hrv_day_data = client.get_hrv_data(current_date)
        if hrv_day_data and 'hrvSummary' in hrv_day_data:
            date_str = current_date.strftime('%Y-%m-%d')
            hrv_summary = hrv_day_data['hrvSummary']
            
            rmssd = hrv_summary.get('lastNightAvg')
            print(f"  ✅ HRV найден: RMSSD = {rmssd}")
            
            hrv_data[date_str] = {
                'rmssd': rmssd,
                'stress_score': None,
                'recovery_score': None
            }
        else:
            print("  📭 Нет HRV данных")
            
        current_date += timedelta(days=1)
    
    # Сохранение в базу данных
    if hrv_data:
        print(f"\n💾 Сохранение {len(hrv_data)} записей HRV...")
        hrv_result = database.sync_hrv_data(hrv_data)
        print(f"  🆕 Новых: {hrv_result['new']}")
        print(f"  🔄 Обновлено: {hrv_result['updated']}")
        
        # Проверяем результат
        saved_hrv = database.get_hrv_data(30)
        print(f"\n📊 Всего HRV записей в БД: {len(saved_hrv)}")
        
        if len(saved_hrv) > 0:
            print("📋 Последние записи:")
            for _, row in saved_hrv.head(5).iterrows():
                print(f"  {row['date'].strftime('%Y-%m-%d')}: RMSSD = {row['rmssd']}")
        
        return True
    else:
        print("\n📭 Нет HRV данных для синхронизации")
        return False

if __name__ == "__main__":
    success = test_hrv_sync()
    if success:
        print("\n🎉 HRV синхронизация работает!")
        print("📱 Теперь попробуйте: streamlit run app.py")
    else:
        print("\n❌ Проблемы с HRV синхронизацией")
