"""Headless bounded delivery of the active plan to Intervals.icu."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config.settings import Settings
from data.database import Database
from models.intervals_workout_delivery import (
    build_delivery_events,
    provider_event_is_executable,
    provider_event_is_owned,
    provider_event_preserves_required_targets,
    provider_event_requires_pace_targets,
)
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from services.intervals_icu import IntervalsICUClient, get_client


def athlete_local_date(observed_at_utc: datetime | None = None) -> date:
    """Resolve today's delivery boundary in the configured athlete timezone."""
    observed = observed_at_utc or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    timezone_name = str(Settings.ATHLETE_TIMEZONE or "").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("ATHLETE_TIMEZONE must be a valid IANA timezone") from exc
    return observed.astimezone(zone).date()


def _selected_dates(
    *,
    days: int | None,
    dates: Sequence[str] | None,
    today: date | None,
) -> list[str]:
    if (days is None) == (dates is None):
        raise ValueError("exactly one of days or dates is required")
    if days is not None:
        count = int(days)
        if not 1 <= count <= 90:
            raise ValueError("delivery range must be between 1 and 90 days")
        start = today or athlete_local_date()
        return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]
    normalized = sorted({date.fromisoformat(str(value)[:10]).isoformat() for value in (dates or [])})
    if not normalized:
        return []
    if (date.fromisoformat(normalized[-1]) - date.fromisoformat(normalized[0])).days > 90:
        raise ValueError("delivery dates must fit inside 90 days")
    return normalized


