import numpy as np
import pandas as pd

class HRVAnalyzer:
    
    @staticmethod
    def calculate_rmssd(rr_intervals):
        """Root Mean Square of Successive Differences"""
        if len(rr_intervals) < 2:
            return None
        
        successive_diffs = np.diff(rr_intervals)
        rmssd = np.sqrt(np.mean(successive_diffs ** 2))
        return rmssd
    
    @staticmethod
    def recovery_score(rmssd_current, rmssd_baseline):
        """Оценка восстановления на основе RMSSD"""
        if rmssd_baseline > 0:
            recovery_ratio = rmssd_current / rmssd_baseline
            # Нормализация в проценты
            recovery_score = min(100, max(0, recovery_ratio * 100))
            return recovery_score
        return 50  # Нейтральное значение