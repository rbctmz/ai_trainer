import json
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import Settings

class Database:
    _ACTIVITY_COLUMN_ORDER = [
        'activity_id',
        'date',
        'sport',
        'duration_minutes',
        'moving_duration_minutes',
        'distance_km',
        'avg_hr',
        'max_hr',
        'avg_power',
        'max_power',
        'normalized_power',
        'elevation_gain',
        'calories',
        'training_effect',
        'anaerobic_effect',
        'activity_name',
        'description',
        'garmin_training_load',
        'source_tss',
        'moderate_intensity_minutes',
        'vigorous_intensity_minutes',
        'hr_time_in_zone_1_seconds',
        'hr_time_in_zone_2_seconds',
        'hr_time_in_zone_3_seconds',
        'hr_time_in_zone_4_seconds',
        'hr_time_in_zone_5_seconds',
        'tss_method',
        'tss',
        'tss_ftp_used',
    ]

    _ACTIVITY_COLUMN_TYPES = {
        'activity_id': 'TEXT PRIMARY KEY',
        'date': 'DATE',
        'sport': 'TEXT',
        'duration_minutes': 'REAL',
        'moving_duration_minutes': 'REAL',
        'distance_km': 'REAL',
        'avg_hr': 'REAL',
        'max_hr': 'REAL',
        'avg_power': 'REAL',
        'max_power': 'REAL',
        'normalized_power': 'REAL',
        'elevation_gain': 'REAL',
        'calories': 'INTEGER',
        'training_effect': 'REAL',
        'anaerobic_effect': 'REAL',
        'activity_name': 'TEXT',
        'description': 'TEXT',
        'garmin_training_load': 'REAL',
        'source_tss': 'REAL',
        'moderate_intensity_minutes': 'REAL',
        'vigorous_intensity_minutes': 'REAL',
        'hr_time_in_zone_1_seconds': 'REAL',
        'hr_time_in_zone_2_seconds': 'REAL',
        'hr_time_in_zone_3_seconds': 'REAL',
        'hr_time_in_zone_4_seconds': 'REAL',
        'hr_time_in_zone_5_seconds': 'REAL',
        'tss_method': 'TEXT',
        'tss': 'REAL',
        'tss_ftp_used': 'REAL',
    }

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

    _DAILY_HEALTH_COLUMN_TYPES = {
        'resting_hr': 'INTEGER',
        'steps': 'INTEGER',
        'floors_climbed': 'INTEGER',
        'calories_active': 'INTEGER',
        'calories_bmr': 'INTEGER',
        'distance_meters': 'INTEGER',
        'active_minutes': 'INTEGER',
        'intensity_minutes': 'INTEGER',
        'respiration_avg': 'REAL',
        'respiration_min': 'REAL',
        'respiration_max': 'REAL',
        'spo2_avg': 'REAL',
        'spo2_min': 'REAL',
        'skin_temperature_avg': 'REAL',
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

    @staticmethod
    def _cutoff_date(days):
        """Return YYYY-MM-DD cutoff for recent-data queries."""
        return (datetime.now() - timedelta(days=float(days))).strftime('%Y-%m-%d')
    
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
                moving_duration_minutes REAL,
                distance_km REAL,
                avg_hr REAL,
                max_hr REAL,
                avg_power REAL,
                max_power REAL,
                normalized_power REAL,
                elevation_gain REAL,
                calories INTEGER,
                training_effect REAL,
                anaerobic_effect REAL,
                activity_name TEXT,
                description TEXT,
                garmin_training_load REAL,
                source_tss REAL,
                moderate_intensity_minutes REAL,
                vigorous_intensity_minutes REAL,
                hr_time_in_zone_1_seconds REAL,
                hr_time_in_zone_2_seconds REAL,
                hr_time_in_zone_3_seconds REAL,
                hr_time_in_zone_4_seconds REAL,
                hr_time_in_zone_5_seconds REAL,
                tss_method TEXT,
                tss REAL,
                tss_ftp_used REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица HRV данных
        # recovery_score = пиковое значение Body Battery за день (см.
        # services/sync.py:_peak_body_battery), а не снимок на момент синка.
        # Строки, записанные до этого фикса, могут быть смесью утренних и
        # вечерних снимков -- не считать их надёжным временным рядом задним
        # числом без пересчёта из сырого bodyBatteryValuesArray.
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

        # Athlete profile (FTP/вес/LTHR), синкается из intervals.icu вместо
        # статичных env-переменных (issue #102). Append-only: каждый sync
        # добавляет новую строку, get_athlete_profile() читает последнюю.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS athlete_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ftp REAL,
                weight_kg REAL,
                lthr REAL,
                source TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                respiration_avg REAL,
                respiration_min REAL,
                respiration_max REAL,
                spo2_avg REAL,
                spo2_min REAL,
                skin_temperature_avg REAL,
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

        conn.execute('''
            CREATE TABLE IF NOT EXISTS coach_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                workout_id TEXT,
                chat_id TEXT,
                message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS coach_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                params_json TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                chat_id TEXT,
                message_id TEXT,
                resolved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self._ensure_activity_columns(conn)
        self._repair_legacy_activity_tss(conn)
        self._ensure_daily_health_columns(conn)
        self._ensure_training_status_columns(conn)
        conn.commit()
        conn.close()

    def _ensure_activity_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление недостающих колонок в таблицу activities (для обратной совместимости)."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(activities)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._ACTIVITY_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE activities ADD COLUMN {column} {column_type}')
        conn.commit()

    @staticmethod
    def _numeric_equal(left, right, digits: int = 1) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        try:
            return round(float(left), digits) == round(float(right), digits)
        except (TypeError, ValueError):
            return left == right

    def _repair_legacy_activity_tss(self, conn: sqlite3.Connection) -> None:
        """Пересчитывает сохраненный activity TSS по текущим resolver-правилам."""
        from data.data_processor import ActivityProcessor, resolve_athlete_ftp_lthr

        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT *
            FROM activities
            '''
        )
        rows = cursor.fetchall()
        if not rows:
            return

        ftp, lthr = resolve_athlete_ftp_lthr(self)

        for row in rows:
            activity = dict(row)
            resolved = ActivityProcessor.resolve_tss(
                activity,
                ftp=ftp,
                lthr=lthr,
            )
            needs_update = (
                not self._numeric_equal(activity.get('tss'), resolved['tss'])
                or activity.get('tss_method') != resolved['tss_method']
                or not self._numeric_equal(activity.get('source_tss'), resolved['source_tss'])
                or not self._numeric_equal(
                    activity.get('garmin_training_load'),
                    resolved['garmin_training_load'],
                )
                or not self._numeric_equal(activity.get('tss_ftp_used'), resolved['tss_ftp_used'])
            )
            if not needs_update:
                continue

            cursor.execute(
                '''
                UPDATE activities
                SET tss = ?,
                    tss_method = ?,
                    source_tss = ?,
                    garmin_training_load = ?,
                    tss_ftp_used = ?
                WHERE activity_id = ?
                ''',
                (
                    self.clean_value(resolved['tss']),
                    self.clean_value(resolved['tss_method']),
                    self.clean_value(resolved['source_tss']),
                    self.clean_value(resolved['garmin_training_load']),
                    self.clean_value(resolved['tss_ftp_used']),
                    self.clean_value(activity.get('activity_id')),
                ),
            )
        conn.commit()
    
    def _ensure_training_status_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление недостающих колонок в таблицу training_status (для обратной совместимости)."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(training_status)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._TRAINING_STATUS_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE training_status ADD COLUMN {column} {column_type}')
        conn.commit()

    def _ensure_daily_health_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление недостающих колонок daily_health для новых Garmin wellness сигналов."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(daily_health)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._DAILY_HEALTH_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE daily_health ADD COLUMN {column} {column_type}')
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

    def save_coach_decision(
        self,
        decision_type,
        reason,
        workout_id=None,
        chat_id=None,
        message_id=None,
        date=None,
    ):
        """Сохраняет решение коуча для audit trail."""
        allowed = {"Push", "Moderate", "Recovery", "Monitor"}
        decision_type = str(decision_type or "").strip()
        if decision_type not in allowed:
            raise ValueError(f"decision_type must be one of {sorted(allowed)}")

        reason = " ".join(str(reason or "").split())
        if not reason:
            raise ValueError("reason must be non-empty")

        if date is None:
            date = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        elif isinstance(date, datetime):
            date = date.replace(microsecond=0).isoformat()
        else:
            date = str(date)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO coach_decisions
                (date, decision_type, reason, workout_id, chat_id, message_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                self.clean_value(date),
                self.clean_value(decision_type),
                self.clean_value(reason),
                self.clean_value(workout_id),
                self.clean_value(chat_id),
                self.clean_value(message_id),
            ),
        )
        decision_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, date, decision_type, reason, workout_id, chat_id, message_id, created_at
            FROM coach_decisions
            WHERE id = ?
            ''',
            (decision_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_decision_row(row)

    def get_coach_decisions(self, days=30, limit=100):
        """Возвращает решения коуча за последние N дней, новые первыми."""
        cutoff_date = self._cutoff_date(days)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, date, decision_type, reason, workout_id, chat_id, message_id, created_at
            FROM coach_decisions
            WHERE substr(date, 1, 10) >= ?
            ORDER BY date DESC, id DESC
            LIMIT ?
            ''',
            (cutoff_date, max(1, int(limit or 1))),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_coach_decision_row(row) for row in rows]

    def _deserialize_coach_decision_row(self, row):
        if not row:
            return None
        return {
            'id': row[0],
            'date': row[1],
            'decision_type': row[2],
            'reason': row[3],
            'workout_id': row[4],
            'chat_id': row[5],
            'message_id': row[6],
            'created_at': row[7],
        }

    def save_coach_proposal(
        self,
        action,
        params,
        preview,
        chat_id=None,
        message_id=None,
        date=None,
    ):
        """Сохраняет pending-предложение коуча, требующее approve/reject."""
        allowed_actions = {"build_plan", "adjust_plan"}
        action = str(action or "").strip()
        if action not in allowed_actions:
            raise ValueError(f"action must be one of {sorted(allowed_actions)}")
        if not isinstance(params, dict):
            raise ValueError("params must be a dict")
        if not isinstance(preview, dict):
            raise ValueError("preview must be a dict")

        if date is None:
            date = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        elif isinstance(date, datetime):
            date = date.replace(microsecond=0).isoformat()
        else:
            date = str(date)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO coach_proposals
                (date, action, status, params_json, preview_json, chat_id, message_id)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            ''',
            (
                self.clean_value(date),
                self.clean_value(action),
                json.dumps(params, ensure_ascii=False, default=str),
                json.dumps(preview, ensure_ascii=False, default=str),
                self.clean_value(chat_id),
                self.clean_value(message_id),
            ),
        )
        proposal_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at
            FROM coach_proposals
            WHERE id = ?
            ''',
            (proposal_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_proposal_row(row)

    def get_coach_proposal(self, proposal_id):
        """Возвращает одно предложение коуча по id или None."""
        if proposal_id is None:
            return None
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at
            FROM coach_proposals
            WHERE id = ?
            LIMIT 1
            ''',
            (int(proposal_id),),
        )
        row = cursor.fetchone()
        conn.close()
        return self._deserialize_coach_proposal_row(row)

    def get_coach_proposals(self, days=30, status=None, limit=100):
        """Возвращает предложения коуча за последние N дней, новые первыми."""
        cutoff_date = self._cutoff_date(days)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if status:
            cursor.execute(
                '''
                SELECT id, date, action, status, params_json, preview_json, result_json,
                       error, chat_id, message_id, resolved_at, created_at
                FROM coach_proposals
                WHERE substr(date, 1, 10) >= ? AND status = ?
                ORDER BY date DESC, id DESC
                LIMIT ?
                ''',
                (cutoff_date, str(status), max(1, int(limit or 1))),
            )
        else:
            cursor.execute(
                '''
                SELECT id, date, action, status, params_json, preview_json, result_json,
                       error, chat_id, message_id, resolved_at, created_at
                FROM coach_proposals
                WHERE substr(date, 1, 10) >= ?
                ORDER BY date DESC, id DESC
                LIMIT ?
                ''',
                (cutoff_date, max(1, int(limit or 1))),
            )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_coach_proposal_row(row) for row in rows]

    def update_coach_proposal_status(self, proposal_id, status, result=None, error=None):
        """Обновляет lifecycle proposal: approved/rejected/failed."""
        allowed_statuses = {"pending", "approved", "rejected", "failed"}
        status = str(status or "").strip()
        if status not in allowed_statuses:
            raise ValueError(f"status must be one of {sorted(allowed_statuses)}")

        resolved_at = None
        if status != "pending":
            resolved_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        result_json = None
        if result is not None:
            result_json = json.dumps(result, ensure_ascii=False, default=str)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE coach_proposals
            SET status = ?, result_json = ?, error = ?, resolved_at = ?
            WHERE id = ?
            ''',
            (
                self.clean_value(status),
                result_json,
                self.clean_value(error),
                self.clean_value(resolved_at),
                int(proposal_id),
            ),
        )
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at
            FROM coach_proposals
            WHERE id = ?
            ''',
            (int(proposal_id),),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_proposal_row(row)

    def _deserialize_coach_proposal_row(self, row):
        if not row:
            return None

        def _loads(raw):
            if not raw:
                return {}
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return {}
            return value if isinstance(value, dict) else {}

        return {
            'id': row[0],
            'date': row[1],
            'action': row[2],
            'status': row[3],
            'params': _loads(row[4]),
            'preview': _loads(row[5]),
            'result': _loads(row[6]),
            'error': row[7],
            'chat_id': row[8],
            'message_id': row[9],
            'resolved_at': row[10],
            'created_at': row[11],
        }
    
    def get_activities(self, days=30):
        """Получение активностей из БД"""
        conn = sqlite3.connect(self.db_path)
        
        # Если данные есть, получаем их с фильтрацией
        cutoff_date = self._cutoff_date(days)
        
        query = '''
            SELECT * FROM activities 
            WHERE date >= ?
            ORDER BY date DESC
        '''
        df = pd.read_sql_query(query, conn, params=(cutoff_date,))
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
        columns = ', '.join(self._ACTIVITY_COLUMN_ORDER)
        placeholders = ', '.join('?' for _ in self._ACTIVITY_COLUMN_ORDER)
        
        for activity in activities:
            values = tuple(self.clean_value(activity.get(column)) for column in self._ACTIVITY_COLUMN_ORDER)
            conn.execute(
                f'''
                INSERT OR REPLACE INTO activities ({columns})
                VALUES ({placeholders})
                ''',
                values,
            )
        
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
    
    def get_latest_data_dates(self):
        """Последние даты (YYYY-MM-DD) по таблицам синка для инкрементального режима"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        latest = {}
        for table in ('activities', 'hrv_data', 'sleep_data', 'daily_health'):
            try:
                cursor.execute(f'SELECT MAX(substr(date, 1, 10)) FROM {table}')
                row = cursor.fetchone()
                latest[table] = row[0] if row and row[0] else None
            except sqlite3.OperationalError:
                latest[table] = None

        conn.close()
        return latest

    def sync_activities(self, activities):
        """Умная синхронизация активностей без дублей"""
        if not activities:
            return {'new': 0, 'updated': 0, 'skipped': 0}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        activity_columns = [column for column in self._ACTIVITY_COLUMN_ORDER if column != 'activity_id']
        update_sql = ', '.join(f"{column}=?" for column in activity_columns)
        insert_columns = ', '.join(self._ACTIVITY_COLUMN_ORDER)
        insert_placeholders = ', '.join('?' for _ in self._ACTIVITY_COLUMN_ORDER)
        
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
                values = [self.clean_value(activity.get(column)) for column in activity_columns]
                values.append(activity_id)
                cursor.execute(
                    f'''
                    UPDATE activities SET
                    {update_sql}
                    WHERE activity_id=?
                    ''',
                    tuple(values),
                )
                updated_count += 1
            else:
                # Вставляем новую запись
                values = tuple(self.clean_value(activity.get(column)) for column in self._ACTIVITY_COLUMN_ORDER)
                cursor.execute(
                    f'''
                    INSERT INTO activities ({insert_columns})
                    VALUES ({insert_placeholders})
                    ''',
                    values,
                )
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

        try:
            cursor.execute('DELETE FROM coach_decisions')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('DELETE FROM coach_proposals')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()

    def get_user_setting(self, key, default=None):
        """Получение пользовательской настройки по ключу."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM user_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return default
        return row[0]

    def set_user_setting(self, key, value):
        """Сохранение пользовательской настройки."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            '''
            INSERT INTO user_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (key, value),
        )
        conn.commit()
        conn.close()

    def delete_user_setting(self, key):
        """Удаление пользовательской настройки."""
        conn = sqlite3.connect(self.db_path)
        conn.execute('DELETE FROM user_settings WHERE key = ?', (key,))
        conn.commit()
        conn.close()

    def save_athlete_profile(self, profile):
        """Сохраняет новый снэпшот athlete profile (FTP/вес/LTHR)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            '''
            INSERT INTO athlete_profile (ftp, weight_kg, lthr, source)
            VALUES (?, ?, ?, ?)
            ''',
            (
                self.clean_value(profile.get('ftp')),
                self.clean_value(profile.get('weight_kg')),
                self.clean_value(profile.get('lthr')),
                profile.get('source'),
            ),
        )
        conn.commit()
        conn.close()

    def get_athlete_profile(self):
        """Возвращает самый свежий снэпшот athlete profile, или None если ещё ничего не синкалось."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT ftp, weight_kg, lthr, source, synced_at
            FROM athlete_profile
            ORDER BY synced_at DESC, id DESC
            LIMIT 1
            '''
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return None
        return {
            'ftp': row[0],
            'weight_kg': row[1],
            'lthr': row[2],
            'source': row[3],
            'synced_at': row[4],
        }

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

        try:
            cursor.execute('SELECT COUNT(*) FROM coach_decisions')
            coach_decisions_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            coach_decisions_count = 0

        try:
            cursor.execute('SELECT COUNT(*) FROM coach_proposals')
            coach_proposals_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            coach_proposals_count = 0
        
        conn.close()
        
        return {
            'activities': activities_count,
            'hrv_data': hrv_count,
            'user_settings': settings_count,
            'sleep_data': sleep_count,
            'daily_health': health_count,
            'training_status': training_count,
            'coach_decisions': coach_decisions_count,
            'coach_proposals': coach_proposals_count
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
        columns = list(self._DAILY_HEALTH_COLUMN_TYPES)
        insert_columns = ['date'] + columns
        insert_placeholders = ', '.join('?' for _ in insert_columns)
        
        # Получаем существующие даты
        cursor.execute('SELECT date FROM daily_health')
        existing_dates = {row[0] for row in cursor.fetchall()}
        
        new_count = 0
        updated_count = 0
        
        for date_str, data in health_data.items():
            clean_date = self.clean_value(date_str)
            
            if clean_date in existing_dates:
                # Обновляем только переданные поля: отсутствующий ключ означает
                # «нет данных за этот проход» и не должен затирать сохранённое значение NULL-ом
                present_columns = [column for column in columns if column in data]
                if not present_columns:
                    continue
                update_clause = ', '.join(f"{column}=?" for column in present_columns)
                column_values = [self.clean_value(data.get(column)) for column in present_columns]
                cursor.execute(
                    f'UPDATE daily_health SET {update_clause} WHERE date=?',
                    (*column_values, clean_date),
                )
                updated_count += 1
            else:
                # Вставляем новую запись
                column_values = [self.clean_value(data.get(column)) for column in columns]
                cursor.execute(
                    f"INSERT INTO daily_health ({', '.join(insert_columns)}) VALUES ({insert_placeholders})",
                    [clean_date] + column_values,
                )
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
        
        cutoff_date = self._cutoff_date(days)
        
        query = '''
            SELECT * FROM sleep_data 
            WHERE date >= ?
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn, params=(cutoff_date,))
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
        
        cutoff_date = self._cutoff_date(days)
        
        query = '''
            SELECT * FROM daily_health 
            WHERE date >= ?
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn, params=(cutoff_date,))
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
        
        cutoff_date = self._cutoff_date(days)
        
        query = '''
            SELECT * FROM training_status 
            WHERE date >= ?
            ORDER BY date DESC
        '''
        
        try:
            df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        except pd.io.sql.DatabaseError:
            # Таблица не существует
            df = pd.DataFrame()
        
        conn.close()
        
        # Преобразование даты в datetime если она есть  
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='coerce')
        
        return df
