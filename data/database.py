import json
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import Settings

class Database:
    _ACTIVITY_COLUMN_ORDER = [
        'activity_id',
        'date',
        'started_at_utc',
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
        'started_at_utc': 'TEXT',
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

    _SLEEP_COLUMN_TYPES = {
        'awake_sleep_minutes': 'REAL',
        'sleep_score_source': "TEXT DEFAULT 'legacy_unknown'",
        'sleep_efficiency_source': "TEXT DEFAULT 'legacy_unknown'",
    }

    _COACH_DECISION_COLUMN_TYPES = {
        'metrics_window_days': 'INTEGER',
        'as_of_date': 'TEXT',
    }

    _COACH_PROPOSAL_COLUMN_TYPES = {
        'source': 'TEXT',
        'source_key': 'TEXT',
        'active_key': 'TEXT',
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
                started_at_utc TEXT,
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
                awake_sleep_minutes REAL,
                sleep_score_source TEXT DEFAULT 'legacy_unknown',
                sleep_efficiency_source TEXT DEFAULT 'legacy_unknown',
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
                metrics_window_days INTEGER,
                as_of_date TEXT,
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
                source TEXT,
                source_key TEXT,
                active_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS recovery_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                date TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL,
                report_json TEXT NOT NULL,
                plan_checkpoint_id INTEGER,
                proposal_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS session_quality_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                rule_version TEXT NOT NULL,
                target_date TEXT NOT NULL,
                plan_checkpoint_id INTEGER NOT NULL,
                plan_session_index INTEGER NOT NULL,
                planned_role TEXT NOT NULL,
                planned_sport TEXT NOT NULL,
                planned_tss REAL NOT NULL,
                planned_duration_minutes INTEGER,
                prediction_pct INTEGER NOT NULL,
                prediction_band TEXT NOT NULL,
                input_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                recovery_decision_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                plan_adherence TEXT,
                quality_rating_1_5 INTEGER,
                quality_outcome TEXT,
                actual_activity_ids_json TEXT,
                actual_snapshot_json TEXT,
                unscored_reason TEXT,
                brier_score REAL,
                resolved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS plan_actual_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_match_id INTEGER,
                session_id TEXT,
                base_checkpoint_id INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                match_status TEXT NOT NULL,
                match_method TEXT NOT NULL,
                confidence REAL NOT NULL,
                planned_snapshot_json TEXT NOT NULL,
                actual_activity_ids_json TEXT NOT NULL,
                actual_snapshot_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS session_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_feedback_id INTEGER,
                session_id TEXT NOT NULL,
                parent_session_id TEXT,
                match_revision_id INTEGER,
                match_snapshot_json TEXT NOT NULL,
                actual_activity_ids_json TEXT NOT NULL,
                completion_status TEXT NOT NULL,
                completion_pct REAL,
                completion_pct_source TEXT,
                session_rpe_1_10 INTEGER,
                quality_rating_1_5 INTEGER,
                note TEXT,
                source TEXT NOT NULL,
                session_end_at_utc TEXT,
                session_end_provenance TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                rule_version TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS session_feedback_prompt_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                session_id TEXT NOT NULL,
                prompt_fingerprint TEXT,
                event TEXT NOT NULL,
                reason TEXT,
                source TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS session_quality_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_evaluation_id INTEGER,
                prediction_id INTEGER NOT NULL,
                prediction_target_key TEXT NOT NULL,
                feedback_id INTEGER NOT NULL,
                match_revision_id INTEGER,
                status TEXT NOT NULL,
                plan_adherence TEXT,
                quality_rating_1_5 INTEGER,
                quality_outcome TEXT,
                unscored_reason TEXT,
                brier_score REAL,
                evidence_json TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS readiness_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_snapshot_id INTEGER,
                capture_mode TEXT NOT NULL,
                local_date TEXT NOT NULL,
                athlete_timezone TEXT NOT NULL,
                observed_at_utc TEXT NOT NULL,
                capture_run_id TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                score REAL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                as_of_date TEXT NOT NULL,
                is_provisional INTEGER NOT NULL,
                source_completeness REAL NOT NULL,
                stale INTEGER NOT NULL,
                eligibility_status TEXT NOT NULL,
                eligibility_reasons_json TEXT NOT NULL,
                factors_json TEXT NOT NULL,
                drivers_json TEXT NOT NULL,
                missing_inputs_json TEXT NOT NULL,
                tsb_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS recovery_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                target_key TEXT NOT NULL,
                revision INTEGER NOT NULL,
                supersedes_episode_id INTEGER,
                session_id TEXT NOT NULL,
                plan_checkpoint_id INTEGER,
                match_revision_id INTEGER,
                feedback_id INTEGER,
                session_date TEXT NOT NULL,
                iso_week TEXT,
                capture_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                template_id TEXT,
                stimulus_family TEXT,
                sport TEXT,
                role TEXT,
                phase TEXT,
                actual_tss REAL,
                load_bucket TEXT,
                adherence TEXT,
                rpe_band TEXT,
                pre_snapshot_id INTEGER,
                d1_snapshot_id INTEGER,
                d2_snapshot_id INTEGER,
                d3_snapshot_id INTEGER,
                exclusion_reasons_json TEXT NOT NULL,
                planned_json TEXT NOT NULL,
                actual_json TEXT NOT NULL,
                feedback_json TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                confounders_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target_key, revision)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS coach_constraints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                note TEXT,
                plan_id TEXT,
                session_id TEXT,
                metadata_json TEXT,
                resolved_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # ADR-0008 (#269): multi-source activity ingestion. One canonical activity
        # (activity_id) may carry provider links from BOTH Garmin and Intervals;
        # provider_tss lives per-link (native loads differ per source); match_status
        # is the data home for fail-closed "flag for review". Additive, non-destructive.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS activity_provider_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_activity_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_activity_id TEXT NOT NULL,
                external_provider TEXT,
                external_id TEXT,
                provider_tss REAL,
                provider_payload TEXT,
                match_status TEXT NOT NULL DEFAULT 'unmatched',
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, provider_activity_id),
                CHECK (match_status IN ('matched', 'ambiguous', 'unmatched')),
                CHECK (
                    (external_id IS NULL AND external_provider IS NULL)
                    OR (external_id IS NOT NULL AND external_provider IS NOT NULL)
                )
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_provider_links_canonical
            ON activity_provider_links(canonical_activity_id)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_provider_links_external
            ON activity_provider_links(external_provider, external_id)
            WHERE external_id IS NOT NULL
        ''')
        self._ensure_activity_columns(conn)
        self._repair_legacy_activity_tss(conn)
        self._ensure_sleep_columns(conn)
        self._ensure_daily_health_columns(conn)
        self._ensure_training_status_columns(conn)
        self._ensure_coach_decision_columns(conn)
        self._ensure_coach_proposal_columns(conn)
        self._ensure_session_feedback_prompt_columns(conn)
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_coach_proposals_source_key
            ON coach_proposals(source_key)
            WHERE source_key IS NOT NULL
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_coach_proposals_active_key
            ON coach_proposals(active_key)
            WHERE active_key IS NOT NULL AND status IN ('pending', 'applying')
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_quality_target
            ON session_quality_predictions(target_key, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_quality_status
            ON session_quality_predictions(status, target_date)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_plan_actual_matches_target
            ON plan_actual_matches(target_key, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_plan_actual_matches_date
            ON plan_actual_matches(session_date, match_status)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_feedback_target
            ON session_feedback(target_key, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_feedback_session
            ON session_feedback(session_id, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_feedback_prompt_session
            ON session_feedback_prompt_events(session_id, created_at)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_session_quality_evaluation_prediction
            ON session_quality_evaluations(prediction_id, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_readiness_snapshot_target
            ON readiness_snapshots(target_key, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_readiness_snapshot_anchor
            ON readiness_snapshots(capture_mode, local_date, observed_at_utc)
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_readiness_snapshot_capture_run
            ON readiness_snapshots(capture_mode, capture_run_id)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_recovery_episode_target
            ON recovery_episodes(target_key, revision)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_recovery_episode_projection
            ON recovery_episodes(capture_mode, status, session_date)
        ''')
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
    def _ensure_session_feedback_prompt_columns(conn: sqlite3.Connection) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(session_feedback_prompt_events)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if "prompt_fingerprint" not in existing_columns:
            try:
                cursor.execute(
                    "ALTER TABLE session_feedback_prompt_events "
                    "ADD COLUMN prompt_fingerprint TEXT"
                )
            except sqlite3.OperationalError as exc:
                # Two API/test processes can initialize the same SQLite file at
                # once. If the other process won the migration race, the schema
                # is already in the desired state and initialization remains
                # idempotent. Do not swallow unrelated migration failures.
                if "duplicate column name" not in str(exc).lower():
                    raise
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

    def _ensure_sleep_columns(self, conn: sqlite3.Connection) -> None:
        """Add provenance columns without rewriting legacy sleep metrics."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sleep_data)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._SLEEP_COLUMN_TYPES.items():
            if column in existing_columns:
                continue
            try:
                cursor.execute(f'ALTER TABLE sleep_data ADD COLUMN {column} {column_type}')
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.commit()

    def _ensure_coach_decision_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление недостающих колонок coach_decisions для audit metadata."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(coach_decisions)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._COACH_DECISION_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE coach_decisions ADD COLUMN {column} {column_type}')
        conn.commit()

    def _ensure_coach_proposal_columns(self, conn: sqlite3.Connection) -> None:
        """Добавление provenance-колонок proposal для идемпотентных agent actions."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(coach_proposals)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column, column_type in self._COACH_PROPOSAL_COLUMN_TYPES.items():
            if column not in existing_columns:
                cursor.execute(f'ALTER TABLE coach_proposals ADD COLUMN {column} {column_type}')
        conn.commit()

    @staticmethod
    def _json_value(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _json_load(value, fallback):
        if value is None:
            return fallback
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed

    def save_readiness_snapshot(self, payload):
        """Atomically append or idempotently return a readiness revision."""
        required = {
            'fingerprint', 'target_key', 'capture_mode', 'local_date',
            'athlete_timezone', 'observed_at_utc', 'capture_run_id',
            'rule_version', 'status', 'confidence', 'as_of_date',
            'eligibility_status',
        }
        missing = sorted(required - set(payload or {}))
        if missing:
            raise ValueError(f"missing readiness snapshot fields: {missing}")
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 30000')
        try:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute(
                'SELECT * FROM readiness_snapshots WHERE fingerprint = ?',
                (str(payload['fingerprint']),),
            ).fetchone()
            if existing is not None:
                conn.commit()
                return {'snapshot': self._deserialize_readiness_snapshot(existing), 'created': False}
            previous = conn.execute(
                '''
                SELECT id, revision FROM readiness_snapshots
                WHERE target_key = ? ORDER BY revision DESC, id DESC LIMIT 1
                ''',
                (str(payload['target_key']),),
            ).fetchone()
            revision = int(previous['revision']) + 1 if previous else 1
            columns = (
                'fingerprint', 'target_key', 'revision', 'supersedes_snapshot_id',
                'capture_mode', 'local_date', 'athlete_timezone', 'observed_at_utc',
                'capture_run_id', 'rule_version', 'score', 'status', 'confidence',
                'as_of_date', 'is_provisional', 'source_completeness', 'stale',
                'eligibility_status', 'eligibility_reasons_json', 'factors_json',
                'drivers_json', 'missing_inputs_json', 'tsb_json', 'provenance_json',
                'snapshot_json',
            )
            values = (
                str(payload['fingerprint']), str(payload['target_key']), revision,
                int(previous['id']) if previous else None, str(payload['capture_mode']),
                str(payload['local_date']), str(payload['athlete_timezone']),
                str(payload['observed_at_utc']), str(payload['capture_run_id']),
                str(payload['rule_version']), payload.get('score'), str(payload['status']),
                float(payload.get('confidence') or 0.0), str(payload['as_of_date']),
                int(bool(payload.get('is_provisional'))),
                float(payload.get('source_completeness') or 0.0),
                int(bool(payload.get('stale'))), str(payload['eligibility_status']),
                self._json_value(payload.get('eligibility_reasons') or []),
                self._json_value(payload.get('factors') or []),
                self._json_value(payload.get('drivers') or []),
                self._json_value(payload.get('missing_inputs') or []),
                self._json_value(payload.get('tsb') or {}),
                self._json_value(payload.get('provenance') or {}),
                self._json_value(payload.get('snapshot') or {}),
            )
            placeholders = ', '.join('?' for _ in columns)
            cursor = conn.execute(
                f"INSERT INTO readiness_snapshots ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            row = conn.execute(
                'SELECT * FROM readiness_snapshots WHERE id = ?', (int(cursor.lastrowid),)
            ).fetchone()
            conn.commit()
            return {'snapshot': self._deserialize_readiness_snapshot(row), 'created': True}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_readiness_snapshot_history(self, target_key):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            '''SELECT * FROM readiness_snapshots
               WHERE target_key = ? ORDER BY revision, id''',
            (str(target_key),),
        ).fetchall()
        conn.close()
        return [self._deserialize_readiness_snapshot(row) for row in rows]

    def get_readiness_snapshots(self, *, capture_mode=None, local_date=None):
        clauses, params = [], []
        if capture_mode is not None:
            clauses.append('capture_mode = ?')
            params.append(str(capture_mode))
        if local_date is not None:
            clauses.append('local_date = ?')
            params.append(str(local_date))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f'''SELECT * FROM readiness_snapshots {where}
                ORDER BY local_date, observed_at_utc, revision, id''',
            tuple(params),
        ).fetchall()
        conn.close()
        return [self._deserialize_readiness_snapshot(row) for row in rows]

    def _deserialize_readiness_snapshot(self, row):
        if row is None:
            return None
        value = dict(row)
        mapping = {
            'eligibility_reasons_json': ('eligibility_reasons', []),
            'factors_json': ('factors', []), 'drivers_json': ('drivers', []),
            'missing_inputs_json': ('missing_inputs', []), 'tsb_json': ('tsb', {}),
            'provenance_json': ('provenance', {}), 'snapshot_json': ('snapshot', {}),
        }
        for source, (target, fallback) in mapping.items():
            value[target] = self._json_load(value.pop(source, None), fallback)
        value['is_provisional'] = bool(value.get('is_provisional'))
        value['stale'] = bool(value.get('stale'))
        return value

    def save_recovery_episode(self, payload):
        """Atomically append one immutable recovery-episode revision."""
        required = {
            'fingerprint', 'target_key', 'session_id', 'session_date',
            'capture_mode', 'status', 'rule_version',
        }
        missing = sorted(required - set(payload or {}))
        if missing:
            raise ValueError(f"missing recovery episode fields: {missing}")
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 30000')
        try:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute(
                'SELECT * FROM recovery_episodes WHERE fingerprint = ?',
                (str(payload['fingerprint']),),
            ).fetchone()
            if existing is not None:
                conn.commit()
                return {'episode': self._deserialize_recovery_episode(existing), 'created': False}
            previous = conn.execute(
                '''SELECT id, revision FROM recovery_episodes
                   WHERE target_key = ? ORDER BY revision DESC, id DESC LIMIT 1''',
                (str(payload['target_key']),),
            ).fetchone()
            revision = int(previous['revision']) + 1 if previous else 1
            scalar_columns = (
                'fingerprint', 'target_key', 'revision', 'supersedes_episode_id',
                'session_id', 'plan_checkpoint_id', 'match_revision_id', 'feedback_id',
                'session_date', 'iso_week', 'capture_mode', 'status', 'rule_version',
                'template_id', 'stimulus_family', 'sport', 'role', 'phase', 'actual_tss',
                'load_bucket', 'adherence', 'rpe_band', 'pre_snapshot_id',
                'd1_snapshot_id', 'd2_snapshot_id', 'd3_snapshot_id',
            )
            scalar_values = (
                str(payload['fingerprint']), str(payload['target_key']), revision,
                int(previous['id']) if previous else None, str(payload['session_id']),
                payload.get('plan_checkpoint_id'), payload.get('match_revision_id'),
                payload.get('feedback_id'), str(payload['session_date']),
                payload.get('iso_week'), str(payload['capture_mode']), str(payload['status']),
                str(payload['rule_version']), payload.get('template_id'),
                payload.get('stimulus_family'), payload.get('sport'), payload.get('role'),
                payload.get('phase'), payload.get('actual_tss'), payload.get('load_bucket'),
                payload.get('adherence'), payload.get('rpe_band'), payload.get('pre_snapshot_id'),
                payload.get('d1_snapshot_id'), payload.get('d2_snapshot_id'),
                payload.get('d3_snapshot_id'),
            )
            json_columns = (
                'exclusion_reasons_json', 'planned_json', 'actual_json', 'feedback_json',
                'outcome_json', 'confounders_json',
            )
            json_values = tuple(
                self._json_value(payload.get(key) or ([] if key == 'exclusion_reasons' else {}))
                for key in ('exclusion_reasons', 'planned', 'actual', 'feedback', 'outcome', 'confounders')
            )
            columns = scalar_columns + json_columns
            values = scalar_values + json_values
            cursor = conn.execute(
                f"INSERT INTO recovery_episodes ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
            row = conn.execute(
                'SELECT * FROM recovery_episodes WHERE id = ?', (int(cursor.lastrowid),)
            ).fetchone()
            conn.commit()
            return {'episode': self._deserialize_recovery_episode(row), 'created': True}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_recovery_episodes(self, *, latest_only=False, capture_mode=None):
        params = []
        where = ''
        if capture_mode is not None:
            where = 'WHERE capture_mode = ?'
            params.append(str(capture_mode))
        if latest_only:
            query = f'''
                SELECT episode.* FROM recovery_episodes episode
                JOIN (
                    SELECT target_key, MAX(revision) AS revision
                    FROM recovery_episodes {where} GROUP BY target_key
                ) latest ON latest.target_key = episode.target_key
                        AND latest.revision = episode.revision
                {'WHERE episode.capture_mode = ?' if capture_mode is not None else ''}
                ORDER BY episode.session_date, episode.target_key
            '''
            query_params = tuple(params + (params if capture_mode is not None else []))
        else:
            query = f'''SELECT * FROM recovery_episodes {where}
                        ORDER BY session_date, target_key, revision'''
            query_params = tuple(params)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, query_params).fetchall()
        conn.close()
        return [self._deserialize_recovery_episode(row) for row in rows]

    def _deserialize_recovery_episode(self, row):
        if row is None:
            return None
        value = dict(row)
        for source, target, fallback in (
            ('exclusion_reasons_json', 'exclusion_reasons', []),
            ('planned_json', 'planned', {}), ('actual_json', 'actual', {}),
            ('feedback_json', 'feedback', {}), ('outcome_json', 'outcome', {}),
            ('confounders_json', 'confounders', {}),
        ):
            value[target] = self._json_load(value.pop(source, None), fallback)
        return value

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
        metrics_window_days=None,
        as_of_date=None,
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
                (date, decision_type, reason, workout_id, chat_id, message_id, metrics_window_days, as_of_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                self.clean_value(date),
                self.clean_value(decision_type),
                self.clean_value(reason),
                self.clean_value(workout_id),
                self.clean_value(chat_id),
                self.clean_value(message_id),
                self.clean_value(metrics_window_days),
                self.clean_value(as_of_date),
            ),
        )
        decision_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, date, decision_type, reason, workout_id, chat_id, message_id,
                   metrics_window_days, as_of_date, created_at
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
            SELECT id, date, decision_type, reason, workout_id, chat_id, message_id,
                   metrics_window_days, as_of_date, created_at
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
            'metrics_window_days': row[7] if len(row) > 8 else None,
            'as_of_date': row[8] if len(row) > 8 else None,
            'created_at': row[9] if len(row) > 9 else row[7],
        }

    def save_recovery_decision(
        self,
        fingerprint,
        outcome,
        reason,
        report,
        plan_checkpoint_id=None,
        date=None,
    ):
        """Идемпотентно сохраняет один исход salience-gate."""
        allowed_outcomes = {"silence", "data_gap", "conflict"}
        fingerprint = str(fingerprint or "").strip()
        outcome = str(outcome or "").strip()
        reason = " ".join(str(reason or "").split())
        if not fingerprint:
            raise ValueError("fingerprint must be non-empty")
        if outcome not in allowed_outcomes:
            raise ValueError(f"outcome must be one of {sorted(allowed_outcomes)}")
        if not reason:
            raise ValueError("reason must be non-empty")
        if not isinstance(report, dict):
            raise ValueError("report must be a dict")

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
            INSERT OR IGNORE INTO recovery_decisions
                (fingerprint, date, outcome, reason, report_json, plan_checkpoint_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                self.clean_value(fingerprint),
                self.clean_value(date),
                self.clean_value(outcome),
                self.clean_value(reason),
                json.dumps(report, ensure_ascii=False, default=str),
                self.clean_value(plan_checkpoint_id),
            ),
        )
        created = cursor.rowcount == 1
        cursor.execute(
            '''
            SELECT id, fingerprint, date, outcome, reason, report_json,
                   plan_checkpoint_id, proposal_id, created_at
            FROM recovery_decisions
            WHERE fingerprint = ?
            LIMIT 1
            ''',
            (fingerprint,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return {"decision": self._deserialize_recovery_decision_row(row), "created": created}

    def link_recovery_decision_proposal(self, decision_id, proposal_id):
        """Связывает recovery decision с durable proposal."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE recovery_decisions
            SET proposal_id = COALESCE(proposal_id, ?)
            WHERE id = ?
            ''',
            (int(proposal_id), int(decision_id)),
        )
        cursor.execute(
            '''
            SELECT id, fingerprint, date, outcome, reason, report_json,
                   plan_checkpoint_id, proposal_id, created_at
            FROM recovery_decisions
            WHERE id = ?
            ''',
            (int(decision_id),),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_recovery_decision_row(row)

    def get_recovery_decisions(self, days=30, limit=100):
        """Возвращает recovery decisions за последние N дней, новые первыми."""
        cutoff_date = self._cutoff_date(days)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, fingerprint, date, outcome, reason, report_json,
                   plan_checkpoint_id, proposal_id, created_at
            FROM recovery_decisions
            WHERE substr(date, 1, 10) >= ?
            ORDER BY date DESC, id DESC
            LIMIT ?
            ''',
            (cutoff_date, max(1, int(limit or 1))),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_recovery_decision_row(row) for row in rows]

    @staticmethod
    def _deserialize_recovery_decision_row(row):
        if not row:
            return None
        try:
            report = json.loads(row[5]) if row[5] else {}
        except (TypeError, json.JSONDecodeError):
            report = {}
        return {
            'id': row[0],
            'fingerprint': row[1],
            'date': row[2],
            'outcome': row[3],
            'reason': row[4],
            'report': report if isinstance(report, dict) else {},
            'plan_checkpoint_id': row[6],
            'proposal_id': row[7],
            'created_at': row[8],
        }

    def save_session_quality_prediction(
        self,
        *,
        fingerprint,
        target_key,
        rule_version,
        target_date,
        plan_checkpoint_id,
        plan_session_index,
        planned_session,
        forecast,
        inputs,
        evidence,
        recovery_decision_id=None,
        created_at=None,
    ):
        """Append one immutable forecast revision, idempotent by fingerprint."""
        if not isinstance(planned_session, dict) or not isinstance(forecast, dict):
            raise ValueError("planned_session and forecast must be dicts")
        if not isinstance(inputs, dict) or not isinstance(evidence, list):
            raise ValueError("inputs must be a dict and evidence must be a list")
        fingerprint = str(fingerprint or "").strip()
        target_key = str(target_key or "").strip()
        rule_version = str(rule_version or "").strip()
        if not fingerprint or not target_key or not rule_version:
            raise ValueError("forecast identity must be non-empty")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            "SELECT id FROM session_quality_predictions WHERE fingerprint = ? LIMIT 1",
            (fingerprint,),
        )
        existing = cursor.fetchone()
        created = existing is None
        if existing is None:
            cursor.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM session_quality_predictions WHERE target_key = ?",
                (target_key,),
            )
            revision = int(cursor.fetchone()[0])
            values = (
                fingerprint,
                target_key,
                revision,
                rule_version,
                str(target_date)[:10],
                int(plan_checkpoint_id),
                int(plan_session_index),
                str(planned_session.get("role") or ""),
                str(planned_session.get("sport") or ""),
                float(planned_session.get("tss") or 0.0),
                planned_session.get("duration_minutes"),
                int(forecast["prediction_pct"]),
                str(forecast["prediction_band"]),
                json.dumps(inputs, ensure_ascii=False, default=str),
                json.dumps(evidence, ensure_ascii=False, default=str),
                self.clean_value(recovery_decision_id),
            )
            if created_at is None:
                cursor.execute(
                    '''
                    INSERT INTO session_quality_predictions
                        (fingerprint, target_key, revision, rule_version, target_date,
                         plan_checkpoint_id, plan_session_index, planned_role, planned_sport,
                         planned_tss, planned_duration_minutes, prediction_pct, prediction_band,
                         input_json, evidence_json, recovery_decision_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    values,
                )
            else:
                cursor.execute(
                    '''
                    INSERT INTO session_quality_predictions
                        (fingerprint, target_key, revision, rule_version, target_date,
                         plan_checkpoint_id, plan_session_index, planned_role, planned_sport,
                         planned_tss, planned_duration_minutes, prediction_pct, prediction_band,
                         input_json, evidence_json, recovery_decision_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (*values, str(created_at)),
                )
            prediction_id = int(cursor.lastrowid)
        else:
            prediction_id = int(existing[0])
            if recovery_decision_id is not None:
                cursor.execute(
                    '''
                    UPDATE session_quality_predictions
                    SET recovery_decision_id = COALESCE(recovery_decision_id, ?)
                    WHERE id = ?
                    ''',
                    (int(recovery_decision_id), prediction_id),
                )
        row = self._select_session_quality_prediction(cursor, prediction_id)
        conn.commit()
        conn.close()
        return {"prediction": self._deserialize_session_quality_prediction_row(row), "created": created}

    @staticmethod
    def _select_session_quality_prediction(cursor, prediction_id):
        cursor.execute(
            '''
            SELECT id, fingerprint, target_key, revision, rule_version, target_date,
                   plan_checkpoint_id, plan_session_index, planned_role, planned_sport,
                   planned_tss, planned_duration_minutes, prediction_pct, prediction_band,
                   input_json, evidence_json, recovery_decision_id, status, plan_adherence,
                   quality_rating_1_5, quality_outcome, actual_activity_ids_json,
                   actual_snapshot_json, unscored_reason, brier_score, resolved_at, created_at
            FROM session_quality_predictions
            WHERE id = ?
            LIMIT 1
            ''',
            (int(prediction_id),),
        )
        return cursor.fetchone()

    def get_session_quality_prediction(self, prediction_id):
        conn = sqlite3.connect(self.db_path)
        row = self._select_session_quality_prediction(conn.cursor(), prediction_id)
        conn.close()
        return self._deserialize_session_quality_prediction_row(row)

    def get_session_quality_predictions(self, days=30, limit=200, target_key=None):
        cutoff_date = self._cutoff_date(days)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        params = [cutoff_date]
        target_clause = ""
        if target_key:
            target_clause = "AND target_key = ?"
            params.append(str(target_key))
        params.append(max(1, int(limit or 1)))
        cursor.execute(
            f'''
            SELECT id, fingerprint, target_key, revision, rule_version, target_date,
                   plan_checkpoint_id, plan_session_index, planned_role, planned_sport,
                   planned_tss, planned_duration_minutes, prediction_pct, prediction_band,
                   input_json, evidence_json, recovery_decision_id, status, plan_adherence,
                   quality_rating_1_5, quality_outcome, actual_activity_ids_json,
                   actual_snapshot_json, unscored_reason, brier_score, resolved_at, created_at
            FROM session_quality_predictions
            WHERE substr(target_date, 1, 10) >= ? {target_clause}
            ORDER BY target_date DESC, target_key ASC, revision ASC
            LIMIT ?
            ''',
            tuple(params),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_session_quality_prediction_row(row) for row in rows]

    def link_session_quality_prediction_decision(self, prediction_id, decision_id):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE session_quality_predictions
            SET recovery_decision_id = COALESCE(recovery_decision_id, ?)
            WHERE id = ?
            ''',
            (int(decision_id), int(prediction_id)),
        )
        row = self._select_session_quality_prediction(cursor, prediction_id)
        conn.commit()
        conn.close()
        return self._deserialize_session_quality_prediction_row(row)

    def resolve_session_quality_prediction_group(self, target_key, resolutions):
        """Atomically resolve pending revisions for one target without rewriting facts."""
        if not isinstance(resolutions, list) or not resolutions:
            raise ValueError("resolutions must be a non-empty list")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        resolved_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        for resolution in resolutions:
            status = str(resolution.get("status") or "")
            if status not in {"scored", "unscored"}:
                conn.rollback()
                conn.close()
                raise ValueError("resolution status must be scored or unscored")
            cursor.execute(
                '''
                UPDATE session_quality_predictions
                SET status = ?, plan_adherence = ?, quality_rating_1_5 = ?,
                    quality_outcome = ?, actual_activity_ids_json = ?,
                    actual_snapshot_json = ?, unscored_reason = ?, brier_score = ?,
                    resolved_at = ?
                WHERE id = ? AND target_key = ? AND status = 'pending'
                ''',
                (
                    status,
                    resolution.get("plan_adherence"),
                    resolution.get("quality_rating_1_5"),
                    resolution.get("quality_outcome"),
                    json.dumps(resolution.get("actual_activity_ids") or [], ensure_ascii=False),
                    json.dumps(resolution.get("actual_snapshot") or {}, ensure_ascii=False, default=str),
                    resolution.get("unscored_reason"),
                    resolution.get("brier_score"),
                    resolved_at,
                    int(resolution["id"]),
                    str(target_key),
                ),
            )
        conn.commit()
        conn.close()
        return self.get_session_quality_predictions(days=36500, target_key=target_key)

    @staticmethod
    def _deserialize_session_quality_prediction_row(row):
        if not row:
            return None

        def _json(raw, fallback):
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                return fallback

        return {
            'id': row[0],
            'fingerprint': row[1],
            'target_key': row[2],
            'revision': row[3],
            'rule_version': row[4],
            'target_date': row[5],
            'plan_checkpoint_id': row[6],
            'plan_session_index': row[7],
            'planned_session': {
                'date': row[5],
                'index': row[7],
                'role': row[8],
                'sport': row[9],
                'tss': row[10],
                'duration_minutes': row[11],
            },
            'prediction_pct': row[12],
            'prediction_band': row[13],
            'inputs': _json(row[14], {}),
            'evidence': _json(row[15], []),
            'recovery_decision_id': row[16],
            'status': row[17],
            'plan_adherence': row[18],
            'quality_rating_1_5': row[19],
            'quality_outcome': row[20],
            'actual_activity_ids': _json(row[21], []),
            'actual_snapshot': _json(row[22], {}),
            'unscored_reason': row[23],
            'brier_score': row[24],
            'resolved_at': row[25],
            'created_at': row[26],
        }

    def get_activities_by_ids(self, activity_ids):
        ids = [str(value) for value in (activity_ids or []) if str(value or "").strip()]
        if not ids:
            return []
        columns = list(self._ACTIVITY_COLUMN_ORDER)
        placeholders = ", ".join("?" for _ in ids)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(columns)} FROM activities WHERE activity_id IN ({placeholders})",
            tuple(ids),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]

    def get_activities_between(self, start_date, end_date):
        columns = list(self._ACTIVITY_COLUMN_ORDER)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {', '.join(columns)} FROM activities WHERE date BETWEEN ? AND ? ORDER BY date, started_at_utc, activity_id",
            (str(start_date), str(end_date)),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(zip(columns, row)) for row in rows]

    def save_plan_actual_match(self, payload):
        """Append one immutable user match revision, idempotent by fingerprint."""
        required = {
            "fingerprint",
            "target_key",
            "base_checkpoint_id",
            "session_date",
            "match_status",
            "match_method",
            "confidence",
            "planned_snapshot",
            "actual_activity_ids",
            "actual_snapshot",
            "evidence",
            "rule_version",
        }
        missing = sorted(key for key in required if key not in payload)
        if missing:
            raise ValueError(f"plan actual match missing fields: {', '.join(missing)}")
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM plan_actual_matches WHERE fingerprint = ? LIMIT 1",
                (str(payload["fingerprint"]),),
            )
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                return self._deserialize_plan_actual_match(existing)
            cursor.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM plan_actual_matches WHERE target_key = ?",
                (str(payload["target_key"]),),
            )
            revision = int(cursor.fetchone()[0])
            cursor.execute(
                '''
                INSERT INTO plan_actual_matches
                    (fingerprint, target_key, revision, supersedes_match_id, session_id,
                     base_checkpoint_id, session_date, match_status, match_method, confidence,
                     planned_snapshot_json, actual_activity_ids_json, actual_snapshot_json,
                     evidence_json, rule_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    str(payload["fingerprint"]),
                    str(payload["target_key"]),
                    revision,
                    payload.get("supersedes_match_id"),
                    payload.get("session_id"),
                    int(payload["base_checkpoint_id"]),
                    str(payload["session_date"]),
                    str(payload["match_status"]),
                    str(payload["match_method"]),
                    float(payload["confidence"]),
                    json.dumps(payload.get("planned_snapshot") or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload.get("actual_activity_ids") or [], ensure_ascii=False),
                    json.dumps(payload.get("actual_snapshot") or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload.get("evidence") or [], ensure_ascii=False),
                    str(payload["rule_version"]),
                ),
            )
            row_id = cursor.lastrowid
            cursor.execute("SELECT * FROM plan_actual_matches WHERE id = ?", (row_id,))
            row = cursor.fetchone()
            conn.commit()
            return self._deserialize_plan_actual_match(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_latest_plan_actual_matches(self, *, start_date, end_date):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT pam.*
            FROM plan_actual_matches pam
            JOIN (
                SELECT target_key, MAX(revision) AS revision
                FROM plan_actual_matches
                WHERE session_date BETWEEN ? AND ?
                GROUP BY target_key
            ) latest
              ON latest.target_key = pam.target_key AND latest.revision = pam.revision
            ORDER BY pam.session_date, pam.target_key
            ''',
            (str(start_date), str(end_date)),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_plan_actual_match(row) for row in rows]

    @staticmethod
    def _deserialize_plan_actual_match(row):
        if not row:
            return None
        def _json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except (TypeError, json.JSONDecodeError):
                return fallback
        return {
            "id": row[0],
            "fingerprint": row[1],
            "target_key": row[2],
            "revision": row[3],
            "supersedes_match_id": row[4],
            "session_id": row[5],
            "base_checkpoint_id": row[6],
            "session_date": row[7],
            "match_status": row[8],
            "match_method": row[9],
            "confidence": row[10],
            "planned_snapshot": _json(row[11], {}),
            "actual_activity_ids": _json(row[12], []),
            "actual_snapshot": _json(row[13], {}),
            "evidence": _json(row[14], []),
            "rule_version": row[15],
            "created_at": row[16],
        }

    def save_session_feedback(self, payload):
        """Append an immutable feedback revision, idempotent by client fingerprint."""
        required = {
            "fingerprint", "target_key", "session_id", "match_snapshot",
            "actual_activity_ids", "completion_status", "source",
            "session_end_provenance", "status", "rule_version", "submitted_at",
        }
        missing = sorted(key for key in required if key not in payload)
        if missing:
            raise ValueError(f"session feedback missing fields: {', '.join(missing)}")
        fingerprint = str(payload.get("fingerprint") or "").strip()
        target_key = str(payload.get("target_key") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not fingerprint or not target_key or not session_id:
            raise ValueError("session feedback identity must be non-empty")
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM session_feedback WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            )
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                return {
                    "feedback": self._deserialize_session_feedback(existing),
                    "created": False,
                    "conflict": False,
                }
            cursor.execute(
                '''
                SELECT * FROM session_feedback
                WHERE target_key = ?
                ORDER BY revision DESC, id DESC
                LIMIT 1
                ''',
                (target_key,),
            )
            latest = cursor.fetchone()
            if "expected_latest_feedback_id" in payload:
                expected_latest_id = payload.get("expected_latest_feedback_id")
                actual_latest_id = latest[0] if latest else None
                if actual_latest_id != expected_latest_id:
                    conn.commit()
                    return {
                        "feedback": self._deserialize_session_feedback(latest),
                        "created": False,
                        "conflict": True,
                    }
            cursor.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM session_feedback WHERE target_key = ?",
                (target_key,),
            )
            revision = int(cursor.fetchone()[0])
            cursor.execute(
                '''
                INSERT INTO session_feedback
                    (fingerprint, target_key, revision, supersedes_feedback_id, session_id,
                     parent_session_id, match_revision_id, match_snapshot_json,
                     actual_activity_ids_json, completion_status, completion_pct,
                     completion_pct_source, session_rpe_1_10, quality_rating_1_5, note,
                     source, session_end_at_utc, session_end_provenance, status,
                     rule_version, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    fingerprint,
                    target_key,
                    revision,
                    payload.get("supersedes_feedback_id"),
                    session_id,
                    payload.get("parent_session_id"),
                    payload.get("match_revision_id"),
                    json.dumps(payload.get("match_snapshot") or {}, ensure_ascii=False, sort_keys=True, default=str),
                    json.dumps(payload.get("actual_activity_ids") or [], ensure_ascii=False),
                    str(payload.get("completion_status") or ""),
                    payload.get("completion_pct"),
                    payload.get("completion_pct_source"),
                    payload.get("session_rpe_1_10"),
                    payload.get("quality_rating_1_5"),
                    self.clean_value(payload.get("note")),
                    str(payload.get("source") or ""),
                    payload.get("session_end_at_utc"),
                    str(payload.get("session_end_provenance") or ""),
                    str(payload.get("status") or "active"),
                    str(payload.get("rule_version") or ""),
                    str(payload.get("submitted_at") or ""),
                ),
            )
            row_id = int(cursor.lastrowid)
            cursor.execute("SELECT * FROM session_feedback WHERE id = ?", (row_id,))
            row = cursor.fetchone()
            conn.commit()
            return {
                "feedback": self._deserialize_session_feedback(row),
                "created": True,
                "conflict": False,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_session_feedback(self, feedback_id):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM session_feedback WHERE id = ? LIMIT 1",
            (int(feedback_id),),
        ).fetchone()
        conn.close()
        return self._deserialize_session_feedback(row)

    def get_session_feedback_by_fingerprint(self, fingerprint):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM session_feedback WHERE fingerprint = ? LIMIT 1",
            (str(fingerprint),),
        ).fetchone()
        conn.close()
        return self._deserialize_session_feedback(row)

    def get_session_feedback_history(self, session_id):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM session_feedback WHERE session_id = ? ORDER BY revision, id",
            (str(session_id),),
        ).fetchall()
        conn.close()
        return [self._deserialize_session_feedback(row) for row in rows]

    def get_latest_session_feedback(self, session_id):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            '''
            SELECT * FROM session_feedback
            WHERE session_id = ?
            ORDER BY revision DESC, id DESC
            LIMIT 1
            ''',
            (str(session_id),),
        ).fetchone()
        conn.close()
        return self._deserialize_session_feedback(row)

    def get_latest_session_feedbacks(self, *, start_date=None, end_date=None):
        conn = sqlite3.connect(self.db_path)
        clauses = []
        params = []
        if start_date is not None:
            clauses.append("substr(sf.submitted_at, 1, 10) >= ?")
            params.append(str(start_date)[:10])
        if end_date is not None:
            clauses.append("substr(sf.submitted_at, 1, 10) <= ?")
            params.append(str(end_date)[:10])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f'''
            SELECT sf.*
            FROM session_feedback sf
            JOIN (
                SELECT target_key, MAX(revision) AS revision
                FROM session_feedback
                GROUP BY target_key
            ) latest
              ON latest.target_key = sf.target_key AND latest.revision = sf.revision
            {where}
            ORDER BY sf.submitted_at DESC, sf.id DESC
            ''',
            tuple(params),
        ).fetchall()
        conn.close()
        return [self._deserialize_session_feedback(row) for row in rows]

    @staticmethod
    def _deserialize_session_feedback(row):
        if not row:
            return None
        def _json(value, fallback):
            try:
                return json.loads(value) if value else fallback
            except (TypeError, json.JSONDecodeError):
                return fallback
        return {
            "id": row[0],
            "fingerprint": row[1],
            "target_key": row[2],
            "revision": row[3],
            "supersedes_feedback_id": row[4],
            "session_id": row[5],
            "parent_session_id": row[6],
            "match_revision_id": row[7],
            "match_snapshot": _json(row[8], {}),
            "actual_activity_ids": _json(row[9], []),
            "completion_status": row[10],
            "completion_pct": row[11],
            "completion_pct_source": row[12],
            "session_rpe_1_10": row[13],
            "quality_rating_1_5": row[14],
            "note": row[15],
            "source": row[16],
            "provenance_label": "athlete-entered" if row[16] == "user_web" else "admin-entered",
            "session_end_at_utc": row[17],
            "session_end_provenance": row[18],
            "status": row[19],
            "rule_version": row[20],
            "submitted_at": row[21],
            "created_at": row[22],
        }

    def save_session_feedback_prompt_event(self, payload):
        required = {"fingerprint", "target_key", "session_id", "event", "source", "rule_version"}
        missing = sorted(key for key in required if key not in payload)
        if missing:
            raise ValueError(f"session feedback prompt event missing fields: {', '.join(missing)}")
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR IGNORE INTO session_feedback_prompt_events
                    (fingerprint, target_key, session_id, prompt_fingerprint,
                     event, reason, source, rule_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    str(payload["fingerprint"]), str(payload["target_key"]),
                    str(payload["session_id"]), payload.get("prompt_fingerprint"),
                    str(payload["event"]),
                    self.clean_value(payload.get("reason")), str(payload["source"]),
                    str(payload["rule_version"]),
                ),
            )
            created = cursor.rowcount == 1
            row = cursor.execute(
                '''
                SELECT id, fingerprint, target_key, session_id, prompt_fingerprint,
                       event, reason, source, rule_version, created_at
                FROM session_feedback_prompt_events
                WHERE fingerprint = ?
                ''',
                (str(payload["fingerprint"]),),
            ).fetchone()
            conn.commit()
            return {"event": self._deserialize_session_feedback_prompt_event(row), "created": created}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_latest_session_feedback_prompt_events(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            '''
            SELECT event.id, event.fingerprint, event.target_key, event.session_id,
                   event.prompt_fingerprint, event.event, event.reason, event.source,
                   event.rule_version, event.created_at
            FROM session_feedback_prompt_events event
            JOIN (
                SELECT session_id, MAX(id) AS id
                FROM session_feedback_prompt_events
                GROUP BY session_id
            ) latest ON latest.id = event.id
            ORDER BY event.id DESC
            '''
        ).fetchall()
        conn.close()
        return [self._deserialize_session_feedback_prompt_event(row) for row in rows]

    @staticmethod
    def _deserialize_session_feedback_prompt_event(row):
        if not row:
            return None
        return {
            "id": row[0], "fingerprint": row[1], "target_key": row[2],
            "session_id": row[3], "prompt_fingerprint": row[4],
            "event": row[5], "reason": row[6],
            "source": row[7], "rule_version": row[8], "created_at": row[9],
        }

    def save_session_quality_evaluation(self, payload):
        """Append one immutable evaluation revision for a forecast prediction."""
        required = {
            "fingerprint", "target_key", "prediction_id", "prediction_target_key",
            "feedback_id", "status", "evidence", "rule_version",
        }
        missing = sorted(key for key in required if key not in payload)
        if missing:
            raise ValueError(f"session quality evaluation missing fields: {', '.join(missing)}")
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM session_quality_evaluations WHERE fingerprint = ? LIMIT 1",
                (str(payload["fingerprint"]),),
            )
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                return {"evaluation": self._deserialize_session_quality_evaluation(existing), "created": False}
            cursor.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM session_quality_evaluations WHERE target_key = ?",
                (str(payload["target_key"]),),
            )
            revision = int(cursor.fetchone()[0])
            cursor.execute(
                '''
                INSERT INTO session_quality_evaluations
                    (fingerprint, target_key, revision, supersedes_evaluation_id,
                     prediction_id, prediction_target_key, feedback_id, match_revision_id,
                     status, plan_adherence, quality_rating_1_5, quality_outcome,
                     unscored_reason, brier_score, evidence_json, rule_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    str(payload["fingerprint"]), str(payload["target_key"]), revision,
                    payload.get("supersedes_evaluation_id"), int(payload["prediction_id"]),
                    str(payload["prediction_target_key"]), int(payload["feedback_id"]),
                    payload.get("match_revision_id"), str(payload["status"]),
                    payload.get("plan_adherence"), payload.get("quality_rating_1_5"),
                    payload.get("quality_outcome"), payload.get("unscored_reason"),
                    payload.get("brier_score"),
                    json.dumps(payload.get("evidence") or {}, ensure_ascii=False, sort_keys=True, default=str),
                    str(payload["rule_version"]),
                ),
            )
            row_id = int(cursor.lastrowid)
            row = cursor.execute(
                "SELECT * FROM session_quality_evaluations WHERE id = ?", (row_id,)
            ).fetchone()
            conn.commit()
            return {"evaluation": self._deserialize_session_quality_evaluation(row), "created": True}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_latest_session_quality_evaluations(self, prediction_ids=None):
        ids = [int(value) for value in (prediction_ids or [])]
        where = ""
        params = []
        if ids:
            placeholders = ", ".join("?" for _ in ids)
            where = f"WHERE prediction_id IN ({placeholders})"
            params.extend(ids)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            f'''
            SELECT evaluation.*
            FROM session_quality_evaluations evaluation
            JOIN (
                SELECT target_key, MAX(revision) AS revision
                FROM session_quality_evaluations
                {where}
                GROUP BY target_key
            ) latest
              ON latest.target_key = evaluation.target_key
             AND latest.revision = evaluation.revision
            ORDER BY evaluation.prediction_id, evaluation.revision
            ''',
            tuple(params),
        ).fetchall()
        conn.close()
        return [self._deserialize_session_quality_evaluation(row) for row in rows]

    def get_session_quality_evaluations(self, *, prediction_ids=None, feedback_ids=None):
        clauses = []
        params = []
        for column, values in (
            ("prediction_id", prediction_ids or []),
            ("feedback_id", feedback_ids or []),
        ):
            normalized = [int(value) for value in values]
            if normalized:
                placeholders = ", ".join("?" for _ in normalized)
                clauses.append(f"{column} IN ({placeholders})")
                params.extend(normalized)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            f'''
            SELECT * FROM session_quality_evaluations
            {where}
            ORDER BY prediction_id, revision, id
            ''',
            tuple(params),
        ).fetchall()
        conn.close()
        return [self._deserialize_session_quality_evaluation(row) for row in rows]

    @staticmethod
    def _deserialize_session_quality_evaluation(row):
        if not row:
            return None
        try:
            evidence = json.loads(row[15]) if row[15] else {}
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        return {
            "id": row[0], "fingerprint": row[1], "target_key": row[2],
            "revision": row[3], "supersedes_evaluation_id": row[4],
            "prediction_id": row[5], "prediction_target_key": row[6],
            "feedback_id": row[7], "match_revision_id": row[8],
            "status": row[9], "plan_adherence": row[10],
            "quality_rating_1_5": row[11], "quality_outcome": row[12],
            "unscored_reason": row[13], "brier_score": row[14],
            "evidence": evidence, "rule_version": row[16], "created_at": row[17],
        }

    def save_coach_proposal(
        self,
        action,
        params,
        preview,
        chat_id=None,
        message_id=None,
        date=None,
        source=None,
        source_key=None,
        active_key=None,
    ):
        """Сохраняет pending-предложение коуча, требующее approve/reject."""
        allowed_actions = {"build_plan", "adjust_plan", "recovery_replan"}
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
        values = (
            self.clean_value(date),
            self.clean_value(action),
            json.dumps(params, ensure_ascii=False, default=str),
            json.dumps(preview, ensure_ascii=False, default=str),
            self.clean_value(chat_id),
            self.clean_value(message_id),
            self.clean_value(source),
            self.clean_value(source_key),
            self.clean_value(active_key),
        )
        if source_key or active_key:
            cursor.execute(
                '''
                INSERT OR IGNORE INTO coach_proposals
                    (date, action, status, params_json, preview_json, chat_id, message_id,
                     source, source_key, active_key)
                VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                ''',
                values,
            )
            row = None
            if source_key:
                cursor.execute(
                    '''
                    SELECT id
                    FROM coach_proposals
                    WHERE source_key = ?
                    LIMIT 1
                    ''',
                    (self.clean_value(source_key),),
                )
                row = cursor.fetchone()
            if row is None and active_key:
                cursor.execute(
                    '''
                    SELECT id
                    FROM coach_proposals
                    WHERE active_key = ? AND status IN ('pending', 'applying')
                    LIMIT 1
                    ''',
                    (self.clean_value(active_key),),
                )
                row = cursor.fetchone()
            if row is None:
                conn.close()
                raise RuntimeError("proposal insert was ignored without an idempotency match")
            proposal_id = row[0]
        else:
            cursor.execute(
                '''
                INSERT INTO coach_proposals
                    (date, action, status, params_json, preview_json, chat_id, message_id,
                     source, source_key, active_key)
                VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                ''',
                values,
            )
            proposal_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at, source, source_key,
                   active_key
            FROM coach_proposals
            WHERE id = ?
            ''',
            (proposal_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_proposal_row(row)

    def update_coach_proposal_preview(self, proposal_id, preview):
        """Обновляет preview ещё pending-предложения (идемпотентный пересчёт
        RecoveryReplan v2 не должен плодить строки — только освежать превью)."""
        if not isinstance(preview, dict):
            raise ValueError("preview must be a dict")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE coach_proposals
            SET preview_json = ?
            WHERE id = ? AND status = 'pending'
            ''',
            (json.dumps(preview, ensure_ascii=False, default=str), int(proposal_id)),
        )
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at, source, source_key,
                   active_key
            FROM coach_proposals
            WHERE id = ?
            ''',
            (int(proposal_id),),
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
                   error, chat_id, message_id, resolved_at, created_at, source, source_key,
                   active_key
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
                       error, chat_id, message_id, resolved_at, created_at, source, source_key,
                       active_key
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
                       error, chat_id, message_id, resolved_at, created_at, source, source_key,
                       active_key
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
        allowed_statuses = {"pending", "approved", "rejected", "failed", "rolled_back"}
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
                   error, chat_id, message_id, resolved_at, created_at, source, source_key,
                   active_key
            FROM coach_proposals
            WHERE id = ?
            ''',
            (int(proposal_id),),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_proposal_row(row)

    def transition_coach_proposal_status(self, proposal_id, from_status, to_status):
        """Атомарно захватывает proposal для apply/rollback без двойной мутации."""
        allowed = {
            ("pending", "applying"),
            ("applying", "pending"),
            ("approved", "rolling_back"),
            ("rolling_back", "approved"),
        }
        transition = (str(from_status), str(to_status))
        if transition not in allowed:
            raise ValueError(f"unsupported proposal transition: {transition}")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE coach_proposals
            SET status = ?
            WHERE id = ? AND status = ?
            ''',
            (transition[1], int(proposal_id), transition[0]),
        )
        claimed = cursor.rowcount == 1
        cursor.execute(
            '''
            SELECT id, date, action, status, params_json, preview_json, result_json,
                   error, chat_id, message_id, resolved_at, created_at, source, source_key,
                   active_key
            FROM coach_proposals
            WHERE id = ?
            ''',
            (int(proposal_id),),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_proposal_row(row) if claimed else None

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
            'source': row[12] if len(row) > 12 else None,
            'source_key': row[13] if len(row) > 13 else None,
            'active_key': row[14] if len(row) > 14 else None,
        }

    def save_coach_constraint(
        self,
        date,
        kind,
        source="coach",
        note=None,
        plan_id=None,
        session_id=None,
        metadata=None,
    ):
        """Сохраняет durable-ограничение, которое должен учитывать replan."""
        allowed_kinds = {
            "sick",
            "unavailable",
            "forced_rest",
            "manual_delete",
            "disabled_plan_day",
        }
        kind = str(kind or "").strip()
        if kind not in allowed_kinds:
            raise ValueError(f"kind must be one of {sorted(allowed_kinds)}")

        source = str(source or "coach").strip()
        if not source:
            source = "coach"

        date_value = str(date or "").strip()[:10]
        if not date_value:
            raise ValueError("date must be non-empty")

        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dict")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO coach_constraints
                (date, kind, status, source, note, plan_id, session_id, metadata_json)
            VALUES (?, ?, 'active', ?, ?, ?, ?, ?)
            ''',
            (
                self.clean_value(date_value),
                self.clean_value(kind),
                self.clean_value(source),
                self.clean_value(note),
                self.clean_value(plan_id),
                self.clean_value(session_id),
                json.dumps(metadata, ensure_ascii=False, default=str),
            ),
        )
        constraint_id = cursor.lastrowid
        cursor.execute(
            '''
            SELECT id, date, kind, status, source, note, plan_id, session_id,
                   metadata_json, resolved_at, created_at
            FROM coach_constraints
            WHERE id = ?
            ''',
            (constraint_id,),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_constraint_row(row)

    def get_coach_constraint(self, constraint_id):
        """Возвращает одно durable-ограничение по id или None."""
        if constraint_id is None:
            return None
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, date, kind, status, source, note, plan_id, session_id,
                   metadata_json, resolved_at, created_at
            FROM coach_constraints
            WHERE id = ?
            LIMIT 1
            ''',
            (int(constraint_id),),
        )
        row = cursor.fetchone()
        conn.close()
        return self._deserialize_coach_constraint_row(row)

    def get_coach_constraints(
        self,
        start_date=None,
        end_date=None,
        active_only=True,
        limit=100,
    ):
        """Возвращает durable-ограничения за окно дат, новые первыми внутри даты."""
        clauses = []
        params = []
        if start_date:
            clauses.append("date >= ?")
            params.append(str(start_date)[:10])
        if end_date:
            clauses.append("date <= ?")
            params.append(str(end_date)[:10])
        if active_only:
            clauses.append("status = 'active'")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            f'''
            SELECT id, date, kind, status, source, note, plan_id, session_id,
                   metadata_json, resolved_at, created_at
            FROM coach_constraints
            {where}
            ORDER BY date ASC, id ASC
            LIMIT ?
            ''',
            (*params, max(1, int(limit or 1))),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._deserialize_coach_constraint_row(row) for row in rows]

    def deactivate_coach_constraint(self, constraint_id):
        """Деактивирует constraint, сохраняя строку как audit trail."""
        resolved_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE coach_constraints
            SET status = 'inactive', resolved_at = ?
            WHERE id = ?
            ''',
            (self.clean_value(resolved_at), int(constraint_id)),
        )
        cursor.execute(
            '''
            SELECT id, date, kind, status, source, note, plan_id, session_id,
                   metadata_json, resolved_at, created_at
            FROM coach_constraints
            WHERE id = ?
            ''',
            (int(constraint_id),),
        )
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return self._deserialize_coach_constraint_row(row)

    def _deserialize_coach_constraint_row(self, row):
        if not row:
            return None
        metadata = {}
        if row[8]:
            try:
                parsed = json.loads(row[8])
                metadata = parsed if isinstance(parsed, dict) else {}
            except (TypeError, json.JSONDecodeError):
                metadata = {}
        return {
            'id': row[0],
            'date': row[1],
            'kind': row[2],
            'status': row[3],
            'source': row[4],
            'note': row[5],
            'plan_id': row[6],
            'session_id': row[7],
            'metadata': metadata,
            'resolved_at': row[9],
            'created_at': row[10],
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

    def _resolve_garmin_coordinate(self, cursor, garmin_id):
        """Assign ``canonical_activity_id`` + ``match_status`` for every link that
        shares the Garmin coordinate ``(garmin, garmin_id)``, order-independently.

        A Garmin coordinate is the only mergeable namespace in the beta: the Garmin
        self-link (``provider_activity_id == garmin_id``) plus any Intervals links
        that reference it. Rules (ADR-0008 п.2):
        - exactly one Intervals claimant + a Garmin link → unique match → both on
          ``garmin_id``, ``matched``;
        - exactly one Intervals claimant, no Garmin link → standalone, ``unmatched``
          (pending the Garmin activity);
        - two+ Intervals claimants → ambiguous: NONE merges — every one goes to its
          own ``intervals_<id>`` canonical and is flagged ``ambiguous`` (so no
          arbitrary first-arrival winner).

        Returns the set of canonical ids touched (old + new), for reprojection.
        """
        # The Garmin activity is identified by its provider_activity_id (the Garmin id
        # IS the coordinate), NOT by a self-referential external_id — so a BACKFILLED
        # Garmin self-link (external_id NULL, ADR-0008 п.7) is still found and merges
        # with its Intervals copy. Intervals copies reference it via the external
        # coordinate (garmin, id). An OR returns each row once, so no dedup is needed.
        cursor.execute(
            "SELECT id, provider, provider_activity_id, canonical_activity_id "
            "FROM activity_provider_links "
            "WHERE (provider='garmin' AND provider_activity_id=?) "
            "   OR (external_provider='garmin' AND external_id=?)",
            (garmin_id, garmin_id),
        )
        links = cursor.fetchall()
        touched = {row[3] for row in links}  # current canonicals, before reassignment
        garmin_links = [row for row in links if row[1] == 'garmin']
        intervals_links = [row for row in links if row[1] == 'intervals']

        def assign(link_id, canonical, status):
            cursor.execute(
                'UPDATE activity_provider_links SET canonical_activity_id=?, match_status=? WHERE id=?',
                (canonical, status, link_id),
            )
            touched.add(canonical)

        if len(intervals_links) >= 2:
            for row in intervals_links:
                assign(row[0], f"intervals_{row[2]}", 'ambiguous')
            for row in garmin_links:
                assign(row[0], garmin_id, 'unmatched')
        elif len(intervals_links) == 1:
            interval = intervals_links[0]
            if garmin_links:
                assign(interval[0], garmin_id, 'matched')
                for row in garmin_links:
                    assign(row[0], garmin_id, 'matched')
            else:
                assign(interval[0], f"intervals_{interval[2]}", 'unmatched')
        else:
            for row in garmin_links:
                assign(row[0], garmin_id, 'unmatched')

        return touched

    def _project_canonical(self, cursor, canonical_id, primary_source):
        """Rebuild the ``activities`` row for ``canonical_id`` from the payloads of
        its provider-links (ADR-0008 п.4). The primary source's payload wins; absent
        it, the alphabetically-first provider's payload (deterministic). A canonical
        with no links is deleted; one whose links carry no payload is left untouched.
        This is what makes merges, demotions and identity changes lossless and
        order-independent — canonical fields are always a pure function of the links.
        """
        cursor.execute(
            'SELECT provider, provider_payload FROM activity_provider_links '
            'WHERE canonical_activity_id=?',
            (canonical_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute('DELETE FROM activities WHERE activity_id=?', (canonical_id,))
            return
        payloads = {}
        for provider, payload_json in rows:
            if payload_json:
                try:
                    payloads[provider] = json.loads(payload_json)
                except (TypeError, ValueError):
                    continue
        if not payloads:
            return  # e.g. legacy links without a snapshot — keep the existing row
        chosen = payloads.get(primary_source) or payloads[min(payloads)]
        row = {**chosen, 'activity_id': canonical_id}
        columns = self._ACTIVITY_COLUMN_ORDER
        # Create-or-update rather than INSERT OR REPLACE: REPLACE deletes+reinserts
        # and re-stamps the `created_at` default, so a repeat projection of identical
        # data would churn created_at. An UPDATE of the projected columns leaves
        # created_at untouched (idempotent).
        cursor.execute('SELECT 1 FROM activities WHERE activity_id=?', (canonical_id,))
        if cursor.fetchone() is None:
            values = tuple(self.clean_value(row.get(column)) for column in columns)
            cursor.execute(
                f"INSERT INTO activities ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
        else:
            update_columns = [column for column in columns if column != 'activity_id']
            set_sql = ', '.join(f"{column}=?" for column in update_columns)
            values = [self.clean_value(row.get(column)) for column in update_columns]
            values.append(canonical_id)
            cursor.execute(f"UPDATE activities SET {set_sql} WHERE activity_id=?", tuple(values))

    def write_provider_activity(self, canonical, link, *, primary_source):
        """ADR-0008 (#269): atomically write ONE provider activity — provider-link
        (with its field snapshot) + a re-projected canonical row — in a SINGLE
        transaction. Does NOT advance any sync cursor: cursor advance is a
        batch-level step (see ``services.activity_ingest.ingest_provider_batch``),
        never inside a per-activity transaction.

        The link stores the source's normalized fields (``provider_payload``); the
        canonical ``activities`` row is then a deterministic PROJECTION of the links
        (:meth:`_project_canonical`). Canonical assignment for a Garmin coordinate is
        resolved order-independently by :meth:`_resolve_garmin_coordinate`. Together
        these make every event — first ingest, cross-provider merge, ambiguous
        duplicate, external-identity change — lossless and independent of arrival
        order, and guarantee no link is ever left without its canonical.

        ``link`` carries ``provider``, ``provider_activity_id``,
        ``external_provider``, ``external_id``, ``provider_tss`` and a
        ``standalone_canonical_id``. ``primary_source`` decides which provider's
        payload is authoritative for the canonical row; the data layer stays
        config-agnostic and receives the resolved value.
        """
        provider = link.get('provider')
        provider_activity_id = self.clean_value(link.get('provider_activity_id'))
        if not provider or not provider_activity_id:
            raise ValueError(
                "write_provider_activity: link requires provider and provider_activity_id"
            )
        standalone_id = (
            self.clean_value(link.get('standalone_canonical_id'))
            or self.clean_value(canonical.get('activity_id'))
        )
        if not standalone_id:
            raise ValueError("write_provider_activity: a canonical/standalone id is required")
        external_provider = self.clean_value(link.get('external_provider'))
        external_id = self.clean_value(link.get('external_id'))
        provider_tss = self.clean_value(link.get('provider_tss'))
        payload_json = json.dumps(canonical, default=str)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Existing link → re-ingest idempotency + external-identity-change detection.
            cursor.execute(
                'SELECT id, canonical_activity_id, external_provider, external_id '
                'FROM activity_provider_links WHERE provider=? AND provider_activity_id=?',
                (provider, provider_activity_id),
            )
            existing_link = cursor.fetchone()
            affected = set()
            old_garmin_coord = None
            if existing_link:
                affected.add(existing_link[1])
                if existing_link[2] == 'garmin':
                    old_garmin_coord = existing_link[3]
                cursor.execute(
                    '''UPDATE activity_provider_links
                       SET canonical_activity_id=?, external_provider=?, external_id=?,
                           provider_tss=?, provider_payload=?, match_status='unmatched'
                       WHERE id=?''',
                    (standalone_id, external_provider, external_id, provider_tss,
                     payload_json, existing_link[0]),
                )
            else:
                cursor.execute(
                    '''INSERT INTO activity_provider_links
                         (canonical_activity_id, provider, provider_activity_id,
                          external_provider, external_id, provider_tss, provider_payload,
                          match_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'unmatched')''',
                    (standalone_id, provider, provider_activity_id,
                     external_provider, external_id, provider_tss, payload_json),
                )
            affected.add(standalone_id)

            # Resolve canonical assignment for the affected Garmin coordinate(s): the
            # new one, and the old one too if the coordinate changed.
            new_garmin_coord = external_id if external_provider == 'garmin' else None
            if new_garmin_coord:
                affected |= self._resolve_garmin_coordinate(cursor, new_garmin_coord)
            if old_garmin_coord and old_garmin_coord != new_garmin_coord:
                affected |= self._resolve_garmin_coordinate(cursor, old_garmin_coord)

            # Re-project every touched canonical from its links (lossless & ordered).
            for canonical_id in affected:
                self._project_canonical(cursor, canonical_id, primary_source)

            cursor.execute(
                'SELECT canonical_activity_id, match_status FROM activity_provider_links '
                'WHERE provider=? AND provider_activity_id=?',
                (provider, provider_activity_id),
            )
            final = cursor.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            'canonical_activity_id': final[0],
            'provider': provider,
            'match_status': final[1],
            'ambiguous': final[1] == 'ambiguous',
        }

    def backfill_activity_provider_links(self, classify):
        """ADR-0008 п.7 (#269): offline, idempotent backfill — one provider-link per
        existing canonical activity, classified by ``classify(activity_id)`` (the
        service owns the policy; the data layer stays policy-free). Never touches
        the network; ``external_id`` stays NULL (a later ingest attaches the
        cross-provider link when Intervals data arrives). ``provider_tss`` ← current
        ``source_tss``. Re-running inserts nothing new and mutates no classification.
        """
        columns = self._ACTIVITY_COLUMN_ORDER
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {', '.join(columns)} FROM activities")
            activity_rows = cursor.fetchall()
            # An activity already COVERED by any provider-link (its id is some link's
            # canonical_activity_id) must be skipped — including projection-created
            # canonicals like `intervals_<id>`, which would otherwise be misclassified
            # as `legacy_unknown` and get a spurious second link. Backfill is only for
            # legacy activities that predate the provider-link model.
            cursor.execute('SELECT canonical_activity_id FROM activity_provider_links')
            covered = {row[0] for row in cursor.fetchall()}

            counts = {'garmin': 0, 'demo': 0, 'legacy_unknown': 0, 'skipped_existing': 0}
            for values in activity_rows:
                record = dict(zip(columns, values))
                activity_id = record.get('activity_id')
                if not activity_id:
                    continue
                if activity_id in covered:
                    counts['skipped_existing'] += 1
                    continue
                provider = classify(activity_id)
                # Snapshot the existing canonical fields onto the link so the link is
                # self-describing (projection stays lossless if the row is later
                # re-derived from the link set).
                payload_json = json.dumps(record, default=str)
                cursor.execute(
                    '''INSERT INTO activity_provider_links
                         (canonical_activity_id, provider, provider_activity_id,
                          external_provider, external_id, provider_tss, provider_payload,
                          match_status)
                       VALUES (?, ?, ?, NULL, NULL, ?, ?, 'unmatched')''',
                    (activity_id, provider, activity_id,
                     self.clean_value(record.get('source_tss')), payload_json),
                )
                covered.add(activity_id)
                counts[provider] = counts.get(provider, 0) + 1

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return counts

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

        try:
            cursor.execute('DELETE FROM recovery_decisions')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('DELETE FROM session_quality_predictions')
        except sqlite3.OperationalError:
            pass

        for table in (
            'session_feedback',
            'session_feedback_prompt_events',
            'session_quality_evaluations',
            'readiness_snapshots',
            'recovery_episodes',
            'athlete_profile',
            # ADR-0008 (#269): provider-links must be cleared with activities, else
            # a reset leaves orphan links that double-count load on the next sync.
            'activity_provider_links',
        ):
            try:
                cursor.execute(f'DELETE FROM {table}')
            except sqlite3.OperationalError:
                pass

        try:
            cursor.execute('DELETE FROM coach_constraints')
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

        try:
            cursor.execute('SELECT COUNT(*) FROM coach_constraints')
            coach_constraints_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            coach_constraints_count = 0

        try:
            cursor.execute('SELECT COUNT(*) FROM recovery_decisions')
            recovery_decisions_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            recovery_decisions_count = 0

        try:
            cursor.execute('SELECT COUNT(*) FROM session_quality_predictions')
            session_quality_predictions_count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            session_quality_predictions_count = 0

        journal_counts = {}
        for table in (
            'session_feedback',
            'session_feedback_prompt_events',
            'session_quality_evaluations',
            'readiness_snapshots',
            'recovery_episodes',
        ):
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {table}')
                journal_counts[table] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                journal_counts[table] = 0
        
        conn.close()
        
        return {
            'activities': activities_count,
            'hrv_data': hrv_count,
            'user_settings': settings_count,
            'sleep_data': sleep_count,
            'daily_health': health_count,
            'training_status': training_count,
            'coach_decisions': coach_decisions_count,
            'coach_proposals': coach_proposals_count,
            'coach_constraints': coach_constraints_count,
            'recovery_decisions': recovery_decisions_count,
            'session_quality_predictions': session_quality_predictions_count,
            **journal_counts,
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
                    bedtime=?, wakeup_time=?, sleep_efficiency=?,
                    awake_sleep_minutes=?, sleep_score_source=?,
                    sleep_efficiency_source=?
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
                    self.clean_value(data.get('awake_sleep_minutes')),
                    self.clean_value(data.get('sleep_score_source') or 'legacy_unknown'),
                    self.clean_value(data.get('sleep_efficiency_source') or 'legacy_unknown'),
                    clean_date
                ))
                updated_count += 1
            else:
                # Вставляем новую запись
                cursor.execute('''
                    INSERT INTO sleep_data 
                    (date, total_sleep_minutes, deep_sleep_minutes, light_sleep_minutes,
                     rem_sleep_minutes, awakenings_count, sleep_score, bedtime, 
                     wakeup_time, sleep_efficiency, awake_sleep_minutes,
                     sleep_score_source, sleep_efficiency_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    self.clean_value(data.get('sleep_efficiency')),
                    self.clean_value(data.get('awake_sleep_minutes')),
                    self.clean_value(data.get('sleep_score_source') or 'legacy_unknown'),
                    self.clean_value(data.get('sleep_efficiency_source') or 'legacy_unknown')
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
