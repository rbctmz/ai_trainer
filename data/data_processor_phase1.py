"""
Процессор данных для Фазы 1 - обработка расширенных данных Garmin
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
import pandas as pd

class Phase1DataProcessor:
    """Класс для обработки новых типов данных Фазы 1"""
    
    _TRAINING_STATUS_CODE_MAP: Dict[int, str] = {
        0: "NO_STATUS",
        1: "DETRAINING",
        2: "UNPRODUCTIVE",
        3: "MAINTAINING",
        4: "PRODUCTIVE",
        5: "PEAK",
        6: "OVERREACHING",
        7: "RECOVERY",
        8: "BASE",
        9: "BUILD",
        10: "IMPROVING",
    }

    _TRAINING_FEEDBACK_BASE_MAP: Dict[str, str] = {
        "UNPRODUCTIVE": "Непродуктивно — нагрузка не даёт прогресса. Проверьте восстановление и интенсивность.",
        "PRODUCTIVE": "Продуктивно — тренировки развивают форму.",
        "RECOVERY": "Восстановление — снизьте нагрузку и дайте телу восстановиться.",
        "MAINTAINING": "Поддержание — форма стабилизируется.",
        "DETRAINING": "Потеря формы — увеличьте регулярность и интенсивность тренировок.",
        "PEAK": "Пик формы — вы готовы к ключевым стартам.",
        "OVERREACHING": "Перегрузка — высок риск перетренированности.",
        "BASE": "База — закладываете фундамент выносливости.",
        "BUILD": "Билд — развиваете специальную форму.",
        "IMPROVING": "Форма растёт — продолжайте соблюдать баланс.",
    }

    _BALANCE_ZONE_TRANSLATIONS: Dict[str, str] = {
        "AEROBIC_HIGH": "высокоаэробной",
        "AEROBIC_LOW": "низкоаэробной",
        "ANAEROBIC": "анаэробной",
    }
    
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
                awake_count_from_levels = 0
                for level in levels:
                    duration_m = level.get('durationInSeconds', 0) // 60
                    level_type = str(level.get('activityLevel', '')).lower()
                    if level_type == 'deep': deep_m += duration_m
                    elif level_type == 'light': light_m += duration_m
                    elif level_type == 'rem': rem_m += duration_m
                    elif level_type == 'awake': awake_count_from_levels += 1
                processed_data['deep_sleep_minutes'] = deep_m
                processed_data['light_sleep_minutes'] = light_m
                processed_data['rem_sleep_minutes'] = rem_m
                processed_data['_awake_count_from_levels'] = awake_count_from_levels
            
            else:
                print("DEBUG PROCESSOR: ❌ Не найден ни один источник данных для фаз сна. Устанавливаем нули.")
                processed_data['deep_sleep_minutes'] = 0
                processed_data['light_sleep_minutes'] = 0
                processed_data['rem_sleep_minutes'] = 0

            # 4. Извлекаем остальные данные
            # Оценка сна
            if sleep_scores.get('overall', {}).get('value'):
                processed_data['sleep_score'] = sleep_scores['overall']['value']
            
            # Пробуждения: приоритет awakeCount, затем из sleepLevels, затем расчёт
            if 'awakeCount' in sleep_dto:
                processed_data['awakenings_count'] = sleep_dto.get('awakeCount', 0)
            elif '_awake_count_from_levels' in processed_data:
                processed_data['awakenings_count'] = processed_data.pop('_awake_count_from_levels')
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
        
        processed_data: Dict[str, Any] = {}
        
        try:
            embedded_vo2: Optional[Dict[str, Any]] = None
            if isinstance(status_raw_data, dict) and 'mostRecentTrainingStatus' in status_raw_data:
                status_raw_data, embedded_vo2 = Phase1DataProcessor._normalize_training_status_payload(status_raw_data)
                if embedded_vo2 and not vo2_data:
                    vo2_data = embedded_vo2

            # Основные показатели тренированности
            if status_raw_data:
                if not isinstance(status_raw_data, dict):
                    status_raw_data = {}

                def _normalize_text(value: Any) -> Optional[str]:
                    if value is None:
                        return None
                    if isinstance(value, str):
                        cleaned = value.strip()
                        return cleaned.upper() if cleaned else None
                    return None

                def _normalize_number(value: Any) -> Optional[float]:
                    if value is None:
                        return None
                    if isinstance(value, (int, float)):
                        return float(value)
                    if isinstance(value, str):
                        try:
                            return float(value.replace(',', '.'))
                        except ValueError:
                            return None
                    return None

                training_status_value = (
                    status_raw_data.get('trainingStatusKey')
                    or status_raw_data.get('trainingStatus')
                )
                if isinstance(training_status_value, dict):
                    training_status_value = (
                        training_status_value.get('typeKey')
                        or training_status_value.get('status')
                        or training_status_value.get('displayValue')
                    )
                if not training_status_value:
                    primary_status = status_raw_data.get('primaryStatus') or status_raw_data.get('primaryTrainingStatus')
                    if isinstance(primary_status, dict):
                        training_status_value = (
                            primary_status.get('typeKey')
                            or primary_status.get('status')
                            or primary_status.get('displayValue')
                        )
                training_feedback_phrase = None
                balance_feedback_code = None

                if not training_status_value:
                    events = status_raw_data.get('trainingStatusEvents')
                    if isinstance(events, list) and events:
                        event = events[0]
                        if isinstance(event, dict):
                            training_feedback_phrase = training_feedback_phrase or event.get('trainingStatusFeedbackPhrase')
                            training_status_value = (
                                event.get('trainingStatusType', {}).get('typeKey')
                                or event.get('status')
                            )

                training_status_value = _normalize_text(training_status_value)
                if training_status_value:
                    processed_data['training_status'] = training_status_value
                
                training_feedback_phrase = (
                    training_feedback_phrase
                    or status_raw_data.get('trainingFeedbackCode')
                    or status_raw_data.get('trainingFeedback')
                )
                balance_feedback_code = (
                    balance_feedback_code
                    or status_raw_data.get('trainingBalanceFeedbackCode')
                    or status_raw_data.get('trainingBalanceFeedback')
                )
                if training_feedback_phrase:
                    processed_data['training_feedback_code'] = training_feedback_phrase
                if balance_feedback_code:
                    processed_data['training_balance_feedback_code'] = balance_feedback_code

                load7_value = (
                    status_raw_data.get('load7Day')
                    or status_raw_data.get('load7day')
                    or status_raw_data.get('load7d')
                )
                if load7_value is None:
                    training_load = status_raw_data.get('trainingLoad')
                    if isinstance(training_load, dict):
                        load7_value = (
                            training_load.get('load7Day')
                            or training_load.get('load7DaySum')
                            or training_load.get('loadSevenDays')
                            or training_load.get('trainingLoadSevenDays')
                            or training_load.get('trainingLoad')
                        )
                load7_value = _normalize_number(load7_value)
                if load7_value is not None:
                    processed_data['training_load_7d'] = load7_value
                
                load_ratio_value = status_raw_data.get('loadRatio')
                if load_ratio_value is None:
                    training_load = status_raw_data.get('trainingLoad')
                    if isinstance(training_load, dict):
                        load_ratio_value = training_load.get('loadRatio')
                load_ratio_value = _normalize_number(load_ratio_value)
                if load_ratio_value is not None:
                    processed_data['load_ratio'] = load_ratio_value
                
                recovery_value = status_raw_data.get('recoveryTimeHours')
                if recovery_value is None:
                    recovery = status_raw_data.get('recoveryTime')
                    if isinstance(recovery, dict):
                        recovery_value = (
                            recovery.get('hours')
                            or recovery.get('value')
                            or recovery.get('minutes')
                        )
                        if recovery_value and isinstance(recovery_value, (int, float)) and recovery_value > 48:
                            recovery_value = recovery_value / 60.0
                        elif isinstance(recovery_value, str):
                            try:
                                numeric_recovery = float(recovery_value.replace(',', '.'))
                                recovery_value = numeric_recovery / 60.0 if numeric_recovery > 48 else numeric_recovery
                            except ValueError:
                                recovery_value = None
                recovery_value = _normalize_number(recovery_value)
                if recovery_value is not None:
                    processed_data['recovery_time_hours'] = recovery_value
                
                chronic_value = (
                    status_raw_data.get('training_load_chronic')
                    or status_raw_data.get('trainingLoadChronic')
                )
                if chronic_value is None:
                    training_load = status_raw_data.get('trainingLoad')
                    if isinstance(training_load, dict):
                        chronic_value = training_load.get('trainingLoadChronic') or training_load.get('dailyTrainingLoadChronic')
                chronic_value = _normalize_number(chronic_value)
                if chronic_value is not None:
                    processed_data['training_load_chronic'] = chronic_value

                acwr_status = (
                    status_raw_data.get('acwr_status')
                    or status_raw_data.get('acwrStatus')
                )
                acwr_status_feedback = (
                    status_raw_data.get('acwr_status_feedback')
                    or status_raw_data.get('acwrStatusFeedback')
                )
                acwr_percent = (
                    status_raw_data.get('acwr_percent')
                    or status_raw_data.get('acwrPercent')
                )
                if acwr_status is None or acwr_percent is None:
                    acute_data = status_raw_data.get('acuteTrainingLoadDTO')
                    if isinstance(acute_data, dict):
                        acwr_status = acwr_status or acute_data.get('acwrStatus')
                        acwr_status_feedback = acwr_status_feedback or acute_data.get('acwrStatusFeedback')
                        acwr_percent = acwr_percent or acute_data.get('acwrPercent')
                        if chronic_value is None:
                            chronic_from_acute = acute_data.get('dailyTrainingLoadChronic')
                            chronic_from_acute = _normalize_number(chronic_from_acute)
                            if chronic_from_acute is not None:
                                processed_data['training_load_chronic'] = chronic_from_acute

                acwr_status = _normalize_text(acwr_status)
                if acwr_status:
                    processed_data['acwr_status'] = acwr_status
                if acwr_status_feedback:
                    processed_data['acwr_status_feedback'] = acwr_status_feedback
                acwr_percent = _normalize_number(acwr_percent)
                if acwr_percent is not None:
                    processed_data['acwr_percent'] = acwr_percent

                since_date = (
                    status_raw_data.get('training_since_date')
                    or status_raw_data.get('trainingSinceDate')
                    or status_raw_data.get('sinceDate')
                )
                if since_date:
                    processed_data['training_since_date'] = since_date

                fitness_trend = status_raw_data.get('fitness_trend') or status_raw_data.get('fitnessTrend')
                if fitness_trend is not None:
                    processed_data['fitness_trend'] = fitness_trend

                fitness_trend_sport = status_raw_data.get('fitness_trend_sport') or status_raw_data.get('fitnessTrendSport')
                if fitness_trend_sport:
                    processed_data['fitness_trend_sport'] = fitness_trend_sport

                sport_value = status_raw_data.get('sport')
                if sport_value:
                    processed_data['sport'] = sport_value

                device_id = status_raw_data.get('device_id') or status_raw_data.get('deviceId')
                if device_id is not None:
                    processed_data['device_id'] = device_id

                last_primary_sync = (
                    status_raw_data.get('last_primary_sync_date')
                    or status_raw_data.get('lastPrimarySyncDate')
                )
                if last_primary_sync:
                    processed_data['last_primary_sync_date'] = last_primary_sync

                monthly_low = (
                    status_raw_data.get('monthly_load_aerobic_low')
                    or status_raw_data.get('monthlyLoadAerobicLow')
                )
                monthly_low = _normalize_number(monthly_low)
                if monthly_low is not None:
                    processed_data['monthly_load_aerobic_low'] = monthly_low
                monthly_low_min = (
                    status_raw_data.get('monthly_load_aerobic_low_target_min')
                    or status_raw_data.get('monthlyLoadAerobicLowTargetMin')
                )
                monthly_low_min = _normalize_number(monthly_low_min)
                if monthly_low_min is not None:
                    processed_data['monthly_load_aerobic_low_target_min'] = monthly_low_min
                monthly_low_max = (
                    status_raw_data.get('monthly_load_aerobic_low_target_max')
                    or status_raw_data.get('monthlyLoadAerobicLowTargetMax')
                )
                monthly_low_max = _normalize_number(monthly_low_max)
                if monthly_low_max is not None:
                    processed_data['monthly_load_aerobic_low_target_max'] = monthly_low_max

                monthly_high = (
                    status_raw_data.get('monthly_load_aerobic_high')
                    or status_raw_data.get('monthlyLoadAerobicHigh')
                )
                monthly_high = _normalize_number(monthly_high)
                if monthly_high is not None:
                    processed_data['monthly_load_aerobic_high'] = monthly_high
                monthly_high_min = (
                    status_raw_data.get('monthly_load_aerobic_high_target_min')
                    or status_raw_data.get('monthlyLoadAerobicHighTargetMin')
                )
                monthly_high_min = _normalize_number(monthly_high_min)
                if monthly_high_min is not None:
                    processed_data['monthly_load_aerobic_high_target_min'] = monthly_high_min
                monthly_high_max = (
                    status_raw_data.get('monthly_load_aerobic_high_target_max')
                    or status_raw_data.get('monthlyLoadAerobicHighTargetMax')
                )
                monthly_high_max = _normalize_number(monthly_high_max)
                if monthly_high_max is not None:
                    processed_data['monthly_load_aerobic_high_target_max'] = monthly_high_max

                monthly_ana = (
                    status_raw_data.get('monthly_load_anaerobic')
                    or status_raw_data.get('monthlyLoadAnaerobic')
                )
                monthly_ana = _normalize_number(monthly_ana)
                if monthly_ana is not None:
                    processed_data['monthly_load_anaerobic'] = monthly_ana
                monthly_ana_min = (
                    status_raw_data.get('monthly_load_anaerobic_target_min')
                    or status_raw_data.get('monthlyLoadAnaerobicTargetMin')
                )
                monthly_ana_min = _normalize_number(monthly_ana_min)
                if monthly_ana_min is not None:
                    processed_data['monthly_load_anaerobic_target_min'] = monthly_ana_min
                monthly_ana_max = (
                    status_raw_data.get('monthly_load_anaerobic_target_max')
                    or status_raw_data.get('monthlyLoadAnaerobicTargetMax')
                )
                monthly_ana_max = _normalize_number(monthly_ana_max)
                if monthly_ana_max is not None:
                    processed_data['monthly_load_anaerobic_target_max'] = monthly_ana_max

                feedback_message = Phase1DataProcessor._translate_training_feedback(training_feedback_phrase, balance_feedback_code)
                if feedback_message:
                    processed_data['training_feedback'] = feedback_message

                balance_message = Phase1DataProcessor._translate_balance_feedback(balance_feedback_code)
                if balance_message:
                    processed_data['training_balance_feedback'] = balance_message
            
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
        
            # Удаляем пустые значения
            processed_data = {
                key: value for key, value in processed_data.items()
                if value not in (None, "", [], {})
            }
            if not processed_data:
                return None
        except Exception as e:
            print(f"Ошибка обработки статуса тренированности: {e}")
            return None
        
        return processed_data
    
    @staticmethod
    def _translate_training_feedback(feedback_code: Optional[str], balance_code: Optional[str] = None) -> Optional[str]:
        if not feedback_code:
            return None
        base_key = feedback_code.split('_')[0].upper()
        base_message = Phase1DataProcessor._TRAINING_FEEDBACK_BASE_MAP.get(
            base_key,
            feedback_code.replace('_', ' ').title()
        )
        balance_message = Phase1DataProcessor._translate_balance_feedback(balance_code)
        if balance_message:
            return f"{base_message} {balance_message}".strip()
        return base_message

    @staticmethod
    def _translate_balance_feedback(balance_code: Optional[str]) -> Optional[str]:
        if not balance_code:
            return None
        code = balance_code.upper()
        if code in {"BALANCED", "AEROBIC_BALANCED"}:
            return "Баланс нагрузки в норме."
        if code == "RECOVERY_TIME_LOW":
            return "Организм готов к новой нагрузке."
        if code == "RECOVERY_TIME_HIGH":
            return "Повысьте качество восстановления."

        zone_label = None
        for key, translation in Phase1DataProcessor._BALANCE_ZONE_TRANSLATIONS.items():
            if code.startswith(key):
                zone_label = translation
                break

        if zone_label:
            if code.endswith("SHORTAGE"):
                return f"Добавьте {zone_label} нагрузки."
            if code.endswith("SURPLUS"):
                return f"Снизьте {zone_label} нагрузку."

        if "BALANCED" in code:
            return "Баланс нагрузки в норме."
        return balance_code.replace('_', ' ').title()

    @staticmethod
    def _normalize_training_status_payload(status_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Преобразует расширенный ответ Garmin в компактный словарь."""
        normalized: Dict[str, Any] = {}
        vo2_normalized: Optional[Dict[str, Any]] = None

        status_section = status_payload.get('mostRecentTrainingStatus')
        latest_entry: Optional[Dict[str, Any]] = None
        if isinstance(status_section, dict):
            latest_map = status_section.get('latestTrainingStatusData')
            if isinstance(latest_map, dict):
                for value in latest_map.values():
                    if isinstance(value, dict):
                        latest_entry = value
                        break
        if latest_entry:
            feedback_phrase = latest_entry.get('trainingStatusFeedbackPhrase')
            status_code = latest_entry.get('trainingStatus')
            status_key = None
            if isinstance(feedback_phrase, str) and feedback_phrase:
                status_key = feedback_phrase.split('_')[0]
            if not status_key and isinstance(status_code, int):
                status_key = Phase1DataProcessor._TRAINING_STATUS_CODE_MAP.get(status_code)
            normalized['trainingStatusKey'] = status_key

            weekly_load = latest_entry.get('weeklyTrainingLoad')
            acute_data = latest_entry.get('acuteTrainingLoadDTO')
            if isinstance(acute_data, dict):
                if weekly_load is None:
                    weekly_load = acute_data.get('dailyTrainingLoadAcute')
                normalized['loadRatio'] = acute_data.get('dailyAcuteChronicWorkloadRatio')
                normalized['trainingLoadChronic'] = acute_data.get('dailyTrainingLoadChronic')
                normalized['acwrStatus'] = acute_data.get('acwrStatus')
                normalized['acwrStatusFeedback'] = acute_data.get('acwrStatusFeedback')
                normalized['acwrPercent'] = acute_data.get('acwrPercent')
            normalized['load7Day'] = weekly_load

            recovery_hours = latest_entry.get('recoveryTimeHours')
            if recovery_hours is None:
                recovery_minutes = latest_entry.get('recoveryTimeMinutes')
                if isinstance(recovery_minutes, (int, float)):
                    recovery_hours = recovery_minutes / 60.0
            normalized['recoveryTimeHours'] = recovery_hours
            normalized['trainingFeedbackCode'] = feedback_phrase
            normalized['trainingSinceDate'] = latest_entry.get('sinceDate')
            normalized['fitnessTrend'] = latest_entry.get('fitnessTrend')
            normalized['fitnessTrendSport'] = latest_entry.get('fitnessTrendSport')
            normalized['sport'] = latest_entry.get('sport')
            normalized['deviceId'] = latest_entry.get('deviceId')

        vo2_section = status_payload.get('mostRecentVO2Max')
        if isinstance(vo2_section, dict):
            generic_vo2 = vo2_section.get('generic')
            if isinstance(generic_vo2, dict):
                vo2_value = generic_vo2.get('vo2MaxPreciseValue') or generic_vo2.get('vo2MaxValue')
                vo2_normalized = {
                    'vo2MaxValue': vo2_value,
                    'fitnessAge': generic_vo2.get('fitnessAge'),
                }

        balance_section = status_payload.get('mostRecentTrainingLoadBalance')
        if isinstance(balance_section, dict):
            metrics_map = balance_section.get('metricsTrainingLoadBalanceDTOMap')
            if isinstance(metrics_map, dict):
                for value in metrics_map.values():
                    if isinstance(value, dict):
                        normalized['monthlyLoadAerobicLow'] = value.get('monthlyLoadAerobicLow')
                        normalized['monthlyLoadAerobicLowTargetMin'] = value.get('monthlyLoadAerobicLowTargetMin')
                        normalized['monthlyLoadAerobicLowTargetMax'] = value.get('monthlyLoadAerobicLowTargetMax')
                        normalized['monthlyLoadAerobicHigh'] = value.get('monthlyLoadAerobicHigh')
                        normalized['monthlyLoadAerobicHighTargetMin'] = value.get('monthlyLoadAerobicHighTargetMin')
                        normalized['monthlyLoadAerobicHighTargetMax'] = value.get('monthlyLoadAerobicHighTargetMax')
                        normalized['monthlyLoadAnaerobic'] = value.get('monthlyLoadAnaerobic')
                        normalized['monthlyLoadAnaerobicTargetMin'] = value.get('monthlyLoadAnaerobicTargetMin')
                        normalized['monthlyLoadAnaerobicTargetMax'] = value.get('monthlyLoadAnaerobicTargetMax')
                        normalized['trainingBalanceFeedbackCode'] = value.get('trainingBalanceFeedbackPhrase')
                        break
            if not normalized.get('trainingBalanceFeedbackCode'):
                normalized['trainingBalanceFeedbackCode'] = balance_section.get('trainingBalanceFeedbackPhrase')

        if isinstance(status_section, dict):
            normalized['lastPrimarySyncDate'] = status_section.get('lastPrimarySyncDate')

        feedback_phrase = normalized.get('trainingFeedbackCode')
        balance_code = normalized.get('trainingBalanceFeedbackCode')
        if feedback_phrase:
            normalized['trainingFeedback'] = Phase1DataProcessor._translate_training_feedback(feedback_phrase, balance_code)
        if balance_code:
            normalized['trainingBalanceFeedback'] = Phase1DataProcessor._translate_balance_feedback(balance_code)

        normalized = {
            key: value for key, value in normalized.items()
            if value not in (None, "", [], {})
        }

        return normalized, vo2_normalized
    
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
