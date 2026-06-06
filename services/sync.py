"""Garmin sync orchestration helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any, Callable, Dict

from config.settings import Settings
from data.data_processor import ActivityProcessor
from data.data_processor_phase1 import Phase1DataProcessor
from services.data_cache import clear_data_caches
from state import StateManager

from . import garmin as garmin_service


logger = logging.getLogger(__name__)

SyncCounts = Dict[str, int]
SyncProgressCallback = Callable[["SyncProgressUpdate"], None]


def _empty_activity_counts() -> SyncCounts:
    return {"new": 0, "updated": 0, "skipped": 0}


def _empty_sync_counts() -> SyncCounts:
    return {"new": 0, "updated": 0}


@dataclass(frozen=True)
class SyncProgressUpdate:
    """A UI-agnostic progress event emitted during Garmin sync."""

    percent: int
    message: str
    step_text: str | None = None
    stats_message: str | None = None


@dataclass
class GarminSyncResult:
    """Structured sync result that the UI can render."""

    activity_result: SyncCounts = field(default_factory=_empty_activity_counts)
    hrv_result: SyncCounts = field(default_factory=_empty_sync_counts)
    sleep_result: SyncCounts = field(default_factory=_empty_sync_counts)
    health_result: SyncCounts = field(default_factory=_empty_sync_counts)
    training_status_result: SyncCounts = field(default_factory=_empty_sync_counts)
    warnings: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    success_messages: list[str] = field(default_factory=list)


def sync_garmin_data(
    state: StateManager,
    days: int = 30,
    on_progress: SyncProgressCallback | None = None,
) -> GarminSyncResult:
    """Synchronize Garmin activities and related health metrics into local storage."""
    if not garmin_service.is_authenticated(state):
        raise ValueError("Не подключен к Garmin Connect")

    client = garmin_service.get_client(state)
    database = state.database
    result = GarminSyncResult()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    date_list = _build_date_list(start_date, end_date)

    _emit_progress(
        on_progress,
        percent=10,
        message=f"📊 Загрузка активностей за {days} дней...",
        step_text="Шаг 1/5: Получение активностей...",
    )

    activities, activities_error = garmin_service.get_activities_with_error(
        state,
        start_date,
        end_date,
    )
    if activities_error and activities_error.get("message"):
        result.warnings.append(activities_error["message"])

    _emit_progress(
        on_progress,
        percent=30,
        message=f"⚙️ Обработка {len(activities)} активностей..." if activities else "⚙️ Новые активности не найдены",
        step_text="Шаг 2/5: Обработка активностей...",
        stats_message=f"Найдено активностей: {len(activities)}" if activities else None,
    )
    result.activity_result = _sync_activities(database, activities)

    _emit_progress(
        on_progress,
        percent=70,
        message="💓 Загрузка HRV и данных восстановления...",
        step_text="Шаг 3/5: Загрузка HRV...",
    )
    hrv_data = _collect_hrv_data(client, date_list, on_progress)

    _emit_progress(
        on_progress,
        percent=80,
        message="😴 Загрузка данных сна...",
        step_text="Шаг 4/5: Загрузка сна и здоровья...",
    )
    sleep_data, daily_health_data = _collect_phase1_daily_data(
        client,
        date_list[: min(len(date_list), days + 1)],
    )

    _emit_progress(
        on_progress,
        percent=85,
        message="🎯 Загрузка статуса тренированности...",
        step_text="Шаг 4/5: Загрузка сна и здоровья...",
    )
    training_status_data = _collect_training_status_data(client)

    _emit_progress(
        on_progress,
        percent=95,
        message="💾 Сохранение расширенных данных...",
        step_text="Шаг 5/5: Сохранение данных...",
    )

    if hrv_data:
        result.hrv_result = database.sync_hrv_data(hrv_data)
    if sleep_data:
        result.sleep_result = database.sync_sleep_data(sleep_data)
    if daily_health_data:
        result.health_result = database.sync_daily_health(daily_health_data)
    if training_status_data:
        result.training_status_result = database.sync_training_status(training_status_data)

    clear_data_caches()

    result.details = _build_sync_details(sleep_data, daily_health_data, training_status_data)
    result.success_messages = _build_success_messages(result)

    _emit_progress(
        on_progress,
        percent=100,
        message="✅ Синхронизация завершена!",
        step_text="✅ Синхронизация завершена!",
    )

    return result


def _emit_progress(
    on_progress: SyncProgressCallback | None,
    *,
    percent: int,
    message: str,
    step_text: str | None = None,
    stats_message: str | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        SyncProgressUpdate(
            percent=percent,
            message=message,
            step_text=step_text,
            stats_message=stats_message,
        )
    )


def _build_date_list(start_date: datetime, end_date: datetime) -> list[datetime]:
    date_list: list[datetime] = []
    current_date = start_date
    while current_date <= end_date:
        date_list.append(current_date)
        current_date += timedelta(days=1)
    return date_list


def _db_date(date_value: datetime) -> str:
    return date_value.strftime("%Y-%m-%d")


def _sync_activities(database: Any, activities: list[dict[str, Any]]) -> SyncCounts:
    if not activities:
        return _empty_activity_counts()

    df = ActivityProcessor.process_activities(activities)
    if df.empty:
        return _empty_activity_counts()

    tss_values = []
    for _, row in df.iterrows():
        activity_dict = row.to_dict()
        tss_values.append(
            ActivityProcessor.calculate_tss(
                activity_dict,
                ftp=Settings.USER_FTP,
                lthr=Settings.USER_LTHR,
            )
        )

    df["tss"] = tss_values
    return database.sync_activities(df.to_dict("records"))


def _collect_hrv_data(
    client: Any,
    date_list: list[datetime],
    on_progress: SyncProgressCallback | None,
) -> dict[str, dict[str, Any]]:
    hrv_data: dict[str, dict[str, Any]] = {}
    batch_size = 5
    total_batches = max(1, len(date_list) // batch_size + (1 if len(date_list) % batch_size else 0))

    for batch_index, start_index in enumerate(range(0, len(date_list), batch_size), start=1):
        batch_dates = date_list[start_index:start_index + batch_size]

        for date_value in batch_dates:
            date_str = _db_date(date_value)

            hrv_day_data = client.get_hrv_data(date_value)
            rmssd_value = None

            logger.debug("DEBUG HRV: Получены данные HRV для %s: %s", date_str, type(hrv_day_data))
            if hrv_day_data:
                logger.debug("DEBUG HRV: Структура данных: %s", hrv_day_data)

            if isinstance(hrv_day_data, dict):
                if "hrvSummary" in hrv_day_data and isinstance(hrv_day_data["hrvSummary"], dict):
                    hrv_summary = hrv_day_data["hrvSummary"]
                    rmssd_value = hrv_summary.get("rmssd") or hrv_summary.get("lastNightAvg")
                elif "daily_rmssd" in hrv_day_data:
                    rmssd_value = hrv_day_data["daily_rmssd"]
                elif "rmssd" in hrv_day_data:
                    rmssd_value = hrv_day_data["rmssd"]

            stress_score = None
            stress_data = client.get_stress_data(date_value)
            logger.debug("DEBUG STRESS SYNC: Получены данные стресса для %s: %s", date_str, type(stress_data))
            if stress_data:
                logger.debug("DEBUG STRESS SYNC: Структура данных стресса: %s", stress_data)

            if isinstance(stress_data, dict):
                stress_score = stress_data.get("avgStressLevel") or stress_data.get("overallStressLevel")
            elif isinstance(stress_data, (int, float)):
                stress_score = stress_data

            recovery_score = None
            body_battery_data = client.get_body_battery_data(date_value)
            if body_battery_data and isinstance(body_battery_data, list) and len(body_battery_data) > 0:
                entry = body_battery_data[0]
                if "bodyBatteryValuesArray" in entry and entry["bodyBatteryValuesArray"]:
                    battery_values = entry["bodyBatteryValuesArray"]
                    if battery_values:
                        recovery_score = battery_values[-1][1]

            if rmssd_value is not None or stress_score is not None or recovery_score is not None:
                hrv_data[date_str] = {
                    "rmssd": rmssd_value,
                    "stress_score": stress_score,
                    "recovery_score": recovery_score,
                }

        progress = 70 + batch_index / total_batches * 10
        _emit_progress(
            on_progress,
            percent=min(int(progress), 80),
            message="💓 Загрузка HRV и данных восстановления...",
            step_text="Шаг 3/5: Загрузка HRV...",
        )

    return hrv_data


def _collect_phase1_daily_data(
    client: Any,
    dates_to_process: list[datetime],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    sleep_data: dict[str, dict[str, Any]] = {}
    daily_health_data: dict[str, dict[str, Any]] = {}

    for date_value in dates_to_process:
        date_str = _db_date(date_value)

        try:
            sleep_raw = client.get_sleep_data(date_value)
            logger.debug("DEBUG SYNC: Получены данные сна для %s: %s", date_str, type(sleep_raw))

            if sleep_raw:
                processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw)
                logger.debug("DEBUG SYNC: Обработанные данные сна для %s: %s", date_str, processed_sleep)

                if processed_sleep:
                    date_key = processed_sleep.get("sleep_date") or date_str
                    sleep_data[date_key] = processed_sleep
        except Exception as exc:
            logger.debug("DEBUG SYNC: Ошибка обработки данных сна для %s: %s", date_str, exc)

        try:
            daily_summary = client.get_daily_summary(date_value)
            resting_hr = client.get_resting_heart_rate(date_value)

            if daily_summary or resting_hr:
                processed_health = Phase1DataProcessor.process_daily_health_data(
                    daily_summary,
                    resting_hr,
                )
                if processed_health:
                    daily_health_data[date_str] = processed_health
        except Exception:
            pass

    return sleep_data, daily_health_data


def _collect_training_status_data(client: Any) -> dict[str, dict[str, Any]]:
    training_status_data: dict[str, dict[str, Any]] = {}

    try:
        training_status = client.get_training_status()
        vo2_data = client.get_vo2_max()
        readiness_data = client.get_training_readiness()

        if training_status or vo2_data:
            processed_status = Phase1DataProcessor.process_training_status_data(
                training_status,
                vo2_data,
                readiness_data,
            )
            if processed_status:
                training_status_data[datetime.now().strftime("%Y-%m-%d")] = processed_status
    except Exception:
        pass

    return training_status_data


def _build_sync_details(
    sleep_data: dict[str, dict[str, Any]],
    daily_health_data: dict[str, dict[str, Any]],
    training_status_data: dict[str, dict[str, Any]],
) -> list[str]:
    details: list[str] = []

    if len(sleep_data) == 0:
        details.append("😴 Данные сна: не найдены (возможно, недоступны в Garmin Connect)")
    if len(daily_health_data) == 0:
        details.append("🏃 Данные здоровья: не найдены")
    if len(training_status_data) == 0:
        details.append("🎯 Статус тренированности: не найден (возможно, требуется Premium подписка Garmin)")

    return details


def _build_success_messages(result: GarminSyncResult) -> list[str]:
    success_messages: list[str] = []

    if result.activity_result["new"] > 0:
        success_messages.append(f"🆕 {result.activity_result['new']} новых активностей")
    if result.activity_result["updated"] > 0:
        success_messages.append(f"🔄 {result.activity_result['updated']} активностей обновлено")
    if result.activity_result["skipped"] > 0:
        success_messages.append(f"⏭️ {result.activity_result['skipped']} активностей пропущено")

    if result.hrv_result["new"] > 0:
        success_messages.append(f"💓 {result.hrv_result['new']} новых HRV записей")
    if result.hrv_result["updated"] > 0:
        success_messages.append(f"💓 {result.hrv_result['updated']} HRV записей обновлено")

    if result.sleep_result["new"] > 0:
        success_messages.append(f"😴 {result.sleep_result['new']} новых записей сна")
    if result.sleep_result["updated"] > 0:
        success_messages.append(f"😴 {result.sleep_result['updated']} записей сна обновлено")

    if result.health_result["new"] > 0:
        success_messages.append(f"🏃 {result.health_result['new']} новых записей здоровья")
    if result.health_result["updated"] > 0:
        success_messages.append(f"🏃 {result.health_result['updated']} записей здоровья обновлено")

    if result.training_status_result["new"] > 0 or result.training_status_result["updated"] > 0:
        success_messages.append("🎯 Статус тренированности обновлён")

    return success_messages


__all__ = [
    "GarminSyncResult",
    "SyncProgressUpdate",
    "sync_garmin_data",
]
