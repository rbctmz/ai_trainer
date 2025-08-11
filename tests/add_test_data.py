#!/usr/bin/env python3
"""
Скрипт для добавления тестовых данных активностей и HRV
"""

import sys
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Добавляем путь к модулям
sys.path.append('.')

from data.database import Database

def add_test_activities():
    """Добавление тестовых активностей"""
    db = Database()
    
    # Создаем тестовые данные за последние 30 дней
    activities = []
    
    base_date = datetime.now() - timedelta(days=30)
    
    sports = ['running', 'cycling', 'swimming', 'gym']
    
    for i in range(40):  # 40 тренировок за 30 дней
        date = base_date + timedelta(days=np.random.randint(0, 30))
        sport = np.random.choice(sports)
        
        # Параметры в зависимости от вида спорта
        if sport == 'running':
            duration = np.random.randint(30, 120)  # 30-120 мин
            distance = duration * np.random.uniform(0.08, 0.15)  # 8-15 км/ч
            avg_hr = np.random.randint(140, 180)
            tss = duration * np.random.uniform(0.5, 1.2)
            calories = duration * 10 + np.random.randint(0, 100)
        elif sport == 'cycling':
            duration = np.random.randint(60, 180)  # 60-180 мин
            distance = duration * np.random.uniform(0.25, 0.45)  # 25-45 км/ч
            avg_hr = np.random.randint(130, 170)
            avg_power = np.random.randint(150, 280)
            tss = duration * np.random.uniform(0.6, 1.3)
            calories = duration * 8 + np.random.randint(0, 150)
        elif sport == 'swimming':
            duration = np.random.randint(45, 90)   # 45-90 мин
            distance = duration * np.random.uniform(0.025, 0.04)  # 1.5-2.4 км/ч
            avg_hr = np.random.randint(120, 160)
            tss = duration * np.random.uniform(0.7, 1.1)
            calories = duration * 12 + np.random.randint(0, 80)
        else:  # gym
            duration = np.random.randint(45, 90)   # 45-90 мин
            distance = 0  # Без дистанции
            avg_hr = np.random.randint(110, 150)
            tss = duration * np.random.uniform(0.4, 0.8)
            calories = duration * 6 + np.random.randint(0, 100)
        
        activity = {
            'activity_id': f'test_{i}_{int(date.timestamp())}',
            'date': date.date(),
            'sport': sport,
            'duration_minutes': duration,
            'distance_km': round(distance, 2),
            'avg_hr': int(avg_hr),
            'max_hr': int(avg_hr + np.random.randint(10, 30)),
            'avg_power': int(avg_power) if sport == 'cycling' else None,
            'max_power': int(avg_power * 1.5) if sport == 'cycling' else None,
            'elevation_gain': np.random.randint(0, 500) if sport in ['running', 'cycling'] else 0,
            'calories': int(calories),
            'tss': round(tss, 1)
        }
        
        activities.append(activity)
    
    # Сохраняем в базу
    db.save_activities(activities)
    print(f"✅ Добавлено {len(activities)} тестовых активностей")

def add_test_hrv():
    """Добавление тестовых данных HRV"""
    db = Database()
    
    hrv_data = {}
    base_date = datetime.now() - timedelta(days=30)
    
    # Базовое значение RMSSD
    base_rmssd = 35.0
    
    for i in range(30):  # 30 дней данных
        date = base_date + timedelta(days=i)
        
        # Имитация естественных колебаний HRV
        trend = np.sin(i * 0.2) * 5  # Недельный цикл
        noise = np.random.normal(0, 3)  # Случайный шум
        daily_variation = np.random.normal(0, 2)  # Ежедневные колебания
        
        rmssd = base_rmssd + trend + noise + daily_variation
        rmssd = max(15, min(60, rmssd))  # Ограничиваем реальными значениями
        
        # Стресс-индекс обратно коррелирует с RMSSD
        stress_score = max(0, min(100, 60 - (rmssd - 25) * 2 + np.random.normal(0, 10)))
        
        # Индекс восстановления на основе RMSSD
        recovery_score = max(0, min(100, (rmssd - 20) * 3 + np.random.normal(0, 8)))
        
        hrv_data[date.strftime('%Y-%m-%d')] = {
            'rmssd': round(rmssd, 1),
            'stress_score': round(stress_score, 1),
            'recovery_score': round(recovery_score, 1)
        }
    
    # Сохраняем в базу
    db.save_hrv_data(hrv_data)
    print(f"✅ Добавлено {len(hrv_data)} записей HRV данных")

def main():
    print("🧪 Добавление тестовых данных...")
    print("=" * 50)
    
    add_test_activities()
    add_test_hrv()
    
    print("=" * 50)
    print("✅ Тестовые данные успешно добавлены!")
    print("\n📱 Теперь можете протестировать новые разделы:")
    print("   streamlit run app.py")
    print("\n🔍 Проверьте разделы:")
    print("   - 🏃‍♂️ Активности")
    print("   - 💓 Анализ HRV")

if __name__ == "__main__":
    main()