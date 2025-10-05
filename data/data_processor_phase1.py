"""
Процессор данных для Фазы 1 - обработка расширенных данных Garmin
"""

from datetime import datetime, timedelta, timezone
import pandas as pd

class Phase1DataProcessor:
    """Класс для обработки новых типов данных Фазы 1"""
    
    @staticmethod
    def process_sleep_data(sleep_raw_data):
        """Обработка сырых данных сна от Garmin с четким приоритетом источников и датой."""
        if not sleep_raw_data or not isinstance(sleep_raw_data, dict):
            print("DEBUG PROCESSOR: sleep_raw_data пуст или имеет неверный тип.")
            return None
        
        # Проверяем наличие календарной даты
        calendar_date = sleep_raw_data.get('calendarDate')
        if not calendar_date:
            # Пытаемся получить дату из временной метки окончания сна
            end_ts = sleep_raw_data.get('sleepEndTimestampLocal')
            end_dt = Phase1DataProcessor._parse_local_timestamp(end_ts)
            if end_dt:
                calendar_date = end_dt.strftime('%Y-%m-%d')

        print(f"DEBUG PROCESSOR: Начинаем обработку данных сна. Ключи: {list(sleep_raw_data.keys())}")
        
        processed_data = {}
        
        try:
            # 1. Извлекаем ключевые объекты
            sleep_dto = sleep_raw_data.get('dailySleepDTO', {})
            sleep_scores = sleep_raw_data.get('sleepScores', {})

            # 2. Получаем общее время сна (самый надежный показатель)
            total_minutes = sleep_dto.get('sleepTimeSeconds', 0) // 60
            processed_data['total_sleep_minutes'] = total_minutes
            print(f"DEBUG PROCESSOR: Общее время сна: {total_minutes} минут.")

            # 3. Определяем фазы сна по приоритету
            deep_s = sleep_dto.get('deepSleepSeconds')
            light_s = sleep_dto.get('lightSleepSeconds')
            rem_s = sleep_dto.get('remSleepSeconds')

            # Приоритет 1: Прямые значения в секундах из dailySleepDTO
            if deep_s is not None and light_s is not None and rem_s is not None:
                print(f"DEBUG PROCESSOR: ✅ Приоритет 1: Используем прямые значения секунд из DTO (deep={deep_s}, light={light_s}, rem={rem_s}).")
                processed_data['deep_sleep_minutes'] = deep_s // 60
                processed_data['light_sleep_minutes'] = light_s // 60
                processed_data['rem_sleep_minutes'] = rem_s // 60
            
            # Приоритет 2: Расчет по процентам из sleepScores
            elif total_minutes > 0 and sleep_scores:
                deep_pct = sleep_scores.get('deepPercentage', {}).get('value')
                light_pct = sleep_scores.get('lightPercentage', {}).get('value')
                rem_pct = sleep_scores.get('remPercentage', {}).get('value')
                
                if deep_pct is not None and light_pct is not None and rem_pct is not None:
                    print(f"DEBUG PROCESSOR: ✅ Приоритет 2: Рассчитываем фазы из процентов (deep={deep_pct}%, light={light_pct}%, rem={rem_pct}%).")
                    processed_data['deep_sleep_minutes'] = round(total_minutes * deep_pct / 100)
                    processed_data['light_sleep_minutes'] = round(total_minutes * light_pct / 100)
                    processed_data['rem_sleep_minutes'] = round(total_minutes * rem_pct / 100)
                else:
                    print("DEBUG PROCESSOR: ⚠️ Проценты в sleepScores отсутствуют, фазы будут нулевыми.")
                    processed_data['deep_sleep_minutes'] = 0
                    processed_data['light_sleep_minutes'] = 0
                    processed_data['rem_sleep_minutes'] = 0
            
            # Приоритет 3: Парсинг массива sleepLevels (менее надежный)
            elif 'sleepLevels' in sleep_raw_data and sleep_raw_data['sleepLevels']:
                print("DEBUG PROCESSOR: ✅ Приоритет 3: Попытка восстановить фазы из sleepLevels.")
                levels = sleep_raw_data['sleepLevels']
                deep_m, light_m, rem_m = 0, 0, 0
                for level in levels:
                    duration_m = level.get('durationInSeconds', 0) // 60
                    level_type = str(level.get('activityLevel', '')).lower()
                    if level_type == 'deep': deep_m += duration_m
                    elif level_type == 'light': light_m += duration_m
                    elif level_type == 'rem': rem_m += duration_m
                processed_data['deep_sleep_minutes'] = deep_m
                processed_data['light_sleep_minutes'] = light_m
                processed_data['rem_sleep_minutes'] = rem_m
            
            else:
                print("DEBUG PROCESSOR: ❌ Не найден ни один источник данных для фаз сна. Устанавливаем нули.")
                processed_data['deep_sleep_minutes'] = 0
                processed_data['light_sleep_minutes'] = 0
                processed_data['rem_sleep_minutes'] = 0

            # 4. Извлекаем остальные данные
            # Оценка сна
            if sleep_scores.get('overall', {}).get('value'):
                processed_data['sleep_score'] = sleep_scores['overall']['value']
            
            # Пробуждения
            if 'awakeCount' in sleep_dto:
                processed_data['awakenings_count'] = sleep_dto.get('awakeCount', 0)
            else:
                processed_data['awakenings_count'] = sleep_dto.get('awakeSleepSeconds', 0) // 300

            # Время сна (в миллисекундах) с учетом временной зоны
            start_ts = sleep_dto.get('sleepStartTimestampLocal')
            end_ts = sleep_dto.get('sleepEndTimestampLocal')

            start_dt = Phase1DataProcessor._parse_local_timestamp(start_ts)
            end_dt = Phase1DataProcessor._parse_local_timestamp(end_ts)

            if start_dt and end_dt:
                
                # Сохраняем время в 24-часовом формате
                processed_data['bedtime'] = start_dt.strftime('%H:%M')
                processed_data['wakeup_time'] = end_dt.strftime('%H:%M')
                
                # Используем дату окончания сна для определения даты записи
                processed_data['sleep_date'] = end_dt.date().strftime('%Y-%m-%d')

            # 5. Рассчитываем производные метрики, если их нет
            if 'sleep_score' not in processed_data and total_minutes > 0:
                deep_rem_ratio = (processed_data.get('deep_sleep_minutes', 0) + processed_data.get('rem_sleep_minutes', 0)) / total_minutes
                awakening_penalty = min(processed_data.get('awakenings_count', 0) * 5, 20)
                duration_bonus = 10 if 420 <= total_minutes <= 540 else 0
                score = 50 + (deep_rem_ratio * 40) - awakening_penalty + duration_bonus
                processed_data['sleep_score'] = round(max(0, min(100, score)), 1)
                print(f"DEBUG PROCESSOR:  ক্যাল Расчетный sleep_score: {processed_data['sleep_score']}")

            if 'sleep_efficiency' not in processed_data and total_minutes > 0:
                in_bed_time = total_minutes + (processed_data.get('awakenings_count', 0) * 5) # Приблизительно
                if in_bed_time > 0:
                    processed_data['sleep_efficiency'] = round((total_minutes / in_bed_time) * 100, 1)

        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА при обработке данных сна: {e}")
            return None
        
        print(f"DEBUG PROCESSOR: ✅ Обработка завершена. Результат: {processed_data}")
        return processed_data

    @staticmethod
    def process_daily_health_data(health_raw_data, resting_hr_data=None):
        """Обработка ежедневных показателей здоровья"""
        if not health_raw_data and not resting_hr_data:
            return None
        
        processed_data = {}
        
        try:
            # Обработка общих показателей активности
            if health_raw_data:
                processed_data['steps'] = health_raw_data.get('totalSteps')
                processed_data['distance_meters'] = health_raw_data.get('totalDistanceMeters')
                processed_data['calories_active'] = health_raw_data.get('activeKilocalories')
                processed_data['calories_bmr'] = health_raw_data.get('bmrKilocalories')
                processed_data['active_minutes'] = health_raw_data.get('vigorousIntensityMinutes', 0) + \
                                                 health_raw_data.get('moderateIntensityMinutes', 0)
                processed_data['intensity_minutes'] = health_raw_data.get('vigorousIntensityMinutes', 0)
                processed_data['floors_climbed'] = health_raw_data.get('floorsAscended')
            
            # Обработка пульса покоя
            if resting_hr_data:
                if isinstance(resting_hr_data, dict):
                    processed_data['resting_hr'] = resting_hr_data.get('restingHeartRate')
                else:
                    # Если это просто значение
                    processed_data['resting_hr'] = resting_hr_data
            
        except Exception as e:
            print(f"Ошибка обработки показателей здоровья: {e}")
            return None
        
        return processed_data

    @staticmethod
    def _parse_local_timestamp(value):
        """Приводит различные форматы временных меток Garmin к naive datetime."""
        if value is None:
            return None

        try:
            if isinstance(value, (int, float)):
                timestamp = value
                if timestamp > 1600000000000:
                    timestamp = timestamp / 1000
                return datetime.utcfromtimestamp(timestamp)

            if isinstance(value, str):
                candidate = value.strip()
                if candidate.endswith('Z'):
                    candidate = candidate[:-1] + '+00:00'
                dt = datetime.fromisoformat(candidate)
                if dt.tzinfo:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt

            # Попытка через pandas, если формат нестандартный
            parsed = pd.to_datetime(value, errors='coerce')
            if pd.notna(parsed):
                if getattr(parsed, 'tzinfo', None):
                    parsed = parsed.tz_convert(None)
                return parsed.to_pydatetime()
        except Exception as exc:
            print(f"DEBUG PROCESSOR: Не удалось распарсить временную метку {value}: {exc}")
            return None

        return None
    
    @staticmethod
    def process_training_status_data(status_raw_data, vo2_data=None, readiness_data=None):
        """Обработка данных статуса тренированности"""
        if not status_raw_data and not vo2_data:
            return None
        
        processed_data = {}
        
        try:
            # Основные показатели тренированности
            if status_raw_data:
                processed_data['training_status'] = status_raw_data.get('trainingStatusKey')
                processed_data['training_load_7d'] = status_raw_data.get('load7Day')
                processed_data['load_ratio'] = status_raw_data.get('loadRatio')
                processed_data['recovery_time_hours'] = status_raw_data.get('recoveryTimeHours')
            
            # VO2 max данные
            if vo2_data:
                if isinstance(vo2_data, dict):
                    processed_data['vo2_max'] = vo2_data.get('vo2MaxValue')
                    processed_data['fitness_age'] = vo2_data.get('fitnessAge')
                else:
                    processed_data['vo2_max'] = vo2_data
            
            # Готовность к тренировке
            if readiness_data:
                if isinstance(readiness_data, dict):
                    processed_data['training_readiness'] = readiness_data.get('readinessScore')
                else:
                    processed_data['training_readiness'] = readiness_data
            
        except Exception as e:
            print(f"Ошибка обработки статуса тренированности: {e}")
            return None
        
        return processed_data
    
    @staticmethod
    def calculate_comprehensive_readiness(sleep_data, hrv_data, health_data, training_data):
        """Расчёт комплексного индекса готовности с защитой от None."""
        try:
            factors = {}
            weights = {}
            
            # Фактор сна (25%)
            if sleep_data and sleep_data.get('sleep_score') is not None:
                factors['sleep'] = sleep_data['sleep_score']
                weights['sleep'] = 0.25
            
            # Фактор HRV (25%)
            if hrv_data and hrv_data.get('rmssd') is not None:
                rmssd = hrv_data['rmssd']
                if rmssd > 0:
                    hrv_score = min(100, max(0, ((rmssd - 20) / 60) * 100))
                    factors['hrv'] = hrv_score
                    weights['hrv'] = 0.25
            
            # Фактор пульса покоя (20%)
            if health_data and health_data.get('resting_hr') is not None:
                resting_hr = health_data['resting_hr']
                if resting_hr > 0:
                    hr_score = min(100, max(0, 100 - ((resting_hr - 40) / 40) * 100))
                    factors['resting_hr'] = hr_score
                    weights['resting_hr'] = 0.20
            
            # Фактор готовности от Garmin (15%)
            if training_data and training_data.get('training_readiness') is not None:
                factors['training_readiness'] = training_data['training_readiness']
                weights['training_readiness'] = 0.15
            
            # Фактор стресса (15%)
            if hrv_data and hrv_data.get('stress_score') is not None:
                stress = hrv_data['stress_score']
                stress_score = min(100, max(0, 100 - stress))
                factors['stress'] = stress_score
                weights['stress'] = 0.15
            
            # Рассчитываем взвешенную оценку
            if factors:
                total_weight = sum(weights.values())
                if total_weight > 0:
                    weighted_sum = sum(score * weights[factor] for factor, score in factors.items() if score is not None)
                    readiness_score = weighted_sum / total_weight
                    
                    return {
                        'readiness_score': round(readiness_score, 1),
                        'factors_used': list(factors.keys()),
                        'factor_scores': factors
                    }
            
            return None
            
        except Exception as e:
            print(f"Ошибка расчёта индекса готовности: {e}")
            return None
