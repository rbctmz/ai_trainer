"""Demo-mode helpers for the first-run product flow."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from services.data_cache import clear_data_caches
from state import StateManager


def is_demo_mode(state: StateManager) -> bool:
    """Return whether the current session is using demo data."""
    return bool(getattr(state, "demo_mode", False))


def activate_demo_mode(state: StateManager) -> dict[str, int]:
    """Replace local cache with a deterministic demo dataset and enable demo mode."""
    database = state.database

    database.clear_all_data()
    state.reset_planner_overrides()

    activities = _build_demo_activities()
    hrv_data = _build_demo_hrv()
    sleep_data = _build_demo_sleep()
    health_data = _build_demo_health()
    training_status = _build_demo_training_status()

    database.save_activities(activities)
    database.save_hrv_data(hrv_data)
    database.sync_sleep_data(sleep_data)
    database.sync_daily_health(health_data)
    database.sync_training_status(training_status)
    clear_data_caches()

    state.demo_mode = True
    state.selected_page = "📊 Дашборд"

    return {
        "activities": len(activities),
        "hrv_days": len(hrv_data),
        "sleep_days": len(sleep_data),
        "health_days": len(health_data),
        "training_status_days": len(training_status),
    }


def deactivate_demo_mode(state: StateManager) -> None:
    """Clear the temporary demo dataset and leave demo mode."""
    database = state.database
    database.clear_all_data()
    clear_data_caches()
    state.reset_planner_overrides()
    state.demo_mode = False
    state.selected_page = "📊 Дашборд"


def _build_demo_activities() -> list[dict[str, Any]]:
    today = datetime.now().date()
    templates = [
        {"sport": "cycling", "duration": 95, "distance": 38.2, "avg_hr": 141, "avg_power": 212, "elevation": 340, "calories": 840, "tss": 86.0},
        {"sport": "running", "duration": 52, "distance": 9.6, "avg_hr": 154, "avg_power": None, "elevation": 42, "calories": 640, "tss": 71.0},
        {"sport": "swimming", "duration": 48, "distance": 2.1, "avg_hr": 128, "avg_power": None, "elevation": 0, "calories": 420, "tss": 39.0},
        {"sport": "cycling", "duration": 130, "distance": 52.4, "avg_hr": 146, "avg_power": 228, "elevation": 510, "calories": 1120, "tss": 118.0},
        {"sport": "running", "duration": 36, "distance": 6.4, "avg_hr": 148, "avg_power": None, "elevation": 28, "calories": 390, "tss": 42.0},
        {"sport": "gym", "duration": 55, "distance": 0.0, "avg_hr": 119, "avg_power": None, "elevation": 0, "calories": 310, "tss": 28.0},
    ]

    offsets = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 22, 25]
    activities: list[dict[str, Any]] = []

    for index, offset in enumerate(offsets):
        template = templates[index % len(templates)]
        activity_date = today - timedelta(days=offset)
        duration = template["duration"] + (index % 3) * 4
        tss = template["tss"] + (index % 4) * 3
        avg_hr = template["avg_hr"] + (index % 3)
        max_hr = avg_hr + 18 + (index % 4)
        avg_power = template["avg_power"]
        max_power = int(avg_power * 1.35) if avg_power else None

        activities.append(
            {
                "activity_id": f"demo_activity_{activity_date.strftime('%Y%m%d')}_{index}",
                "date": activity_date,
                "sport": template["sport"],
                "duration_minutes": duration,
                "distance_km": round(template["distance"] + (index % 3) * 0.6, 2),
                "avg_hr": avg_hr,
                "max_hr": max_hr,
                "avg_power": avg_power,
                "max_power": max_power,
                "elevation_gain": template["elevation"] + (index % 2) * 30,
                "calories": template["calories"] + (index % 3) * 45,
                "tss": round(tss, 1),
            }
        )

    return activities


def _build_demo_hrv() -> dict[str, dict[str, float]]:
    today = datetime.now().date()
    values: dict[str, dict[str, float]] = {}

    for offset in range(21):
        date = today - timedelta(days=offset)
        rmssd = 44.0 + ((offset + 2) % 5) * 2.3 - (offset % 3) * 0.8
        stress = 31.0 + (offset % 4) * 4.5
        recovery = 79.0 - (offset % 5) * 3.2
        values[date.strftime("%Y-%m-%d")] = {
            "rmssd": round(rmssd, 1),
            "stress_score": round(stress, 1),
            "recovery_score": round(recovery, 1),
        }

    return values


def _build_demo_sleep() -> dict[str, dict[str, Any]]:
    today = datetime.now().date()
    values: dict[str, dict[str, Any]] = {}

    for offset in range(14):
        date = today - timedelta(days=offset)
        total_sleep = 435 + (offset % 4) * 12
        deep = 82 + (offset % 3) * 8
        rem = 74 + (offset % 4) * 6
        light = total_sleep - deep - rem
        bedtime_minutes = 23 * 60 + 5 + (offset % 4) * 10
        wake_minutes = bedtime_minutes + total_sleep + 18 + (offset % 3) * 6

        values[date.strftime("%Y-%m-%d")] = {
            "total_sleep_minutes": total_sleep,
            "deep_sleep_minutes": deep,
            "light_sleep_minutes": light,
            "rem_sleep_minutes": rem,
            "awakenings_count": 1 + (offset % 3),
            "sleep_score": 78 + (offset % 4) * 4,
            "bedtime": _format_clock(bedtime_minutes),
            "wakeup_time": _format_clock(wake_minutes),
            "sleep_efficiency": round(86.0 + (offset % 4) * 2.1, 1),
        }

    return values


def _build_demo_health() -> dict[str, dict[str, int]]:
    today = datetime.now().date()
    values: dict[str, dict[str, int]] = {}

    for offset in range(14):
        date = today - timedelta(days=offset)
        values[date.strftime("%Y-%m-%d")] = {
            "resting_hr": 47 + (offset % 4),
            "steps": 8200 + offset * 230,
            "floors_climbed": 9 + (offset % 3),
            "calories_active": 410 + offset * 16,
            "calories_bmr": 1620,
            "distance_meters": 6400 + offset * 180,
            "active_minutes": 52 + (offset % 4) * 7,
            "intensity_minutes": 24 + (offset % 3) * 5,
        }

    return values


def _build_demo_training_status() -> dict[str, dict[str, Any]]:
    today = datetime.now().date()
    training_date = today.strftime("%Y-%m-%d")

    return {
        training_date: {
            "vo2_max": 51.2,
            "fitness_age": 31.0,
            "training_load_7d": 348.0,
            "training_status": "PRODUCTIVE",
            "training_readiness": 81.0,
            "recovery_time_hours": 13.0,
            "load_ratio": 1.04,
            "training_feedback_code": "PRODUCTIVE",
            "training_feedback": "Нагрузка хорошо усваивается, можно продолжать прогрессию.",
            "training_load_chronic": 332.0,
            "acwr_status": "OPTIMAL",
            "acwr_status_feedback": "Нагрузка находится в стабильной рабочей зоне.",
            "acwr_percent": 58.0,
            "training_since_date": (today - timedelta(days=70)).strftime("%Y-%m-%d"),
            "fitness_trend": 1,
            "fitness_trend_sport": "cycling",
            "sport": "cycling",
            "device_id": "demo-device",
            "last_primary_sync_date": training_date,
            "training_balance_feedback_code": "BALANCED",
            "training_balance_feedback": "Баланс объёма и интенсивности выглядит устойчивым.",
            "monthly_load_aerobic_low": 162.0,
            "monthly_load_aerobic_low_target_min": 140.0,
            "monthly_load_aerobic_low_target_max": 185.0,
            "monthly_load_aerobic_high": 118.0,
            "monthly_load_aerobic_high_target_min": 95.0,
            "monthly_load_aerobic_high_target_max": 135.0,
            "monthly_load_anaerobic": 42.0,
            "monthly_load_anaerobic_target_min": 30.0,
            "monthly_load_anaerobic_target_max": 55.0,
        }
    }


def _format_clock(total_minutes: int) -> str:
    minutes = total_minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


__all__ = ["activate_demo_mode", "deactivate_demo_mode", "is_demo_mode"]
