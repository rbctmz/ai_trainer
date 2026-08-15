import numpy as np

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
    
    @staticmethod
    def recovery_score_advanced(hrv_data_df):
        """
        Оценка восстановления по методу AI Endurance:
        - 7-дневное скользящее среднее vs 60-дневная базовая линия
        - Требует минимум 10 дней данных
        """
        if len(hrv_data_df) < 10:
            return None, "Недостаточно данных (минимум 10 дней)"
        
        # Сортируем по дате
        df = hrv_data_df.sort_values('date').copy()
        df = df.dropna(subset=['rmssd'])
        
        if len(df) < 10:
            return None, "Недостаточно валидных RMSSD данных"
        
        # 7-дневное скользящее среднее (последние 7 дней)
        recent_7d = df.tail(7)['rmssd'].mean()
        
        # 60-дневная базовая линия
        if len(df) >= 60:
            baseline_60d = df.tail(60)['rmssd'].mean()
        else:
            # Используем все доступные данные как базовую линию
            baseline_60d = df['rmssd'].mean()
        
        # Расчет балла восстановления
        if baseline_60d > 0:
            recovery_ratio = recent_7d / baseline_60d
            # Нормализация: 100% при соотношении 1.0, ниже - пропорционально меньше
            recovery_score = min(100, max(0, recovery_ratio * 100))
            
            return recovery_score, f"7д среднее: {recent_7d:.1f}, базовая линия: {baseline_60d:.1f}"
        
        return None, "Ошибка в базовых данных"