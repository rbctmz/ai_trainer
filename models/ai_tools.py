"""
Система инструментов для AI тренера (аналог MCP сервера)
Позволяет AI делать динамические запросы к базе данных
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from data.database import Database
from models.banister import BanisterModel
from models.hrv_analyzer import HRVAnalyzer


class AITools:
    """Система инструментов для AI тренера"""
    
    def __init__(self, database: Database):
        self.db = database
        self.banister = BanisterModel()
        self.hrv_analyzer = HRVAnalyzer()
        
        # Регистрируем доступные инструменты
        self.tools = {
            "get_activities": self.get_activities,
            "get_hrv_data": self.get_hrv_data,
            "get_activity_stats": self.get_activity_stats,
            "get_performance_metrics": self.get_performance_metrics,
            "get_recent_activities": self.get_recent_activities,
            "analyze_training_load": self.analyze_training_load,
            "analyze_hrv_trends": self.analyze_hrv_trends,
            "compare_periods": self.compare_periods,
            "get_activity_by_sport": self.get_activity_by_sport,
            "calculate_weekly_stats": self.calculate_weekly_stats,
            "find_best_performances": self.find_best_performances,
            "analyze_recovery_state": self.analyze_recovery_state,
            "get_activities_by_date_range": self.get_activities_by_date_range
        }
    
    def get_available_tools(self) -> Dict[str, str]:
        """Возвращает список доступных инструментов с описанием"""
        return {
            "get_activities": "Получить список активностей за период (days=30)",
            "get_hrv_data": "Получить HRV данные за период (days=30)",
            "get_activity_stats": "Получить статистику по активностям (days=30)",
            "get_performance_metrics": "Получить метрики производительности (CTL/ATL/TSB) (days=90)",
            "get_recent_activities": "Получить последние N активностей (limit=10)",
            "analyze_training_load": "Анализ тренировочной нагрузки за период (days=30)",
            "analyze_hrv_trends": "Анализ трендов HRV (days=30)",
            "compare_periods": "Сравнить два периода тренировок (period1_days=30, period2_days=30)",
            "get_activity_by_sport": "Получить активности по виду спорта (sport='cycling', days=30)",
            "calculate_weekly_stats": "Рассчитать недельную статистику (weeks=4)",
            "find_best_performances": "Найти лучшие результаты по метрикам (metric='tss', limit=10)",
            "analyze_recovery_state": "Проанализировать текущее состояние восстановления",
            "get_activities_by_date_range": "Получить активности за конкретный период (start_date='2025-05-01', end_date='2025-05-31')"
        }
    
    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Выполняет инструмент с параметрами"""
        if tool_name not in self.tools:
            return {
                "error": f"Инструмент '{tool_name}' не найден",
                "available_tools": list(self.tools.keys())
            }
        
        try:
            result = self.tools[tool_name](**kwargs)
            return {
                "success": True,
                "tool": tool_name,
                "parameters": kwargs,
                "result": result
            }
        except Exception as e:
            return {
                "error": f"Ошибка выполнения инструмента '{tool_name}': {str(e)}",
                "parameters": kwargs
            }
    
    # === ИНСТРУМЕНТЫ ===
    
    def get_activities(self, days: int = 30) -> Dict[str, Any]:
        """Получить активности за период"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет активностей за указанный период", "count": 0}
        
        # Конвертируем в удобный формат
        activities = []
        for _, row in df.iterrows():
            activity = {
                "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None,
                "sport": row.get("sport", "unknown"),
                "duration_minutes": float(row.get("duration_minutes", 0)) if pd.notna(row.get("duration_minutes")) else 0,
                "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                "avg_hr": float(row.get("avg_hr", 0)) if pd.notna(row.get("avg_hr")) else 0,
                "avg_power": float(row.get("avg_power", 0)) if pd.notna(row.get("avg_power")) else 0
            }
            activities.append(activity)
        
        return {
            "count": len(activities),
            "period_days": days,
            "activities": activities[:20]  # Ограничиваем для читаемости
        }
    
    def get_hrv_data(self, days: int = 30) -> Dict[str, Any]:
        """Получить HRV данные за период"""
        df = self.db.get_hrv_data(days)
        
        if df.empty:
            return {"message": "Нет HRV данных за указанный период", "count": 0}
        
        hrv_data = []
        for _, row in df.iterrows():
            hrv_entry = {
                "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else None,
                "rmssd": float(row.get("rmssd", 0)) if pd.notna(row.get("rmssd")) else 0,
                "stress_score": float(row.get("stress_score", 0)) if pd.notna(row.get("stress_score")) else None,
                "recovery_score": float(row.get("recovery_score", 0)) if pd.notna(row.get("recovery_score")) else None
            }
            hrv_data.append(hrv_entry)
        
        return {
            "count": len(hrv_data),
            "period_days": days,
            "avg_rmssd": df["rmssd"].mean(),
            "current_rmssd": float(df.iloc[0]["rmssd"]) if len(df) > 0 else 0,
            "data": hrv_data[:20]  # Последние 20 записей
        }
    
    def get_activity_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику по активностям"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет данных для статистики", "period_days": days}
        
        return {
            "period_days": days,
            "total_activities": len(df),
            "total_duration_hours": float(df["duration_minutes"].sum() / 60),
            "total_distance_km": float(df["distance_km"].sum()) if "distance_km" in df.columns else 0,
            "total_tss": float(df["tss"].sum()) if "tss" in df.columns else 0,
            "avg_tss_per_session": float(df["tss"].mean()) if "tss" in df.columns else 0,
            "activities_per_week": float(len(df) * 7 / days),
            "sports_distribution": df["sport"].value_counts().to_dict() if "sport" in df.columns else {},
            "avg_duration_minutes": float(df["duration_minutes"].mean()),
            "avg_heart_rate": float(df["avg_hr"].mean()) if "avg_hr" in df.columns and not df["avg_hr"].isna().all() else 0
        }
    
    def get_performance_metrics(self, days: int = 90) -> Dict[str, Any]:
        """Получить метрики производительности (CTL/ATL/TSB)"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет данных для расчета метрик производительности"}
        
        # Подготавливаем данные для модели Банистера
        tss_data = []
        dates = []
        
        for _, row in df.iterrows():
            tss_val = row.get("tss", 0)
            if pd.isna(tss_val):
                tss_val = 0
            tss_data.append(float(tss_val))
            dates.append(row["date"])
        
        metrics = self.banister.get_current_metrics(tss_data, dates)
        
        return {
            "ctl": float(metrics["ctl"]),
            "atl": float(metrics["atl"]),
            "tsb": float(metrics["tsb"]),
            "form_state": self._interpret_tsb(metrics["tsb"]),
            "fitness_trend": self._calculate_fitness_trend(tss_data),
            "fatigue_level": self._interpret_atl(metrics["atl"])
        }
    
    def get_recent_activities(self, limit: int = 10) -> Dict[str, Any]:
        """Получить последние N активностей"""
        df = self.db.get_activities(30)  # Берем за 30 дней
        
        if df.empty:
            return {"message": "Нет недавних активностей", "count": 0}
        
        recent = df.head(limit)
        activities = []
        
        for _, row in recent.iterrows():
            activity = {
                "date": row["date"].strftime("%Y-%m-%d"),
                "sport": row.get("sport", "unknown"),
                "duration_minutes": float(row.get("duration_minutes", 0)),
                "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                "description": f"{row.get('sport', 'unknown')} - {row.get('duration_minutes', 0):.0f}мин - TSS:{row.get('tss', 0):.0f}"
            }
            activities.append(activity)
        
        return {
            "count": len(activities),
            "activities": activities
        }
    
    def analyze_training_load(self, days: int = 30) -> Dict[str, Any]:
        """Анализ тренировочной нагрузки"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": "Нет данных для анализа нагрузки"}
        
        # Преобразуем дату в datetime если нужно
        df["date"] = pd.to_datetime(df["date"])
        
        # Анализ по неделям
        df["week"] = df["date"].dt.isocalendar().week
        weekly_stats = df.groupby("week").agg({
            "tss": ["sum", "mean", "count"],
            "duration_minutes": "sum"
        }).round(2)
        
        weekly_data = []
        for week, stats in weekly_stats.iterrows():
            weekly_data.append({
                "week": int(week),
                "total_tss": float(stats[("tss", "sum")]),
                "avg_tss": float(stats[("tss", "mean")]),
                "session_count": int(stats[("tss", "count")]),
                "total_duration": float(stats[("duration_minutes", "sum")])
            })
        
        return {
            "period_days": days,
            "weekly_breakdown": weekly_data,
            "load_trend": self._calculate_load_trend(df),
            "intensity_distribution": self._analyze_intensity_distribution(df)
        }
    
    def analyze_hrv_trends(self, days: int = 30) -> Dict[str, Any]:
        """Анализ трендов HRV"""
        df = self.db.get_hrv_data(days)
        
        if df.empty:
            return {"message": "Нет HRV данных для анализа трендов"}
        
        if len(df) < 7:
            return {"message": "Недостаточно данных для анализа трендов (нужно минимум 7 дней)"}
        
        # Анализ тренда
        x = np.arange(len(df))
        trend_coefficient = np.polyfit(x, df["rmssd"], 1)[0]
        
        # Недавние vs базовые значения
        recent_avg = df.head(7)["rmssd"].mean()
        baseline_avg = df["rmssd"].median()
        
        return {
            "period_days": days,
            "data_points": len(df),
            "current_rmssd": float(df.iloc[0]["rmssd"]),
            "recent_avg_7days": float(recent_avg),
            "baseline_median": float(baseline_avg),
            "trend_direction": "improving" if trend_coefficient > 0 else "declining",
            "trend_slope": float(trend_coefficient),
            "recovery_state": self._assess_recovery_state(recent_avg, baseline_avg),
            "variability": float(df["rmssd"].std())
        }
    
    def compare_periods(self, period1_days: int = 30, period2_days: int = 30) -> Dict[str, Any]:
        """Сравнить два периода тренировок"""
        # Первый период (недавний)
        df1 = self.db.get_activities(period1_days)
        
        # Второй период (более ранний)
        start_date2 = datetime.now() - timedelta(days=period1_days + period2_days)
        end_date2 = datetime.now() - timedelta(days=period1_days)
        
        # Получаем активности за второй период
        all_activities = self.db.get_activities(period1_days + period2_days)
        df2 = all_activities[all_activities["date"] < end_date2.date()] if not all_activities.empty else pd.DataFrame()
        
        def get_period_stats(df, period_name):
            if df.empty:
                return {"period": period_name, "no_data": True}
            
            return {
                "period": period_name,
                "activity_count": len(df),
                "total_tss": float(df["tss"].sum()) if "tss" in df.columns else 0,
                "avg_tss": float(df["tss"].mean()) if "tss" in df.columns else 0,
                "total_duration": float(df["duration_minutes"].sum()),
                "activities_per_week": float(len(df) * 7 / period1_days)
            }
        
        recent_stats = get_period_stats(df1, f"последние {period1_days} дней")
        previous_stats = get_period_stats(df2, f"предыдущие {period2_days} дней")
        
        # Сравнение
        comparison = {}
        if not df1.empty and not df2.empty:
            comparison = {
                "tss_change": float(recent_stats["total_tss"] - previous_stats["total_tss"]),
                "activity_count_change": recent_stats["activity_count"] - previous_stats["activity_count"],
                "volume_change": float(recent_stats["total_duration"] - previous_stats["total_duration"])
            }
        
        return {
            "recent_period": recent_stats,
            "previous_period": previous_stats,
            "comparison": comparison
        }
    
    def get_activity_by_sport(self, sport: str, days: int = 30) -> Dict[str, Any]:
        """Получить активности по виду спорта"""
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": f"Нет активностей за {days} дней", "sport": sport}
        
        sport_df = df[df["sport"].str.lower() == sport.lower()] if "sport" in df.columns else pd.DataFrame()
        
        if sport_df.empty:
            available_sports = df["sport"].unique().tolist() if "sport" in df.columns else []
            return {
                "message": f"Нет активностей по виду спорта '{sport}'",
                "available_sports": available_sports
            }
        
        return {
            "sport": sport,
            "count": len(sport_df),
            "total_distance": float(sport_df["distance_km"].sum()) if "distance_km" in sport_df.columns else 0,
            "total_duration": float(sport_df["duration_minutes"].sum()),
            "avg_duration": float(sport_df["duration_minutes"].mean()),
            "total_tss": float(sport_df["tss"].sum()) if "tss" in sport_df.columns else 0,
            "avg_tss": float(sport_df["tss"].mean()) if "tss" in sport_df.columns else 0
        }
    
    def calculate_weekly_stats(self, weeks: int = 4) -> Dict[str, Any]:
        """Рассчитать недельную статистику"""
        days = weeks * 7
        df = self.db.get_activities(days)
        
        if df.empty:
            return {"message": f"Нет данных за {weeks} недель"}
        
        # Группируем по неделям
        df["week"] = df["date"].dt.isocalendar().week
        weekly_stats = df.groupby("week").agg({
            "tss": "sum",
            "duration_minutes": "sum",
            "distance_km": "sum",
            "date": "count"  # количество тренировок
        }).round(2)
        
        weekly_data = []
        for week, stats in weekly_stats.iterrows():
            weekly_data.append({
                "week": int(week),
                "total_tss": float(stats["tss"]) if pd.notna(stats["tss"]) else 0,
                "training_sessions": int(stats["date"]),
                "total_duration_hours": float(stats["duration_minutes"] / 60),
                "total_distance": float(stats["distance_km"]) if pd.notna(stats["distance_km"]) else 0
            })
        
        return {
            "weeks_analyzed": weeks,
            "weekly_stats": weekly_data,
            "avg_weekly_tss": float(weekly_stats["tss"].mean()) if not weekly_stats["tss"].isna().all() else 0,
            "avg_sessions_per_week": float(weekly_stats["date"].mean())
        }
    
    def find_best_performances(self, metric: str = "tss", limit: int = 10) -> Dict[str, Any]:
        """Найти лучшие результаты по метрикам"""
        df = self.db.get_activities(90)  # За последние 3 месяца
        
        if df.empty:
            return {"message": "Нет данных для поиска лучших результатов"}
        
        available_metrics = ["tss", "duration_minutes", "distance_km", "avg_power", "avg_hr"]
        if metric not in available_metrics:
            return {
                "error": f"Метрика '{metric}' не доступна",
                "available_metrics": available_metrics
            }
        
        if metric not in df.columns or df[metric].isna().all():
            return {"message": f"Нет данных по метрике '{metric}'"}
        
        # Сортируем по убыванию и берем топ
        best_performances = df.nlargest(limit, metric)
        
        results = []
        for _, row in best_performances.iterrows():
            result = {
                "date": row["date"].strftime("%Y-%m-%d"),
                "sport": row.get("sport", "unknown"),
                "metric_value": float(row[metric]),
                "duration_minutes": float(row.get("duration_minutes", 0)),
                "description": f"{row.get('sport', 'unknown')} - {metric}: {row[metric]:.1f}"
            }
            results.append(result)
        
        return {
            "metric": metric,
            "best_performances": results,
            "analysis_period": "90 дней"
        }
    
    def analyze_recovery_state(self) -> Dict[str, Any]:
        """Проанализировать текущее состояние восстановления"""
        # HRV данные
        hrv_df = self.db.get_hrv_data(14)  # Последние 2 недели
        
        # Данные о нагрузке
        activities_df = self.db.get_activities(7)  # Последняя неделя
        
        recovery_analysis = {"factors": []}
        
        # Анализ HRV
        if not hrv_df.empty and len(hrv_df) >= 3:
            current_rmssd = hrv_df.iloc[0]["rmssd"]
            baseline_rmssd = hrv_df["rmssd"].median()
            
            recovery_analysis["hrv"] = {
                "current_rmssd": float(current_rmssd),
                "baseline_rmssd": float(baseline_rmssd),
                "deviation_percent": float((current_rmssd - baseline_rmssd) / baseline_rmssd * 100) if baseline_rmssd > 0 else 0
            }
            
            if current_rmssd > baseline_rmssd * 1.1:
                recovery_analysis["factors"].append("HRV значительно выше базового уровня - отличное восстановление")
            elif current_rmssd > baseline_rmssd * 0.95:
                recovery_analysis["factors"].append("HRV в норме - хорошее восстановление")
            else:
                recovery_analysis["factors"].append("HRV ниже базового уровня - возможна усталость")
        
        # Анализ нагрузки
        if not activities_df.empty:
            week_tss = activities_df["tss"].sum() if "tss" in activities_df.columns else 0
            recent_sessions = len(activities_df)
            
            recovery_analysis["training_load"] = {
                "week_tss": float(week_tss),
                "session_count": recent_sessions,
                "avg_tss_per_session": float(week_tss / recent_sessions) if recent_sessions > 0 else 0
            }
            
            if week_tss > 400:
                recovery_analysis["factors"].append("Высокая нагрузка за неделю - требуется внимание к восстановлению")
            elif recent_sessions > 6:
                recovery_analysis["factors"].append("Много тренировок за неделю - следите за признаками переутомления")
        
        # Общая рекомендация
        if not recovery_analysis["factors"]:
            recovery_analysis["factors"].append("Недостаточно данных для полноценного анализа восстановления")
        
        return recovery_analysis
    
    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===
    
    def _interpret_tsb(self, tsb: float) -> str:
        """Интерпретация TSB"""
        if tsb > 10:
            return "пиковая форма"
        elif tsb > 0:
            return "хорошая форма"
        elif tsb > -15:
            return "поддержание"
        elif tsb > -30:
            return "накопление"
        else:
            return "перегрузка"
    
    def _interpret_atl(self, atl: float) -> str:
        """Интерпретация ATL (уровень усталости)"""
        if atl > 80:
            return "высокая"
        elif atl > 50:
            return "умеренная"
        elif atl > 20:
            return "низкая"
        else:
            return "минимальная"
    
    def _calculate_fitness_trend(self, tss_data: List[float]) -> str:
        """Определение тренда фитнеса"""
        if len(tss_data) < 14:
            return "недостаточно данных"
        
        recent = np.mean(tss_data[-7:])
        previous = np.mean(tss_data[-14:-7])
        
        change = (recent - previous) / previous * 100 if previous > 0 else 0
        
        if change > 10:
            return "быстрый рост"
        elif change > 5:
            return "рост"
        elif change < -10:
            return "быстрое снижение"
        elif change < -5:
            return "снижение"
        else:
            return "стабильность"
    
    def _calculate_load_trend(self, df: pd.DataFrame) -> str:
        """Анализ тренда нагрузки"""
        if len(df) < 14:
            return "недостаточно данных"
        
        # Сравниваем последние 2 недели  
        df["date"] = pd.to_datetime(df["date"])
        now = pd.Timestamp.now()
        
        recent_week = df[df["date"] >= (now - timedelta(days=7))]
        previous_week = df[(df["date"] >= (now - timedelta(days=14))) & 
                          (df["date"] < (now - timedelta(days=7)))]
        
        recent_tss = recent_week["tss"].sum() if not recent_week.empty and "tss" in recent_week.columns else 0
        previous_tss = previous_week["tss"].sum() if not previous_week.empty and "tss" in previous_week.columns else 0
        
        if previous_tss == 0:
            return "нет данных для сравнения"
        
        change = (recent_tss - previous_tss) / previous_tss * 100
        
        if change > 20:
            return "резкое увеличение"
        elif change > 5:
            return "увеличение"
        elif change < -20:
            return "резкое снижение"
        elif change < -5:
            return "снижение"
        else:
            return "стабильность"
    
    def _analyze_intensity_distribution(self, df: pd.DataFrame) -> Dict[str, float]:
        """Анализ распределения интенсивности"""
        if df.empty or "tss" not in df.columns or df["tss"].isna().all():
            return {"low": 0, "moderate": 0, "high": 0}
        
        tss_values = df["tss"].dropna()
        total = len(tss_values)
        
        if total == 0:
            return {"low": 0, "moderate": 0, "high": 0}
        
        low = len(tss_values[tss_values < 50])
        moderate = len(tss_values[(tss_values >= 50) & (tss_values < 100)])
        high = len(tss_values[tss_values >= 100])
        
        return {
            "low_intensity_percent": round(low / total * 100, 1),
            "moderate_intensity_percent": round(moderate / total * 100, 1),
            "high_intensity_percent": round(high / total * 100, 1)
        }
    
    def _assess_recovery_state(self, recent_avg: float, baseline_avg: float) -> str:
        """Оценка состояния восстановления по HRV"""
        if recent_avg > baseline_avg * 1.1:
            return "отличное"
        elif recent_avg > baseline_avg * 0.95:
            return "хорошее"
        elif recent_avg > baseline_avg * 0.85:
            return "удовлетворительное"
        else:
            return "плохое"

    def format_tool_descriptions_for_ai(self) -> str:
        """Форматирует описания инструментов для AI"""
        tools_desc = "ДОСТУПНЫЕ ИНСТРУМЕНТЫ:\n\n"
        
        for tool_name, description in self.get_available_tools().items():
            tools_desc += f"• **{tool_name}**: {description}\n"
        
        tools_desc += """\n
