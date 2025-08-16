#!/usr/bin/env python3
"""
Скрипт для добавления тестовых HRV данных и проверки проблем с отображением
"""

import sys
import os
sys.path.append('..')

import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random
from data.database import Database

def add_test_hrv_data():
    """Добавляет тестовые HRV данные за последние 45 дней"""
    print("=" * 80)
    print("ДОБАВЛЕНИЕ ТЕСТОВЫХ HRV ДАННЫХ")
    print("=" * 80)
    
    db = Database()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # Генерируем данные за последние 45 дней
    end_date = datetime.now()
    start_date = end_date - timedelta(days=45)
    
    hrv_data = {}
    current_date = start_date
    
    print("\n📝 Генерация тестовых данных...")
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Генерируем реалистичные значения
        base_rmssd = 45 + random.gauss(0, 10)  # Среднее 45 с вариацией
        
        # Добавляем недельный цикл (ниже HRV в начале недели)
        day_of_week = current_date.weekday()
        if day_of_week == 0:  # Понедельник
            base_rmssd -= 5
        elif day_of_week == 6:  # Воскресенье  
            base_rmssd += 5
            
        # Ограничиваем значения
        rmssd = max(20, min(80, base_rmssd))
        
        # Стресс обратно пропорционален HRV
        stress = max(20, min(80, 100 - rmssd + random.gauss(0, 5)))
        
        # Восстановление прямо пропорционально HRV
        recovery = max(30, min(95, rmssd + random.gauss(0, 10)))
        
        hrv_data[date_str] = {
            'rmssd': round(rmssd, 1),
            'stress_score': round(stress, 0),
            'recovery_score': round(recovery, 0)
        }
        
        current_date += timedelta(days=1)
    
    # Сохраняем в базу
    print(f"\n💾 Сохранение {len(hrv_data)} записей в базу...")
    sync_result = db.sync_hrv_data(hrv_data)
    print(f"   Новых: {sync_result['new']}, Обновлено: {sync_result['updated']}")
    
    # Проверяем что сохранилось
    print("\n✅ Проверка сохраненных данных:")
    cursor.execute("SELECT COUNT(*) FROM hrv_data")
    total = cursor.fetchone()[0]
    print(f"   Всего записей в БД: {total}")
    
    # Проверяем проблему с выборкой
    print("\n🔍 ПРОВЕРКА ПРОБЛЕМЫ С ВЫБОРКОЙ:")
    print("-" * 40)
    
    # 1. Получаем данные методом get_hrv_data()
    print("\n1. Метод get_hrv_data(30):")
    df_30 = db.get_hrv_data(30)
    print(f"   Получено записей: {len(df_30)}")
    if not df_30.empty:
        print(f"   Диапазон дат: {df_30['date'].min()} - {df_30['date'].max()}")
        print(f"   Порядок сортировки: {'DESC' if df_30['date'].iloc[0] > df_30['date'].iloc[-1] else 'ASC'}")
    
    # 2. Проверяем что происходит с tail()
    print("\n2. После df.tail(7):")
    df_tail_7 = df_30.tail(7)
    if not df_tail_7.empty:
        print(f"   Получено записей: {len(df_tail_7)}")
        print(f"   Диапазон дат: {df_tail_7['date'].min()} - {df_tail_7['date'].max()}")
        print(f"   Это {'СТАРЫЕ' if df_tail_7['date'].max() < df_30['date'].max() else 'НОВЫЕ'} данные!")
        
        # Показываем даты
        print("\n   Даты в выборке tail(7):")
        for date in df_tail_7['date'].sort_values(ascending=False):
            print(f"     - {date.date()}")
    
    # 3. Проверяем head() вместо tail()
    print("\n3. С использованием head(7):")
    df_head_7 = df_30.head(7)
    if not df_head_7.empty:
        print(f"   Получено записей: {len(df_head_7)}")
        print(f"   Диапазон дат: {df_head_7['date'].min()} - {df_head_7['date'].max()}")
        print(f"   Это {'СТАРЫЕ' if df_head_7['date'].max() < df_30['date'].max() else 'НОВЫЕ'} данные!")
        
        print("\n   Даты в выборке head(7):")
        for date in df_head_7['date'].sort_values(ascending=False):
            print(f"     - {date.date()}")
    
    # 4. Правильный подход - фильтрация по дате
    print("\n4. ПРАВИЛЬНЫЙ ПОДХОД - фильтрация по дате:")
    cutoff_date = datetime.now() - timedelta(days=7)
    df_correct = df_30[pd.to_datetime(df_30['date']) >= cutoff_date]
    if not df_correct.empty:
        print(f"   Получено записей: {len(df_correct)}")
        print(f"   Диапазон дат: {df_correct['date'].min()} - {df_correct['date'].max()}")
        
        print("\n   Даты в правильной выборке:")
        for date in df_correct['date'].sort_values(ascending=False):
            print(f"     - {date.date()}")
    
    # Выводим таблицу для наглядности
    print("\n📊 СРАВНИТЕЛЬНАЯ ТАБЛИЦА:")
    print("-" * 60)
    print(f"{'Метод':<20} {'Записей':<10} {'Мин дата':<12} {'Макс дата':<12}")
    print("-" * 60)
    
    if not df_30.empty:
        print(f"{'get_hrv_data(30)':<20} {len(df_30):<10} {df_30['date'].min().date()!s:<12} {df_30['date'].max().date()!s:<12}")
    if not df_tail_7.empty:
        print(f"{'+ tail(7)':<20} {len(df_tail_7):<10} {df_tail_7['date'].min().date()!s:<12} {df_tail_7['date'].max().date()!s:<12}")
    if not df_head_7.empty:
        print(f"{'+ head(7)':<20} {len(df_head_7):<10} {df_head_7['date'].min().date()!s:<12} {df_head_7['date'].max().date()!s:<12}")
    if not df_correct.empty:
        print(f"{'Правильная фильтр.':<20} {len(df_correct):<10} {df_correct['date'].min().date()!s:<12} {df_correct['date'].max().date()!s:<12}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("⚠️  ВЫВОД: Проблема в том, что get_hrv_data() сортирует по убыванию (DESC),")
    print("    а tail() берет последние строки DataFrame, которые являются самыми старыми!")
    print("    Нужно либо использовать head(), либо изменить сортировку на ASC.")
    print("=" * 80)

if __name__ == "__main__":
    add_test_hrv_data()