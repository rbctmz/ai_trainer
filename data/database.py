import json
import sqlite3
import pandas as pd
from datetime import datetime
from config.settings import Settings

class Database:
    _TRAINING_STATUS_COLUMN_ORDER = [
        'vo2_max',
        'fitness_age',
        'training_load_7d',
        'training_status',
        'training_readiness',
        'recovery_time_hours',
        'load_ratio',
        'training_feedback_code',
        'training_feedback',
        'training_load_chronic',
        'acwr_status',
        'acwr_status_feedback',
        'acwr_percent',
        'training_since_date',
        'fitness_trend',
        'fitness_trend_sport',
        'sport',
        'device_id',
        'last_primary_sync_date',
        'training_balance_feedback_code',
        'training_balance_feedback',
        'monthly_load_aerobic_low',
        'monthly_load_aerobic_low_target_min',
        'monthly_load_aerobic_low_target_max',
        'monthly_load_aerobic_high',
        'monthly_load_aerobic_high_target_min',
        'monthly_load_aerobic_high_target_max',
        'monthly_load_anaerobic',
        'monthly_load_anaerobic_target_min',
        'monthly_load_anaerobic_target_max'
    ]

    _TRAINING_STATUS_COLUMN_TYPES = {
        'vo2_max': 'REAL',
        'fitness_age': 'REAL',
        'training_load_7d': 'REAL',
        'training_status': 'TEXT',
        'training_readiness': 'REAL',
        'recovery_time_hours': 'REAL',
        'load_ratio': 'REAL',
        'training_feedback_code': 'TEXT',
        'training_feedback': 'TEXT',
        'training_load_chronic': 'REAL',
        'acwr_status': 'TEXT',
        'acwr_status_feedback': 'TEXT',
        'acwr_percent': 'REAL',
        'training_since_date': 'TEXT',
        'fitness_trend': 'INTEGER',
        'fitness_trend_sport': 'TEXT',
        'sport': 'TEXT',
        'device_id': 'TEXT',
        'last_primary_sync_date': 'TEXT',
        'training_balance_feedback_code': 'TEXT',
        'training_balance_feedback': 'TEXT',
        'monthly_load_aerobic_low': 'REAL',
        'monthly_load_aerobic_low_target_min': 'REAL',
        'monthly_load_aerobic_low_target_max': 'REAL',
        'monthly_load_aerobic_high': 'REAL',
        'monthly_load_aerobic_high_target_min': 'REAL',
        'monthly_load_aerobic_high_target_max': 'REAL',
        'monthly_load_anaerobic': 'REAL',
        'monthly_load_anaerobic_target_min': 'REAL',
        'monthly_load_anaerobic_target_max': 'REAL'
    }
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
        
        # Таблица данных сна
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sleep_data (
                date DATE PRIMARY KEY,
                total_sleep_minutes INTEGER,
                deep_sleep_minutes INTEGER,
                light_sleep_minutes INTEGER,
                rem_sleep_minutes INTEGER,
                awakenings_count INTEGER,
                sleep_score REAL,
                bedtime TEXT,
                wakeup_time TEXT,
                sleep_efficiency REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица ежедневных показателей здоровья
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_health (
                date DATE PRIMARY KEY,
                resting_hr INTEGER,
                steps INTEGER,
                floors_climbed INTEGER,
                calories_active INTEGER,
                calories_bmr INTEGER,
                distance_meters INTEGER,
                active_minutes INTEGER,
                intensity_minutes INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица статуса тренированности
        conn.execute('''
            CREATE TABLE IF NOT EXISTS training_status (
                date DATE PRIMARY KEY,
                vo2_max REAL,
                fitness_age REAL,
                training_load_7d REAL,
                training_status TEXT,
                training_readiness REAL,
                recovery_time_hours REAL,
                load_ratio REAL,
                training_feedback_code TEXT,
                training_feedback TEXT,
                training_load_chronic REAL,
                acwr_status TEXT,
                acwr_status_feedback TEXT,
                acwr_percent REAL,
                training_since_date TEXT,
                fitness_trend INTEGER,
                fitness_trend_sport TEXT,
                sport TEXT,
                device_id TEXT,
                last_primary_sync_date TEXT,
                training_balance_feedback_code TEXT,
                training_balance_feedback TEXT,
                monthly_load_aerobic_low REAL,
                monthly_load_aerobic_low_target_min REAL,
                monthly_load_aerobic_low_target_max REAL,
                monthly_load_aerobic_high REAL,
                monthly_load_aerobic_high_target_min REAL,
                monthly_load_aerobic_high_target_max REAL,
                monthly_load_anaerobic REAL,
                monthly_load_anaerobic_target_min REAL,
                monthly_load_anaerobic_target_max REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS planning_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_type TEXT,
                distance TEXT,
                weeks_to_race INTEGER,
                checkpoint_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self._ensure_training_status_columns(conn)
        conn.commit()
        conn.close()
    
    def _ensure_training_status_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление недостающих колонок в таблицу training_status (для обратной совместимости)."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(training_status)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._TRAINING_STATUS_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE training_status ADD COLUMN {column} {column_type}')
        conn.commit()

    def save_planning_checkpoint(self, checkpoint_data):
        """Сохраняет компактный planning checkpoint для dashboard/AI handoff."""
        if not checkpoint_data or not isinstance(checkpoint_data, dict):
            raise ValueError("checkpoint_data must be a non-empty dict")

        payload = json.dumps(checkpoint_data, ensure_ascii=False)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO planning_checkpoints (goal_type, distance, weeks_to_race, checkpoint_data)
            VALUES (?, ?, ?, ?)
            ''',
            (
                self.clean_value(checkpoint_data.get('goal_type')),
                self.clean_value(checkpoint_data.get('distance')),
                self.clean_value(checkpoint_data.get('weeks_to_race')),
                payload,
            ),
        )
        checkpoint_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, goal_type, distance, weeks_to_race, checkpoint_data, created_at
            FROM planning_checkpoints
            WHERE id = ?
            ''',
            (checkpoint_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_planning_checkpoint_row(row)

    def get_latest_planning_checkpoint(self):
        """Возвращает последний planning checkpoint или None."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, goal_type, distance, weeks_to_race, checkpoint_data, created_at
            FROM planning_checkpoints
            ORDER BY id DESC
            LIMIT 1
            '''
        )
        row = cursor.fetchone()
        conn.close()
        return self._deserialize_planning_checkpoint_row(row)

    def get_planning_checkpoint(self, checkpoint_id):
        """Возвращает planning checkpoint по id или None."""
        if checkpoint_id is None:
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, goal_type, distance, weeks_to_race, checkpoint_data, created_at
            FROM planning_checkpoints
            WHERE id = ?
            LIMIT 1
            ''',
            (int(checkpoint_id),),
        )
        row = cursor.fetchone()
        conn.close()
        return self._deserialize_planning_checkpoint_row(row)

    def get_recent_planning_checkpoints(self, limit=3):
        """Возвращает последние planning checkpoints для dashboard/AI surfaces."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, goal_type, distance, weeks_to_race, checkpoint_data, created_at
            FROM planning_checkpoints
            ORDER BY id DESC
            LIMIT ?
            ''',
            (max(1, int(limit or 1)),),
        )
        rows = cursor.fetchall()
        conn.close()
        return [item for item in (self._deserialize_planning_checkpoint_row(row) for row in rows) if item]

    def _deserialize_planning_checkpoint_row(self, row):
        if not row:
            return None

        checkpoint_payload = {}
        raw_payload = row[4]
        if raw_payload:
            try:
                checkpoint_payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                checkpoint_payload = {}

        result = dict(checkpoint_payload) if isinstance(checkpoint_payload, dict) else {}
        result.update(
            {
                'id': row[0],
                'goal_type': row[1] or result.get('goal_type'),
                'distance': row[2] or result.get('distance'),
                'weeks_to_race': row[3] if row[3] is not None else result.get('weeks_to_race'),
                'created_at': row[5],
            }
        )
        return result
    
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
            # Обрабатываем смешанные форматы дат и нормализуем до полуночи
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce').dt.normalize()
        
        return df
    
    def get_hrv_data(self, days=30):
        """Получение данных HRV за последние N дней (исправлено)"""
        from datetime import datetime, timedelta
        conn = sqlite3.connect(self.db_path)
        
        # Вычисляем дату начала периода в Python
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Используем параметризованный запрос для надежности
        query = """
            SELECT date, rmssd, stress_score, recovery_score
            FROM hrv_data
            WHERE date >= ?
            ORDER BY date DESC
        """
        
        try:
            df = pd.read_sql_query(query, conn, params=(start_date,))
        except Exception as e:
            print(f"Ошибка при выполнении запроса HRV: {e}")
            df = pd.DataFrame() # Возвращаем пустой DataFrame в случае ошибки
        finally:
            conn.close()
        
        # Преобразование даты в datetime, если данные есть
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        
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
    
    def clear_all_data(self):
        """Очистка всех данных из базы"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Очищаем все таблицы
        cursor.execute('DELETE FROM activities')
        cursor.execute('DELETE FROM hrv_data') 
        cursor.execute('DELETE FROM user_settings')
        
        # Очищаем новые таблицы
        try:
            cursor.execute('DELETE FROM sleep_data')
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute('DELETE FROM daily_health')
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute('DELETE FROM training_status')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('DELETE FROM planning_checkpoints')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
    
    def get_database_stats(self):
        """Получение статистики по базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Подсчитываем записи в каждой таблице
        cursor.execute('SELECT COUNT(*) FROM activities')
        activities_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM hrv_data')
        hrv_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM user_settings')
        settings_count = cursor.fetchone()[0]
        
        # Новые таблицы
        try:
            cursor.execute('SELECT COUNT(*) FROM sleep_data')
            sleep_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            sleep_count = 0
            
        try:
            cursor.execute('SELECT COUNT(*) FROM daily_health')
            health_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            health_count = 0
            
        try:
            cursor.execute('SELECT COUNT(*) FROM training_status')
            training_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            training_count = 0
        
        conn.close()
        
        return {
            'activities': activities_count,
            'hrv_data': hrv_count,
            'user_settings': settings_count,
            'sleep_data': sleep_count,
            'daily_health': health_count,
            'training_status': training_count
        }
    
    # =================== НОВЫЕ МЕТОДЫ СИНХРОНИЗАЦИИ ФАЗА 1 ===================
    
    def sync_sleep_data(self, sleep_data):
        """Умная синхронизация данных сна без дублей"""
        if not sleep_data:
            return {'new': 0, 'updated': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем существующие даты
        cursor.execute('SELECT date FROM sleep_data')
        existing_dates = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        
        for date_str, data in sleep_data.items():
            clean_date = self.clean_value(date_str)
            
            if clean_date in existing_dates:
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE sleep_data SET 
                    total_sleep_minutes=?, deep_sleep_minutes=?, light_sleep_minutes=?,
                    rem_sleep_minutes=?, awakenings_count=?, sleep_score=?,
                    bedtime=?, wakeup_time=?, sleep_efficiency=?
                    WHERE date=?
                ''', (
                    self.clean_value(data.get('total_sleep_minutes')),
                    self.clean_value(data.get('deep_sleep_minutes')),
                    self.clean_value(data.get('light_sleep_minutes')),
                    self.clean_value(data.get('rem_sleep_minutes')),
                    self.clean_value(data.get('awakenings_count')),
                    self.clean_value(data.get('sleep_score')),
                    self.clean_value(data.get('bedtime')),
                    self.clean_value(data.get('wakeup_time')),
                    self.clean_value(data.get('sleep_efficiency')),
                    clean_date
                ))
                updated_count += 1
            else:
                # Вставляем новую запись
                cursor.execute('''
                    INSERT INTO sleep_data 
                    (date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes,
                     rem_sleep_minutes, awakenings_count, sleep_score, bedtime, 
                     wakeup_time, sleep_efficiency)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clean_date,
                    self.clean_value(data.get('total_sleep_minutes')),
                    self.clean_value(data.get('deep_sleep_minutes')),
                    self.clean_value(data.get('light_sleep_minutes')),
                    self.clean_value(data.get('rem_sleep_minutes')),
                    self.clean_value(data.get('awakenings_count')),
                    self.clean_value(data.get('sleep_score')),
                    self.clean_value(data.get('bedtime')),
                    self.clean_value(data.get('wakeup_time')),
                    self.clean_value(data.get('sleep_efficiency'))
                ))
                existing_dates.add(clean_date)
                new_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            'new': new_count,
            'updated': updated_count
        }
    
    def sync_daily_health(self, health_data):
        """Умная синхронизация ежедневных показателей здоровья"""
        if not health_data:
            return {'new': 0, 'updated': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем существующие даты
        cursor.execute('SELECT date FROM daily_health')
        existing_dates = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        
        for date_str, data in health_data.items():
            clean_date = self.clean_value(date_str)
            
            if clean_date in existing_dates:
                # Обновляем существующую запись
                cursor.execute('''
                    UPDATE daily_health SET 
                    resting_hr=?, steps=?, floors_climbed=?,
                    calories_active=?, calories_bmr=?, distance_meters=?,
                    active_minutes=?, intensity_minutes=?
                    WHERE date=?
                ''', (
                    self.clean_value(data.get('resting_hr')),
                    self.clean_value(data.get('steps')),
                    self.clean_value(data.get('floors_climbed')),
                    self.clean_value(data.get('calories_active')),
                    self.clean_value(data.get('calories_bmr')),
                    self.clean_value(data.get('distance_meters')),
                    self.clean_value(data.get('active_minutes')),
                    self.clean_value(data.get('intensity_minutes')),
                    clean_date
                ))
                updated_count += 1
            else:
                # Вставляем новую запись
                cursor.execute('''
                    INSERT INTO daily_health 
                    (date, resting_hr, steps, floors_climbed, calories_active,
                     calories_bmr, distance_meters, active_minutes, intensity_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    clean_date,
                    self.clean_value(data.get('resting_hr')),
                    self.clean_value(data.get('steps')),
                    self.clean_value(data.get('floors_climbed')),
                    self.clean_value(data.get('calories_active')),
                    self.clean_value(data.get('calories_bmr')),
                    self.clean_value(data.get('distance_meters')),
                    self.clean_value(data.get('active_minutes')),
                    self.clean_value(data.get('intensity_minutes'))
                ))
                existing_dates.add(clean_date)
                new_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            'new': new_count,
            'updated': updated_count
        }
    
    def sync_training_status(self, status_data):
        """Синхронизация статуса тренированности"""
        if not status_data:
            return {'new': 0, 'updated': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Получаем существующие даты
        cursor.execute('SELECT date FROM training_status')
        existing_dates = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        
        for date_str, data in status_data.items():
            clean_date = self.clean_value(date_str)
            column_values = [self.clean_value(data.get(column)) for column in self._TRAINING_STATUS_COLUMN_ORDER]
            update_clause = ', '.join(f"{column}=?" for column in self._TRAINING_STATUS_COLUMN_ORDER)
            insert_columns = ['date'] + self._TRAINING_STATUS_COLUMN_ORDER
            insert_placeholders = ', '.join('?' for _ in insert_columns)
            
            if clean_date in existing_dates:
                cursor.execute(
                    f'UPDATE training_status SET {update_clause} WHERE date=?',
                    (*column_values, clean_date)
                )
                updated_count += 1
            else:
                cursor.execute(
                    f"INSERT INTO training_status ({', '.join(insert_columns)}) VALUES ({insert_placeholders})",
                    [clean_date] + column_values
                )
                existing_dates.add(clean_date)
                new_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            'new': new_count,
            'updated': updated_count
        }
    
    # =================== МЕТОДЫ ПОЛУЧЕНИЯ НОВЫХ ДАННЫХ ===================
    
    def get_sleep_data(self, days=30):
        """Получение данных сна за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        
        cutoff_date = (datetime.now() - pd.Timedelta(days=days)).date()
        
        query = f'''
            SELECT * FROM sleep_data 
            WHERE date >= '{cutoff_date}'
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn)
        except pd.io.sql.DatabaseError:
            # Таблица не существует
            df = pd.DataFrame()
        
        conn.close()
        
        # Преобразование даты в datetime если она есть  
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        
        return df
    
    def get_daily_health(self, days=30):
        """Получение ежедневных показателей здоровья за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        
        cutoff_date = (datetime.now() - pd.Timedelta(days=days)).date()
        
        query = f'''
            SELECT * FROM daily_health 
            WHERE date >= '{cutoff_date}'
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn)
        except pd.io.sql.DatabaseError:
            # Таблица не существует
            df = pd.DataFrame()
        
        conn.close()
        
        # Преобразование даты в datetime если она есть  
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        
        return df
    
    def get_training_status_history(self, days=90):
        """Получение истории статуса тренированности за последние N дней"""
        conn = sqlite3.connect(self.db_path)
        
        cutoff_date = (datetime.now() - pd.Timedelta(days=days)).date()
        
        query = f'''
            SELECT * FROM training_status 
            WHERE date >= '{cutoff_date}'
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn)
        except pd.io.sql.DatabaseError:
            # Таблица не существует
            df = pd.DataFrame()
        
        conn.close()
        
        # Преобразование даты в datetime если она есть  
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        
        return df
