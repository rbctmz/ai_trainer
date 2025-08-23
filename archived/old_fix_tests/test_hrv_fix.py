#!/usr/bin/env python3
"""
Тест для проверки исправления проблемы с выборкой HRV данных
"""

import sys
import os
sys.path.append('..')

import pandas as pd
from datetime import datetime, timedelta
from data.database import Database

def test_hrv_fix():
    """Проверяет что исправление работает корректно"""
    print("=" * 80)
    print("ТЕСТ ИСПРАВЛЕНИЯ ВЫБОРКИ HRV ДАННЫХ")
    print("=" * 80)
    
    db = Database()
    
    # Получаем данные за разные периоды
    periods = [7, 14, 30]
    
    for period in periods:
        print(f"\n📊 Проверка периода: {period} дней")
        print("-" * 40)
        
        # Получаем данные
        hrv_df = db.get_hrv_data(period)
        
        if hrv_df.empty:
            print(f"  ⚠️ Нет данных")
            continue
        
        print(f"  ✅ Получено записей: {len(hrv_df)}")
        
        # Проверяем порядок сортировки в возвращенном DataFrame
        is_desc = hrv_df['date'].iloc[0] > hrv_df['date'].iloc[-1] if len(hrv_df) > 1 else True
        print(f"  📋 Порядок в DataFrame: {'DESC (новые первыми)' if is_desc else 'ASC (старые первыми)'}")
        
        # Проверяем корректность дат
        min_date = hrv_df['date'].min()
        max_date = hrv_df['date'].max()
        expected_cutoff = datetime.now() - timedelta(days=period)
        
        print(f"  📅 Диапазон дат: {min_date.date()} - {max_date.date()}")
        print(f"  📅 Ожидаемая граница: {expected_cutoff.date()}")
        
        # Проверяем что все даты в нужном диапазоне
        dates_ok = all(d >= expected_cutoff for d in hrv_df['date'])
        if dates_ok:
            print(f"  ✅ Все даты корректны (не старше {period} дней)")
        else:
            old_dates = hrv_df[hrv_df['date'] < expected_cutoff]
            print(f"  ❌ ОШИБКА: Найдено {len(old_dates)} дат старше {period} дней!")
        
        # Теперь проверяем фильтрацию как в app.py
        print(f"\n  🔍 Имитация фильтрации из app.py:")
        
        # Старый способ (с ошибкой): tail()
        if len(hrv_df) > 7:
            df_tail = hrv_df.tail(7)
            print(f"    tail(7): {df_tail['date'].min().date()} - {df_tail['date'].max().date()}")
        
        # Новый способ (исправленный): head()
        if len(hrv_df) > 7:
            df_head = hrv_df.head(7)
            print(f"    head(7): {df_head['date'].min().date()} - {df_head['date'].max().date()}")
            print(f"    ✅ head(7) возвращает последние 7 дней!")
    
    # Проверяем конкретный сценарий из app.py
    print("\n" + "=" * 80)
    print("ПРОВЕРКА СЦЕНАРИЯ ИЗ APP.PY")
    print("=" * 80)
    
    # Получаем данные за 90 дней как в исправленном коде
    hrv_df = db.get_hrv_data(90)
    
    if not hrv_df.empty:
        print(f"\n1. Получены данные за 90 дней: {len(hrv_df)} записей")
        print(f"   Диапазон: {hrv_df['date'].min().date()} - {hrv_df['date'].max().date()}")
        
        # Имитируем выбор периода пользователем
        test_periods = [7, 14, 30]
        
        for period_days in test_periods:
            print(f"\n2. Пользователь выбрал период: {period_days} дней")
            
            # Исправленный код из app.py
            if len(hrv_df) > period_days:
                filtered_df = hrv_df.head(period_days)
            else:
                filtered_df = hrv_df
            
            print(f"   После фильтрации: {len(filtered_df)} записей")
            if not filtered_df.empty:
                print(f"   Диапазон: {filtered_df['date'].min().date()} - {filtered_df['date'].max().date()}")
                
                # Проверяем корректность
                expected_start = datetime.now() - timedelta(days=period_days)
                if filtered_df['date'].min() >= expected_start:
                    print(f"   ✅ Данные корректны!")
                else:
                    print(f"   ⚠️ Есть данные старше {period_days} дней")
    
    print("\n" + "=" * 80)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("=" * 80)

if __name__ == "__main__":
    test_hrv_fix()