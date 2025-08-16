#!/usr/bin/env python3
"""
Тестовый скрипт для проверки корректности выборки и отображения HRV данных
"""

import sys
import os
sys.path.append('..')

import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from data.database import Database
from tabulate import tabulate

def check_hrv_data():
    """Проверка HRV данных в базе"""
    print("=" * 80)
    print("ПРОВЕРКА HRV ДАННЫХ В БАЗЕ")
    print("=" * 80)
    
    # Подключаемся к базе данных
    db = Database()
    
    # 1. Проверяем структуру таблицы
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    print("\n📋 Структура таблицы hrv_data:")
    cursor.execute("PRAGMA table_info(hrv_data)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # 2. Проверяем общее количество записей
    cursor.execute("SELECT COUNT(*) FROM hrv_data")
    total_records = cursor.fetchone()[0]
    print(f"\n📊 Всего записей в БД: {total_records}")
    
    # 3. Проверяем данные за последние 30 дней
    print("\n📅 Данные за последние 30 дней:")
    hrv_df = db.get_hrv_data(30)
    
    if hrv_df.empty:
        print("  ⚠️ Нет данных за последние 30 дней")
    else:
        print(f"  ✅ Найдено записей: {len(hrv_df)}")
        
        # Проверяем типы данных
        print("\n📝 Типы данных в DataFrame:")
        print(hrv_df.dtypes)
        
        # Проверяем наличие NaN значений
        print("\n🔍 Проверка на пропущенные значения:")
        nan_counts = hrv_df.isnull().sum()
        for col, count in nan_counts.items():
            if count > 0:
                print(f"  - {col}: {count} NaN значений ({count/len(hrv_df)*100:.1f}%)")
        
        # Выводим первые и последние записи
        print("\n📋 Первые 5 записей:")
        print(hrv_df.head().to_string())
        
        print("\n📋 Последние 5 записей:")
        print(hrv_df.tail().to_string())
        
        # Статистика по данным
        print("\n📈 Статистика по RMSSD:")
        if 'rmssd' in hrv_df.columns:
            rmssd_stats = hrv_df['rmssd'].describe()
            print(rmssd_stats)
            
            # Проверяем аномальные значения
            print("\n⚠️ Проверка на аномальные значения RMSSD:")
            abnormal = hrv_df[(hrv_df['rmssd'] < 10) | (hrv_df['rmssd'] > 200)]
            if not abnormal.empty:
                print(f"  Найдено {len(abnormal)} аномальных значений:")
                print(abnormal[['date', 'rmssd']].to_string())
            else:
                print("  ✅ Аномальных значений не найдено")
    
    # 4. Проверяем проблемы с выборкой по периодам
    print("\n🔄 Проверка выборки по разным периодам:")
    periods = [7, 14, 30, 60, 90]
    for period in periods:
        df = db.get_hrv_data(period)
        cutoff_date = datetime.now() - timedelta(days=period)
        
        if not df.empty:
            actual_start = pd.to_datetime(df['date'].min())
            expected_start = cutoff_date
            
            print(f"\n  Период {period} дней:")
            print(f"    - Записей: {len(df)}")
            print(f"    - Ожидаемая начальная дата: {expected_start.date()}")
            print(f"    - Фактическая начальная дата: {actual_start.date()}")
            print(f"    - Последняя дата: {pd.to_datetime(df['date'].max()).date()}")
            
            # Проверяем корректность фильтрации
            if actual_start.date() < expected_start.date():
                print(f"    ⚠️ ОШИБКА: Выбраны данные старше {period} дней!")
    
    # 5. Проверяем SQL запрос напрямую
    print("\n🔍 Прямой SQL запрос за последние 7 дней:")
    cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    query = f"SELECT date, rmssd, stress_score, recovery_score FROM hrv_data WHERE date >= '{cutoff}' ORDER BY date DESC"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if rows:
        print(f"  Найдено {len(rows)} записей")
        print("\n  Таблица данных:")
        headers = ['Дата', 'RMSSD', 'Стресс', 'Восстановление']
        print(tabulate(rows[:10], headers=headers, tablefmt='grid'))
    else:
        print("  ⚠️ Данные не найдены")
    
    # 6. Проверяем корректность tail() операции
    print("\n🔄 Проверка операции tail() для фильтрации:")
    df_all = db.get_hrv_data(90)
    if not df_all.empty:
        for period in [7, 14, 30]:
            df_tail = df_all.tail(period)
            print(f"\n  tail({period}):")
            print(f"    - Всего записей: {len(df_tail)}")
            if not df_tail.empty:
                print(f"    - Диапазон дат: {df_tail['date'].min()} - {df_tail['date'].max()}")
                
                # Проверяем, что это действительно последние записи
                last_n_dates = df_all.nlargest(period, 'date')['date'].values
                tail_dates = df_tail['date'].values
                
                if not all(d in last_n_dates for d in tail_dates):
                    print(f"    ⚠️ ОШИБКА: tail() не возвращает последние записи по дате!")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("АНАЛИЗ ЗАВЕРШЕН")
    print("=" * 80)
    
    # Выводим рекомендации
    print("\n💡 ОБНАРУЖЕННЫЕ ПРОБЛЕМЫ И РЕКОМЕНДАЦИИ:")
    print("""
    1. Метод get_hrv_data() использует ORDER BY date DESC, но потом tail() берет последние строки,
       что может привести к выбору самых старых данных вместо самых новых.
       
    2. В app.py используется hrv_df.tail(period_days) после получения данных за 30 дней,
       что неправильно фильтрует данные по периоду.
       
    3. Рекомендуется:
       - Изменить ORDER BY date DESC на ORDER BY date ASC в get_hrv_data()
       - Или использовать head() вместо tail() при фильтрации
       - Или правильно фильтровать данные по дате в SQL запросе
    """)

if __name__ == "__main__":
    check_hrv_data()