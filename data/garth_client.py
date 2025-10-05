"""
Клиент для работы с Garmin Connect через библиотеку garth
"""

import garth
from datetime import datetime, timedelta
import streamlit as st
import sys
import os
from typing import Any, Dict
from pydantic import ValidationError

# Добавляем путь к логгеру
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import garmin_logger

class GarthClient:
    """Улучшенный клиент для работы с Garmin Connect через garth"""
    
    def __init__(self):
        self.is_authenticated = False
        self.auth_error = None
        self.username = None
        self._cached_profile: Dict[str, Any] | None = None
        self._profile_fetch_failed = False
    
    def authenticate(self, email, password):
        """Аутентификация через garth"""
        garmin_logger.info(f"🔐 Попытка авторизации через garth для {email}")
        try:
            garth.login(email, password)
            self.is_authenticated = True
            self.auth_error = None
            self.username = garth.client.username if hasattr(garth.client, 'username') else email
            garmin_logger.info(f"✅ Авторизация через garth успешна для {self.username}")
            return True
        except Exception as e:
            self.auth_error = str(e)
            self.is_authenticated = False
            garmin_logger.error(f"❌ Ошибка авторизации через garth: {e}")
            return False
    
    def get_sleep_data_garth(self, date):
        """Получение данных сна через garth API"""
        if not self.is_authenticated:
            garmin_logger.warning("🔒 Попытка получения данных сна без авторизации")
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            garmin_logger.info(f"😴 Получение данных сна через garth для {date_str}")
            
            # Метод 1: Через DailySleep класс
            try:
                garmin_logger.debug(f"📡 Попытка DailySleep.get({date_str})")
                daily_sleep = garth.DailySleep.get(date_str)
                if daily_sleep:
                    garmin_logger.info(f"✅ Данные сна получены через DailySleep для {date_str}")
                    garmin_logger.log_garth_object(daily_sleep, "DailySleep")
                    # Конвертируем объект garth в словарь для совместимости
                    converted = self._convert_sleep_to_dict(daily_sleep)
                    garmin_logger.debug(f"🔄 Конвертированные данные сна: {converted}")
                    return converted
                else:
                    garmin_logger.warning(f"❌ DailySleep.get вернул пустой результат для {date_str}")
            except Exception as e:
                garmin_logger.error(f"❌ DailySleep failed for {date_str}: {e}")
            
            # Метод 2: Через SleepData класс
            try:
                garmin_logger.debug(f"📡 Попытка SleepData.list({date_str}, {date_str})")
                sleep_data = garth.SleepData.list(date_str, date_str)
                if sleep_data:
                    garmin_logger.info(f"✅ Данные сна получены через SleepData для {date_str}")
                    garmin_logger.log_garth_object(sleep_data, "SleepData")
                    # Если список, берем первый элемент
                    if isinstance(sleep_data, list) and len(sleep_data) > 0:
                        garmin_logger.debug(f"📋 SleepData.list вернул список из {len(sleep_data)} элементов")
                        converted = self._convert_sleep_to_dict(sleep_data[0])
                    else:
                        converted = self._convert_sleep_to_dict(sleep_data)
                    garmin_logger.debug(f"🔄 Конвертированные данные сна: {converted}")
                    return converted
                else:
                    garmin_logger.warning(f"❌ SleepData.list вернул пустой результат для {date_str}")
            except Exception as e:
                garmin_logger.error(f"❌ SleepData failed for {date_str}: {e}")
            
            # Метод 3: Через прямой API вызов
            try:
                username = getattr(garth.client, 'username', self.username)
                if username:
                    api_url = f"/wellness-service/wellness/dailySleepData/{username}"
                    params = {"date": date_str, "nonSleepBufferMinutes": 60}
                    garmin_logger.debug(f"📡 Попытка connectapi: {api_url} с параметрами {params}")
                    
                    sleep_raw = garth.connectapi(api_url, params=params)
                    if sleep_raw:
                        garmin_logger.info(f"✅ Данные сна получены через connectapi для {date_str}")
                        garmin_logger.log_garth_object(sleep_raw, "ConnectAPI-Sleep")
                        return sleep_raw
                    else:
                        garmin_logger.warning(f"❌ connectapi вернул пустой результат для {date_str}")
                else:
                    garmin_logger.error(f"❌ Не удалось получить username для connectapi")
            except Exception as e:
                garmin_logger.error(f"❌ connectapi sleep failed for {date_str}: {e}")
            
            garmin_logger.warning(f"🚫 Все методы получения данных сна не сработали для {date_str}")
            return None
            
        except Exception as e:
            garmin_logger.error(f"❌ Общая ошибка получения данных сна для {date}: {e}")
            return None
    
    def get_body_battery_garth(self, date):
        """Получение данных Body Battery через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            # Метод 1: Через прямой API
            try:
                body_battery = garth.connectapi(
                    "/wellness-service/wellness/bodyBattery/reports/daily",
                    params={"startDate": date_str, "endDate": date_str}
                )
                if body_battery:
                    print(f"DEBUG: Body Battery получен через connectapi для {date_str}")
                    return body_battery
            except Exception as e:
                print(f"DEBUG: Body Battery connectapi failed for {date_str}: {e}")
            
            # Метод 2: Альтернативный endpoint
            try:
                body_battery_alt = garth.connectapi(
                    f"/wellness-service/wellness/bodyBattery/{date_str}"
                )
                if body_battery_alt:
                    print(f"DEBUG: Body Battery получен через альтернативный API для {date_str}")
                    return body_battery_alt
            except Exception as e:
                print(f"DEBUG: Body Battery alt API failed for {date_str}: {e}")
            
            return None
            
        except Exception as e:
            print(f"DEBUG: Ошибка получения Body Battery для {date}: {e}")
            return None
    
    def get_hrv_data_garth(self, date):
        """Получение HRV данных через garth с fallback'ом"""
        if not self.is_authenticated:
            return None
        
        date_str = date.strftime("%Y-%m-%d")
        
        # Метод 1: Через DailyHRV класс
        try:
            daily_hrv = garth.DailyHRV.get(date_str)
            if daily_hrv:
                print(f"DEBUG GARTH HRV: HRV данные получены через DailyHRV для {date_str}")
                result = self._convert_hrv_to_dict(daily_hrv)
                print(f"DEBUG GARTH HRV: Конвертированные данные: {result}")
                return result
        except Exception as e:
            print(f"DEBUG GARTH HRV: DailyHRV failed for {date_str}: {e}")
        
        # Метод 2: Через HRVData класс
        try:
            hrv_data = garth.HRVData.get(date_str)
            if hrv_data:
                print(f"DEBUG GARTH HRV: HRV данные получены через HRVData для {date_str}")
                result = self._convert_hrv_to_dict(hrv_data)
                print(f"DEBUG GARTH HRV: Конвертированные данные: {result}")
                return result
        except Exception as e:
            print(f"DEBUG GARTH HRV: HRVData failed for {date_str}: {e}")
            
        # Метод 3: Через прямой API запрос к HRV endpoint
        try:
            username = getattr(garth.client, 'username', self.username)
            if username:
                # Пробуем специфичный HRV endpoint
                hrv_api_url = f"/hrv-service/hrv/{username}"
                params = {"fromDate": date_str, "untilDate": date_str}
                print(f"DEBUG GARTH HRV: Попытка HRV API: {hrv_api_url}")
                
                try:
                    hrv_response = garth.connectapi(hrv_api_url, params=params)
                    if hrv_response:
                        print(f"DEBUG GARTH HRV: HRV API ответ получен: {type(hrv_response)}")
                        if isinstance(hrv_response, list) and len(hrv_response) > 0:
                            hrv_entry = hrv_response[0]
                            if 'lastNightAvg' in hrv_entry or 'rmssd' in hrv_entry:
                                rmssd_val = hrv_entry.get('lastNightAvg') or hrv_entry.get('rmssd')
                                print(f"DEBUG GARTH HRV: HRV значение из API: {rmssd_val}")
                                return {
                                    'hrvSummary': {
                                        'lastNightAvg': rmssd_val,
                                        'rmssd': rmssd_val
                                    }
                                }
                except Exception as hrv_e:
                    print(f"DEBUG GARTH HRV: HRV-specific API failed: {hrv_e}")
                
                # Пробуем общий daily summary endpoint
                api_url = f"/usersummary-service/usersummary/daily/{username}"
                params = {"calendarDate": date_str}
                print(f"DEBUG GARTH HRV: Попытка daily summary API: {api_url}")
                
                daily_data = garth.connectapi(api_url, params=params)
                if daily_data and isinstance(daily_data, dict):
                    print(f"DEBUG GARTH HRV: Daily data ключи: {list(daily_data.keys())}")
                    
                    # Ищем HRV в разных местах
                    hrv_value = None
                    if 'lastNightAvg' in daily_data:
                        hrv_value = daily_data['lastNightAvg']
                    elif 'restingHeartRateData' in daily_data and isinstance(daily_data['restingHeartRateData'], dict):
                        hrv_value = daily_data['restingHeartRateData'].get('hrv')
                    elif 'hrvData' in daily_data:
                        hrv_data_nested = daily_data['hrvData']
                        if isinstance(hrv_data_nested, dict):
                            hrv_value = hrv_data_nested.get('lastNightAvg') or hrv_data_nested.get('rmssd')
                    
                    if hrv_value:
                        print(f"DEBUG GARTH HRV: HRV найден в daily summary: {hrv_value}")
                        return {
                            'hrvSummary': {
                                'lastNightAvg': hrv_value,
                                'rmssd': hrv_value
                            }
                        }
        except Exception as e:
            print(f"DEBUG GARTH HRV: Direct API failed for {date_str}: {e}")
            
        # Метод 4: Fallback через общую сводку дня
        print(f"DEBUG GARTH HRV: HRV методы не сработали, пробуем fallback через daily summary для {date_str}")
        daily_summary = self.get_daily_summary_garth(date)
        if daily_summary:
            print(f"DEBUG GARTH HRV: Daily summary получен, ключи: {list(daily_summary.keys()) if isinstance(daily_summary, dict) else 'не словарь'}")
            if 'hrv' in daily_summary:
                print(f"DEBUG GARTH HRV: HRV данные найдены в daily summary для {date_str}")
                return self._convert_hrv_to_dict(daily_summary['hrv'])
            
        print(f"DEBUG GARTH HRV: Не удалось получить HRV данные для {date_str}")
        return None
    
    def _convert_hrv_to_dict(self, hrv_obj):
        """Конвертирует объект HRV из garth в словарь для совместимости"""
        try:
            print(f"DEBUG CONVERT HRV: Входной тип: {type(hrv_obj)}")
            
            # Если уже словарь, работаем с ним
            if isinstance(hrv_obj, dict):
                hrv_dict = hrv_obj
            # Проверяем доступные атрибуты объекта
            elif hasattr(hrv_obj, '__dict__'):
                hrv_dict = hrv_obj.__dict__.copy()
            elif hasattr(hrv_obj, 'dict'):
                hrv_dict = hrv_obj.dict()
            else:
                # Пытаемся получить основные поля вручную
                hrv_dict = {}
                for attr in ['lastNightAvg', 'rmssd', 'daily_rmssd', 'hrvSummary', 'hrv_summary', 'last_night_avg']:
                    if hasattr(hrv_obj, attr):
                        hrv_dict[attr] = getattr(hrv_obj, attr)
            
            print(f"DEBUG CONVERT HRV: Ключи словаря: {list(hrv_dict.keys()) if isinstance(hrv_dict, dict) else 'не словарь'}")
            
            # Ищем HRV значение в разных местах
            rmssd_value = None
            
            # Вариант 1: hrv_summary объект с атрибутами
            if 'hrv_summary' in hrv_dict:
                hrv_summary = hrv_dict['hrv_summary']
                print(f"DEBUG CONVERT HRV: Найден hrv_summary, тип: {type(hrv_summary)}")
                if hasattr(hrv_summary, 'last_night_avg'):
                    rmssd_value = hrv_summary.last_night_avg
                    print(f"DEBUG CONVERT HRV: Извлечен last_night_avg из объекта: {rmssd_value}")
                elif hasattr(hrv_summary, 'lastNightAvg'):
                    rmssd_value = hrv_summary.lastNightAvg
                elif isinstance(hrv_summary, dict):
                    rmssd_value = hrv_summary.get('last_night_avg') or hrv_summary.get('lastNightAvg')
            
            # Вариант 2: hrvSummary словарь
            if not rmssd_value and 'hrvSummary' in hrv_dict:
                hrv_summary = hrv_dict['hrvSummary']
                if isinstance(hrv_summary, dict):
                    rmssd_value = hrv_summary.get('lastNightAvg') or hrv_summary.get('rmssd') or hrv_summary.get('last_night_avg')
                elif hasattr(hrv_summary, 'last_night_avg'):
                    rmssd_value = hrv_summary.last_night_avg
                elif hasattr(hrv_summary, 'lastNightAvg'):
                    rmssd_value = hrv_summary.lastNightAvg
            
            # Вариант 3: Прямые поля в корне
            if not rmssd_value:
                rmssd_value = hrv_dict.get('lastNightAvg') or hrv_dict.get('rmssd') or hrv_dict.get('daily_rmssd') or hrv_dict.get('last_night_avg')
            
            print(f"DEBUG CONVERT HRV: Финальное значение RMSSD: {rmssd_value}")
            
            # Создаем структуру совместимую с garminconnect
            if rmssd_value is not None:
                return {
                    'hrvSummary': {
                        'lastNightAvg': rmssd_value,
                        'rmssd': rmssd_value
                    },
                    'raw_data': hrv_dict  # Сохраняем сырые данные для отладки
                }
            
            # Если структура неизвестна, возвращаем как есть с обёрткой
            print(f"DEBUG CONVERT HRV: RMSSD не найден, возвращаем сырые данные")
            return {
                'hrvSummary': hrv_dict,
                'raw_data': hrv_dict
            }
            
        except Exception as e:
            print(f"DEBUG CONVERT HRV: Ошибка конвертации HRV объекта: {e}")
            import traceback
            traceback.print_exc()
            # В крайнем случае создаем минимальную структуру
            return {
                'hrvSummary': {
                    'lastNightAvg': None
                },
                'raw_data': str(hrv_obj)
            }
    
    def _convert_sleep_to_dict(self, sleep_obj):
        """Конвертирует объект Sleep из garth в словарь для совместимости"""
        try:
            # Проверяем доступные атрибуты объекта
            if hasattr(sleep_obj, '__dict__'):
                sleep_dict = sleep_obj.__dict__.copy()
            elif hasattr(sleep_obj, 'dict'):
                sleep_dict = sleep_obj.dict()
            else:
                # Пытаемся получить основные поля вручную
                sleep_dict = {}
                for attr in ['sleepTimeSeconds', 'deepSleepSeconds', 'lightSleepSeconds', 'remSleepSeconds', 'awakeTimeSeconds']:
                    if hasattr(sleep_obj, attr):
                        sleep_dict[attr] = getattr(sleep_obj, attr)
            
            # Создаем структуру совместимую с garminconnect (если есть базовые поля)
            if any(key in sleep_dict for key in ['sleepTimeSeconds', 'deepSleepSeconds', 'lightSleepSeconds']):
                return {
                    'sleepTimeSeconds': sleep_dict.get('sleepTimeSeconds', 0),
                    'deepSleepSeconds': sleep_dict.get('deepSleepSeconds', 0),
                    'lightSleepSeconds': sleep_dict.get('lightSleepSeconds', 0),
                    'remSleepSeconds': sleep_dict.get('remSleepSeconds', 0),
                    'awakeTimeSeconds': sleep_dict.get('awakeTimeSeconds', 0),
                    'raw_data': sleep_dict  # Сохраняем сырые данные для отладки
                }
            
            # Если структура неизвестна, возвращаем как есть
            return {
                'raw_data': sleep_dict,
                'garth_object': True
            }
            
        except Exception as e:
            print(f"DEBUG: Ошибка конвертации Sleep объекта: {e}")
            # В крайнем случае создаем минимальную структуру
            return {
                'sleepTimeSeconds': 0,
                'raw_data': str(sleep_obj),
                'error': str(e)
            }
    
    def get_stress_data_garth(self, date):
        """Получение данных стресса через garth с fallback'ом"""
        if not self.is_authenticated:
            return None
        
        date_str = date.strftime("%Y-%m-%d")
        
        # Метод 1: Через прямой API запрос к правильному endpoint
        try:
            # Используем правильный endpoint для стресс-данных
            stress_api_url = f"/wellness-service/wellness/dailyStress/{date_str}"
            print(f"DEBUG STRESS: Попытка wellness stress API: {stress_api_url}")
            
            stress_response = garth.connectapi(stress_api_url)
            if stress_response:
                print(f"DEBUG STRESS: Stress API ответ получен через wellness")
                return self._convert_stress_to_dict(stress_response)
        except Exception as e:
            print(f"DEBUG STRESS: Wellness stress API failed: {e}")
        
        # Метод 2: Через endpoint с userId
        try:
            username = getattr(garth.client, 'username', self.username)
            if username:
                # Пробуем другой endpoint  
                stress_api_url = f"/wellness-service/wellness/dailyStress"
                params = {"date": date_str}
                print(f"DEBUG STRESS: Попытка stress API с параметрами: {stress_api_url}")
                
                stress_response = garth.connectapi(stress_api_url, params=params)
                if stress_response:
                    print(f"DEBUG STRESS: Stress API ответ получен")
                    return self._convert_stress_to_dict(stress_response)
        except Exception as e:
            print(f"DEBUG STRESS: Stress API с параметрами failed: {e}")
        
        # Метод 3: Пробуем получить через учетные данные пользователя
        try:
            # Часто стресс включен в данные дня
            user_data_url = f"/usersummary-service/usersummary/daily/{date_str}"
            print(f"DEBUG STRESS: Попытка usersummary API: {user_data_url}")
            
            user_summary = garth.connectapi(user_data_url)
            if user_summary:
                print(f"DEBUG STRESS: User summary получен, ищем стресс")
                if isinstance(user_summary, dict):
                    # Ищем стресс в разных местах
                    if 'averageStressLevel' in user_summary:
                        return {'avgStressLevel': user_summary['averageStressLevel']}
                    elif 'stressLevel' in user_summary:
                        return {'avgStressLevel': user_summary['stressLevel']}
                    elif 'maxStressLevel' in user_summary:
                        # Если есть только максимальный, используем его
                        return {'avgStressLevel': user_summary['maxStressLevel']}
        except Exception as e:
            print(f"DEBUG STRESS: User summary failed: {e}")
        
        # Метод 4: Возвращаем заглушку, если стресс данные недоступны
        print(f"DEBUG STRESS: Не удалось получить данные стресса для {date_str}")
        # Можно вернуть расчетный стресс на основе других данных
        return None
    
    def _convert_stress_to_dict(self, stress_obj):
        """Конвертирует объект стресса в нужный формат"""
        try:
            print(f"DEBUG CONVERT STRESS: Входной тип: {type(stress_obj)}")
            
            # Если это уже число - это средний уровень стресса
            if isinstance(stress_obj, (int, float)):
                print(f"DEBUG CONVERT STRESS: Простое число: {stress_obj}")
                return {'avgStressLevel': stress_obj, 'overallStressLevel': stress_obj}
            
            # Если это словарь
            if isinstance(stress_obj, dict):
                avg_stress = stress_obj.get('avgStressLevel') or stress_obj.get('overallStressLevel') or stress_obj.get('averageStressLevel')
                if avg_stress:
                    print(f"DEBUG CONVERT STRESS: Извлечен уровень из словаря: {avg_stress}")
                    return {'avgStressLevel': avg_stress, 'overallStressLevel': avg_stress}
            
            # Если это объект с атрибутами
            if hasattr(stress_obj, '__dict__'):
                stress_dict = stress_obj.__dict__
                print(f"DEBUG CONVERT STRESS: Ключи объекта: {list(stress_dict.keys())}")
                
                # Ищем средний уровень стресса
                avg_stress = None
                if hasattr(stress_obj, 'avgStressLevel'):
                    avg_stress = stress_obj.avgStressLevel
                elif hasattr(stress_obj, 'overallStressLevel'):
                    avg_stress = stress_obj.overallStressLevel
                elif hasattr(stress_obj, 'averageStressLevel'):
                    avg_stress = stress_obj.averageStressLevel
                elif 'stressData' in stress_dict and isinstance(stress_dict['stressData'], dict):
                    avg_stress = stress_dict['stressData'].get('avgStressLevel')
                
                if avg_stress:
                    print(f"DEBUG CONVERT STRESS: Извлечен уровень из объекта: {avg_stress}")
                    return {'avgStressLevel': avg_stress, 'overallStressLevel': avg_stress}
            
            # Если не смогли извлечь - возвращаем None
            print(f"DEBUG CONVERT STRESS: Не удалось извлечь уровень стресса")
            return None
            
        except Exception as e:
            print(f"DEBUG CONVERT STRESS: Ошибка конвертации: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_daily_summary_garth(self, date):
        """Получение общей сводки за день (часто содержит HRV, стресс и т.д.)"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            username = getattr(garth.client, 'username', self.username)
            if username:
                summary = garth.connectapi(
                    f"/wellness-service/wellness/dailySummary/{username}",
                    params={"calendarDate": date_str}
                )
                if summary:
                    print(f"DEBUG: Daily summary получено для {date_str}")
                    return summary
            return None
        except Exception as e:
            print(f"DEBUG: Ошибка получения daily summary для {date}: {e}")
            return None
    
    def get_wellness_comprehensive(self, date):
        """Получение комплексных данных здоровья за день"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            # Собираем все доступные данные
            comprehensive_data = {
                'date': date_str,
                'sleep': None,
                'hrv': None,
                'stress': None,
                'body_battery': None,
                'steps': None
            }
            
            # Данные сна
            comprehensive_data['sleep'] = self.get_sleep_data_garth(date)
            
            # HRV данные
            comprehensive_data['hrv'] = self.get_hrv_data_garth(date)
            
            # Данные стресса
            comprehensive_data['stress'] = self.get_stress_data_garth(date)
            
            # Body Battery
            comprehensive_data['body_battery'] = self.get_body_battery_garth(date)
            
            # Шаги и активность
            try:
                daily_steps = garth.DailySteps.get(date_str)
                comprehensive_data['steps'] = daily_steps
            except Exception as e:
                print(f"DEBUG: DailySteps failed for {date_str}: {e}")
            
            # Проверяем, что хотя бы что-то получено
            has_data = any(comprehensive_data[key] is not None for key in comprehensive_data if key != 'date')
            
            if has_data:
                print(f"DEBUG: Комплексные данные получены для {date_str}")
                return comprehensive_data
            else:
                print(f"DEBUG: Комплексные данные не получены для {date_str}")
                return None
                
        except Exception as e:
            print(f"DEBUG: Ошибка получения комплексных данных для {date}: {e}")
            return None
    
    @staticmethod
    def _snake_to_camel(key: str) -> str:
        parts = key.split('_')
        if not parts:
            return key
        return parts[0] + ''.join(part.capitalize() for part in parts[1:])

    def _normalize_profile(self, profile_obj: Any) -> Dict[str, Any] | None:
        """Приводим профиль garth к словарю, нормализуем проблемные поля и ключи."""
        if profile_obj is None:
            return None

        if hasattr(profile_obj, "model_dump"):
            profile_data = profile_obj.model_dump()
        elif isinstance(profile_obj, dict):
            profile_data = dict(profile_obj)
        else:
            profile_data = {
                key: getattr(profile_obj, key)
                for key in dir(profile_obj)
                if not key.startswith("_") and not callable(getattr(profile_obj, key))
            }

        normalized = dict(profile_data)

        for key in ("motivation", "other_motivation", "otherMotivation"):
            if key in normalized and normalized[key] is not None and not isinstance(normalized[key], str):
                normalized[key] = str(normalized[key])

        additional_keys: Dict[str, Any] = {}
        for key, value in list(normalized.items()):
            if '_' in key:
                camel_key = self._snake_to_camel(key)
                if camel_key not in normalized:
                    additional_keys[camel_key] = value

        if additional_keys:
            normalized.update(additional_keys)

        return normalized

    def get_user_profile(self):
        """Получение профиля пользователя через garth"""
        if not self.is_authenticated:
            return None

        if self._cached_profile is not None:
            return self._cached_profile

        if not self._profile_fetch_failed:
            try:
                profile = garth.UserProfile.get()
                if profile:
                    print("DEBUG: Профиль пользователя получен через garth")
                    normalized = self._normalize_profile(profile)
                    self._cached_profile = normalized
                    return normalized
            except ValidationError as e:
                self._profile_fetch_failed = True
                print(f"DEBUG: Ошибка валидации профиля garth: {e}")
            except Exception as e:
                self._profile_fetch_failed = True
                print(f"DEBUG: Ошибка получения профиля: {e}")

        # Резервный сценарий: получаем профиль напрямую и нормализуем
        try:
            raw_profile = garth.connectapi("/userprofile-service/socialProfile")
            if raw_profile:
                print("DEBUG: Профиль пользователя получен через резервный socialProfile API")
                normalized = self._normalize_profile(raw_profile)
                self._cached_profile = normalized
                return normalized
        except Exception as e:
            print(f"DEBUG: Ошибка резервного получения профиля: {e}")

        return None
    
    def test_connection(self):
        """Тестирование подключения и доступных данных"""
        if not self.is_authenticated:
            return {"error": "Не авторизован"}
        
        results = {
            "authenticated": True,
            "username": self.username,
            "available_methods": [],
            "test_results": {}
        }
        
        # Тестируем доступные методы
        test_date = datetime.now() - timedelta(days=1)
        
        test_date_str = test_date.strftime("%Y-%m-%d")

        methods_to_test = [
            ("SleepData", lambda: garth.SleepData.get(test_date_str)),
            ("DailySleep", lambda: garth.DailySleep.list(end=test_date_str, period=1)),
            ("HRVData", lambda: garth.HRVData.get(test_date_str)),
            ("DailyHRV", lambda: garth.DailyHRV.list(end=test_date_str, period=1)),
            ("DailyStress", lambda: garth.DailyStress.list(end=test_date_str, period=1)),
            ("DailySteps", lambda: garth.DailySteps.list(end=test_date_str, period=1)),
            ("UserProfile", lambda: self.get_user_profile()),
        ]
        
        for method_name, method_func in methods_to_test:
            try:
                result = method_func()
                results["test_results"][method_name] = "✅ Работает" if result else "❌ Нет данных"
                if result:
                    results["available_methods"].append(method_name)
            except Exception as e:
                results["test_results"][method_name] = f"❌ Ошибка: {str(e)[:50]}"
        
        return results
    
    def disconnect(self):
        """Отключение"""
        self.is_authenticated = False
        self.auth_error = None
        self.username = None
        self._cached_profile = None
        self._profile_fetch_failed = False
