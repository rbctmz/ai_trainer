import sqlite3
import pandas as pd
import os

# Определяем путь к базе данных относительно этого скрипта
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_trainer.db')

def check_hrv_data_in_db():
    """Подключается к БД и выводит содержимое таблицы hrv_data."""
    print(f"🔍 Подключение к базе данных: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Ошибка: Файл базы данных не найден по пути {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        print("✅ Соединение с БД установлено.")
        
        query = "SELECT * FROM hrv_data ORDER BY date DESC"
        print(f"Executing query: {query}")
        
        df = pd.read_sql_query(query, conn)
        
        conn.close()
        
        if df.empty:
            print("⚠️ Таблица 'hrv_data' пуста.")
        else:
            print(f"✅ Найдено {len(df)} записей в таблице 'hrv_data':")
            print(df.to_string())
            
            # Дополнительная проверка на наличие не-NULL значений
            print("\n📊 Анализ колонок:")
            for col in ['rmssd', 'stress_score']:
                if col in df.columns:
                    non_null_count = df[col].notna().sum()
                    if non_null_count > 0:
                        print(f"  - Колонка '{col}' содержит {non_null_count} непустых значений. ✅")
                    else:
                        print(f"  - Колонка '{col}' ПОЛНОСТЬЮ ПУСТАЯ (NULL). ❌")
                else:
                    print(f"  - Колонка '{col}' не найдена в таблице. ❌")

    except Exception as e:
        print(f"❌ Произошла ошибка при чтении из БД: {e}")

if __name__ == "__main__":
    check_hrv_data_in_db()
