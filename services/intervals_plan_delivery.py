"""Headless bounded delivery of the active plan to Intervals.icu."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Sequence

from config.settings import Settings
from data.database import Database
from models.intervals_workout_delivery import (
    build_delivery_events,
    provider_event_is_executable,
    provider_event_is_owned,
)
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from services.intervals_icu import IntervalsICUClient, get_client


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
        start = today or date.today()
        return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]
    normalized = sorted({date.fromisoformat(str(value)[:10]).isoformat() for value in (dates or [])})
    if not normalized:
        raise ValueError("at least one delivery date is required")
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
    upserted = resolved_client.upsert_events_by_uid(desired) if desired else []
    desired_uids = {str(row.get("uid") or "") for row in desired}
    doomed = [
        {"id": row.get("id"), "external_id": row.get("external_id")}
        for row in existing
        if provider_event_is_owned(row)
        and row.get("id") is not None
        and str(row.get("uid") or "") not in desired_uids
    ]
    deleted_count = resolved_client.delete_events(doomed) if doomed else 0
    executable_count = sum(provider_event_is_executable(row) for row in upserted)
    calendar_only_count = len(upserted) - executable_count
    failed_count = max(0, len(desired) - len(upserted))
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
        "provider_event_ids": [row.get("id") for row in upserted if row.get("id") is not None],
        "desired_count": len(desired),
        "executable_count": executable_count,
        "calendar_only_count": calendar_only_count,
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
        return deliver_active_plan(
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
        return {
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


__all__ = ["deliver_active_plan", "safe_deliver_active_plan"]
