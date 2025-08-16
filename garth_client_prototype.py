
import garth
from datetime import datetime, timedelta

class GarthClient:
    """Клиент для работы с Garmin Connect через библиотеку garth"""
    
    def __init__(self):
        self.is_authenticated = False
        self.auth_error = None
    
    def authenticate(self, email, password):
        """Аутентификация через garth"""
        try:
            garth.login(email, password)
            self.is_authenticated = True
            self.auth_error = None
            return True
        except Exception as e:
            self.auth_error = str(e)
            self.is_authenticated = False
            return False
    
    def get_sleep_data(self, date):
        """Получение данных сна через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            sleep_data = garth.connectapi(
                f"/wellness-service/wellness/dailySleepData/{garth.client.username}",
                params={"date": date_str, "nonSleepBufferMinutes": 60}
            )
            return sleep_data
        except Exception as e:
            print(f"Ошибка получения данных сна: {e}")
            return None
    
    def get_body_battery_data(self, date):
        """Получение данных Body Battery через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            body_battery = garth.connectapi(
                "/wellness-service/wellness/bodyBattery/reports/daily",
                params={"startDate": date_str, "endDate": date_str}
            )
            return body_battery
        except Exception as e:
            print(f"Ошибка получения Body Battery: {e}")
            return None
    
    def get_wellness_data(self, date):
        """Получение общих данных здоровья через garth"""
        if not self.is_authenticated:
            return None
        
        try:
            date_str = date.strftime("%Y-%m-%d")
            wellness = garth.connectapi(
                f"/wellness-service/wellness/wellness/{date_str}"
            )
            return wellness
        except Exception as e:
            print(f"Ошибка получения данных здоровья: {e}")
            return None
