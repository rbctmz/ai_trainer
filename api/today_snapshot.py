"""Headless composition of the versioned daily decision snapshot."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from api.briefing_settings import get_briefing_frequency, is_quiet_day
from api.operational_state import build_operational_state
from api.planning_service import reconciliation_at
from api.readiness_snapshot import build_readiness_snapshot
from api.recovery_replan_loop import run_recovery_replan_loop
from api.session_feedback import feedback_from_today_evidence
from data.database import Database
from models.planning_checkpoints import (
    restore_goal_plan_from_checkpoint,
    summarize_checkpoint_provenance,
)
from models.readiness_conflicts import ROLE_LABELS_RU
from services.intervals_plan_delivery import athlete_local_date

TODAY_SNAPSHOT_VERSION = "today_decision_snapshot_v2"

_KEY_ROLES = {"quality", "long"}
_ACTIVE_PROPOSAL_STATUSES = {"pending", "applying"}
_HANDLED_PROPOSAL_STATUSES = {"approved", "rejected", "rolled_back"}
_FORECAST_HORIZON_DAYS = 7

_NO_PLAN_REASON = (
    "Нет активного плана — контуру не с чем сверять готовность. "
    "Построй план, и экран оживёт."
)


def _device_sync_hint(
    checkpoint: Mapping[str, Any] | None,
    as_of: str,
    deliveries: Sequence[Mapping[str, Any]],
) -> dict[str, str] | None:
    """Напоминание синхронизировать устройство (#397).

    План на сегодня был перепланирован сегодня (recovery_replan) — доставка в
    Intervals.icu прошла, но на устройство Garmin воркаут попадает только после
    синка часов. Возвращаем подсказку только когда переплан свежий И успешно
    доставлен именно на сегодня (review P1/P2) — иначе синк не принесёт
    обновлённую тренировку.
    """
    if not isinstance(checkpoint, dict):
        return None
    source = str(checkpoint.get("checkpoint_source") or "").strip().lower()
    # #411 review P2: перенос сессии тоже меняет план на сегодня (checkpoint
    # recovery_replan_transfer) — подсказка синка должна срабатывать и для него.
    if source not in {"recovery_replan", "recovery_replan_transfer"}:
        return None
    created_at = str(checkpoint.get("created_at") or "").strip()
    try:
        checkpoint_created_at = datetime.fromisoformat(created_at.replace(" ", "T"))
        if checkpoint_created_at.tzinfo is None:
            checkpoint_created_at = checkpoint_created_at.replace(tzinfo=timezone.utc)
        checkpoint_local_date = athlete_local_date(checkpoint_created_at).isoformat()
    except (TypeError, ValueError):
        return None
    checkpoint_id = checkpoint.get("id")
    if (
        checkpoint_id is None
        or not created_at
        or checkpoint_local_date != str(as_of)[:10]
    ):
        return None
    delivery = next(
        (
            item
            for item in deliveries
            if item.get("checkpoint_id") == int(checkpoint_id)
            and str(as_of)[:10]
            in [str(value) for value in (item.get("dates") or [])]
            and str(item.get("status") or "") == "success"
        ),
        None,
    )
    if delivery is None:
        return None
    return {
        "reason": "recovery_replan",
        "at": created_at,
        "delivered_at": delivery.get("created_at"),
    }


def build_today_decision_snapshot(
    db: Database,
    *,
    demo: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Build one fail-open daily snapshot without delegating decisions to a UI."""
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0)
    generated_at = generated_at_utc.isoformat()
    checkpoint = _latest_checkpoint(db)
    goal_plan = restore_goal_plan_from_checkpoint(checkpoint) if checkpoint else None
    loop_result = _run_loop(db, today=today)
    report = dict(loop_result.get("readiness_conflicts") or {})
    snapshot, readiness_error = _readiness_snapshot(db)

    fallback_date = (today or datetime.now().date()).isoformat()
    as_of = str(report.get("as_of") or fallback_date)[:10]
    readiness = _project_readiness(snapshot)
    session = _day_session(report, goal_plan, as_of)
    proposal = _resolve_proposal(db, loop_result, checkpoint)
    forecast = _resolve_forecast(db, loop_result, checkpoint, goal_plan, as_of)
    yesterday = _yesterday_reconciliation(db, as_of, checkpoint is not None)
    feedback = _feedback_block(
        db,
        yesterday=yesterday,
        current_day={
            "status": yesterday.get("status"),
            "rows": yesterday.get("current_day_rows") or [],
        },
        goal_plan=goal_plan,
        forecast=forecast,
        now_utc=generated_at_utc,
        as_of=as_of,
    )
    state, reason, primary_action = _resolve_state(
        checkpoint=checkpoint,
        report=report,
        outcome=loop_result.get("outcome"),
        proposal=proposal,
        readiness_error=readiness_error,
    )
    gate = _project_gate(loop_result, report)

    has_data = checkpoint is not None or readiness is not None
    checkpoint_provenance = summarize_checkpoint_provenance(checkpoint)
    active_proposal = (
        proposal.get("proposal")
        if proposal.get("relation") == "current"
        and (proposal.get("proposal") or {}).get("status") in _ACTIVE_PROPOSAL_STATUSES
        else None
    )
    briefing = {
        "frequency": get_briefing_frequency(db),
        "is_quiet_day": is_quiet_day(gate, active_proposal),
    }
    return {
        "snapshot_version": TODAY_SNAPSHOT_VERSION,
        "date": as_of,
        "state": state,
        "reason": reason,
        "primary_action": primary_action,
        "readiness": readiness,
        "readiness_source": "canonical_snapshot",
        "session": session,
        "device_sync_hint": _device_sync_hint(
            checkpoint, as_of, db.get_approved_recovery_replan_deliveries()
        ),
        "gate": gate,
        "briefing": briefing,
        "proposal": proposal,
        "forecast": forecast,
        "pending_proposal": active_proposal,
        "yesterday": yesterday,
        "feedback": feedback,
        "loop_outcome": loop_result.get("outcome"),
        "provenance": {
            "generated_at": generated_at,
            "as_of": as_of,
            "checkpoint": {
                "id": _checkpoint_id(checkpoint),
                "created_at": (checkpoint or {}).get("created_at"),
                "source": (checkpoint_provenance or {}).get("source"),
            },
            "readiness": {
                "source": "canonical_snapshot",
                "computed_at": snapshot.get("computed_at") if snapshot else None,
                "error": readiness_error,
            },
            "gate": {
                "decision_id": (loop_result.get("decision") or {}).get("id"),
                "fingerprint": (loop_result.get("decision") or {}).get("fingerprint"),
            },
            "forecast": {
                "prediction_id": (forecast.get("prediction") or {}).get("id"),
                "rule_version": (forecast.get("prediction") or {}).get("rule_version"),
            },
            "reconciliation": {
                "rule_version": yesterday.get("rule_version"),
                "base_checkpoint_id": yesterday.get("base_checkpoint_id"),
            },
            "feedback": {
                "rule_version": feedback.get("rule_version"),
                "status": feedback.get("status"),
            },
        },
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=as_of if has_data else None,
            stale_after_days=2,
        ),
    }


