"""Экран «Сегодня»: утренний payload агентного контура (issue #158).

Чистая композиция существующих контрактов, без новой бизнес-логики:
RecoveryReplanLoop (вердикт gate + журнал + актуальное предложение, #154/#156),
канонический readiness snapshot (api/readiness_snapshot.py — единственный
источник числа готовности для всех поверхностей, уроки #134/#152), сессия дня
из gate-отчёта и one-liner факта за вчера.

Осознанный write-on-read: GET вызывает run_recovery_replan_loop, потому что
утренний экран обязан быть самодостаточным (контур должен отработать до
первого сообщения коучу). Вызов идемпотентен по построению: fingerprint-дедуп
решений и active_key-дедуп предложений. Подробности: docs/today_screen_execplan.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends

from api.deps import get_database
from api.operational_state import build_operational_state
from api.readiness_snapshot import build_readiness_snapshot
from api.recovery_replan_loop import run_recovery_replan_loop
from data.database import Database
from models.readiness_conflicts import ROLE_LABELS_RU

router = APIRouter(prefix="/api/today", tags=["today"])

_KEY_ROLES = {"quality", "long"}
_ACTIVE_PROPOSAL_STATUSES = {"pending", "applying"}

_NO_PLAN_REASON = (
    "Нет активного плана — контуру не с чем сверять готовность. "
    "Построй план, и экран оживёт."
)


@router.get("")
def today_view(
    demo: bool = False,
    db: Database = Depends(get_database),
) -> dict[str, Any]:
    checkpoint = _latest_checkpoint(db)
    loop_result = _run_loop(db)
    report = loop_result.get("readiness_conflicts") or {}
    snapshot = build_readiness_snapshot(db)

    as_of = str(report.get("as_of") or datetime.now().date().isoformat())[:10]
    readiness = _project_readiness(snapshot)
    session = _day_session(report)
    proposal = _active_proposal(loop_result)
    outcome = loop_result.get("outcome")

    if checkpoint is None:
        state = "no_plan"
        reason = _NO_PLAN_REASON
    elif report.get("data_gap"):
        state = "data_gap"
        reason = str(report.get("reason") or "Недостаточно данных о восстановлении.")
    elif outcome == "conflict" and proposal is not None:
        state = "conflict"
        reason = str(report.get("reason") or "")
    else:
        state = "silence"
        reason = str(report.get("reason") or "")

    has_data = checkpoint is not None or readiness is not None
    return {
        "date": as_of,
        "state": state,
        "reason": reason,
        "readiness": readiness,
        "readiness_source": "canonical_snapshot",
        "session": session,
        "pending_proposal": proposal,
        "yesterday": _yesterday_summary(db),
        "loop_outcome": outcome,
        "operational_state": build_operational_state(
            db,
            demo=demo,
            has_data=has_data,
            latest_data_at=as_of if has_data else None,
            stale_after_days=2,
        ),
    }


def _latest_checkpoint(db: Database) -> dict[str, Any] | None:
    try:
        checkpoint = db.get_latest_planning_checkpoint()
    except Exception:
        return None
    return checkpoint if isinstance(checkpoint, dict) and checkpoint.get("id") else None


def _run_loop(db: Database) -> dict[str, Any]:
    try:
        return run_recovery_replan_loop(db)
    except Exception as exc:  # деградация, как в соседних роутерах: экран живёт
        return {
            "outcome": None,
            "decision": None,
            "proposal": None,
            "readiness_conflicts": {
                "data_gap": True,
                "reason": f"Контур недоступен: {exc}",
            },
        }


def _project_readiness(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or snapshot.get("score") is None:
        return None
    return {
        "score": snapshot.get("score"),
        "status": snapshot.get("status"),
        "confidence": snapshot.get("confidence"),
        "drivers": list(snapshot.get("drivers") or []),
        "factors": list(snapshot.get("factors") or []),
        "tsb": snapshot.get("tsb"),
        "stale": bool(snapshot.get("stale")),
        "reason": snapshot.get("reason"),
    }


def _day_session(report: dict[str, Any]) -> dict[str, Any] | None:
    for session in report.get("sessions_evaluated") or []:
        if not isinstance(session, dict):
            continue
        try:
            if int(session.get("days_until", -1)) != 0:
                continue
        except (TypeError, ValueError):
            continue
        role = str(session.get("role") or "")
        return {
            "date": str(session.get("date") or "")[:10],
            "name": str(session.get("name") or "Сессия"),
            "role": role,
            "role_label": ROLE_LABELS_RU.get(role, role),
            "tss": int(round(float(session.get("tss") or 0.0))),
            "sport_label": str(session.get("sport_label") or ""),
            "is_key": role in _KEY_ROLES,
        }
    return None


def _active_proposal(loop_result: dict[str, Any]) -> dict[str, Any] | None:
    proposal = loop_result.get("proposal")
    if not isinstance(proposal, dict):
        return None
    if proposal.get("status") not in _ACTIVE_PROPOSAL_STATUSES:
        return None
    return proposal


def _yesterday_summary(db: Database) -> dict[str, Any] | None:
    try:
        df = db.get_activities(3)
    except Exception:
        return None
    if df is None or getattr(df, "empty", True) or "date" not in df.columns:
        return None
    yesterday = datetime.now().date() - timedelta(days=1)
    rows = df[df["date"].dt.date == yesterday]
    if rows.empty:
        return None
    minutes = float(rows.get("duration_minutes", 0).fillna(0).sum()) if "duration_minutes" in rows else 0.0
    tss = float(rows.get("tss", 0).fillna(0).sum()) if "tss" in rows else 0.0
    sports = sorted(
        {str(value) for value in rows.get("sport", []).dropna().tolist()}
        if "sport" in rows
        else set()
    )
    return {
        "activities": int(len(rows)),
        "minutes": int(round(minutes)),
        "tss": int(round(tss)),
        "sports": sports,
    }
