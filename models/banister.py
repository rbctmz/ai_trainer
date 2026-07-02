import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Canonical TSB zones — the single source of truth for how a TSB value
# (Training Stress Balance = CTL - ATL, i.e. how fresh or fatigued the
# athlete is right now) is described to the user anywhere in the app.
# Moved here from api/routers/dashboard.py (see git history: commit
# 028ac6a / PR #59 / issue #54, then issue #63) so every layer — not just
# the dashboard API — can share one definition instead of each inventing
# its own boundaries. Mirrored by hand (Python has no build step that
# shares code with the frontend) in web/components/ui/Tooltip.tsx's
# TsbContent. Boundaries -20/-10/+10 match ui/pages/dashboard.py's
# _build_dashboard_v2_summary state_label logic, which remains the
# authoritative composite source these zones were copied from (it
# combines TSB with readiness and is intentionally different — do not
# change it to match this table).
TSB_ZONES: list[tuple[float, str, str, str]] = [
    # (upper bound exclusive, label, tone, daily-outlook clause)
    (-20, "Высокая усталость", "danger", "высокая усталость — приоритет восстановлению"),
    (-10, "Накопленная усталость", "warning", "накопленная усталость — контролируйте интенсивность"),
    (10, "Стабильная нагрузка", "neutral", "стабильная нагрузка — придерживайтесь плана"),
    (float("inf"), "Свежесть", "success", "хорошая свежесть — можно работать на качество"),
]


def tsb_zone(tsb: float) -> dict[str, str]:
    """Classify a TSB value into the canonical 4-zone description.

    Returns a dict with 'label' (Russian zone name), 'tone' (one of
    'danger'/'warning'/'neutral'/'success', for UI color-coding), and
    'clause' (a lowercase Russian clause meant to be embedded mid-sentence).
    """
    for upper, label, tone, clause in TSB_ZONES:
        if tsb < upper:
            return {"label": label, "tone": tone, "clause": clause}
    last = TSB_ZONES[-1]
    return {"label": last[1], "tone": last[2], "clause": last[3]}