ИСПОЛЬЗОВАНИЕ ИНСТРУМЕНТОВ:
Чтобы получить конкретные данные, используй формат:
[TOOL: tool_name, param1=value1, param2=value2]

Примеры:
- [TOOL: get_recent_activities, limit=5] - последние 5 тренировок
- [TOOL: get_performance_metrics, days=60] - метрики за 60 дней  
- [TOOL: analyze_hrv_trends, days=14] - анализ HRV за 2 недели
- [TOOL: get_activity_by_sport, sport=cycling, days=30] - велотренировки
- [TOOL: get_activities_by_date_range, start_date=2025-05-01, end_date=2025-05-31] - активности за май 2025

ВАЖНО: Используй инструменты для получения точных, актуальных данных вместо общих предположений.
"""
        return tools_desc
    
    def get_activities_by_date_range(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """Получить активности за конкретный диапазон дат"""
        try:
            # Парсим даты
            from datetime import datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # Получаем все активности (берем большой период чтобы покрыть любые даты)
            df = self.db.get_activities(365 * 2)  # 2 года данных
            
            if df.empty:
                return {"message": "Нет данных активностей", "count": 0}
            
            # Преобразуем даты в datetime
            df["date"] = pd.to_datetime(df["date"])
            
            # Фильтруем по диапазону
            filtered_df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]
            
            if filtered_df.empty:
                return {
                    "message": f"Нет активностей в период с {start_date} по {end_date}",
                    "count": 0,
                    "period": f"{start_date} - {end_date}"
                }
            
            # Форматируем результат
            activities = []
            for _, row in filtered_df.iterrows():
                activity = {
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "sport": row.get("sport", "unknown"),
                    "duration_minutes": float(row.get("duration_minutes", 0)),
                    "distance_km": float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                    "tss": float(row.get("tss", 0)) if pd.notna(row.get("tss")) else 0,
                    "avg_hr": float(row.get("avg_hr", 0)) if pd.notna(row.get("avg_hr")) else 0
                }
                activities.append(activity)
            
            # Статистика за период
            stats = {
                "total_activities": len(filtered_df),
                "total_duration_hours": float(filtered_df["duration_minutes"].sum() / 60),
                "total_distance_km": float(filtered_df["distance_km"].sum()) if "distance_km" in filtered_df.columns else 0,
                "total_tss": float(filtered_df["tss"].sum()) if "tss" in filtered_df.columns else 0,
                "avg_tss_per_session": float(filtered_df["tss"].mean()) if "tss" in filtered_df.columns else 0,
                "sports_distribution": filtered_df["sport"].value_counts().to_dict() if "sport" in filtered_df.columns else {},
                "period": f"{start_date} - {end_date}"
            }
            
            return {
                "count": len(activities),
                "period": f"{start_date} - {end_date}",
                "activities": activities,
                "statistics": stats
            }
            
        except ValueError as e:
            return {
                "error": f"Неверный формат даты. Используйте YYYY-MM-DD. Ошибка: {str(e)}",
                "example": "Пример: start_date=2025-05-01, end_date=2025-05-31"
            }
        except Exception as e:
            return {
                "error": f"Ошибка получения активностей по датам: {str(e)}"
            }