def _feedback_block(
    db: Database,
    *,
    yesterday: Mapping[str, Any],
    current_day: Mapping[str, Any],
    goal_plan: Mapping[str, Any] | None,
    forecast: Mapping[str, Any],
    now_utc: datetime,
    as_of: str,
) -> dict[str, Any]:
    prediction = forecast.get("prediction")
    forecasts = [dict(prediction)] if isinstance(prediction, Mapping) else []
    try:
        return feedback_from_today_evidence(
            db,
            yesterday=yesterday,
            current_day=current_day,
            goal_plan=goal_plan,
            forecasts=forecasts,
            now_utc=now_utc,
            as_of=as_of,
        )
    except Exception as exc:  # feedback must not take down the daily decision shell
        return {
            "status": "unavailable",
            "reason": str(exc),
            "rule_version": None,
            "prompts": [],
            "primary": None,
            "metrics": {},
        }


def _latest_checkpoint(db: Database) -> dict[str, Any] | None:
    try:
        checkpoint = db.get_latest_planning_checkpoint()
    except Exception:
        return None
    return checkpoint if isinstance(checkpoint, dict) and checkpoint.get("id") else None


def _checkpoint_id(checkpoint: Mapping[str, Any] | None) -> int | None:
    try:
        return int((checkpoint or {}).get("id"))
    except (TypeError, ValueError):
        return None


