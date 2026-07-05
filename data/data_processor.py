import pandas as pd
import numpy as np
from datetime import datetime

from config.settings import Settings
from utils.product_semantics import normalize_sport_key


def resolve_athlete_ftp_lthr(database):
    """Return (ftp, lthr) to use for TSS math: the athlete's Intervals.icu-synced
    profile when available, falling back to the static Settings.USER_FTP/USER_LTHR
    for any field the synced profile does not have (or when nothing has been
    synced yet)."""
    profile = database.get_athlete_profile()
    if not profile:
        return Settings.USER_FTP, Settings.USER_LTHR
    ftp = profile.get('ftp') or Settings.USER_FTP
    lthr = profile.get('lthr') or Settings.USER_LTHR
    return ftp, lthr

class ActivityProcessor:
    _GARMIN_SOURCE_TSS_KEYS = (
        'activityTrainingLoad',
        'trainingLoad',
        'trainingStressScore',
        'activityTrainingStressScore',
    )
    _SWIM_HR_ZONE_TSS_WEIGHTS = (0.0, 0.4, 0.5, 0.6, 1.8)
    _RUN_HR_ZONE_TSS_WEIGHTS = (0.45, 0.7, 1.0, 1.2, 1.5)
    _BIKE_HR_ZONE_TSS_WEIGHTS = (0.2, 0.35, 0.65, 0.95, 1.3)
    _RUN_FALLBACK_TSS_PER_HOUR = 50.0
    _BIKE_FALLBACK_TSS_PER_HOUR = 60.0
    _SWIM_FALLBACK_TSS_PER_HOUR = 25.0
    _WALK_SHORT_TSS_PER_HOUR = 9.0
    _WALK_LONG_TSS_PER_HOUR = 7.0
    _WALK_SHORT_SESSION_THRESHOLD_MINUTES = 45.0
    _WALK_MIN_MOVING_MINUTES_FOR_FLOOR = 8.0
    _WALK_MIN_TSS_FLOOR = 2.0
    _STRENGTH_FALLBACK_TSS_PER_HOUR = 22.0
    _OTHER_FALLBACK_TSS_PER_HOUR = 20.0

    @staticmethod
    def _safe_float(value, default=None):
        try:
            if value is None or pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _extract_source_tss(cls, activity):
        for key in cls._GARMIN_SOURCE_TSS_KEYS:
            value = cls._safe_float(activity.get(key))
            if value is not None and value > 0:
                return round(value, 1)
        return None

    @classmethod
    def _extract_first_numeric(cls, activity, *keys):
        for key in keys:
            value = cls._safe_float(activity.get(key))
            if value is not None:
                return value
        return None

    @classmethod
    def _duration_minutes(cls, seconds_value):
        seconds = cls._safe_float(seconds_value)
        if seconds is None or seconds <= 0:
            return 0
        return seconds / 60

    @staticmethod
    def _tss_duration_minutes(activity_data):
        moving = ActivityProcessor._safe_float(activity_data.get('moving_duration_minutes'))
        if moving is not None and moving > 0:
            return moving
        duration = ActivityProcessor._safe_float(activity_data.get('duration_minutes'))
        if duration is not None and duration > 0:
            return duration
        return 0

    @staticmethod
    def _hr_tss(duration_minutes, avg_hr, lthr):
        if duration_minutes <= 0 or not lthr or lthr <= 0 or not avg_hr or avg_hr <= 0:
            return None
        duration_hours = duration_minutes / 60
        intensity_factor = avg_hr / lthr
        return round(duration_hours * intensity_factor ** 2 * 100, 1)

    @staticmethod
    def _power_tss(duration_minutes, avg_power, ftp):
        if duration_minutes <= 0 or not ftp or ftp <= 0 or not avg_power or avg_power <= 0:
            return None
        duration_hours = duration_minutes / 60
        intensity_factor = avg_power / ftp
        return round(duration_hours * intensity_factor ** 2 * 100, 1)

    @classmethod
    def _zone_weighted_tss(cls, activity_data, weights):
        total = 0.0
        has_zone_data = False

        for zone_index, weight in enumerate(weights, start=1):
            seconds = cls._safe_float(activity_data.get(f'hr_time_in_zone_{zone_index}_seconds'))
            if seconds is None or seconds <= 0:
                continue
            has_zone_data = True
            total += (seconds / 60) * weight

        if not has_zone_data:
            return None
        return round(total, 1)

    @classmethod
    def _heuristic_tss(cls, sport_key, duration_minutes):
        duration_hours = max(duration_minutes, 0) / 60
        if duration_hours <= 0:
            return 0.0, 'no_duration'

        if sport_key == 'walk':
            base_tss = (
                cls._WALK_SHORT_TSS_PER_HOUR
                if duration_minutes < cls._WALK_SHORT_SESSION_THRESHOLD_MINUTES
                else cls._WALK_LONG_TSS_PER_HOUR
            )
            method = 'heuristic_duration_walk'
            walk_tss = round(duration_hours * base_tss, 1)
            if duration_minutes >= cls._WALK_MIN_MOVING_MINUTES_FOR_FLOOR:
                walk_tss = max(cls._WALK_MIN_TSS_FLOOR, walk_tss)
            return walk_tss, method
        elif sport_key == 'swim':
            base_tss = cls._SWIM_FALLBACK_TSS_PER_HOUR
            method = 'heuristic_duration_swim'
        elif sport_key == 'run':
            base_tss = cls._RUN_FALLBACK_TSS_PER_HOUR
            method = 'heuristic_duration_run'
        elif sport_key == 'bike':
            base_tss = cls._BIKE_FALLBACK_TSS_PER_HOUR
            method = 'heuristic_duration_bike'
        elif sport_key in {'strength', 'yoga'}:
            base_tss = cls._STRENGTH_FALLBACK_TSS_PER_HOUR
            method = f'heuristic_duration_{sport_key}'
        else:
            base_tss = cls._OTHER_FALLBACK_TSS_PER_HOUR
            method = 'heuristic_duration_other'

        return round(duration_hours * base_tss, 1), method
    
    @staticmethod
    def process_activities(activities_data):
        """Преобразование данных активностей в DataFrame"""
        if not activities_data:
            return pd.DataFrame()
        
        processed = []
        
        for activity in activities_data:
            try:
                # Безопасное извлечение данных с проверками
                activity_id = activity.get('activityId', str(datetime.now().timestamp()))
                
                # Парсинг даты
                start_time = activity.get('startTimeLocal', activity.get('startTimeGMT', ''))
                if start_time:
                    try:
                        if 'T' in start_time:
                            date = datetime.fromisoformat(start_time.replace('Z', '+00:00')).date()
                        else:
                            date = datetime.strptime(start_time[:10], '%Y-%m-%d').date()
                    except:
                        date = datetime.now().date()
                else:
                    date = datetime.now().date()
                
                # Извлечение типа активности
                activity_type = activity.get('activityType', {})
                if isinstance(activity_type, dict):
                    sport = activity_type.get('typeKey', 'unknown')
                else:
                    sport = str(activity_type) if activity_type else 'unknown'
                
                # Обработка числовых полей с безопасными значениями по умолчанию
                processed.append({
                    'activity_id': activity_id,
                    'date': date,
                    'sport': sport,
                    'duration_minutes': ActivityProcessor._duration_minutes(activity.get('duration')),
                    'moving_duration_minutes': ActivityProcessor._duration_minutes(activity.get('movingDuration')),
                    'distance_km': float(activity.get('distance', 0)) / 1000 if activity.get('distance') else 0,
                    'avg_hr': activity.get('averageHR') if activity.get('averageHR') else None,
                    'max_hr': activity.get('maxHR') if activity.get('maxHR') else None,
                    'avg_power': ActivityProcessor._extract_first_numeric(activity, 'avgPower', 'averagePower'),
                    'max_power': activity.get('maxPower') if activity.get('maxPower') else None,
                    'normalized_power': ActivityProcessor._extract_first_numeric(activity, 'normPower', 'normalizedPower'),
                    'elevation_gain': float(activity.get('elevationGain', 0)) if activity.get('elevationGain') else 0,
                    'calories': int(activity.get('calories', 0)) if activity.get('calories') else 0,
                    'training_effect': float(activity.get('aerobicTrainingEffect', 0)) if activity.get('aerobicTrainingEffect') else None,
                    'anaerobic_effect': float(activity.get('anaerobicTrainingEffect', 0)) if activity.get('anaerobicTrainingEffect') else None,
                    'activity_name': activity.get('activityName', ''),
                    'description': activity.get('description', ''),
                    'garmin_training_load': ActivityProcessor._extract_source_tss(activity),
                    'source_tss': ActivityProcessor._extract_source_tss(activity),
                    'moderate_intensity_minutes': ActivityProcessor._safe_float(activity.get('moderateIntensityMinutes')),
                    'vigorous_intensity_minutes': ActivityProcessor._safe_float(activity.get('vigorousIntensityMinutes')),
                    'hr_time_in_zone_1_seconds': ActivityProcessor._safe_float(activity.get('hrTimeInZone_1')),
                    'hr_time_in_zone_2_seconds': ActivityProcessor._safe_float(activity.get('hrTimeInZone_2')),
                    'hr_time_in_zone_3_seconds': ActivityProcessor._safe_float(activity.get('hrTimeInZone_3')),
                    'hr_time_in_zone_4_seconds': ActivityProcessor._safe_float(activity.get('hrTimeInZone_4')),
                    'hr_time_in_zone_5_seconds': ActivityProcessor._safe_float(activity.get('hrTimeInZone_5')),
                })
                
            except Exception as e:
                print(f"Ошибка обработки активности {activity.get('activityId', 'unknown')}: {e}")
                continue
        
        if not processed:
            return pd.DataFrame()
        
        df = pd.DataFrame(processed)
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    @classmethod
    def resolve_tss(cls, activity_data, ftp=None, lthr=None):
        """Resolve the stored activity load and explain where it came from."""
        source_tss = cls._safe_float(activity_data.get('source_tss'))
        garmin_training_load = cls._safe_float(activity_data.get('garmin_training_load'))
        if garmin_training_load is None and source_tss is not None and source_tss > 0:
            garmin_training_load = round(source_tss, 1)
        elif garmin_training_load is not None and garmin_training_load > 0:
            garmin_training_load = round(garmin_training_load, 1)
        else:
            garmin_training_load = None

        duration_minutes = cls._tss_duration_minutes(activity_data)
        if duration_minutes <= 0:
            return {
                'tss': 0.0,
                'source_tss': garmin_training_load,
                'garmin_training_load': garmin_training_load,
                'tss_method': 'no_duration',
                'tss_ftp_used': None,
            }

        sport_key = normalize_sport_key(activity_data.get('sport'))
        avg_power = cls._safe_float(activity_data.get('avg_power'))
        normalized_power = cls._safe_float(activity_data.get('normalized_power'))
        avg_hr = cls._safe_float(activity_data.get('avg_hr'))

        if sport_key == 'bike':
            # Normalized power (NP) reflects variable-intensity efforts (surges,
            # coasting) far better than a flat average; Garmin already computes
            # and returns it as normPower in the same payload as avgPower, so we
            # only fall back to avg_power when NP is unavailable.
            power_tss = cls._power_tss(
                duration_minutes,
                normalized_power if normalized_power is not None else avg_power,
                ftp,
            )
            if power_tss is not None:
                return {
                    'tss': power_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'power_tss_bike',
                    'tss_ftp_used': ftp,
                }
            bike_zone_tss = cls._zone_weighted_tss(activity_data, cls._BIKE_HR_ZONE_TSS_WEIGHTS)
            if bike_zone_tss is not None:
                return {
                    'tss': bike_zone_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_zone_tss_bike',
                    'tss_ftp_used': None,
                }
            hr_tss = cls._hr_tss(duration_minutes, avg_hr, lthr)
            if hr_tss is not None:
                return {
                    'tss': hr_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_tss_bike',
                    'tss_ftp_used': None,
                }
        elif sport_key == 'swim':
            swim_zone_tss = cls._zone_weighted_tss(activity_data, cls._SWIM_HR_ZONE_TSS_WEIGHTS)
            if swim_zone_tss is not None:
                return {
                    'tss': swim_zone_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_zone_tss_swim',
                    'tss_ftp_used': None,
                }
            hr_tss = cls._hr_tss(duration_minutes, avg_hr, lthr)
            if hr_tss is not None:
                return {
                    'tss': hr_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_tss_swim',
                    'tss_ftp_used': None,
                }
        elif sport_key == 'run':
            run_zone_tss = cls._zone_weighted_tss(activity_data, cls._RUN_HR_ZONE_TSS_WEIGHTS)
            if run_zone_tss is not None:
                return {
                    'tss': run_zone_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_zone_tss_run',
                    'tss_ftp_used': None,
                }
            hr_tss = cls._hr_tss(duration_minutes, avg_hr, lthr)
            if hr_tss is not None:
                return {
                    'tss': hr_tss,
                    'source_tss': garmin_training_load,
                    'garmin_training_load': garmin_training_load,
                    'tss_method': 'hr_tss_run',
                    'tss_ftp_used': None,
                }

        estimated_tss, method = cls._heuristic_tss(sport_key, duration_minutes)
        return {
            'tss': estimated_tss,
            'source_tss': garmin_training_load,
            'garmin_training_load': garmin_training_load,
            'tss_method': method,
            'tss_ftp_used': None,
        }

    @classmethod
    def calculate_tss(cls, activity_data, ftp=None, lthr=None):
        """Совместимый обёрточный расчёт Training Stress Score."""
        return cls.resolve_tss(activity_data, ftp=ftp, lthr=lthr)['tss']
    
    @staticmethod
    def get_sport_translation(sport_key):
        """Перевод типов активностей на русский язык"""
        translations = {
            'running': 'Бег',
            'cycling': 'Велосипед', 
            'swimming': 'Плавание',
            'walking': 'Ходьба',
            'hiking': 'Походы',
            'strength_training': 'Силовая',
            'yoga': 'Йога',
            'unknown': 'Неизвестно'
        }
        return translations.get(sport_key.lower(), sport_key.title())
