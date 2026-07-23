"""Garmin sync orchestration helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import time
import uuid
from typing import Any, Dict

from config.settings import Settings
from data.data_processor import ActivityProcessor, resolve_athlete_ftp_lthr
from data.data_processor_phase1 import Phase1DataProcessor
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services.data_cache import clear_data_caches
from state import StateManager

from . import garmin as garmin_service
from . import intervals_icu as intervals_icu_service


logger = logging.getLogger(__name__)

SyncCounts = Dict[str, int]
DEFAULT_SYNC_DAYS = 30
_TRANSIENT_ERROR_MARKERS = (
    "429",
    "rate limit",
    "rate-limit",
    "too many requests",
    "timed out",
    "timeout",
    "temporar",
    "503",
    "502",
    "connection aborted",
    "connection reset",
    "connection error",
    "remote disconnected",
)


def _empty_activity_counts() -> SyncCounts:
    return {"new": 0, "updated": 0, "skipped": 0}


def _empty_sync_counts() -> SyncCounts:
    return {"new": 0, "updated": 0}


# Provider-neutral progress contract lives in services.sync_contracts (review P1.1
# / §5): neither the Garmin nor the Intervals adapter owns the shared type. Re-exported
# here so every existing ``from services.sync import SyncProgressUpdate`` keeps working.
from services.sync_contracts import SyncProgressCallback, SyncProgressUpdate  # noqa: E402


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
    mode: str = "full"
    days: int = DEFAULT_SYNC_DAYS
    # Which provider this result came from. Additive in M1 (§5): the ONLY new field
    # the Garmin success-path exposes vs. pre-M1 (gate M1-T3). Defaults to 'garmin'.
    source: str = "garmin"

    def totals(self) -> SyncCounts:
        """Aggregate new/updated/skipped counts across every synced domain."""
        domain_results = (
            self.activity_result,
            self.hrv_result,
            self.sleep_result,
            self.health_result,
            self.training_status_result,
        )
        return {
            "new": sum(counts.get("new", 0) for counts in domain_results),
            "updated": sum(counts.get("updated", 0) for counts in domain_results),
            "skipped": self.activity_result.get("skipped", 0),
        }


@dataclass(frozen=True)
class SyncWindow:
    """Resolved date range for one sync run."""

    start_date: datetime
    end_date: datetime
    days: int
    mode: str  # "full" | "incremental"


def resolve_sync_window(
    database: Any,
    days: int | None = None,
    now: datetime | None = None,
) -> SyncWindow:
    """Pick the date range to sync.

    Explicit ``days`` forces a full reload of that period. Without it the window
    starts at the oldest of the per-table latest dates, re-syncing that boundary
    day on purpose: same-day activities and evolving daily metrics arrive after
    the first sync of the day, and the date-keyed UPDATE path absorbs the overlap
    without duplicates.
    """
    end_date = now or datetime.now()

    if days is not None:
        days = max(1, int(days))
        return SyncWindow(end_date - timedelta(days=days), end_date, days, "full")

    get_latest = getattr(database, "get_latest_data_dates", None)
    latest_dates: dict[str, str | None] = {}
    if callable(get_latest):
        try:
            latest_dates = get_latest() or {}
        except Exception:  # pragma: no cover - defensive path
            latest_dates = {}

    known_dates = sorted(value for value in latest_dates.values() if value)
    if not known_dates:
        return SyncWindow(
            end_date - timedelta(days=DEFAULT_SYNC_DAYS),
            end_date,
            DEFAULT_SYNC_DAYS,
            "full",
        )

    try:
        start_date = datetime.strptime(known_dates[0], "%Y-%m-%d")
    except ValueError:
        return SyncWindow(
            end_date - timedelta(days=DEFAULT_SYNC_DAYS),
            end_date,
            DEFAULT_SYNC_DAYS,
            "full",
        )

    gap_days = (end_date.date() - start_date.date()).days
    if gap_days < 0:
        gap_days = 0
    if gap_days > DEFAULT_SYNC_DAYS:
        start_date = end_date - timedelta(days=DEFAULT_SYNC_DAYS)
        gap_days = DEFAULT_SYNC_DAYS

    return SyncWindow(start_date, end_date, max(1, gap_days), "incremental")


def build_sync_status_payload(result: GarminSyncResult, days: int | None = None) -> dict[str, Any]:
    """Build a dashboard-friendly summary of the latest sync outcome."""
    if days is None:
        days = result.days
    synced_at = datetime.now().isoformat(timespec="seconds")
    period_label = (
        f"последние {days} дней"
        if result.mode == "full"
        else "период с последней синхронизации"
    )
    activity_changes = result.activity_result["new"] + result.activity_result["updated"]
    recovery_changes = (
        result.hrv_result["new"]
        + result.hrv_result["updated"]
        + result.sleep_result["new"]
        + result.sleep_result["updated"]
        + result.health_result["new"]
        + result.health_result["updated"]
        + result.training_status_result["new"]
        + result.training_status_result["updated"]
    )

    if result.warnings:
        title = "Синхронизация Garmin завершена частично"
        summary = (
            f"За {period_label} удалось получить не все данные. "
            "Проверьте замечания ниже, затем решите, нужен ли повторный запуск."
        )
        severity = "warning"
        sync_state = "partial"
    elif activity_changes > 0:
        title = "Синхронизация Garmin завершена"
        summary = (
            f"Загружены свежие тренировки и метрики за {period_label}. "
            "Теперь можно сразу перейти к интерпретации формы и ближайшей нагрузки."
        )
        severity = "success"
        sync_state = "succeeded"
    elif recovery_changes > 0:
        title = "Синхронизация Garmin обновила сигналы восстановления"
        summary = (
            f"Новых активностей за {period_label} не появилось, "
            "но HRV, сон или статус тренированности обновились."
        )
        severity = "success"
        sync_state = "succeeded"
    else:
        title = "Новых Garmin данных не найдено"
        summary = (
            f"За {period_label} новых записей не появилось. "
            "Можно продолжить анализ по уже сохранённым данным."
        )
        severity = "info"
        sync_state = "succeeded"

    return {
        "sync_state": sync_state,
        "severity": severity,
        "title": title,
        "summary": summary,
        "synced_at": synced_at,
        "days": days,
        "mode": result.mode,
        "counts": result.totals(),
        "activity_changes": activity_changes,
        "recovery_changes": recovery_changes,
        "highlights": list(result.success_messages[:4]),
        "notices": list((result.warnings + result.details)[:4]),
        # Additive in M1 (§5): the sole new key vs. the pre-M1 payload (gate M1-T3).
        "source": result.source,
    }


def sync_garmin_data(
    state: StateManager,
    days: int | None = None,
    on_progress: SyncProgressCallback | None = None,
) -> GarminSyncResult:
    """Synchronize Garmin activities and related health metrics into local storage.

    ``days=None`` runs an incremental sync from the last known data in the DB;
    an explicit ``days`` forces a full reload of that period.
    """
    if not garmin_service.is_authenticated(state):
        raise ValueError("Не подключен к Garmin Connect")

    client = garmin_service.get_client(state)
    database = state.database
    window = resolve_sync_window(database, days)
    result = GarminSyncResult(mode=window.mode, days=window.days)

    # Refresh the athlete's FTP/weight/LTHR from Intervals.icu (issue #102) before
    # resolving any activity's TSS this run, so a freshly-synced FTP is used
    # immediately rather than only on the *next* sync. A missing configuration
    # or a failed request is folded into warnings, never raised: this is an
    # optional signal the rest of the Garmin sync does not depend on.
    profile_sync = intervals_icu_service.sync_athlete_profile(database)
    if not profile_sync["synced"] and profile_sync["reason"] != "not_configured":
        result.warnings.append(f"⚠️ Intervals.icu athlete profile: {profile_sync['reason']}")

    start_date, end_date, days = window.start_date, window.end_date, window.days
    date_list = _build_date_list(start_date, end_date)

    _emit_progress(
        on_progress,
        percent=10,
        message=(
            f"📊 Загрузка активностей за {days} дней..."
            if window.mode == "full"
            else "📊 Загрузка новых данных с последней синхронизации..."
        ),
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
    result.activity_result = _sync_activities(database, activities, warnings=result.warnings)

    _emit_progress(
        on_progress,
        percent=70,
        message="💓 Загрузка HRV и данных восстановления...",
        step_text="Шаг 3/5: Загрузка HRV...",
    )
    hrv_data, hrv_warnings = _collect_hrv_data(client, date_list, on_progress)
    _extend_warnings(result.warnings, hrv_warnings)

    _emit_progress(
        on_progress,
        percent=80,
        message="😴 Загрузка данных сна...",
        step_text="Шаг 4/5: Загрузка сна и здоровья...",
    )
    sleep_data, daily_health_data, phase1_warnings = _collect_phase1_daily_data(
        client,
        date_list[: min(len(date_list), days + 1)],
    )
    _extend_warnings(result.warnings, phase1_warnings)

    _emit_progress(
        on_progress,
        percent=85,
        message="🎯 Загрузка статуса тренированности...",
        step_text="Шаг 4/5: Загрузка сна и здоровья...",
    )
    training_status_data, training_status_warnings = _collect_training_status_data(client)
    _extend_warnings(result.warnings, training_status_warnings)

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

    # Scientific capture is derived and fail-open: a valid Garmin sync is not
    # rolled back if the prospective journal cannot be refreshed.  Test/fake
    # database handles that predate the journal simply skip this optional hook.
    if callable(getattr(database, "save_readiness_snapshot", None)):
        try:
            from services.recovery_analytics import record_post_sync_recovery_state

            recovery_capture = record_post_sync_recovery_state(
                database,
                capture_run_id=str(uuid.uuid4()),
                observed_at_utc=datetime.now().astimezone(),
            )
            snapshot = recovery_capture.get("snapshot") or {}
            result.details.append(
                "Recovery snapshot: "
                f"{snapshot.get('eligibility_status', 'unknown')} · rev {snapshot.get('revision', '—')}"
            )
        except Exception as exc:
            result.warnings.append(f"⚠️ Recovery snapshot capture: {exc}")

    result.details.extend(_build_sync_details(sleep_data, daily_health_data, training_status_data))
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


def _pop_client_error(client: Any) -> dict[str, Any] | None:
    pop_error = getattr(client, "pop_last_error", None)
    if callable(pop_error):
        try:
            return pop_error()
        except Exception:  # pragma: no cover - defensive path
            return None
    return None


def _should_retry_client_error(error: dict[str, Any] | None) -> bool:
    if not error:
        return False
    message = str(error.get("message") or "").lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)


def _call_client_method(
    client: Any,
    method_name: str,
    *args: Any,
    warning_context: str,
    max_attempts: int = 3,
) -> tuple[Any, dict[str, Any] | None]:
    method = getattr(client, method_name)
    last_error: dict[str, Any] | None = None

    for attempt in range(1, max_attempts + 1):
        result = method(*args)
        last_error = _pop_client_error(client)
        if last_error and _should_retry_client_error(last_error) and attempt < max_attempts:
            logger.warning(
                "Повтор Garmin %s после transient ошибки (%s/%s): %s",
                warning_context,
                attempt,
                max_attempts,
                last_error.get("message"),
            )
            time.sleep(0.5 * attempt)
            continue
        return result, last_error

    return None, last_error


def _call_optional_client_method(
    client: Any,
    method_name: str,
    *args: Any,
    warning_context: str,
    max_attempts: int = 3,
) -> tuple[Any, dict[str, Any] | None]:
    method = getattr(client, method_name, None)
    if not callable(method):
        return None, None
    return _call_client_method(
        client,
        method_name,
        *args,
        warning_context=warning_context,
        max_attempts=max_attempts,
    )


_OPTIONAL_SIGNAL_LABELS: dict[str, str] = {
    "respiration": "respiration",
    "spo2": "SpO2",
    "skin_temperature": "skin temperature",
}


@dataclass
class _OptionalSignalTracker:
    """Отслеживает опциональные wellness-сигналы (respiration/SpO2/skin-temp)
    за один прогон sync, чтобы не ретраить и не варнить одну и ту же
    неподдерживаемую метрику на каждую дату."""

    unsupported: set[str] = field(default_factory=set)
    missing_day_counts: dict[str, int] = field(default_factory=dict)
    last_messages: dict[str, str] = field(default_factory=dict)

    def record_skip(self, signal_key: str) -> None:
        """Дата пропущена без сетевого вызова, т.к. сигнал уже помечен unsupported."""
        self.missing_day_counts[signal_key] = self.missing_day_counts.get(signal_key, 0) + 1

    def record_failure(self, signal_key: str, error: dict[str, Any] | None) -> None:
        if not error:
            return
        self.missing_day_counts[signal_key] = self.missing_day_counts.get(signal_key, 0) + 1
        message = error.get("message")
        if message:
            self.last_messages[signal_key] = message
        # Не-transient ошибка означает, что сигнал недоступен для этого
        # аккаунта/устройства, а не временный сбой сети — ретраить и дальше
        # опрашивать его до конца прогона бессмысленно.
        if not _should_retry_client_error(error):
            self.unsupported.add(signal_key)

    def summarize_warnings(self) -> list[str]:
        summaries = []
        for signal_key, count in self.missing_day_counts.items():
            label = _OPTIONAL_SIGNAL_LABELS.get(signal_key, signal_key)
            last_message = self.last_messages.get(signal_key)
            suffix = f": {last_message}" if last_message else ""
            summaries.append(f"⚠️ Garmin {label} недоступен за {count} дн.{suffix}")
        return summaries


def _fetch_optional_daily_signal(
    client: Any,
    method_name: str,
    date_value: datetime,
    *,
    signal_key: str,
    warning_context: str,
    tracker: _OptionalSignalTracker,
) -> Any:
    if signal_key in tracker.unsupported:
        tracker.record_skip(signal_key)
        return None
    data, error = _call_optional_client_method(
        client,
        method_name,
        date_value,
        warning_context=warning_context,
    )
    tracker.record_failure(signal_key, error)
    return data


def _append_warning(warnings: list[str], message: str) -> None:
    message = str(message or "").strip()
    if not message or message in warnings:
        return
    if len(warnings) >= 8:
        return
    warnings.append(message)


def _extend_warnings(warnings: list[str], new_warnings: list[str]) -> None:
    for message in new_warnings:
        _append_warning(warnings, message)


def _sync_activities(
    database: Any,
    activities: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
) -> SyncCounts:
    """Persist Garmin activities through the common provider-link ingest (M1 D1).

    Each processed+TSS-resolved activity flows through
    ``normalize_provider_activity(..., "garmin") → ingest_provider_activity`` — the
    same funnel Intervals uses — instead of the legacy bulk ``sync_activities``.
    The returned counts stay 1:1 with the old contract: ``skipped`` = no
    ``activity_id`` (filtered before normalize, as before); ``new`` =
    ``canonical_created`` (the projection created the ``activities`` row);
    ``updated`` = the canonical already existed.

    Success-path behaviour is unchanged (gate M1-T3). Failure-path is
    DELIBERATELY changed (gate M1-T3b): the WHOLE per-activity pipeline (resolve_tss,
    pre-clean, normalize, ingest) is guarded, so any single activity's failure — a
    bad TSS input, a non-scalar field that trips clean_value, or an ingest rollback
    (which is atomic and leaves no orphan link, M0) — is folded into ``warnings``
    while the sync CONTINUES with the rest, instead of the old bulk write's
    all-or-nothing abort. A ``warnings`` list is appended to when provided (the
    Garmin sync passes ``result.warnings``); callers that only want the counts may
    omit it.
    """
    counts = _empty_activity_counts()
    if warnings is None:
        warnings = []
    if not activities:
        return counts

    df = ActivityProcessor.process_activities(activities)
    if df.empty:
        return counts

    ftp, lthr = resolve_athlete_ftp_lthr(database)
    for _, row in df.iterrows():
        # The ENTIRE per-activity pipeline — row.to_dict → resolve_tss → pre-clean →
        # normalize → ingest — runs under ONE try/except, so ANY per-activity failure
        # (a bad TSS input, a non-scalar field that trips clean_value, an ingest
        # rollback) becomes a warning and the sync CONTINUES with the next activity
        # instead of aborting the whole batch (gate M1-T3b). Only an empty
        # activity_id is a distinct SKIP (not a failure), matching legacy
        # sync_activities. activity_id is captured first so the warning can name it.
        activity_id = None
        try:
            activity_dict = row.to_dict()
            activity_id = database.clean_value(activity_dict.get("activity_id"))
            if not activity_id:  # matches legacy sync_activities' skip test
                counts["skipped"] += 1
                continue
            activity_dict.update(
                ActivityProcessor.resolve_tss(activity_dict, ftp=ftp, lthr=lthr)
            )
            # Normalize values to SQLite-native scalars BEFORE they enter the link
            # payload: the projection re-derives the canonical row from that JSON
            # snapshot, so a pandas Timestamp/NaT must be collapsed to the same
            # string/None the legacy `sync_activities` stored (via clean_value) — else
            # a date like "2026-07-10 00:00:00" would replace "2026-07-10" and break
            # date-keyed reads. clean_value is idempotent for these scalars.
            cleaned = {key: database.clean_value(value) for key, value in activity_dict.items()}
            candidate = normalize_provider_activity(cleaned, "garmin")
            outcome = ingest_provider_activity(
                database, candidate, primary_source=Settings.PRIMARY_ACTIVITY_SOURCE
            )
        except Exception as exc:  # per-activity failure → warn and continue (M1-T3b)
            _append_warning(
                warnings, f"⚠️ Активность {activity_id or '<без id>'} не сохранена: {exc}"
            )
            continue
        if outcome.get("canonical_created"):
            counts["new"] += 1
        else:
            counts["updated"] += 1

    return counts


def _peak_body_battery(battery_values: list[Any]) -> float | None:
    # bodyBatteryValuesArray is [timestamp_ms, value] pairs sorted ascending by
    # time. The peak (usually hit soon after waking) approximates how
    # recovered the day started. The *last* point is just whatever the
    # battery read at sync time, so re-syncing the same date later in the
    # day (once the full array is available) silently overwrites a fresh
    # morning reading with a drained evening one -- that was the bug.
    values = [point[1] for point in battery_values if point and point[1] is not None]
    return max(values) if values else None


def _collect_hrv_data(
    client: Any,
    date_list: list[datetime],
    on_progress: SyncProgressCallback | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    hrv_data: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    batch_size = 5
    total_batches = max(1, len(date_list) // batch_size + (1 if len(date_list) % batch_size else 0))

    for batch_index, start_index in enumerate(range(0, len(date_list), batch_size), start=1):
        batch_dates = date_list[start_index:start_index + batch_size]

        for date_value in batch_dates:
            date_str = _db_date(date_value)

            hrv_day_data, hrv_error = _call_client_method(
                client,
                "get_hrv_data",
                date_value,
                warning_context=f"HRV {date_str}",
            )
            if hrv_error:
                _append_warning(warnings, f"⚠️ Garmin HRV {date_str}: {hrv_error.get('message')}")
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
            stress_data, stress_error = _call_client_method(
                client,
                "get_stress_data",
                date_value,
                warning_context=f"stress {date_str}",
            )
            if stress_error:
                _append_warning(warnings, f"⚠️ Garmin stress {date_str}: {stress_error.get('message')}")
            logger.debug("DEBUG STRESS SYNC: Получены данные стресса для %s: %s", date_str, type(stress_data))
            if stress_data:
                logger.debug("DEBUG STRESS SYNC: Структура данных стресса: %s", stress_data)

            if isinstance(stress_data, dict):
                stress_score = stress_data.get("avgStressLevel") or stress_data.get("overallStressLevel")
            elif isinstance(stress_data, (int, float)):
                stress_score = stress_data

            recovery_score = None
            body_battery_data, body_battery_error = _call_client_method(
                client,
                "get_body_battery_data",
                date_value,
                warning_context=f"body battery {date_str}",
            )
            if body_battery_error:
                _append_warning(warnings, f"⚠️ Garmin Body Battery {date_str}: {body_battery_error.get('message')}")
            if body_battery_data and isinstance(body_battery_data, list) and len(body_battery_data) > 0:
                entry = body_battery_data[0]
                if "bodyBatteryValuesArray" in entry and entry["bodyBatteryValuesArray"]:
                    recovery_score = _peak_body_battery(entry["bodyBatteryValuesArray"])

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

    return hrv_data, warnings


def _collect_phase1_daily_data(
    client: Any,
    dates_to_process: list[datetime],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    sleep_data: dict[str, dict[str, Any]] = {}
    daily_health_data: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    optional_signals = _OptionalSignalTracker()

    for date_value in dates_to_process:
        date_str = _db_date(date_value)

        try:
            sleep_raw, sleep_error = _call_client_method(
                client,
                "get_sleep_data",
                date_value,
                warning_context=f"sleep {date_str}",
            )
            if sleep_error:
                _append_warning(warnings, f"⚠️ Garmin sleep {date_str}: {sleep_error.get('message')}")
            logger.debug("DEBUG SYNC: Получены данные сна для %s: %s", date_str, type(sleep_raw))

            if sleep_raw:
                processed_sleep = Phase1DataProcessor.process_sleep_data(sleep_raw)
                logger.debug("DEBUG SYNC: Обработанные данные сна для %s: %s", date_str, processed_sleep)

                if processed_sleep:
                    date_key = processed_sleep.get("sleep_date") or date_str
                    sleep_data[date_key] = processed_sleep
        except Exception as exc:
            logger.debug("DEBUG SYNC: Ошибка обработки данных сна для %s: %s", date_str, exc)
            _append_warning(warnings, f"⚠️ Обработка сна {date_str}: {exc}")

        try:
            daily_summary, daily_summary_error = _call_client_method(
                client,
                "get_daily_summary",
                date_value,
                warning_context=f"daily summary {date_str}",
            )
            if daily_summary_error:
                _append_warning(warnings, f"⚠️ Garmin daily summary {date_str}: {daily_summary_error.get('message')}")
            resting_hr, resting_hr_error = _call_client_method(
                client,
                "get_resting_heart_rate",
                date_value,
                warning_context=f"resting HR {date_str}",
            )
            if resting_hr_error:
                _append_warning(warnings, f"⚠️ Garmin resting HR {date_str}: {resting_hr_error.get('message')}")

            respiration_data = _fetch_optional_daily_signal(
                client,
                "get_respiration_data",
                date_value,
                signal_key="respiration",
                warning_context=f"respiration {date_str}",
                tracker=optional_signals,
            )
            spo2_data = _fetch_optional_daily_signal(
                client,
                "get_spo2_data",
                date_value,
                signal_key="spo2",
                warning_context=f"SpO2 {date_str}",
                tracker=optional_signals,
            )
            skin_temperature_data = _fetch_optional_daily_signal(
                client,
                "get_skin_temperature_data",
                date_value,
                signal_key="skin_temperature",
                warning_context=f"skin temperature {date_str}",
                tracker=optional_signals,
            )

            if any([daily_summary, resting_hr, respiration_data, spo2_data, skin_temperature_data]):
                processed_health = Phase1DataProcessor.process_daily_health_data(
                    daily_summary,
                    resting_hr,
                    respiration_data=respiration_data,
                    spo2_data=spo2_data,
                    skin_temperature_data=skin_temperature_data,
                )
                if processed_health:
                    daily_health_data[date_str] = processed_health
        except Exception as exc:
            _append_warning(warnings, f"⚠️ Обработка ежедневного здоровья {date_str}: {exc}")

    _extend_warnings(warnings, optional_signals.summarize_warnings())

    return sleep_data, daily_health_data, warnings


def _collect_training_status_data(client: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    training_status_data: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    try:
        training_status, training_status_error = _call_client_method(
            client,
            "get_training_status",
            warning_context="training status",
        )
        if training_status_error:
            _append_warning(warnings, f"⚠️ Garmin training status: {training_status_error.get('message')}")
        vo2_data, vo2_error = _call_client_method(
            client,
            "get_vo2_max",
            warning_context="VO2 max",
        )
        if vo2_error:
            _append_warning(warnings, f"⚠️ Garmin VO2 max: {vo2_error.get('message')}")
        readiness_data, readiness_error = _call_client_method(
            client,
            "get_training_readiness",
            warning_context="training readiness",
        )
        if readiness_error:
            _append_warning(warnings, f"⚠️ Garmin readiness: {readiness_error.get('message')}")

        if training_status or vo2_data:
            processed_status = Phase1DataProcessor.process_training_status_data(
                training_status,
                vo2_data,
                readiness_data,
            )
            if processed_status:
                training_status_data[datetime.now().strftime("%Y-%m-%d")] = processed_status
    except Exception as exc:
        _append_warning(warnings, f"⚠️ Обработка training status: {exc}")

    return training_status_data, warnings


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
    "DEFAULT_SYNC_DAYS",
    "GarminSyncResult",
    "SyncProgressUpdate",
    "SyncWindow",
    "build_sync_status_payload",
    "resolve_sync_window",
    "sync_garmin_data",
]
