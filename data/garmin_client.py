from garminconnect import Garmin
from datetime import datetime, timedelta
import logging
import pandas as pd

garmin_logger = logging.getLogger("garmin_sync")

# Импорт garth клиента
try:
    from .garth_client import GarthClient
    GARTH_AVAILABLE = True
except ImportError:
    try:
        from garth_client import GarthClient
        GARTH_AVAILABLE = True
    except ImportError:
        GARTH_AVAILABLE = False
        print("WARNING: garth_client не найден, использование только garminconnect")


def _summarize_auth_error(error):
    """Normalize noisy garminconnect auth failures into one actionable message."""
    raw_message = str(error or "").strip()
    normalized = raw_message.lower()
    has_rate_limit = "429" in normalized or "rate limited" in normalized
    has_invalid_credentials = (
        "401 unauthorized" in normalized
        or "invalid username or password" in normalized
    )
    has_widget_fallback_noise = (
        "unexpected title" in normalized
        or "garmin authentication application" in normalized
    )

    detail_parts = []
    if has_rate_limit:
        detail_parts.append("Garmin временно ограничил вход с этого IP (429).")
    if has_invalid_credentials:
        detail_parts.append("Garmin также вернул 401 Unauthorized.")
    if has_widget_fallback_noise:
        detail_parts.append("Встроенный widget fallback тоже не подтвердил логин.")

    if has_rate_limit and has_invalid_credentials:
        summary = (
            "Garmin временно ограничил вход с этого IP (429), а повторная авторизация "
            "завершилась 401 Unauthorized. Подождите 30-60 минут или смените сеть, "
            "затем перепроверьте логин и пароль."
        )
        kind = "rate_limited_with_401"
    elif has_rate_limit:
        summary = (
            "Garmin временно ограничил вход с этого IP (429). "
            "Подождите 30-60 минут или попробуйте другую сеть."
        )
        kind = "rate_limited"
    elif has_invalid_credentials:
        summary = (
            "Garmin отклонил логин или пароль (401 Unauthorized). "
            "Проверьте введенные учетные данные."
        )
        kind = "invalid_credentials"
    elif has_widget_fallback_noise:
        summary = (
            "Garmin не подтвердил fallback-авторизацию через widget flow. "
            "Попробуйте повторить вход позже."
        )
        kind = "widget_fallback"
    else:
        summary = raw_message or "Не удалось авторизоваться в Garmin Connect."
        kind = "unknown"

    return {
        "kind": kind,
        "summary": summary,
        "details": " ".join(detail_parts).strip(),
        "raw": raw_message,
    }

