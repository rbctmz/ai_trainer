import sqlite3
import pandas as pd
from datetime import datetime
from config.settings import Settings

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or Settings.DATABASE_PATH
        self.init_tables()
    
    def init_tables(self):
        """Создание таблиц БД"""
        conn = sqlite3.connect(self.db_path)
        
        # Таблица активностей
        conn.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT PRIMARY KEY,
                date DATE,
                sport TEXT,
                duration_minutes REAL,
                distance_km REAL,
                avg_hr INTEGER,
                max_hr INTEGER,
                avg_power INTEGER,
                max_power INTEGER,
                elevation_gain REAL,
                calories INTEGER,
                tss REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица HRV данных
        conn.execute('''
            CREATE TABLE IF NOT EXISTS hrv_data (
                date DATE PRIMARY KEY,
                rmssd REAL,
                stress_score REAL,
                recovery_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица настроек пользователя
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_activities(self, activities_df):
        """Сохранение активностей"""
        if activities_df.empty:
            return
            
        conn = sqlite3.connect(self.db_path)
        
        # Преобразуем дату в строку для корректного сохранения в SQLite
        df_to_save = activities_df.copy()
        if 'date' in df_to_save.columns:
            df_to_save['date'] = pd.to_datetime(df_to_save['date']).dt.strftime('%Y-%m-%d')
        
        df_to_save.to_sql('activities', conn, if_exists='replace', index=False)
        conn.close()
    
    def get_activities(self, days=30):
        """Получение активностей из БД"""
        conn = sqlite3.connect(self.db_path)
        
        # Если данные есть, получаем их с фильтрацией
        from datetime import datetime, timedelta
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = f'''
            SELECT * FROM activities 
            WHERE date >= '{cutoff_date}'
            ORDER BY date DESC
        '''
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Преобразование даты в datetime если она есть
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        return df