def _run_loop(db: Database, *, today: date | None = None) -> dict[str, Any]:
    try:
        return run_recovery_replan_loop(db, today=today)
    except Exception as exc:  # the daily shell must survive a contour outage
        return {
            "outcome": None,
            "decision": None,
            "proposal": None,
            "proposal_gap": None,
            "session_quality_forecast": None,
            "session_quality_forecast_error": None,
            "readiness_conflicts": {
                "data_gap": True,
                "reason": f"Контур недоступен: {exc}",
            },
        }


def _readiness_snapshot(db: Database) -> tuple[dict[str, Any], str | None]:
    try:
        value = build_readiness_snapshot(db)
    except Exception as exc:
        return {}, str(exc)
    return (dict(value), None) if isinstance(value, Mapping) else ({}, "invalid snapshot")


def _project_readiness(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(snapshot, Mapping) or snapshot.get("score") is None:
        return None
    return {
        "score": snapshot.get("score"),
        "status": snapshot.get("status"),
        "confidence": snapshot.get("confidence"),
        "computed_at": snapshot.get("computed_at"),
        "source_completeness": snapshot.get("source_completeness"),
        "drivers": list(snapshot.get("drivers") or []),
        "factors": list(snapshot.get("factors") or []),
        "missing_inputs": list(snapshot.get("missing_inputs") or []),
        "tsb": snapshot.get("tsb"),
        "stale": bool(snapshot.get("stale")),
        "reason": snapshot.get("reason"),
    }


def _resolve_state(
    *,
    checkpoint: Mapping[str, Any] | None,
    report: Mapping[str, Any],
    outcome: Any,
    proposal: Mapping[str, Any],
    readiness_error: str | None,
) -> tuple[str, str, dict[str, Any]]:
    report_reason = str(report.get("reason") or "")
    relation = str(proposal.get("relation") or "none")
    proposal_status = str((proposal.get("proposal") or {}).get("status") or "")

    if checkpoint is None:
        state = "no_plan"
        reason = _NO_PLAN_REASON
        action = "open_planning"
    elif report.get("data_gap") or readiness_error:
        state = "data_gap"
        reason = report_reason or (
            f"Снимок готовности недоступен: {readiness_error}"
            if readiness_error
            else "Недостаточно данных о восстановлении."
        )
        action = "sync_or_wait"
    elif relation == "current":
        state = "conflict_actionable"
        reason = report_reason or "Есть актуальное предложение по корректировке нагрузки."
        action = "review_proposal"
    elif outcome == "conflict":
        if relation == "resolved" and proposal_status in _HANDLED_PROPOSAL_STATUSES:
            state = "silence"
            reason = report_reason
            action = "follow_plan"
        else:
            state = "conflict_unactionable"
            reason = report_reason or "Конфликт обнаружен, но безопасного предложения нет."
            action = "inspect_evidence"
    else:
        state = "silence"
        reason = report_reason
        action = "follow_plan"
    return state, reason, {"kind": action, "enabled": True, "reason": reason}


def _project_gate(
    loop_result: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    decision = loop_result.get("decision") if isinstance(loop_result.get("decision"), Mapping) else {}
    return {
        "outcome": loop_result.get("outcome"),
        "reason": report.get("reason"),
        "data_gap": bool(report.get("data_gap")),
        "silence": bool(report.get("silence")),
        "conflicts": list(report.get("conflicts") or []),
        "sessions_evaluated": list(report.get("sessions_evaluated") or []),
        "readiness": report.get("readiness"),
        "proposal_gap": loop_result.get("proposal_gap"),
        "decision": {
            "id": decision.get("id"),
            "fingerprint": decision.get("fingerprint"),
            "plan_checkpoint_id": decision.get("plan_checkpoint_id"),
        },
        "forecast_error": loop_result.get("session_quality_forecast_error"),
    }


def _resolve_proposal(
    db: Database,
    loop_result: Mapping[str, Any],
    checkpoint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    active_checkpoint_id = _checkpoint_id(checkpoint)
    try:
        proposals = db.get_coach_proposals(days=36500, limit=500)
    except Exception as exc:
        return {
            "relation": "unavailable",
            "proposal": None,
            "base_checkpoint_id": None,
            "active_checkpoint_id": active_checkpoint_id,
            "reason": str(exc),
        }
    recovery = [
        item
        for item in proposals
        if isinstance(item, Mapping)
        and (item.get("action") == "recovery_replan" or item.get("source") == "recovery_replan")
    ]
    active = [item for item in recovery if item.get("status") in _ACTIVE_PROPOSAL_STATUSES]
    current = next(
        (
            item
            for item in active
            if _coerce_int((item.get("params") or {}).get("base_checkpoint_id"))
            == active_checkpoint_id
        ),
        None,
    )
    if current:
        return _proposal_block("current", current, active_checkpoint_id, "active checkpoint")

    stale = next(iter(active), None)
    loop_proposal = loop_result.get("proposal")
    if isinstance(loop_proposal, Mapping) and loop_proposal.get("status") not in _ACTIVE_PROPOSAL_STATUSES:
        return _proposal_block(
            "resolved",
            dict(loop_proposal),
            active_checkpoint_id,
            "proposal lifecycle is terminal",
        )
    if stale:
        return _proposal_block(
            "stale",
            stale,
            active_checkpoint_id,
            "proposal belongs to another planning checkpoint",
        )
    return {
        "relation": "none",
        "proposal": None,
        "base_checkpoint_id": None,
        "active_checkpoint_id": active_checkpoint_id,
        "reason": loop_result.get("proposal_gap") or "no proposal",
    }


def _proposal_block(
    relation: str,
    proposal: Mapping[str, Any],
    active_checkpoint_id: int | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "relation": relation,
        "proposal": dict(proposal),
        "base_checkpoint_id": _coerce_int((proposal.get("params") or {}).get("base_checkpoint_id")),
        "active_checkpoint_id": active_checkpoint_id,
        "reason": reason,
    }


def _resolve_forecast(
    db: Database,
    loop_result: Mapping[str, Any],
    checkpoint: Mapping[str, Any] | None,
    goal_plan: Mapping[str, Any] | None,
    as_of: str,
) -> dict[str, Any]:
    active_checkpoint_id = _checkpoint_id(checkpoint)
    try:
        anchor = date.fromisoformat(as_of)
    except ValueError:
        anchor = datetime.now().date()
    end = anchor + timedelta(days=_FORECAST_HORIZON_DAYS)
    try:
        rows = db.get_session_quality_predictions(days=36500, limit=1000)
    except Exception as exc:
        return _forecast_block(None, "unavailable", None, error=str(exc))
    relevant = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("status") == "pending"
        and _date_in_range(row.get("target_date"), anchor, end)
    ]
    current = [
        row for row in relevant if _coerce_int(row.get("plan_checkpoint_id")) == active_checkpoint_id
    ]
    pool = current or relevant
    prediction = min(pool, key=_forecast_sort_key) if pool else None
    if prediction is None:
        loop_prediction = (loop_result.get("session_quality_forecast") or {}).get("prediction")
        prediction = dict(loop_prediction) if isinstance(loop_prediction, Mapping) else None
    if prediction is None:
        return _forecast_block(
            None,
            "none",
            None,
            error=loop_result.get("session_quality_forecast_error"),
        )
    relation = (
        "current_checkpoint"
        if _coerce_int(prediction.get("plan_checkpoint_id")) == active_checkpoint_id
        else "stale_checkpoint"
    )
    session_id = _forecast_session_id(prediction, goal_plan) if relation == "current_checkpoint" else None
    return _forecast_block(
        dict(prediction),
        relation,
        session_id,
        error=loop_result.get("session_quality_forecast_error"),
    )


def _forecast_sort_key(row: Mapping[str, Any]) -> tuple[str, int, str, int]:
    """Nearest target first, latest immutable revision first within that target."""
    return (
        str(row.get("target_date") or "9999-12-31")[:10],
        -_timestamp_rank(row.get("created_at")),
        str(row.get("target_key") or ""),
        -int(row.get("id") or 0),
    )


def _timestamp_rank(value: Any) -> int:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _forecast_block(
    prediction: dict[str, Any] | None,
    relation: str,
    session_id: str | None,
    *,
    error: Any = None,
) -> dict[str, Any]:
    return {
        "mode": "shadow",
        "affects_decision": False,
        "relation": relation,
        "prediction": prediction,
        "session_id": session_id,
        "target_time_provenance": "date_only",
        "prestart_status": "unverified_date_only" if prediction else "not_applicable",
        "error": str(error) if error else None,
    }


def _forecast_session_id(
    prediction: Mapping[str, Any],
    goal_plan: Mapping[str, Any] | None,
) -> str | None:
    index = _coerce_int(prediction.get("plan_session_index"))
    templates = list((goal_plan or {}).get("session_templates") or [])
    if index is None or index < 0 or index >= len(templates):
        return None
    template = templates[index]
    return str(template.get("session_id") or "") or None if isinstance(template, Mapping) else None


def _date_in_range(value: Any, start: date, end: date) -> bool:
    try:
        candidate = date.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    return start <= candidate <= end


def _yesterday_reconciliation(
    db: Database,
    as_of: str,
    has_plan: bool,
) -> dict[str, Any]:
    try:
        anchor = date.fromisoformat(as_of)
    except ValueError:
        anchor = datetime.now().date()
    target = anchor - timedelta(days=1)
    empty = _empty_yesterday(target)
    if not has_plan:
        return empty
    try:
        payload = reconciliation_at(
            db,
            weeks=1,
            as_of=anchor,
            include_provider=False,
        )
    except Exception as exc:
        return {**empty, "status": "unavailable", "reason": str(exc)}
    if not payload.get("has_plan"):
        return empty
    target_text = target.isoformat()
    all_rows = [
        dict(row)
        for row in payload.get("rows") or []
        if isinstance(row, Mapping)
    ]
    rows = [row for row in all_rows if str(row.get("date") or "")[:10] == target_text]
    current_day_rows = [
        row for row in all_rows if str(row.get("date") or "")[:10] == anchor.isoformat()
    ]
    unplanned = [
        dict(row)
        for row in payload.get("unplanned_activities") or []
        if isinstance(row, Mapping) and str(row.get("date") or "")[:10] == target_text
    ]
    actual_rows = [
        dict(activity)
        for row in rows
        for activity in row.get("actual_activities") or []
        if isinstance(activity, Mapping)
    ]
    actual = actual_rows + unplanned
    adherence = {
        key: sum(1 for row in rows if row.get("adherence") == key)
        for key in ("exact", "substituted", "major_deviation", "unknown")
    }
    matched_actual_tss = round(sum(_float(row.get("actual_total_tss")) for row in rows), 1)
    unplanned_tss = round(sum(_float(row.get("tss")) for row in unplanned), 1)
    sports = sorted({_legacy_sport(row.get("sport")) for row in actual if row.get("sport")})
    return {
        "status": "available" if rows or actual else "empty",
        "reason": None,
        "date": target_text,
        "planned_sessions": len(rows),
        "matched_sessions": sum(1 for row in rows if row.get("match_status") == "matched"),
        "adherence": adherence,
        "planned_tss": round(sum(_float(row.get("tss")) for row in rows), 1),
        "matched_actual_tss": matched_actual_tss,
        "unplanned_tss": unplanned_tss,
        "total_actual_tss": round(matched_actual_tss + unplanned_tss, 1),
        "rows": rows,
        "current_day_rows": current_day_rows,
        "unplanned_activities": unplanned,
        "data_quality": payload.get("data_quality") or {},
        "rule_version": payload.get("rule_version"),
        "base_checkpoint_id": payload.get("base_checkpoint_id"),
        "activities": len(actual),
        "minutes": int(round(sum(_float(row.get("duration_minutes")) for row in actual))),
        "tss": int(round(matched_actual_tss + unplanned_tss)),
        "sports": sports,
    }


def _empty_yesterday(target: date) -> dict[str, Any]:
    return {
        "status": "empty",
        "reason": None,
        "date": target.isoformat(),
        "planned_sessions": 0,
        "matched_sessions": 0,
        "adherence": {"exact": 0, "substituted": 0, "major_deviation": 0, "unknown": 0},
        "planned_tss": 0.0,
        "matched_actual_tss": 0.0,
        "unplanned_tss": 0.0,
        "total_actual_tss": 0.0,
        "rows": [],
        "current_day_rows": [],
        "unplanned_activities": [],
        "data_quality": {},
        "rule_version": None,
        "base_checkpoint_id": None,
        "activities": 0,
        "minutes": 0,
        "tss": 0,
        "sports": [],
    }


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _legacy_sport(value: Any) -> str:
    normalized = str(value or "")
    return {"bike": "cycling", "run": "running", "swim": "swimming"}.get(
        normalized,
        normalized,
    )


def _day_session(
    report: Mapping[str, Any],
    goal_plan: Mapping[str, Any] | None = None,
    as_of: str = "",
) -> dict[str, Any] | None:
    for session in report.get("sessions_evaluated") or []:
        if not isinstance(session, Mapping):
            continue
        try:
            if int(session.get("days_until", -1)) != 0:
                continue
        except (TypeError, ValueError):
            continue
        session_date = str(session.get("date") or "")[:10]
        return _project_session(dict(session), _template_for_date(goal_plan, session_date))

    template = _template_for_date(goal_plan, as_of)
    if not template or str(template.get("session_role") or "") == "off":
        return None
    return _project_session(
        {
            "date": as_of,
            "role": template.get("session_role"),
            "tss": _planned_tss_for_date(goal_plan, as_of),
            "name": template.get("session_focus") or template.get("export_name"),
            "sport_label": template.get("sport_label") or template.get("sport"),
        },
        template,
    )


def _project_session(
    session: Mapping[str, Any],
    template: Mapping[str, Any],
) -> dict[str, Any]:
    role = str(session.get("role") or template.get("session_role") or "")
    session_date = str(session.get("date") or template.get("date") or "")[:10]
    from models.training_planner import iter_leaf_sessions

    return {
        "session_id": template.get("session_id"),
        # Issue #205 milestone 2.6: every executable leaf session of the day, in
        # order, brick legs listed separately; a rest/race day yields none.
        "sessions": iter_leaf_sessions(template),
        "date": session_date,
        "name": str(
            template.get("template_name")
            or template.get("export_name")
            or session.get("name")
            or "Сессия"
        ),
        "role": role,
        "role_label": ROLE_LABELS_RU.get(role, role),
        "tss": int(round(_float(session.get("tss")))),
        "duration_minutes": template.get("duration_minutes"),
        "phase": template.get("phase") or session.get("phase"),
        "sport_label": str(
            session.get("sport_label")
            or template.get("sport_label")
            or template.get("sport")
            or ""
        ),
        "is_key": role in _KEY_ROLES,
        "kind": str(template.get("kind") or "single"),
        "catalog_version": template.get("catalog_version"),
        "template_key": template.get("template_key"),
        "template_version": template.get("template_version"),
        "template_name": template.get("template_name"),
        "stimulus": template.get("stimulus"),
        "fatigue_cost": list(template.get("fatigue_cost") or []),
        "expected_recovery_hours": template.get("expected_recovery_hours"),
        "materialization_status": template.get("materialization_status"),
        "target_provenance": template.get("target_provenance"),
        "transition_minutes": template.get("transition_minutes"),
        "steps": _compact_steps(template.get("materialized_steps")),
        "legs": [
            {
                "leg_index": leg.get("leg_index"),
                "leg_id": leg.get("leg_id"),
                "sport": leg.get("sport"),
                "template_name": leg.get("template_name"),
                "duration_minutes": leg.get("duration_minutes"),
                "target_tss": leg.get("target_tss"),
                "target_provenance": leg.get("target_provenance"),
                "steps": _compact_steps(leg.get("materialized_steps")),
            }
            for leg in list(template.get("legs") or [])
            if isinstance(leg, Mapping)
        ],
    }


def _planned_tss_for_date(
    goal_plan: Mapping[str, Any] | None,
    session_date: str,
) -> float:
    for row in list((goal_plan or {}).get("daily_plan") or []):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        if str(row[0])[:10] == session_date:
            return _float(row[1])
    return 0.0


def _template_for_date(
    goal_plan: Mapping[str, Any] | None,
    session_date: str,
) -> dict[str, Any]:
    for template in list((goal_plan or {}).get("session_templates") or []):
        if isinstance(template, Mapping) and str(template.get("date") or "")[:10] == session_date:
            return dict(template)
    return {}


def _compact_steps(value: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": step.get("name"),
            "intensity": step.get("intensity"),
            "segment_kind": step.get("segment_kind"),
            "duration_seconds": step.get("duration_seconds"),
            "target": step.get("target"),
        }
        for step in list(value or [])
        if isinstance(step, Mapping)
    ]


__all__ = ["TODAY_SNAPSHOT_VERSION", "build_today_decision_snapshot"]