class GarminClient:
    def __init__(self):
        self.client = None
        self.garth_client = GarthClient() if GARTH_AVAILABLE else None
        self.is_authenticated = False
        self.auth_error = None
        self.auth_error_raw = None
        self.auth_error_kind = None
        self.last_error = None
        self.use_garth = False

    def _clear_last_error(self):
        """Очищает последнюю не-UI ошибку клиента."""
        self.last_error = None

    def _remember_error(self, context, message):
        """Сохраняет ошибку для последующей отрисовки в UI-слое."""
        self.last_error = {
            "context": context,
            "message": message,
        }
        garmin_logger.error(f"{context}: {message}")

    def pop_last_error(self):
        """Возвращает и очищает последнюю ошибку клиента."""
        error = self.last_error
        self.last_error = None
        return error
    
    def authenticate(self, email, password):
        """Authenticate through garminconnect. garth remains diagnostics-only."""
        try:
            self.client = Garmin(email, password)
            self.client.login()
            self.is_authenticated = True
            self.auth_error = None
            self.auth_error_raw = None
            self.auth_error_kind = None
            self._clear_last_error()
            self.use_garth = False
            print("DEBUG: Авторизация через garminconnect успешна")
            return True
        except Exception as e:
            error_info = _summarize_auth_error(e)
            self.auth_error = error_info["summary"]
            self.auth_error_raw = error_info["raw"]
            self.auth_error_kind = error_info["kind"]
            self.is_authenticated = False
            self.use_garth = False
            print(f"DEBUG: Ошибка авторизации через garminconnect: {self.auth_error}")
            if self.auth_error_raw and self.auth_error_raw != self.auth_error:
                print(f"DEBUG: Технические детали авторизации Garmin: {self.auth_error_raw}")
            return False
    
    def get_activities(self, start_date, end_date, limit=100):
        """Получение активностей за период"""
        if not self.is_authenticated:
            return []
        
        # Если используем garth, пробуем его методы
        if self.use_garth and self.garth_client:
            try:
                import garth
                # Получаем активности через garth
                activities = garth.connectapi(
                    "/activitylist-service/activities/search/activities",
                    params={
                        "start": 0,
                        "limit": limit,
                        "startDate": start_date.strftime("%Y-%m-%d"),
                        "endDate": end_date.strftime("%Y-%m-%d")
                    }
                )
                if activities and isinstance(activities, list):
                    self._clear_last_error()
                    print(f"DEBUG: Получено {len(activities)} активностей через garth")
                    return activities[:limit]
                else:
                    print("DEBUG: garth не вернул активности, пробуем альтернативный метод")
            except Exception as e:
                print(f"DEBUG: Ошибка получения активностей через garth: {e}")
        
        # Используем стандартный garminconnect клиент
        if self.client:
            try:
                activities = self.client.get_activities_by_date(
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                    activitytype=None
                )
                self._clear_last_error()
                return activities[:limit] if activities else []
            except Exception as e:
                self._remember_error("activities", f"Ошибка получения активностей: {e}")
                return []

        self._remember_error("activities", "Нет доступного клиента для получения активностей")
        return []
    
    def get_activity_details(self, activity_id):
        """Детальная информация об активности"""
        if not self.is_authenticated:
            return None
        
        # Если используем garth, пробуем его методы
        if self.use_garth and self.garth_client:
            try:
                import garth
                activity_details = garth.connectapi(f"/activity-service/activity/{activity_id}")
                if activity_details:
                    self._clear_last_error()
                    print(f"DEBUG: Детали активности {activity_id} получены через garth")
                    return activity_details
            except Exception as e:
                print(f"DEBUG: Ошибка получения деталей активности через garth: {e}")
        
        # Используем стандартный garminconnect клиент
        if self.client:
            try:
                activity_details = self.client.get_activity_by_id(activity_id)
                self._clear_last_error()
                return activity_details
            except Exception as e:
                self._remember_error("activity_details", f"Ошибка получения деталей активности: {e}")
                return None

        self._remember_error("activity_details", "Нет доступного клиента для получения деталей активности")
        return None
    
    def get_hrv_data(self, date):
        """Получение HRV данных за день"""
        if not self.is_authenticated:
            return None
        
        # Если используем garth, пробуем его методы сначала
        if self.use_garth and self.garth_client:
            hrv_data = self.garth_client.get_hrv_data_garth(date)
            if hrv_data:
                return hrv_data
        
        # Используем стандартный garminconnect клиент
        if self.client:
            try:
                return self.client.get_hrv_data(date.strftime("%Y-%m-%d"))
            except Exception as e:
                # HRV данные часто недоступны, это не критичная ошибка
                return None
        
        return None
    
    def get_stress_data(self, date):
        """Получение данных о стрессе за день"""
        if not self.is_authenticated:
            return None
        
        # Если используем garth, пробуем его методы сначала
        if self.use_garth and self.garth_client:
            stress_data = self.garth_client.get_stress_data_garth(date)
            if stress_data:
                return stress_data
        
        # Используем стандартный garminconnect клиент как fallback
        if self.client:
            try:
                print(f"DEBUG: Пробуем получить стресс через garminconnect для {date.strftime('%Y-%m-%d')}")
                stress_result = self.client.get_stress_data(date.strftime("%Y-%m-%d"))
                if stress_result:
                    print(f"DEBUG: Стресс получен через garminconnect: {type(stress_result)}")
                    # Конвертируем в нужный формат
                    if isinstance(stress_result, list) and len(stress_result) > 0:
                        # Берем средний стресс за день
                        total_stress = sum(item.get('stressLevel', 0) for item in stress_result if item.get('stressLevel'))
                        count = len([item for item in stress_result if item.get('stressLevel')])
                        if count > 0:
                            avg_stress = total_stress / count
                            return {'avgStressLevel': avg_stress}
                    elif isinstance(stress_result, dict):
                        avg = stress_result.get('avgStressLevel') or stress_result.get('averageStressLevel')
                        if avg:
                            return {'avgStressLevel': avg}
                return stress_result
            except Exception as e:
                print(f"DEBUG: Стресс данные недоступны через garminconnect: {e}")
                # Стресс данные могут быть недоступны
                return None
        
        return None
    
    def get_body_battery_data(self, date):
        """Получение данных Body Battery (восстановление) за день"""
        if not self.is_authenticated:
            return None
        
        # Если используем garth, пробуем его методы сначала
        if self.use_garth and self.garth_client:
            battery_data = self.garth_client.get_body_battery_garth(date)
            if battery_data:
                return battery_data
        
        # Используем стандартный garminconnect клиент
        if self.client:
            try:
                # Body Battery возвращает данные за период
                date_str = date.strftime("%Y-%m-%d")
                return self.client.get_body_battery(date_str, date_str)
            except Exception as e:
                # Body Battery данные могут быть недоступны
                return None
        
        return None
    
    def get_user_profile(self):
        """Получение профиля пользователя"""
        if not self.is_authenticated:
            return None
            
        # Если используем garth, пробуем его методы сначала
        if self.use_garth and self.garth_client:
            profile = self.garth_client.get_user_profile()
            if profile:
                self._clear_last_error()
                return profile
        
        # Используем стандартный garminconnect клиент
        if self.client:
            try:
                profile = self.client.get_user_profile()
                if isinstance(profile, dict):
                    normalized_profile = dict(profile)
                    display_name = getattr(self.client, "display_name", None)
                    full_name = getattr(self.client, "full_name", None)

                    if display_name:
                        normalized_profile.setdefault('displayName', display_name)
                        normalized_profile.setdefault('display_name', display_name)
                    if full_name:
                        normalized_profile.setdefault('fullName', full_name)
                        normalized_profile.setdefault('full_name', full_name)

                    self._clear_last_error()
                    return normalized_profile

                self._clear_last_error()
                return profile
            except Exception as e:
                self._remember_error("user_profile", f"Ошибка получения профиля: {e}")
                return None
        
        return None
    
    def get_device_info(self):
        """Получение информации об устройствах"""
        if not self.is_authenticated:
            return []
            
        try:
            devices = self.client.get_devices()
            return devices if devices else []
        except Exception as e:
            return []
    
    def disconnect(self):
        """Отключение от Garmin Connect"""
        self.client = None
        if self.garth_client:
            self.garth_client.disconnect()
        self.is_authenticated = False
        self.auth_error = None
        self.auth_error_raw = None
        self.auth_error_kind = None
        self._clear_last_error()
        self.use_garth = False
    
    # =================== НОВЫЕ МЕТОДЫ ФАЗА 1 ===================
    
    def get_sleep_data(self, date):
        """Получение данных сна за конкретную ночь с поддержкой garth"""
        if not self.is_authenticated:
            garmin_logger.warning("🔒 Попытка получения данных сна без авторизации")
            return None
        
        date_str = date.strftime("%Y-%m-%d")
        garmin_logger.info(f"😴 Получение данных сна для {date_str} (garth: {self.use_garth})")
        
        # Если используем garth, пробуем его методы
        if self.use_garth and self.garth_client:
            garmin_logger.debug(f"🚀 Использование garth для получения данных сна {date_str}")
            result = self.garth_client.get_sleep_data_garth(date)
            if result:
                garmin_logger.info(f"✅ Данные сна получены через garth для {date_str}")
                return result
            else:
                garmin_logger.warning(f"❌ garth не смог получить данные сна для {date_str}")
        
        # Используем стандартные методы garminconnect
        if self.client:
            methods_to_try = [
                ('get_sleep_data', lambda: self.client.get_sleep_data(date_str)),
                ('get_stats_and_body', lambda: self.client.get_stats_and_body(date_str)),
            ]
            
            for method_name, method_func in methods_to_try:
                try:
                    result = method_func()
                    if result:
                        print(f"DEBUG: Данные сна получены через {method_name} для {date_str}")
                        return result
                except Exception as e:
                    print(f"DEBUG: {method_name} failed for {date_str}: {e}")
                    continue
        
        # Если ничего не сработало
        print(f"DEBUG: Все методы получения данных сна не сработали для {date_str}")
        return None
    
    def get_resting_heart_rate(self, date):
        """Получение пульса покоя за день"""
        if not self.is_authenticated:
            return None
        
        try:
            rhr_data = self.client.get_resting_heart_rate(date.strftime("%Y-%m-%d"))
            return rhr_data
        except Exception as e:
            # Пульс покоя может быть недоступен
            return None
    
    def get_daily_steps(self, date):
        """Получение шагов и общей активности за день"""
        if not self.is_authenticated:
            return None
        
        try:
            steps_data = self.client.get_steps_data(date.strftime("%Y-%m-%d"))
            return steps_data
        except Exception as e:
            # Используем альтернативный метод
            try:
                return self.client.get_stats(date.strftime("%Y-%m-%d"))
            except Exception:
                return None
    
    def get_daily_summary(self, date):
        """Получение общей сводки за день"""
        if not self.is_authenticated:
            return None
        
        try:
            summary = self.client.get_stats(date.strftime("%Y-%m-%d"))
            return summary
        except Exception as e:
            return None
    
    def get_training_status(self):
        """Получение текущего статуса тренированности"""
        if not self.is_authenticated:
            return None
        
        # Пробуем разные методы получения статуса тренированности
        from datetime import datetime, timedelta
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        methods_to_try = []

        if self.use_garth and self.garth_client:
            methods_to_try.append(
                ('garth_get_training_status', lambda d=current_date: self.garth_client.get_training_status(d))
            )
            methods_to_try.append(
                (
                    'garth_get_progress_summary_between_dates',
                    lambda start=start_date, end=current_date: self.garth_client.get_progress_summary_between_dates(start, end)
                )
            )

        if self.client:
            methods_to_try.append(
                ('get_training_status', lambda d=current_date: self.client.get_training_status(d))
            )
            methods_to_try.append(
                (
                    'get_progress_summary_between_dates',
                    lambda start=start_date, end=current_date: self.client.get_progress_summary_between_dates(start, end)
                )
            )

        if not methods_to_try:
            print("DEBUG: Нет доступных клиентов для получения статуса тренированности")
            return None
        
        for method_name, method_func in methods_to_try:
            try:
                result = method_func()
                if result:
                    print(f"DEBUG: Статус тренированности получен через {method_name}")
                    try:
                        garmin_logger.debug(f"TRAINING STATUS RAW ({method_name}): {result}")
                    except Exception:
                        pass
                    return result
            except Exception as e:
                print(f"DEBUG: {method_name} failed: {e}")
                continue
        
        print("DEBUG: Все методы получения статуса тренированности не сработали")
        return None
    
    def get_vo2_max(self):
        """Получение текущего VO2 max"""
        if not self.is_authenticated:
            return None
        
        try:
            vo2_data = self.client.get_vo2_max()
            return vo2_data
        except Exception as e:
            return None
    
    def get_training_readiness(self):
        """Получение готовности к тренировке"""
        if not self.is_authenticated:
            return None
        
        try:
            readiness = self.client.get_training_readiness()
            return readiness
        except Exception as e:
            return None
    
    def get_comprehensive_daily_data(self, date):
        """Получение всех доступных данных за день одним вызовом"""
        if not self.is_authenticated:
            return {}
        
        date_str = date.strftime("%Y-%m-%d")
        comprehensive_data = {
            'date': date_str,
            'sleep': None,
            'resting_hr': None,
            'daily_summary': None,
            'steps': None
        }
        
        # Собираем все данные
        try:
            comprehensive_data['sleep'] = self.get_sleep_data(date)
        except Exception:
            pass
            
        try:
            comprehensive_data['resting_hr'] = self.get_resting_heart_rate(date)
        except Exception:
            pass
            
        try:
            comprehensive_data['daily_summary'] = self.get_daily_summary(date)
        except Exception:
            pass
            
        try:
            comprehensive_data['steps'] = self.get_daily_steps(date)
        except Exception:
            pass
        
        return comprehensive_data
    
    def test_garth_connection(self):
        """Return legacy garth diagnostic info and, when possible, live checks."""
        if not self.garth_client:
            return {
                "available": False,
                "mode": "legacy_diagnostic",
                "error": "garth клиент недоступен в окружении",
            }

        return self.garth_client.test_connection()
    
    def get_connection_info(self):
        """Информация о типе подключения"""
        garth_runtime = self.garth_client.get_runtime_info() if self.garth_client else None
        return {
            "authenticated": self.is_authenticated,
            "using_garth": self.use_garth,
            "garth_available": bool(garth_runtime and garth_runtime.get("available")),
            "garth_mode": "legacy_diagnostic",
            "garth_runtime": garth_runtime,
            "auth_error": self.auth_error,
            "auth_error_raw": self.auth_error_raw,
            "auth_error_kind": self.auth_error_kind,
            "last_error": self.last_error,
        }
