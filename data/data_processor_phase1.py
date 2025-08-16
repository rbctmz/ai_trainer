"""
Процессор данных для Фазы 1 - обработка расширенных данных Garmin
"""

from datetime import datetime, timedelta
import pandas as pd

class Phase1DataProcessor:
    """Класс для обработки новых типов данных Фазы 1"""
    
    @staticmethod
    def process_sleep_data(sleep_raw_data):
        """Обработка сырых данных сна от Garmin (поддержка garminconnect и garth)"""
        if not sleep_raw_data:
            print("DEBUG PROCESSOR: sleep_raw_data пуст")
            return None
        
        print(f"DEBUG PROCESSOR: Начинаем обработку данных сна, тип: {type(sleep_raw_data)}")
        print(f"DEBUG PROCESSOR: Ключи верхнего уровня: {list(sleep_raw_data.keys()) if isinstance(sleep_raw_data, dict) else 'НЕ СЛОВАРЬ'}")
        
        processed_data = {}
        
        try:
            # Проверяем, если это данные из garth (уже конвертированные)
            if isinstance(sleep_raw_data, dict) and 'raw_data' in sleep_raw_data:
                raw_data = sleep_raw_data['raw_data']
                
                # Обрабатываем уже конвертированные данные garth
                if 'sleepTimeSeconds' in sleep_raw_data:
                    processed_data['total_sleep_minutes'] = sleep_raw_data.get('sleepTimeSeconds', 0) // 60
                    processed_data['deep_sleep_minutes'] = sleep_raw_data.get('deepSleepSeconds', 0) // 60
                    processed_data['light_sleep_minutes'] = sleep_raw_data.get('lightSleepSeconds', 0) // 60
                    processed_data['rem_sleep_minutes'] = sleep_raw_data.get('remSleepSeconds', 0) // 60
                    processed_data['awakenings_count'] = sleep_raw_data.get('awakeTimeSeconds', 0) // 300  # Примерно каждые 5 минут = пробуждение
                    
                    # Ищем дополнительные данные в raw_data
                    if isinstance(raw_data, dict):
                        processed_data['bedtime'] = raw_data.get('startGMT') or raw_data.get('sleepStartTimestampLocal')
                        processed_data['wakeup_time'] = raw_data.get('endGMT') or raw_data.get('sleepEndTimestampLocal')
                        
                        # Извлекаем sleep score если есть
                        if 'overallSleepScore' in raw_data:
                            processed_data['sleep_score'] = raw_data['overallSleepScore']
                        elif 'sleepScore' in raw_data:
                            processed_data['sleep_score'] = raw_data['sleepScore']
                
                    # Если обработка прошла успешно, не продолжаем дальше
                    if processed_data.get('total_sleep_minutes', 0) > 0:
                        return processed_data
            
            # Пробуем обработать прямые данные garth без конвертации
            elif isinstance(sleep_raw_data, dict):
                # Ищем основные поля данных сна напрямую
                if any(key in sleep_raw_data for key in ['sleepTimeSeconds', 'totalSleepTimeSeconds', 'deepSleepSeconds']):
                    processed_data['total_sleep_minutes'] = (
                        sleep_raw_data.get('sleepTimeSeconds') or 
                        sleep_raw_data.get('totalSleepTimeSeconds') or 0
                    ) // 60
                    processed_data['deep_sleep_minutes'] = sleep_raw_data.get('deepSleepSeconds', 0) // 60
                    processed_data['light_sleep_minutes'] = sleep_raw_data.get('lightSleepSeconds', 0) // 60
                    processed_data['rem_sleep_minutes'] = sleep_raw_data.get('remSleepSeconds', 0) // 60
                    processed_data['awakenings_count'] = sleep_raw_data.get('awakeTimes', 0)
                    
                    # Дополнительные поля
                    processed_data['bedtime'] = sleep_raw_data.get('startGMT') or sleep_raw_data.get('sleepStart')
                    processed_data['wakeup_time'] = sleep_raw_data.get('endGMT') or sleep_raw_data.get('sleepEnd')
                    
                    # Sleep score
                    if 'overallSleepScore' in sleep_raw_data:
                        processed_data['sleep_score'] = sleep_raw_data['overallSleepScore']
                    elif 'sleepScore' in sleep_raw_data:
                        processed_data['sleep_score'] = sleep_raw_data['sleepScore']
                    
            
            # Обрабатываем данные garminconnect (оригинальный формат)
            if 'dailySleepDTO' in sleep_raw_data:
                sleep_dto = sleep_raw_data['dailySleepDTO']
                
                processed_data['total_sleep_minutes'] = sleep_dto.get('sleepTimeSeconds', 0) // 60
                
                # Фазы сна из dailySleepDTO (приоритет: секунды, затем проценты)
                deep_seconds = sleep_dto.get('deepSleepSeconds', 0)
                light_seconds = sleep_dto.get('lightSleepSeconds', 0)
                rem_seconds = sleep_dto.get('remSleepSeconds', 0)
                
                print(f"DEBUG PROCESSOR: Проверяем секунды в dailySleepDTO: deep={deep_seconds}, light={light_seconds}, rem={rem_seconds}")
                
                # ИСПРАВЛЕНО: Используем секунды если они доступны И НЕ ВСЕ равны 0
                # Проверяем что данные действительно доступны и имеют значимые значения
                if (deep_seconds is not None and light_seconds is not None and rem_seconds is not None and 
                    (deep_seconds > 0 or light_seconds > 0 or rem_seconds > 0)):
                    # Используем прямые данные в секундах
                    processed_data['deep_sleep_minutes'] = deep_seconds // 60
                    processed_data['light_sleep_minutes'] = light_seconds // 60
                    processed_data['rem_sleep_minutes'] = rem_seconds // 60
                    print(f"DEBUG PROCESSOR: ✅ Используем СЕКУНДЫ: deep={deep_seconds//60}, light={light_seconds//60}, rem={rem_seconds//60}")
                else:
                    print(f"DEBUG PROCESSOR: Секунды недоступны (None), пробуем проценты...")
                    # Рассчитываем из процентов в sleepScores (fallback)
                    total_minutes = processed_data.get('total_sleep_minutes', 0)
                    if total_minutes > 0 and 'sleepScores' in sleep_raw_data:
                        scores = sleep_raw_data['sleepScores']
                        
                        deep_percent = scores.get('deepPercentage', {}).get('value', 0)
                        light_percent = scores.get('lightPercentage', {}).get('value', 0)
                        rem_percent = scores.get('remPercentage', {}).get('value', 0)
                        
                        print(f"DEBUG PROCESSOR: sleepScores найден, проценты: deep={deep_percent}%, light={light_percent}%, rem={rem_percent}%")
                        
                        if deep_percent > 0 or light_percent > 0 or rem_percent > 0:
                            calculated_deep = round(total_minutes * deep_percent / 100)
                            calculated_light = round(total_minutes * light_percent / 100)
                            calculated_rem = round(total_minutes * rem_percent / 100)
                            
                            processed_data['deep_sleep_minutes'] = calculated_deep
                            processed_data['light_sleep_minutes'] = calculated_light
                            processed_data['rem_sleep_minutes'] = calculated_rem
                            
                            print(f"DEBUG PROCESSOR: ✅ Рассчитаны фазы сна из ПРОЦЕНТОВ: deep={calculated_deep}, light={calculated_light}, rem={calculated_rem}")
                        else:
                            # Fallback to zeros if no data available
                            processed_data['deep_sleep_minutes'] = 0
                            processed_data['light_sleep_minutes'] = 0
                            processed_data['rem_sleep_minutes'] = 0
                            print("DEBUG PROCESSOR: ❌ Все проценты равны 0, устанавливаем фазы сна в 0")
                    else:
                        processed_data['deep_sleep_minutes'] = 0
                        processed_data['light_sleep_minutes'] = 0
                        processed_data['rem_sleep_minutes'] = 0
                        if total_minutes <= 0:
                            print("DEBUG PROCESSOR: ❌ total_minutes <= 0, фазы сна = 0")
                        elif 'sleepScores' not in sleep_raw_data:
                            print("DEBUG PROCESSOR: ❌ sleepScores не найден в данных, фазы сна = 0")
                            print(f"DEBUG PROCESSOR: Доступные ключи: {list(sleep_raw_data.keys())}")
                
                # Используем реальный awakeCount если доступен, иначе рассчитываем по awakeSleepSeconds
                if 'awakeCount' in sleep_dto:
                    processed_data['awakenings_count'] = sleep_dto.get('awakeCount', 0)
                else:
                    processed_data['awakenings_count'] = sleep_dto.get('awakeSleepSeconds', 0) // 300  # Примерно каждые 5 минут
                
                # Sleep score из структуры
                if 'sleepScores' in sleep_raw_data and 'overall' in sleep_raw_data['sleepScores']:
                    if 'value' in sleep_raw_data['sleepScores']['overall']:
                        processed_data['sleep_score'] = sleep_raw_data['sleepScores']['overall']['value']
                
                # Преобразуем timestamps в читаемый формат (milliseconds -> datetime)
                start_ts = sleep_dto.get('sleepStartTimestampLocal')
                end_ts = sleep_dto.get('sleepEndTimestampLocal')
                
                if start_ts:
                    try:
                        bedtime_dt = datetime.fromtimestamp(start_ts / 1000)  # Конвертируем из milliseconds
                        processed_data['bedtime'] = bedtime_dt.strftime('%H:%M')
                    except:
                        pass
                
                if end_ts:
                    try:
                        wakeup_dt = datetime.fromtimestamp(end_ts / 1000)  # Конвертируем из milliseconds
                        processed_data['wakeup_time'] = wakeup_dt.strftime('%H:%M')
                    except:
                        pass
            
            # Фазы сна для garminconnect (только если нет данных из dailySleepDTO или хотим их переопределить)
            if 'sleepLevels' in sleep_raw_data and sleep_raw_data['sleepLevels']:
                levels = sleep_raw_data['sleepLevels']
                
                # Переопределяем данные фаз сна только если есть значимые sleepLevels
                processed_data['deep_sleep_minutes'] = 0
                processed_data['light_sleep_minutes'] = 0
                processed_data['rem_sleep_minutes'] = 0
                processed_data['awakenings_count'] = 0
                
                for level in levels:
                    duration_minutes = level.get('durationInSeconds', 0) // 60
                    activity_level = level.get('activityLevel', '')
                    
                    # Безопасное приведение к строке и нижнему регистру
                    if isinstance(activity_level, str):
                        level_type = activity_level.lower()
                    elif isinstance(activity_level, (int, float)):
                        # Числовые коды: 0=deep, 1=light, 2=rem, 3=awake (примерно)
                        level_type_map = {0: 'deep', 1: 'light', 2: 'rem', 3: 'awake'}
                        level_type = level_type_map.get(int(activity_level), 'unknown')
                    else:
                        level_type = 'unknown'
                    
                    if level_type == 'deep':
                        processed_data['deep_sleep_minutes'] += duration_minutes
                    elif level_type == 'light':
                        processed_data['light_sleep_minutes'] += duration_minutes
                    elif level_type == 'rem':
                        processed_data['rem_sleep_minutes'] += duration_minutes
                    elif level_type == 'awake':
                        processed_data['awakenings_count'] += 1
            
            # Расчёт качества сна и эффективности (если не предоставлены)
            total_sleep = processed_data.get('total_sleep_minutes', 0)
            deep_sleep = processed_data.get('deep_sleep_minutes', 0)
            rem_sleep = processed_data.get('rem_sleep_minutes', 0)
            awakenings = processed_data.get('awakenings_count', 0)
            
            if total_sleep > 0:
                # Рассчитываем sleep_score только если он не был предоставлен
                if 'sleep_score' not in processed_data or processed_data['sleep_score'] is None:
                    # Простая формула качества сна (0-100)
                    deep_rem_ratio = (deep_sleep + rem_sleep) / total_sleep if total_sleep > 0 else 0
                    awakening_penalty = min(awakenings * 5, 20)  # Максимум -20 за пробуждения
                    
                    sleep_score = max(0, min(100, 
                        50 +  # Базовая оценка
                        (deep_rem_ratio * 40) -  # Бонус за глубокий/REM сон
                        awakening_penalty +  # Штраф за пробуждения
                        (10 if 420 <= total_sleep <= 540 else 0)  # Бонус за оптимальную длительность
                    ))
                    
                    processed_data['sleep_score'] = round(sleep_score, 1)
                
                # Эффективность сна (если не предоставлена)
                if 'sleep_efficiency' not in processed_data or processed_data['sleep_efficiency'] is None:
                    in_bed_time = processed_data.get('total_sleep_minutes', 0) + (awakenings * 5)
                    if in_bed_time > 0:
                        processed_data['sleep_efficiency'] = round((total_sleep / in_bed_time) * 100, 1)
            
        except Exception as e:
            print(f"Ошибка обработки данных сна: {e}")
            return None
        
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
        """Расчёт комплексного индекса готовности"""
        try:
            factors = {}
            weights = {}
            
            # Фактор сна (25%)
            if sleep_data and 'sleep_score' in sleep_data:
                factors['sleep'] = sleep_data['sleep_score']
                weights['sleep'] = 0.25
            
            # Фактор HRV (25%)
            if hrv_data and 'rmssd' in hrv_data:
                # Нормализуем RMSSD в оценку 0-100
                rmssd = hrv_data['rmssd']
                if rmssd > 0:
                    # Примерная нормализация: 20-80 мс = 0-100 баллов
                    hrv_score = min(100, max(0, ((rmssd - 20) / 60) * 100))
                    factors['hrv'] = hrv_score
                    weights['hrv'] = 0.25
            
            # Фактор пульса покоя (20%)
            if health_data and 'resting_hr' in health_data:
                resting_hr = health_data['resting_hr']
                if resting_hr and resting_hr > 0:
                    # Нормализация: 40-80 уд/мин, меньше = лучше
                    hr_score = min(100, max(0, 100 - ((resting_hr - 40) / 40) * 100))
                    factors['resting_hr'] = hr_score
                    weights['resting_hr'] = 0.20
            
            # Фактор готовности от Garmin (15%)
            if training_data and 'training_readiness' in training_data:
                factors['training_readiness'] = training_data['training_readiness']
                weights['training_readiness'] = 0.15
            
            # Фактор стресса (15%)
            if hrv_data and 'stress_score' in hrv_data:
                stress = hrv_data['stress_score']
                if stress is not None:
                    # Инвертируем стресс: меньше стресса = лучше
                    stress_score = min(100, max(0, 100 - stress))
                    factors['stress'] = stress_score
                    weights['stress'] = 0.15
            
            # Рассчитываем взвешенную оценку
            if factors:
                total_weight = sum(weights.values())
                if total_weight > 0:
                    weighted_sum = sum(score * weights[factor] for factor, score in factors.items())
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