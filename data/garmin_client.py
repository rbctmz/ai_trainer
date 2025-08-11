from garminconnect import Garmin
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

class GarminClient:
    def __init__(self):
        self.client = None
        self.is_authenticated = False
        self.auth_error = None
    
    def authenticate(self, email, password):
        """Аутентификация в Garmin Connect"""
        try:
            self.client = Garmin(email, password)
            self.client.login()
            self.is_authenticated = True
            self.auth_error = None
            return True
        except Exception as e:
            self.auth_error = str(e)
            self.is_authenticated = False
            return False
    
    def get_activities(self, start_date, end_date, limit=100):
        """Получение активностей за период"""
        if not self.is_authenticated:
            return []
        
        try:
            activities = self.client.get_activities_by_date(
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
                activitytype=None
            )
            return activities[:limit] if activities else []
        except Exception as e:
            st.error(f"Ошибка получения активностей: {e}")
            return []
    
    def get_activity_details(self, activity_id):
        """Детальная информация об активности"""
        if not self.is_authenticated:
            return None
        
        try:
            return self.client.get_activity_by_id(activity_id)
        except Exception as e:
            st.error(f"Ошибка получения деталей активности: {e}")
            return None
    
    def get_hrv_data(self, date):
        """Получение HRV данных за день"""
        if not self.is_authenticated:
            return None
        
        try:
            return self.client.get_hrv_data(date.strftime("%Y-%m-%d"))
        except Exception as e:
            # HRV данные часто недоступны, это не критичная ошибка
            return None
    
    def get_user_profile(self):
        """Получение профиля пользователя"""
        if not self.is_authenticated:
            return None
            
        try:
            return self.client.get_user_profile()
        except Exception as e:
            st.error(f"Ошибка получения профиля: {e}")
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
        self.is_authenticated = False
        self.auth_error = None