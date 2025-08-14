import sqlite3
import pandas as pd
from datetime import datetime
from config.settings import Settings

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or Settings.DATABASE_PATH
        self.init_tables()
    
    @staticmethod
    def clean_value(value):
        """Преобразование значения в тип, поддерживаемый SQLite"""
        import pandas as pd
        import numpy as np
        from datetime import date, datetime
        
        if pd.isna(value) or value is None:
            return None
        elif isinstance(value, (date, datetime)):
            # Преобразуем дату в строку формата YYYY-MM-DD
            return value.strftime('%Y-%m-%d') if hasattr(value, 'strftime') else str(value)
        elif isinstance(value, (np.integer, np.int64, np.int32)):
            return int(value)
        elif isinstance(value, (np.floating, np.float64, np.float32)):
            return float(value)
        elif isinstance(value, (int, float, str)):
            return value
        else:
            return str(value)
    
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
            # Обрабатываем смешанные форматы дат
            df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')
        
        return df
    
    def get_hrv_data(self, days=30):
        """Получение HRV данных за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        
        cutoff_date = (datetime.now() - pd.Timedelta(days=days)).date()
        
        # Изменяем сортировку на ASC, чтобы последние записи были в конце DataFrame
        # Это позволит корректно использовать tail() для получения последних дней
        query = f'''
            SELECT * FROM hrv_data 
            WHERE date >= '{cutoff_date}'
            ORDER BY date ASC
        '''
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Преобразование даты в datetime если она есть  
        if not df.empty and 'date' in df.columns:
            # Обрабатываем смешанные форматы дат
            df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')
        
        # Сортируем по убыванию после преобразования для отображения в UI
        # (самые новые данные первыми)
        if not df.empty:
            df = df.sort_values('date', ascending=False).reset_index(drop=True)
        
        return df
    
    def save_hrv_data(self, hrv_data):
        """Сохранение HRV данных в БД"""
        conn = sqlite3.connect(self.db_path)
        
        for date_str, data in hrv_data.items():
            conn.execute('''
                INSERT OR REPLACE INTO hrv_data 
                (date, rmssd, stress_score, recovery_score)
                VALUES (?, ?, ?, ?)
            ''', (
                self.clean_value(date_str), 
                self.clean_value(data.get('rmssd')), 
                self.clean_value(data.get('stress_score')), 
                self.clean_value(data.get('recovery_score'))
            ))
        
        conn.commit()
        conn.close()
    
    def save_activities(self, activities):
        """Сохранение списка активностей в БД"""
        conn = sqlite3.connect(self.db_path)
        
        for activity in activities:
            conn.execute('''
                INSERT OR REPLACE INTO activities 
                (activity_id, date, sport, duration_minutes, distance_km, avg_hr, max_hr, 
                 avg_power, max_power, elevation_gain, calories, tss)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.clean_value(activity.get('activity_id')),
                self.clean_value(activity.get('date')),
                self.clean_value(activity.get('sport')),
                self.clean_value(activity.get('duration_minutes')),
                self.clean_value(activity.get('distance_km')),
                self.clean_value(activity.get('avg_hr')),
                self.clean_value(activity.get('max_hr')),
                self.clean_value(activity.get('avg_power')),
                self.clean_value(activity.get('max_power')),
                self.clean_value(activity.get('elevation_gain')),
                self.clean_value(activity.get('calories')),
                self.clean_value(activity.get('tss'))
            ))
        
        conn.commit()
        conn.close()
    
    def clean_test_data(self):
        """Очистка всех тестовых данных из базы"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Удаляем тестовые активности
        test_patterns = ['test_%', 'date_test_%', 'test_df_%']
        total_deleted = 0
        
        for pattern in test_patterns:
            cursor.execute('DELETE FROM activities WHERE activity_id LIKE ?', (pattern,))
            total_deleted += cursor.rowcount
        
        # Удаляем дубликаты активностей
        cursor.execute('''
            DELETE FROM activities 
            WHERE rowid NOT IN (
                SELECT MAX(rowid) 
                FROM activities 
                GROUP BY activity_id
            )
        ''')
        duplicates_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return {
            'test_activities_deleted': total_deleted,
            'duplicates_deleted': duplicates_deleted
        }
    
    def clear_all_data(self):
        """Полная очистка всех данных (ОСТОРОЖНО!)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM activities')
        activities_deleted = cursor.rowcount
        
        cursor.execute('DELETE FROM hrv_data')
        hrv_deleted = cursor.rowcount
        
        cursor.execute('DELETE FROM user_settings')
        settings_deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return {
            'activities_deleted': activities_deleted,
            'hrv_deleted': hrv_deleted,
            'settings_deleted': settings_deleted
        }
    
    def sync_activities(self, activities):
        """Умная синхронизация активностей без дублей"""
        if not activities:
            return {'new': 0, 'updated': 0, 'skipped': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем существующие activity_id
        cursor.execute('SELECT activity_id FROM activities')
        existing_ids = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        skipped_count = 0
        
        for activity in activities:
            activity_id = self.clean_value(activity.get('activity_id'))
            
            if not activity_id:  # Пропускаем активности без ID
                skipped_count += 1
                continue
            
            # Проверяем, существует ли уже такая активность
            if activity_id in existing_ids:
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE activities SET
                    date=?, sport=?, duration_minutes=?, distance_km=?, 
                    avg_hr=?, max_hr=?, avg_power=?, max_power=?, 
                    elevation_gain=?, calories=?, tss=?
                    WHERE activity_id=?
                ''', (
                    self.clean_value(activity.get('date')),
                    self.clean_value(activity.get('sport')),
                    self.clean_value(activity.get('duration_minutes')),
                    self.clean_value(activity.get('distance_km')),
                    self.clean_value(activity.get('avg_hr')),
                    self.clean_value(activity.get('max_hr')),
                    self.clean_value(activity.get('avg_power')),
                    self.clean_value(activity.get('max_power')),
                    self.clean_value(activity.get('elevation_gain')),
                    self.clean_value(activity.get('calories')),
                    self.clean_value(activity.get('tss')),
                    activity_id
                ))
                updated_count += 1
            else:
                # Вставляем новую запись
                cursor.execute('''
                    INSERT INTO activities 
                    (activity_id, date, sport, duration_minutes, distance_km, avg_hr, max_hr, 
                     avg_power, max_power, elevation_gain, calories, tss)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    activity_id,
                    self.clean_value(activity.get('date')),
                    self.clean_value(activity.get('sport')),
                    self.clean_value(activity.get('duration_minutes')),
                    self.clean_value(activity.get('distance_km')),
                    self.clean_value(activity.get('avg_hr')),
                    self.clean_value(activity.get('max_hr')),
                    self.clean_value(activity.get('avg_power')),
                    self.clean_value(activity.get('max_power')),
                    self.clean_value(activity.get('elevation_gain')),
                    self.clean_value(activity.get('calories')),
                    self.clean_value(activity.get('tss'))
                ))
                existing_ids.add(activity_id)  # Добавляем в кэш
                new_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            'new': new_count,
            'updated': updated_count, 
            'skipped': skipped_count
        }
    
    def sync_hrv_data(self, hrv_data):
        """Умная синхронизация HRV данных без дублей"""
        if not hrv_data:
            return {'new': 0, 'updated': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем существующие даты
        cursor.execute('SELECT date FROM hrv_data')
        existing_dates = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        
        for date_str, data in hrv_data.items():
            clean_date = self.clean_value(date_str)
            
            if clean_date in existing_dates:
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE hrv_data SET rmssd=?, stress_score=?, recovery_score=?
                    WHERE date=?
                ''', (
                    self.clean_value(data.get('rmssd')),
                    self.clean_value(data.get('stress_score')),
                    self.clean_value(data.get('recovery_score')),
                    clean_date
                ))
                updated_count += 1
            else:
                # Вставляем новую запись
                cursor.execute('''
                    INSERT INTO hrv_data (date, rmssd, stress_score, recovery_score)
                    VALUES (?, ?, ?, ?)
                ''', (
                    clean_date,
                    self.clean_value(data.get('rmssd')),
                    self.clean_value(data.get('stress_score')),
                    self.clean_value(data.get('recovery_score'))
                ))
                existing_dates.add(clean_date)
                new_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            'new': new_count,
            'updated': updated_count
        }