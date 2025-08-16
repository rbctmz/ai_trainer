#!/usr/bin/env python3
"""
Добавление реалистичных тестовых данных тренировок для улучшения анализа корреляции HRV и нагрузки
"""

import sys
import os
sys.path.append('..')

import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random
import uuid
from data.database import Database
from data.data_processor import ActivityProcessor

def add_realistic_training_data():
    """Добавляет реалистичные тренировочные данные с учетом влияния на HRV"""
    print("=" * 80)
    print("ДОБАВЛЕНИЕ ТРЕНИРОВОЧНЫХ ДАННЫХ ДЛЯ АНАЛИЗА КОРРЕЛЯЦИИ")
    print("=" * 80)
    
    db = Database()
    
    # Получаем существующие HRV данные
    hrv_df = db.get_hrv_data(60)
    if hrv_df.empty:
        print("⚠️ Нет HRV данных. Сначала запустите add_test_hrv_data.py")
        return
    
    print(f"📊 Найдено HRV данных: {len(hrv_df)} записей")
    print(f"📅 Диапазон дат HRV: {hrv_df['date'].min().date()} - {hrv_df['date'].max().date()}")
    
    # Генерируем тренировочные данные с реалистичной корреляцией к HRV
    activities = []
    
    # Сортируем HRV данные по дате для последовательной обработки
    hrv_sorted = hrv_df.sort_values('date')
    
    print("\n🏃‍♂️ Генерация тренировочных данных...")
    
    for idx, hrv_row in hrv_sorted.iterrows():
        date = hrv_row['date'].date()
        rmssd = hrv_row['rmssd']
        
        # Определяем вероятность тренировки (5-7 дней в неделю)
        if random.random() < 0.8:  # 80% вероятность тренировки
            
            # Тип тренировки зависит от дня недели и HRV
            day_of_week = date.weekday()
            
            # Базовая интенсивность зависит от HRV (обратная корреляция)
            # Высокий HRV = можно более интенсивную тренировку
            hrv_factor = max(0.5, min(1.5, rmssd / 45))  # Нормализуем к среднему HRV ~45
            
            if day_of_week in [1, 3, 5]:  # Вторник, четверг, суббота - интервалы
                sport = "cycling" if random.random() > 0.3 else "running"
                duration = random.randint(45, 90) * hrv_factor
                
                if sport == "cycling":
                    distance = duration * random.uniform(25, 35) / 60  # км/ч
                    power = random.randint(180, 280) * hrv_factor
                    tss = random.randint(60, 120) / hrv_factor  # Обратная зависимость
                    calories = duration * random.uniform(8, 12)
                else:
                    distance = duration * random.uniform(10, 15) / 60  # км/ч  
                    power = None
                    tss = random.randint(50, 100) / hrv_factor
                    calories = duration * random.uniform(10, 14)
                    
            elif day_of_week in [0, 2]:  # Понедельник, среда - базовые тренировки
                sport = "cycling" if random.random() > 0.4 else "running" 
                duration = random.randint(60, 120)
                
                if sport == "cycling":
                    distance = duration * random.uniform(20, 30) / 60
                    power = random.randint(150, 220)
                    tss = random.randint(40, 80)
                    calories = duration * random.uniform(6, 10)
                else:
                    distance = duration * random.uniform(8, 12) / 60
                    power = None
                    tss = random.randint(30, 70)
                    calories = duration * random.uniform(8, 12)
                    
            elif day_of_week == 6:  # Воскресенье - длинная тренировка
                sport = "cycling" if random.random() > 0.2 else "running"
                duration = random.randint(90, 180)
                
                if sport == "cycling":
                    distance = duration * random.uniform(25, 32) / 60
                    power = random.randint(160, 240)
                    tss = random.randint(80, 150)
                    calories = duration * random.uniform(7, 11)
                else:
                    distance = duration * random.uniform(9, 13) / 60
                    power = None
                    tss = random.randint(60, 120)
                    calories = duration * random.uniform(9, 13)
            else:
                continue  # Отдых
            
            # Добавляем влияние предыдущих тренировок на текущий TSS
            # (накопленная усталость снижает способность выполнять высокий TSS)
            
            activity = {
                'activity_id': str(uuid.uuid4()),
                'date': date.strftime('%Y-%m-%d'),
                'sport': sport,
                'duration_minutes': round(duration),
                'distance_km': round(distance, 2) if distance else None,
                'avg_hr': random.randint(135, 175),
                'max_hr': random.randint(175, 195),
                'avg_power': round(power) if power else None,
                'max_power': round(power * 1.2) if power else None,
                'elevation_gain': random.randint(50, 800) if sport == "cycling" else random.randint(20, 200),
                'calories': round(calories),
                'tss': round(tss, 1)
            }
            
            activities.append(activity)
    
    print(f"📝 Сгенерировано {len(activities)} тренировок")
    
    # Сохраняем в базу данных
    if activities:
        print("\n💾 Сохранение в базу данных...")
        sync_result = db.sync_activities(activities)
        print(f"   Новых: {sync_result['new']}")
        print(f"   Обновлено: {sync_result['updated']}")
        print(f"   Пропущено: {sync_result['skipped']}")
        
        # Проверяем результат
        activities_df = db.get_activities(60)
        print(f"\n✅ Всего активностей в БД: {len(activities_df)}")
        
        # Анализируем корреляцию
        print("\n📊 ПРЕДВАРИТЕЛЬНЫЙ АНАЛИЗ КОРРЕЛЯЦИИ:")
        
        if not activities_df.empty:
            # Агрегируем по дням как в приложении
            daily_training = activities_df.groupby('date').agg({
                'tss': 'sum',
                'duration_minutes': 'sum'
            }).reset_index()
            
            # Объединяем с HRV
            hrv_for_corr = hrv_df.copy()
            hrv_for_corr['date'] = hrv_for_corr['date'].dt.date
            daily_training['date'] = pd.to_datetime(daily_training['date']).dt.date
            
            combined = pd.merge(hrv_for_corr, daily_training, on='date', how='left')
            combined['tss'] = combined['tss'].fillna(0)
            
            # Рассчитываем корреляцию
            correlation = combined[['rmssd', 'tss']].corr().iloc[0, 1]
            
            print(f"   Записей для анализа: {len(combined)}")
            print(f"   Дней с тренировками: {len(combined[combined['tss'] > 0])}")
            print(f"   Корреляция HRV-TSS: {correlation:.3f}")
            
            if abs(correlation) > 0.3:
                if correlation < 0:
                    print("   ✅ Хорошая обратная корреляция (высокий TSS → низкий HRV)")
                else:
                    print("   ⚠️ Прямая корреляция (необычно)")
            else:
                print("   ℹ️ Слабая корреляция - возможно нужно больше данных или улучшить модель")
            
            # Показываем распределение
            print(f"\n📈 Распределение TSS:")
            print(f"   Среднее: {combined['tss'].mean():.1f}")
            print(f"   Медиана: {combined['tss'].median():.1f}") 
            print(f"   Макс: {combined['tss'].max():.1f}")
            print(f"   Дней без тренировок: {len(combined[combined['tss'] == 0])}")
            
            print(f"\n💓 Распределение RMSSD:")
            print(f"   Среднее: {combined['rmssd'].mean():.1f}")
            print(f"   Медиана: {combined['rmssd'].median():.1f}")
            print(f"   Диапазон: {combined['rmssd'].min():.1f} - {combined['rmssd'].max():.1f}")
    
    print("\n" + "=" * 80)
    print("✅ ДАННЫЕ ДОБАВЛЕНЫ")
    print("=" * 80)
    print("Теперь в разделе 'Анализ HRV' должна быть лучше видна корреляция!")

if __name__ == "__main__":
    add_realistic_training_data()