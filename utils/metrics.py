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

    @staticmethod
    def mean_max_power(power_data, durations_secs=(5, 60, 300, 1200, 3600)):
        """Локальная power curve: пиковая средняя мощность на заданных
        длительностях (#382 гибридный фолбэк).

        Для каждой длительности D секунд ищется максимальное среднее по
        скользящему окну длины D. Источник — стрим watts из Intervals.icu
        (``streams.json?types=watts → data``) для активностей без Intervals-id
        (Garmin-only) или когда провайдер недоступен.

        Возвращает ``{duration_secs: peak_avg_watts | None}`` — ``None``, если
        стрим короче длительности (например, 60min в 45-минутной записи).
        Используется как фолбэк к готовой power curve провайдера.
        """
        if power_data is None:
            return {d: None for d in durations_secs}
        series = pd.Series(power_data, dtype="float64").dropna()
        result = {}
        for duration in durations_secs:
            window = int(duration)
            if window <= 0 or len(series) < window:
                result[duration] = None
                continue
            rolling_avg = series.rolling(window).mean()
            peak = rolling_avg.max()
            result[duration] = None if pd.isna(peak) else int(round(float(peak)))
        return result