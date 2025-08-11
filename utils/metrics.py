import numpy as np
import pandas as pd

class MetricsCalculator:
    
    @staticmethod
    def normalized_power(power_data, window=30):
        """Нормализованная мощность (NP)"""
        if len(power_data) == 0:
            return 0
        
        # 30-секундные скользящие средние
        rolling_avg = pd.Series(power_data).rolling(window).mean()
        # 4-я степень средних
        fourth_power = rolling_avg ** 4
        # Среднее и корень 4-й степени
        np_value = fourth_power.mean() ** 0.25
        return np_value
    
    @staticmethod
    def intensity_factor(normalized_power, ftp):
        """Фактор интенсивности"""
        if ftp > 0:
            return normalized_power / ftp
        return 0
    
    @staticmethod
    def training_stress_score(normalized_power, duration_seconds, ftp):
        """Training Stress Score"""
        if ftp > 0:
            intensity_factor = normalized_power / ftp
            duration_hours = duration_seconds / 3600
            tss = duration_hours * (intensity_factor ** 2) * 100
            return tss
        return 0
    
    @staticmethod
    def chronic_training_load(tss_data, days=42):
        """Хроническая тренировочная нагрузка (CTL)"""
        return pd.Series(tss_data).rolling(days).mean().iloc[-1]
    
    @staticmethod
    def acute_training_load(tss_data, days=7):
        """Острая тренировочная нагрузка (ATL)"""
        return pd.Series(tss_data).rolling(days).mean().iloc[-1]
    
    @staticmethod
    def training_stress_balance(ctl, atl):
        """Баланс тренировочного стресса (TSB)"""
        return ctl - atl