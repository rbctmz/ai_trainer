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
            "get_activities_by_date_range": self.get_activities_by_date_range,
            "get_sleep_data": self.get_sleep_data,
            "analyze_sleep_patterns": self.analyze_sleep_patterns,
            "get_sleep_stats": self.get_sleep_stats,
            "get_training_status": self.get_training_status,
            "analyze_training_status": self.analyze_training_status,
            "get_daily_health_stats": self.get_daily_health_stats
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
            "get_activities_by_date_range": "Получить активности за конкретный период (start_date='2025-05-01', end_date='2025-05-31')",
            "get_sleep_data": "Получить данные сна за период (days=30)",
            "analyze_sleep_patterns": "Анализ паттернов и качества сна (days=30)",
            "get_sleep_stats": "Получить статистику сна (days=30)",
            "get_training_status": "Получить историю статуса тренированности и readiness (days=30)",
            "analyze_training_status": "Глубокий анализ статуса тренированности и нагрузки (days=30)",
            "get_daily_health_stats": "Получить ежедневные показатели здоровья (шаги, ЧСС, калории) за период (days=30)"
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
        try:
            now = pd.Timestamp.now().normalize()
            window_days = period1_days + period2_days
            
            # Первый период (недавний)
            df1 = self.db.get_activities(period1_days)
            if not df1.empty and "date" in df1.columns:
                df1 = df1.copy()
                df1["date"] = pd.to_datetime(df1["date"], errors="coerce").dt.normalize()
            
            # Получаем активности за окно, чтобы выделить второй период
            all_activities = self.db.get_activities(window_days)
            if not all_activities.empty and "date" in all_activities.columns:
                all_activities = all_activities.copy()
                all_activities["date"] = pd.to_datetime(all_activities["date"], errors="coerce").dt.normalize()
            
            previous_period_end = now - pd.Timedelta(days=period1_days)
            previous_period_start = previous_period_end - pd.Timedelta(days=period2_days)
            
            if not all_activities.empty:
                mask = (
                    (all_activities["date"] >= previous_period_start)
                    & (all_activities["date"] < previous_period_end)
                )
                df2 = all_activities.loc[mask].copy()
            else:
                df2 = pd.DataFrame()
            
            def get_period_stats(df: pd.DataFrame, period_name: str, period_length: int) -> Dict[str, Any]:
                if df.empty:
                    return {"period": period_name, "no_data": True}
                
                total_tss = float(df["tss"].sum()) if "tss" in df.columns else 0.0
                avg_tss = float(df["tss"].mean()) if "tss" in df.columns else 0.0
                total_duration = float(df["duration_minutes"].sum()) if "duration_minutes" in df.columns else 0.0
                
                return {
                    "period": period_name,
                    "activity_count": int(len(df)),
                    "total_tss": total_tss,
                    "avg_tss": avg_tss,
                    "total_duration": total_duration,
                    "activities_per_week": float(len(df) * 7 / period_length) if period_length > 0 else 0.0
                }
            
            recent_stats = get_period_stats(df1, f"последние {period1_days} дней", period1_days)
            previous_stats = get_period_stats(df2, f"предыдущие {period2_days} дней", period2_days)
            
            comparison: Dict[str, Any] = {}
            if not df1.empty and not df2.empty:
                comparison = {
                    "tss_change": float(recent_stats["total_tss"] - previous_stats["total_tss"]),
                    "activity_count_change": recent_stats["activity_count"] - previous_stats["activity_count"],
                    "volume_change": float(recent_stats["total_duration"] - previous_stats["total_duration"])
                }
            
            return {
                "period1_days": period1_days,
                "period2_days": period2_days,
                "recent_period": recent_stats,
                "previous_period": previous_stats,
                "comparison": comparison
            }
        
        except Exception as exc:
            fallback_summary: Dict[str, Any] = {"reason": str(exc)}
            
            try:
                fallback_summary["recent_activity_stats"] = self.get_activity_stats(period1_days)
            except Exception as stats_exc:  # pragma: no cover - очень редкие ошибки
                fallback_summary["recent_activity_stats_error"] = str(stats_exc)
            
            try:
                fallback_summary["training_load"] = self.analyze_training_load(days=period1_days)
            except Exception as load_exc:  # pragma: no cover
                fallback_summary["training_load_error"] = str(load_exc)
            fallback_summary["period1_days"] = period1_days
            fallback_summary["period2_days"] = period2_days
            
            return {
                "period1_days": period1_days,
                "period2_days": period2_days,
                "message": "Не удалось сравнить периоды из-за несогласованных дат. Возвращаю ручной обзор последних данных.",
                "fallback": fallback_summary
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
- [TOOL: get_training_status, days=30] - статус тренированности и readiness
- [TOOL: analyze_training_status, days=21] - выводы по readiness и нагрузке
- [TOOL: get_daily_health_stats, days=14] - показатели шагов и ЧСС покоя
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
    
    def get_sleep_data(self, days: int = 30) -> Dict[str, Any]:
        """Получить данные сна за последние N дней"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней"
                }
            
            # Форматируем данные для AI
            sleep_records = []
            for _, row in sleep_df.head(10).iterrows():
                record = {
                    "date": row.get("date", ""),
                    "total_sleep_hours": round(row.get("total_sleep_minutes", 0) / 60, 1) if row.get("total_sleep_minutes") else None,
                    "sleep_score": row.get("sleep_score"),
                    "sleep_efficiency": row.get("sleep_efficiency"),
                    "deep_sleep_minutes": row.get("deep_sleep_minutes"),
                    "rem_sleep_minutes": row.get("rem_sleep_minutes"),
                    "light_sleep_minutes": row.get("light_sleep_minutes"),
                    "awakenings": row.get("awakenings_count")
                }
                sleep_records.append(record)
            
            return {
                "has_data": True,
                "period_days": days,
                "data_points": len(sleep_df),
                "recent_sleep": sleep_records
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка получения данных сна: {str(e)}"
            }
    
    def get_sleep_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику сна за период"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней"
                }
            
            # Рассчитываем статистику
            stats = {
                "period_days": days,
                "data_points": len(sleep_df),
                "avg_sleep_hours": sleep_df["total_sleep_minutes"].mean() / 60 if "total_sleep_minutes" in sleep_df.columns else None,
                "avg_sleep_score": sleep_df["sleep_score"].mean() if "sleep_score" in sleep_df.columns else None,
                "avg_sleep_efficiency": sleep_df["sleep_efficiency"].mean() if "sleep_efficiency" in sleep_df.columns else None,
                "avg_deep_sleep_minutes": sleep_df["deep_sleep_minutes"].mean() if "deep_sleep_minutes" in sleep_df.columns else None,
                "avg_rem_sleep_minutes": sleep_df["rem_sleep_minutes"].mean() if "rem_sleep_minutes" in sleep_df.columns else None,
                "avg_awakenings": sleep_df["awakenings_count"].mean() if "awakenings_count" in sleep_df.columns else None
            }
            
            # Анализ качества сна
            if "sleep_score" in sleep_df.columns and not sleep_df["sleep_score"].isna().all():
                current_score = sleep_df.iloc[0]["sleep_score"] if not sleep_df.empty else None
                if current_score:
                    if current_score >= 80:
                        sleep_quality = "отличное"
                    elif current_score >= 60:
                        sleep_quality = "хорошее"
                    elif current_score >= 40:
                        sleep_quality = "удовлетворительное"
                    else:
                        sleep_quality = "плохое"
                else:
                    sleep_quality = "неизвестно"
            else:
                sleep_quality = "неизвестно"
            
            stats["current_sleep_quality"] = sleep_quality
            
            return {
                "has_data": True,
                "statistics": stats
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка расчета статистики сна: {str(e)}"
            }

    def get_training_status(self, days: int = 30) -> Dict[str, Any]:
        """Получить данные статуса тренированности Garmin"""
        df = self.db.get_training_status_history(days)
        
        if df.empty:
            return {
                "message": f"Нет данных статуса тренированности за последние {days} дней",
                "period_days": days
            }
        
        df["date"] = pd.to_datetime(df["date"])
        sorted_df = df.sort_values("date", ascending=False)
        latest = sorted_df.iloc[0].to_dict()
        latest_date = latest.get("date")
        if isinstance(latest_date, pd.Timestamp):
            latest["date"] = latest_date.strftime("%Y-%m-%d")
        
        history_records: List[Dict[str, Any]] = []
        for _, row in sorted_df.head(10).iterrows():
            record = row.to_dict()
            record_date = record.get("date")
            if isinstance(record_date, pd.Timestamp):
                record["date"] = record_date.strftime("%Y-%m-%d")
            history_records.append(record)
        
        summary = {
            "avg_training_readiness": df["training_readiness"].mean() if "training_readiness" in df.columns else None,
            "avg_training_load_7d": df["training_load_7d"].mean() if "training_load_7d" in df.columns else None,
            "avg_vo2_max": df["vo2_max"].mean() if "vo2_max" in df.columns else None,
            "status_distribution": (
                df["training_status"]
                .dropna()
                .str.upper()
                .value_counts()
                .to_dict()
                if "training_status" in df.columns
                else {}
            )
        }
        
        return {
            "has_data": True,
            "period_days": days,
            "latest": latest,
            "summary": summary,
            "history": history_records
        }

    def analyze_training_status(self, days: int = 30) -> Dict[str, Any]:
        """Проанализировать статус тренированности, readiness и нагрузку"""
        df = self.db.get_training_status_history(days)
        
        if df.empty:
            return {
                "message": f"Нет данных статуса тренированности за последние {days} дней"
            }
        
        df["date"] = pd.to_datetime(df["date"])
        sorted_df = df.sort_values("date", ascending=False)
        latest_row = sorted_df.iloc[0]
        
        insights: List[str] = []
        latest_status = latest_row.get("training_status")
        if latest_status:
            insights.append(f"Garmin фиксирует статус: {latest_status}")
        
        readiness_info: Dict[str, Any] = {}
        if "training_readiness" in df.columns and not df["training_readiness"].isna().all():
            readiness_series = sorted_df["training_readiness"].dropna()
            current_readiness = readiness_series.iloc[0]
            avg_readiness = readiness_series.mean()
            readiness_info["current"] = f"Текущее readiness: {current_readiness:.0f}/100"
            readiness_info["average"] = f"Среднее за период: {avg_readiness:.1f}/100"
            
            if len(readiness_series) >= 5:
                recent_mean = readiness_series.head(3).mean()
                earlier_mean = readiness_series.iloc[3:6].mean() if len(readiness_series) >= 6 else readiness_series.tail(3).mean()
                if recent_mean > earlier_mean + 5:
                    readiness_info["trend"] = "Тренд: readiness улучшается"
                elif recent_mean < earlier_mean - 5:
                    readiness_info["trend"] = "Тренд: readiness снижается"
                else:
                    readiness_info["trend"] = "Тренд: без значимых изменений"
            
            if current_readiness < 40:
                insights.append("Низкий readiness — рекомендуется уделить внимание восстановлению")
            elif current_readiness > 70:
                insights.append("Высокий readiness — хорошее окно для интенсивных тренировок")
        
        load_info: Dict[str, Any] = {}
        if "training_load_7d" in df.columns and not df["training_load_7d"].isna().all():
            load_series = sorted_df["training_load_7d"].dropna()
            current_load = load_series.iloc[0]
            avg_load = load_series.mean()
            load_info["current"] = f"Нагрузка (7д): {current_load:.0f}"
            load_info["average"] = f"Среднее за период: {avg_load:.0f}"
            
            if len(load_series) >= 5:
                recent_mean = load_series.head(3).mean()
                earlier_mean = load_series.iloc[3:6].mean() if len(load_series) >= 6 else load_series.tail(3).mean()
                if recent_mean > earlier_mean * 1.2:
                    load_info["trend"] = "Тренд: нагрузка быстро растет"
                    insights.append("Нагрузка резко выросла — стоит контролировать усталость")
                elif recent_mean < earlier_mean * 0.8:
                    load_info["trend"] = "Тренд: нагрузка снижается"
                else:
                    load_info["trend"] = "Тренд: стабильная нагрузка"
            
            if current_load > avg_load * 1.3 and avg_load > 0:
                insights.append("Текущая нагрузка значительно выше средней")
            elif current_load < avg_load * 0.7:
                insights.append("Нагрузка ниже привычной — можно добавить объема")
        
        summary_text = latest_status or "нет данных"
        latest_date = latest_row.get("date")
        if isinstance(latest_date, pd.Timestamp):
            summary_text = f"{summary_text} от {latest_date.strftime('%Y-%m-%d')}"
        elif latest_date:
            summary_text = f"{summary_text} от {latest_date}"
        
        return {
            "latest": {
                "summary": summary_text
            },
            "insights": insights,
            "readiness_assessment": readiness_info,
            "load_assessment": load_info
        }

    def get_daily_health_stats(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику по ежедневным показателям здоровья"""
        df = self.db.get_daily_health(days)
        
        if df.empty:
            return {
                "message": f"Нет данных ежедневного здоровья за последние {days} дней",
                "period_days": days
            }
        
        df["date"] = pd.to_datetime(df["date"])
        stats = {
            "avg_steps": df["steps"].mean() if "steps" in df.columns else None,
            "avg_resting_hr": df["resting_hr"].mean() if "resting_hr" in df.columns else None,
            "avg_active_minutes": df["active_minutes"].mean() if "active_minutes" in df.columns else None,
            "avg_calories_active": df["calories_active"].mean() if "calories_active" in df.columns else None,
            "total_steps": df["steps"].sum() if "steps" in df.columns else None
        }
        
        trend = None
        if "steps" in df.columns:
            steps_series = df.sort_values("date")["steps"].dropna()
            if len(steps_series) >= 2:
                slope = np.polyfit(range(len(steps_series)), steps_series, 1)[0]
                if slope > 0:
                    trend = "increasing"
                elif slope < 0:
                    trend = "decreasing"
                else:
                    trend = "stable"
        
        recent_entries = []
        for _, row in df.sort_values("date", ascending=False).head(5).iterrows():
            record = row.to_dict()
            record_date = record.get("date")
            if isinstance(record_date, pd.Timestamp):
                record["date"] = record_date.strftime("%Y-%m-%d")
            recent_entries.append(record)
        
        return {
            "period_days": days,
            "stats": stats,
            "trend_steps": trend or "н/д",
            "recent_entries": recent_entries
        }
    
    def analyze_sleep_patterns(self, days: int = 30) -> Dict[str, Any]:
        """Анализ паттернов и качества сна"""
        try:
            sleep_df = self.db.get_sleep_data(days)
            
            if sleep_df.empty:
                return {
                    "has_data": False,
                    "message": f"Нет данных сна за последние {days} дней для анализа паттернов"
                }
            
            patterns = {}
            
            # Анализ продолжительности сна
            if "total_sleep_minutes" in sleep_df.columns:
                avg_sleep = sleep_df["total_sleep_minutes"].mean() / 60
                patterns["avg_sleep_duration"] = f"{avg_sleep:.1f} часов"
                
                # Соответствие рекомендациям (7-9 часов)
                optimal_sleep = sleep_df[(sleep_df["total_sleep_minutes"] >= 420) & 
                                       (sleep_df["total_sleep_minutes"] <= 540)]
                adherence = len(optimal_sleep) / len(sleep_df) * 100
                patterns["optimal_sleep_adherence"] = f"{adherence:.0f}% ночей в рекомендуемом диапазоне"
                
                # Постоянство сна
                sleep_std = sleep_df["total_sleep_minutes"].std() / 60
                if sleep_std < 0.5:
                    patterns["sleep_consistency"] = "очень постоянное"
                elif sleep_std < 1:
                    patterns["sleep_consistency"] = "постоянное"
                else:
                    patterns["sleep_consistency"] = "нерегулярное"
            
            # Анализ качества сна
            if "sleep_score" in sleep_df.columns and not sleep_df["sleep_score"].isna().all():
                avg_score = sleep_df["sleep_score"].mean()
                patterns["avg_sleep_score"] = f"{avg_score:.0f}/100"
                
                # Тренд сна за последние 7 дней
                if len(sleep_df) >= 7:
                    recent_score = sleep_df.head(7)["sleep_score"].mean()
                    older_score = sleep_df.tail(7)["sleep_score"].mean()
                    
                    if recent_score > older_score + 5:
                        patterns["sleep_trend"] = "улучшение"
                    elif recent_score < older_score - 5:
                        patterns["sleep_trend"] = "ухудшение"
                    else:
                        patterns["sleep_trend"] = "стабильность"
            
            # Анализ фаз сна
            if all(col in sleep_df.columns for col in ["deep_sleep_minutes", "rem_sleep_minutes", "light_sleep_minutes"]):
                total_phases = sleep_df["deep_sleep_minutes"] + sleep_df["rem_sleep_minutes"] + sleep_df["light_sleep_minutes"]
                patterns["deep_sleep_percentage"] = f"{(sleep_df['deep_sleep_minutes'] / total_phases * 100).mean():.1f}%"
                patterns["rem_sleep_percentage"] = f"{(sleep_df['rem_sleep_minutes'] / total_phases * 100).mean():.1f}%"
            
            # Рекомендации на основе паттернов
            recommendations = []
            
            if "avg_sleep_duration" in patterns:
                avg_hours = float(patterns["avg_sleep_duration"].split()[0])
                if avg_hours < 7:
                    recommendations.append("Увеличить продолжительность сна до 7-9 часов")
                elif avg_hours > 9:
                    recommendations.append("Рассмотреть оптимизацию времени сна")
            
            if "sleep_consistency" in patterns and patterns["sleep_consistency"] == "нерегулярное":
                recommendations.append("Установить регулярный режим сна")
            
            patterns["recommendations"] = recommendations
            
            return {
                "has_data": True,
                "period_days": days,
                "patterns": patterns
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка анализа паттернов сна: {str(e)}"
            }