class BanisterModel:
    def __init__(self):
        # Параметры модели (стандартные значения)
        self.k1 = 1.0      # Фитнес константа
        self.k2 = 2.0      # Усталость константа  
        self.tau1 = 42.0   # Время спада фитнеса (дни)
        self.tau2 = 7.0    # Время спада усталости (дни)
        self.is_fitted = False
    
    def calculate_ctl_atl_tsb(self, tss_data, dates):
        """
        Расчёт CTL (Chronic Training Load), ATL (Acute Training Load) и TSB (Training Stress Balance)
        CTL = экспоненциальное среднее TSS за 42 дня
        ATL = экспоненциальное среднее TSS за 7 дней  
        TSB = CTL - ATL (форма спортсмена)
        """
        if len(tss_data) == 0:
            return [], [], [], []
        
        # Создаём DataFrame с полными данными
        df = pd.DataFrame({
            'date': pd.to_datetime(dates),
            'tss': tss_data
        }).sort_values('date')
        
        # Убираем дубликаты дат, суммируя TSS за один день
        df = df.groupby('date')['tss'].sum().reset_index()
        
        # Заполняем пропущенные дни нулями
        if len(df) > 1:  # Проверяем что есть данные для создания диапазона
            date_range = pd.date_range(start=df['date'].min(), end=df['date'].max(), freq='D')
            df_full = df.set_index('date').reindex(date_range, fill_value=0).reset_index()
            df_full.columns = ['date', 'tss']
        else:
            # Если только одна дата, используем её как есть
            df_full = df
        
        # Расчёт CTL (42 дня) и ATL (7 дней) через экспоненциальное среднее
        ctl_alpha = 1 - np.exp(-1/42)  # α для CTL
        atl_alpha = 1 - np.exp(-1/7)   # α для ATL
        
        ctl_values = []
        atl_values = []
        tsb_values = []
        
        ctl_current = 0
        atl_current = 0
        
        for tss in df_full['tss']:
            # Обновляем CTL и ATL
            ctl_current = ctl_alpha * tss + (1 - ctl_alpha) * ctl_current
            atl_current = atl_alpha * tss + (1 - atl_alpha) * atl_current
            
            # TSB = разница между хронической и острой нагрузкой
            tsb_current = ctl_current - atl_current
            
            ctl_values.append(ctl_current)
            atl_values.append(atl_current)
            tsb_values.append(tsb_current)
        
        return df_full['date'].tolist(), ctl_values, atl_values, tsb_values
    
    def predict_performance(self, training_load, dates=None):
        """Предсказание производительности по модели Банистера"""
        if len(training_load) == 0:
            return [], [], []
        
        dates_list, ctl, atl, tsb = self.calculate_ctl_atl_tsb(training_load, dates or range(len(training_load)))
        
        # В модели Банистера фитнес = CTL, усталость = ATL, форма = TSB
        fitness = np.array(ctl) * self.k1
        fatigue = np.array(atl) * self.k2  
        performance = fitness - fatigue
        
        return performance.tolist(), fitness.tolist(), fatigue.tolist()
    
    def get_current_metrics(self, tss_data, dates):
        """Получение текущих метрик CTL/ATL/TSB"""
        if len(tss_data) == 0 or len(dates) == 0:
            return {
                'ctl': 0,
                'atl': 0, 
                'tsb': 0,
                'fitness': 0,
                'fatigue': 0,
                'form': 'Недостаточно данных'
            }
        
        try:
            _, ctl_values, atl_values, tsb_values = self.calculate_ctl_atl_tsb(tss_data, dates)
        except Exception as e:
            print(f"Ошибка в расчёте метрик: {e}")
            return {
                'ctl': 0,
                'atl': 0, 
                'tsb': 0,
                'fitness': 0,
                'fatigue': 0,
                'form': 'Ошибка расчёта'
            }
        
        current_ctl = ctl_values[-1] if ctl_values else 0
        current_atl = atl_values[-1] if atl_values else 0
        current_tsb = tsb_values[-1] if tsb_values else 0
        
        # Интерпретация TSB — canonical zone label (see TSB_ZONES above)
        form = tsb_zone(current_tsb)["label"]
        
        return {
            'ctl': round(current_ctl, 1),
            'atl': round(current_atl, 1),
            'tsb': round(current_tsb, 1),
            'fitness': round(current_ctl * self.k1, 1),
            'fatigue': round(current_atl * self.k2, 1),
            'form': form
        }
    
    def get_training_recommendation(self, current_metrics):
        """Рекомендации по тренировкам на основе текущего TSB (canonical TSB zone)"""
        tsb = current_metrics.get('tsb', 0)
        zone_tone = tsb_zone(tsb)["tone"]

        if zone_tone == "success":
            return {
                'recommendation': "Время для интенсивных тренировок",
                'intensity': "Высокая",
                'description': "Вы в отличной форме! Можно проводить ключевые тренировки и соревнования.",
                'suggested_tss': f"{int(current_metrics.get('ctl', 50) * 1.2)}-{int(current_metrics.get('ctl', 50) * 1.5)}"
            }
        elif zone_tone == "neutral":
            return {
                'recommendation': "Поддерживающие тренировки",
                'intensity': "Умеренная",
                'description': "Хорошая форма для регулярных тренировок средней интенсивности.",
                'suggested_tss': f"{int(current_metrics.get('ctl', 50) * 0.8)}-{int(current_metrics.get('ctl', 50) * 1.1)}"
            }
        elif zone_tone == "warning":
            return {
                'recommendation': "Лёгкие тренировки и восстановление",
                'intensity': "Низкая",
                'description': "Накопилась усталость. Снизьте интенсивность и объём тренировок.",
                'suggested_tss': f"{int(current_metrics.get('ctl', 50) * 0.5)}-{int(current_metrics.get('ctl', 50) * 0.7)}"
            }
        else:  # "danger"
            return {
                'recommendation': "Полное восстановление",
                'intensity': "Очень низкая/Отдых",
                'description': "Серьёзное переутомление! Необходим отдых и восстановительные процедуры.",
                'suggested_tss': f"0-{int(current_metrics.get('ctl', 50) * 0.3)}"
            }
    
    def simulate_training_load(self, current_metrics, planned_tss_per_week, weeks=4):
        """Симуляция будущих CTL/ATL/TSB при планируемой нагрузке"""
        current_ctl = current_metrics.get('ctl', 0)
        current_atl = current_metrics.get('atl', 0)
        
        # Распределяем недельную нагрузку на дни (примерно)
        daily_tss = planned_tss_per_week / 7
        
        ctl_alpha = 1 - np.exp(-1/42)
        atl_alpha = 1 - np.exp(-1/7)
        
        future_dates = []
        future_ctl = []
        future_atl = []
        future_tsb = []
        
        ctl_sim = current_ctl
        atl_sim = current_atl
        
        start_date = datetime.now()
        
        for day in range(weeks * 7):
            date = start_date + timedelta(days=day)
            future_dates.append(date)
            
            # Обновляем CTL и ATL
            ctl_sim = ctl_alpha * daily_tss + (1 - ctl_alpha) * ctl_sim
            atl_sim = atl_alpha * daily_tss + (1 - atl_alpha) * atl_sim
            tsb_sim = ctl_sim - atl_sim
            
            future_ctl.append(ctl_sim)
            future_atl.append(atl_sim)
            future_tsb.append(tsb_sim)
        
        return future_dates, future_ctl, future_atl, future_tsb

    def simulate_variable_load(self, current_metrics, daily_tss_sequence, start_date=None):
        """Симуляция CTL/ATL/TSB по переменной ежедневной нагрузке (список float).
        daily_tss_sequence: list[float] или list[(datetime, float)]
        Возвращает (dates, ctl, atl, tsb).
        """
        import numpy as np
        from datetime import datetime, timedelta

        current_ctl = current_metrics.get('ctl', 0)
        current_atl = current_metrics.get('atl', 0)

        ctl_alpha = 1 - np.exp(-1/42)
        atl_alpha = 1 - np.exp(-1/7)

        dates = []
        ctl_vals = []
        atl_vals = []
        tsb_vals = []

        ctl_sim = float(current_ctl)
        atl_sim = float(current_atl)
        base_date = start_date or datetime.now()

        for idx, item in enumerate(daily_tss_sequence):
            if isinstance(item, (tuple, list)) and len(item) == 2:
                dt, tss = item
                dt = dt if isinstance(dt, datetime) else base_date + timedelta(days=idx)
                load = float(tss or 0)
            else:
                dt = base_date + timedelta(days=idx)
                load = float(item or 0)

            ctl_sim = ctl_alpha * load + (1 - ctl_alpha) * ctl_sim
            atl_sim = atl_alpha * load + (1 - atl_alpha) * atl_sim
            tsb_sim = ctl_sim - atl_sim

            dates.append(dt)
            ctl_vals.append(ctl_sim)
            atl_vals.append(atl_sim)
            tsb_vals.append(tsb_sim)

        return dates, ctl_vals, atl_vals, tsb_vals
