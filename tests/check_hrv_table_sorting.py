#!/usr/bin/env python3
"""
Проверка типов данных и сортировки в таблице HRV
"""

import sys
sys.path.append('..')

import sqlite3
from data.database import Database

def check_data_types_and_sorting():
    """Проверка типов данных и проблем с сортировкой"""
    print("=" * 80)
    print("ПРОВЕРКА ТИПОВ ДАННЫХ И СОРТИРОВКИ HRV")
    print("=" * 80)
    
    db = Database()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    
    # 1. Проверяем структуру таблицы в БД
    print("\n📋 СТРУКТУРА ТАБЛИЦЫ В БАЗЕ ДАННЫХ:")
    cursor.execute("PRAGMA table_info(hrv_data)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  - {col[1]:<20} Тип: {col[2]:<15} NotNull: {col[3]}  Default: {col[4]}")
    
    # 2. Получаем сырые данные из БД
    print("\n📊 СЫРЫЕ ДАННЫЕ ИЗ БД (первые 10 записей):")
    cursor.execute("SELECT date, rmssd FROM hrv_data ORDER BY date DESC LIMIT 10")
    rows = cursor.fetchall()
    for row in rows:
        print(f"  {row[0]} | RMSSD: {row[1]}")
    
    # 3. Проверяем типы данных в DataFrame после загрузки
    print("\n🔍 ТИПЫ ДАННЫХ В DATAFRAME:")
    hrv_df = db.get_hrv_data(30)
    
    if not hrv_df.empty:
        print(f"  Всего записей: {len(hrv_df)}")
        print("\n  Типы колонок:")
        for col in hrv_df.columns:
            print(f"    - {col:<20} {hrv_df[col].dtype}")
        
        # Проверяем конкретно тип даты
        print("\n  📅 Анализ колонки 'date':")
        print(f"    Тип: {type(hrv_df['date'].iloc[0])}")
        print(f"    Первое значение: {hrv_df['date'].iloc[0]}")
        print(f"    Последнее значение: {hrv_df['date'].iloc[-1]}")
        
        # 4. Проверяем сортировку
        print("\n📈 ПРОВЕРКА СОРТИРОВКИ:")
        is_sorted_desc = all(hrv_df['date'].iloc[i] >= hrv_df['date'].iloc[i+1] 
                             for i in range(len(hrv_df)-1))
        is_sorted_asc = all(hrv_df['date'].iloc[i] <= hrv_df['date'].iloc[i+1] 
                            for i in range(len(hrv_df)-1))
        
        if is_sorted_desc:
            print("  ✅ DataFrame отсортирован по убыванию (новые первыми)")
        elif is_sorted_asc:
            print("  ⚠️ DataFrame отсортирован по возрастанию (старые первыми)")
        else:
            print("  ❌ DataFrame НЕ отсортирован!")
        
        # 5. Имитируем код из app.py для таблицы
        print("\n📋 ИМИТАЦИЯ ОТОБРАЖЕНИЯ ТАБЛИЦЫ (как в app.py):")
        
        # Копируем логику из app.py
        display_df = hrv_df.copy()
        print("\n  До форматирования:")
        print(f"    Тип date: {display_df['date'].dtype}")
        print(f"    Первые 3 даты: {display_df['date'].head(3).tolist()}")
        
        # Форматирование даты как в app.py
        display_df['date'] = display_df['date'].dt.strftime('%d.%m.%Y')
        print("\n  После форматирования в строку:")
        print(f"    Тип date: {display_df['date'].dtype}")
        print(f"    Первые 3 даты: {display_df['date'].head(3).tolist()}")
        
        # Переименование колонок
        display_columns = {
            'date': 'Дата',
            'rmssd': 'RMSSD (мс)',
            'stress_score': 'Стресс-индекс',
            'recovery_score': 'Восстановление (%)'
        }
        
        columns_to_show = [col for col in display_columns.keys() if col in display_df.columns]
        table_df = display_df[columns_to_show].rename(columns=display_columns)
        
        # ЗДЕСЬ ПРОБЛЕМА! Сортировка по строковой дате
        print("\n  ⚠️ ПРОБЛЕМА: Сортировка по колонке 'Дата' (строка):")
        sorted_df = table_df.sort_values('Дата', ascending=False)
        
        print("\n  Первые 10 записей после сортировки строковых дат:")
        for idx, row in sorted_df.head(10).iterrows():
            print(f"    {row['Дата']} | RMSSD: {row['RMSSD (мс)']}")
        
        # Показываем правильный подход
        print("\n✅ ПРАВИЛЬНЫЙ ПОДХОД:")
        print("  1. Сортировать DataFrame ДО форматирования даты в строку")
        print("  2. Или использовать pd.to_datetime для обратного преобразования при сортировке")
        
        # Правильная сортировка
        correct_df = hrv_df.copy()
        correct_df = correct_df.sort_values('date', ascending=False)  # Сортируем datetime
        correct_df['date'] = correct_df['date'].dt.strftime('%d.%m.%Y')  # Потом форматируем
        
        print("\n  Правильно отсортированные данные:")
        for idx, row in correct_df.head(10).iterrows():
            print(f"    {row['date']} | RMSSD: {row['rmssd']:.1f}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("💡 ВЫВОДЫ:")
    print("=" * 80)
    print("""
    1. В БД поле date имеет тип DATE (текстовый в SQLite)
    2. После загрузки в DataFrame преобразуется в pandas datetime64
    3. ПРОБЛЕМА: В app.py дата форматируется в строку '%d.%m.%Y' перед сортировкой
    4. Строковая сортировка дат работает некорректно (01.08 < 10.07 по алфавиту)
    5. РЕШЕНИЕ: Сортировать до форматирования или не сортировать строковые даты
    """)

if __name__ == "__main__":
    check_data_types_and_sorting()