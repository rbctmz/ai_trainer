"""
Клиент для работы с Garmin Connect через библиотеку garth
"""

import garth
from datetime import datetime, timedelta
import streamlit as st
import sys
import os

# Добавляем путь к логгеру
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import garmin_logger

class GarthClient:
    """Улучшенный клиент для работы с Garmin Connect через garth"""
    
    def __init__(self):
        self.is_authenticated = False
        self.auth_error = None
        self.username = None
    
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
        """Получение HRV данных через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            # Метод 1: Через DailyHRV класс
            try:
                daily_hrv = garth.DailyHRV.get(date_str)
                if daily_hrv:
                    print(f"DEBUG: HRV данные получены через DailyHRV для {date_str}")
                    # Конвертируем объект garth в словарь для совместимости
                    return self._convert_hrv_to_dict(daily_hrv)
            except Exception as e:
                print(f"DEBUG: DailyHRV failed for {date_str}: {e}")
            
            # Метод 2: Через HRVData класс
            try:
                hrv_data = garth.HRVData.get(date_str)
                if hrv_data:
                    print(f"DEBUG: HRV данные получены через HRVData для {date_str}")
                    # Конвертируем объект garth в словарь для совместимости
                    return self._convert_hrv_to_dict(hrv_data)
            except Exception as e:
                print(f"DEBUG: HRVData failed for {date_str}: {e}")
            
            return None
            
        except Exception as e:
            print(f"DEBUG: Ошибка получения HRV данных для {date}: {e}")
            return None
    
    def _convert_hrv_to_dict(self, hrv_obj):
        """Конвертирует объект HRV из garth в словарь для совместимости"""
        try:
            # Проверяем доступные атрибуты объекта
            if hasattr(hrv_obj, '__dict__'):
                hrv_dict = hrv_obj.__dict__.copy()
            elif hasattr(hrv_obj, 'dict'):
                hrv_dict = hrv_obj.dict()
            else:
                # Пытаемся получить основные поля вручную
                hrv_dict = {}
                for attr in ['lastNightAvg', 'rmssd', 'daily_rmssd', 'hrvSummary']:
                    if hasattr(hrv_obj, attr):
                        hrv_dict[attr] = getattr(hrv_obj, attr)
            
            # Создаем структуру совместимую с garminconnect
            if 'lastNightAvg' in hrv_dict or 'rmssd' in hrv_dict or 'daily_rmssd' in hrv_dict:
                rmssd_value = hrv_dict.get('lastNightAvg') or hrv_dict.get('rmssd') or hrv_dict.get('daily_rmssd')
                
                return {
                    'hrvSummary': {
                        'lastNightAvg': rmssd_value,
                        'rmssd': rmssd_value
                    },
                    'raw_data': hrv_dict  # Сохраняем сырые данные для отладки
                }
            
            # Если структура неизвестна, возвращаем как есть с обёрткой
            return {
                'hrvSummary': hrv_dict,
                'raw_data': hrv_dict
            }
            
        except Exception as e:
            print(f"DEBUG: Ошибка конвертации HRV объекта: {e}")
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
        """Получение данных стресса через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            # Через DailyStress класс
            try:
                daily_stress = garth.DailyStress.get(date_str)
                if daily_stress:
                    print(f"DEBUG: Данные стресса получены через DailyStress для {date_str}")
                    return daily_stress
            except Exception as e:
                print(f"DEBUG: DailyStress failed for {date_str}: {e}")
            
            return None
            
        except Exception as e:
            print(f"DEBUG: Ошибка получения данных стресса для {date}: {e}")
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
    
    def get_user_profile(self):
        """Получение профиля пользователя через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            profile = garth.UserProfile.get()
            if profile:
                print("DEBUG: Профиль пользователя получен через garth")
                return profile
        except Exception as e:
            print(f"DEBUG: Ошибка получения профиля: {e}")
        
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
        
        methods_to_test = [
            ("DailySleep", lambda: garth.DailySleep.get(test_date.strftime("%Y-%m-%d"))),
            ("SleepData", lambda: garth.SleepData.list(test_date.strftime("%Y-%m-%d"), test_date.strftime("%Y-%m-%d"))),
            ("DailyHRV", lambda: garth.DailyHRV.get(test_date.strftime("%Y-%m-%d"))),
            ("DailyStress", lambda: garth.DailyStress.get(test_date.strftime("%Y-%m-%d"))),
            ("DailySteps", lambda: garth.DailySteps.get(test_date.strftime("%Y-%m-%d"))),
            ("UserProfile", lambda: garth.UserProfile.get())
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