def _base_result(
    *,
    status: str,
    source: str,
    checkpoint_id: int | None,
    dates: Sequence[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "checkpoint_id": checkpoint_id,
        "dates": list(dates),
        "oldest": dates[0] if dates else None,
        "newest": dates[-1] if dates else None,
        "provider_event_ids": [],
        "desired_count": 0,
        "executable_count": 0,
        "calendar_only_count": 0,
        "target_mismatch_count": 0,
        "deleted_count": 0,
        "failed_count": 0,
        "retryable": False,
        "error": None,
    }


def deliver_active_plan(
    db: Database,
    *,
    days: int | None = None,
    dates: Sequence[str] | None = None,
    today: date | None = None,
    source: str,
    client: IntervalsICUClient | Any | None = None,
) -> dict[str, Any]:
    """Converge a bounded provider window on the active local checkpoint."""
    selected = _selected_dates(days=days, dates=dates, today=today)
    checkpoint = db.get_latest_planning_checkpoint()
    checkpoint_id = int(checkpoint["id"]) if checkpoint and checkpoint.get("id") else None
    result = _base_result(
        status="pending",
        source=str(source),
        checkpoint_id=checkpoint_id,
        dates=selected,
    )
    if not selected:
        return {**result, "status": "skipped"}
    resolved_client = client or get_client()
    if not resolved_client.is_configured():
        return {**result, "status": "not_configured"}
    plan = restore_goal_plan_from_checkpoint(checkpoint) if checkpoint else None
    if not plan or not plan.get("daily_plan"):
        return {**result, "status": "no_plan"}

    oldest = date.fromisoformat(selected[0])
    newest = date.fromisoformat(selected[-1])
    existing = resolved_client.list_workout_events(oldest, newest)
    desired = build_delivery_events(plan, selected)
    upserted = (
        resolved_client.upsert_events_by_external_id(desired) if desired else []
    )
    desired_external_ids = {
        str(row.get("external_id") or "") for row in desired
    }
    selected_set = set(selected)
    confirmed = [
        row
        for row in upserted
        if str(row.get("external_id") or "") in desired_external_ids
    ]
    confirmed_external_ids = {
        str(row.get("external_id") or "") for row in confirmed
    }
    pace_desired = {
        str(row.get("external_id") or ""): row
        for row in desired
        if provider_event_requires_pace_targets(row)
    }
    evidence_by_external_id = {
        str(row.get("external_id") or ""): row for row in confirmed
    }
    target_mismatch_ids: set[str] = set()
    if pace_desired:
        read_back = resolved_client.list_workout_events(oldest, newest)
        read_back_by_external_id = {
            str(row.get("external_id") or ""): row
            for row in read_back
            if str(row.get("external_id") or "") in pace_desired
        }
        for external_id, desired_event in pace_desired.items():
            provider_event = read_back_by_external_id.get(external_id)
            if provider_event is None or not provider_event_preserves_required_targets(
                desired_event,
                provider_event,
            ):
                target_mismatch_ids.add(external_id)
                continue
            evidence_by_external_id[external_id] = provider_event
    failed_external_ids = (
        desired_external_ids - confirmed_external_ids
    ) | target_mismatch_ids
    failed_count = len(failed_external_ids)

    # Cleanup is fail closed. An explicit date list may be non-contiguous, so
    # the bounded provider read can contain managed workouts that were not part
    # of this recovery edit. Also keep the previous slots if the provider only
    # confirms part of a replacement payload.
    can_cleanup = not desired or failed_count == 0
    doomed = (
        [
            {"id": row.get("id"), "external_id": row.get("external_id")}
            for row in existing
            if provider_event_is_owned(row)
            and row.get("id") is not None
            and str(row.get("start_date_local") or "")[:10] in selected_set
            and str(row.get("external_id") or "") not in desired_external_ids
        ]
        if can_cleanup
        else []
    )
    deleted_count = resolved_client.delete_events(doomed) if doomed else 0
    executable_count = sum(
        provider_event_is_executable(evidence_by_external_id[external_id])
        and external_id not in target_mismatch_ids
        for external_id in confirmed_external_ids
    )
    calendar_only_count = (
        len(confirmed_external_ids - target_mismatch_ids) - executable_count
    )
    status = (
        "partial"
        if failed_count
        else "calendar_only"
        if calendar_only_count
        else "success"
    )
    return {
        **result,
        "status": status,
        "provider_event_ids": [row.get("id") for row in confirmed if row.get("id") is not None],
        "desired_count": len(desired),
        "executable_count": executable_count,
        "calendar_only_count": calendar_only_count,
        "target_mismatch_count": len(target_mismatch_ids),
        "deleted_count": int(deleted_count or 0),
        "failed_count": failed_count,
        "retryable": bool(failed_count),
    }


def _sanitized_error(exc: Exception, secrets: Sequence[str]) -> str:
    message = str(exc) or exc.__class__.__name__
    for secret in secrets:
        if secret:
            message = message.replace(str(secret), "[redacted]")
    return message


def safe_deliver_active_plan(
    db: Database,
    *,
    days: int | None = None,
    dates: Sequence[str] | None = None,
    today: date | None = None,
    source: str,
    client: IntervalsICUClient | Any | None = None,
    secrets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return retryable delivery evidence without invalidating local truth."""
    try:
        result = deliver_active_plan(
            db,
            days=days,
            dates=dates,
            today=today,
            source=source,
            client=client,
        )
    except Exception as exc:
        try:
            selected = _selected_dates(days=days, dates=dates, today=today)
        except Exception:
            selected = []
        result = {
            **_base_result(
                status="failed",
                source=str(source),
                checkpoint_id=(db.get_latest_planning_checkpoint() or {}).get("id"),
                dates=selected,
            ),
            "status": "failed",
            "failed_count": 1,
            "retryable": True,
            "error": _sanitized_error(
                exc,
                list(secrets or []) + [str(Settings.INTERVALS_ICU_API_KEY or "")],
            ),
        }
    result["history_status"] = "pending"
    result["history_retryable"] = False
    result["history_error"] = None
    try:
        db.save_intervals_plan_delivery(result)
        result["history_status"] = "recorded"
    except Exception as exc:
        # The provider may already have accepted the write. Keep that evidence
        # honest and expose a retryable local-history failure without claiming
        # the provider delivery itself failed.
        result["retryable"] = True
        result["history_status"] = "failed"
        result["history_retryable"] = True
        result["history_error"] = _sanitized_error(
            exc,
            list(secrets or []) + [str(Settings.INTERVALS_ICU_API_KEY or "")],
        )
    return result


__all__ = [
    "athlete_local_date",
    "deliver_active_plan",
    "safe_deliver_active_plan",
]
