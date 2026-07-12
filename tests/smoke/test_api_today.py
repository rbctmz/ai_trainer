"""Behavior contract for issue #158: GET /api/today — экран «Сегодня».

Специфицирует композицию канонического readiness snapshot, salience-gate
(RecoveryReplanLoop) и активного плана в один утренний payload с каскадом
состояний no_plan → data_gap → conflict → silence. Contributor-safe:
временный SQLite, отчёт gate и snapshot подменяются monkeypatch там, где
нужен управляемый исход (тот же паттерн, что tests/smoke/test_recovery_replan_loop.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint


def _goal_plan(today: date, *, target_days_until: int = 0, target_role: str = "quality") -> dict:
    monday = today - timedelta(days=today.weekday())
    target_date = today + timedelta(days=target_days_until)
    daily_plan = []
    templates = []
    for index in range(21):
        session_date = monday + timedelta(days=index)
        is_target = session_date == target_date
        role = target_role if is_target else ("off" if index % 7 == 0 else "easy")
        sport = "bike" if is_target else ("off" if role == "off" else "run")
        total_tss = 60.0 if is_target else (0.0 if role == "off" else 20.0)
        parts = {} if role == "off" else {sport: total_tss}
        daily_plan.append(
            (datetime.combine(session_date, datetime.min.time()), total_tss, parts)
        )
        templates.append(
            {
                "date": session_date.isoformat(),
                "week_index": index // 7,
                "day_index": index % 7,
                "phase": "Build",
                "session_role": role,
                "session_focus": "Качество • вело" if is_target else "Лёгкая • бег",
                "sport": sport,
                "sport_label": "вело" if is_target else "бег",
                "duration_minutes": 60 if is_target else 30,
                "export_name": "Quality bike" if is_target else "Easy run",
            }
        )

    weekly_summary = []
    for week_index in range(3):
        start = week_index * 7
        weekly_summary.append(
            {
                "week_start": monday + timedelta(days=start),
                "phase": "Build",
                "weekly_tss": int(sum(row[1] for row in daily_plan[start : start + 7])),
                "capacity_tss": 250,
                "adjustment_note": "—",
            }
        )

    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": (today + timedelta(days=70)).isoformat(),
        "weeks_to_race": 10,
        "start_week": monday,
        "weekly_tss_plan": [row["weekly_tss"] for row in weekly_summary],
        "base_weekly_tss_plan": [row["weekly_tss"] for row in weekly_summary],
        "phases": ["Build", "Build", "Build"],
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "current_tsb": -18.0,
            "load_state": "fatigued",
            "load_state_label": "Накопленная усталость",
            "notes": [],
        },
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


def _session(today: date, *, days_until: int, role: str, tss: float = 20.0) -> dict:
    session_date = today + timedelta(days=days_until)
    return {
        "date": session_date.isoformat(),
        "days_until": days_until,
        "role": role,
        "tss": tss,
        "name": "Качество • вело" if role == "quality" else "Лёгкая • бег",
        "sport_label": "вело" if role == "quality" else "бег",
        "phase": "Build",
    }


def _report(
    today: date,
    *,
    sessions: list[dict] | None = None,
    conflicts: list[dict] | None = None,
    data_gap: bool = False,
    score: float | None = 72.0,
    status: str = "ready",
) -> dict:
    sessions = sessions or []
    conflicts = conflicts or []
    return {
        "as_of": today.isoformat(),
        "horizon_days": 4,
        "base_horizon_days": 3,
        "lookahead_policy": "base_plus_nearest_quality",
        "horizon_extended_for_quality": False,
        "quality_lookahead_session": None,
        "readiness": {
            "score": None if data_gap else score,
            "status": "unknown" if data_gap else status,
            "confidence": 0.0 if data_gap else 0.8,
        },
        "sessions_evaluated": sessions,
        "conflicts": conflicts,
        "silence": not conflicts,
        "data_gap": data_gap,
        "reason": "Недостаточно данных." if data_gap else (
            "Готовность low расходится с планом." if conflicts else "План и состояние согласны."
        ),
    }


def _conflict_for(session: dict, *, status: str = "low", severity: str = "high") -> dict:
    return {
        "date": session["date"],
        "days_until": session["days_until"],
        "severity": severity,
        "kind": f"{status}_readiness_{session['role']}_session",
        "session": {
            "name": session["name"],
            "role": session["role"],
            "tss": session["tss"],
            "sport_label": session["sport_label"],
        },
        "evidence": [
            "Готовность 35/100 (low): HRV -18% к базе",
            "Сегодня: Качество • вело, 60 TSS",
        ],
    }


def _snapshot(*, score: float | None = 72.0, status: str = "ready") -> dict:
    return {
        "score": score,
        "status": status if score is not None else "unknown",
        "computed_at": None,
        "is_provisional": False,
        "source_completeness": 1.0,
        "factors": [
            {"key": "hrv", "label": "HRV", "evidence": "HRV 41 (+17% к базе)"},
        ],
        "missing_inputs": [],
        "stale": False,
        "reason": "Readiness рассчитан по полному набору основных recovery-сигналов.",
        "drivers": [{"key": "hrv", "evidence": "HRV 41 (+17% к базе)"}],
        "tsb": {"ctl": 18.7, "atl": 36.2, "tsb": -17.5, "window_days": 90},
        "confidence": 0.8,
    }


def _patch_report(monkeypatch, report: dict) -> None:
    from api import recovery_replan_loop as loop_module

    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)


def _patch_snapshot(monkeypatch, snapshot: dict) -> None:
    from api.routers import today as today_module

    monkeypatch.setattr(today_module, "build_readiness_snapshot", lambda _db: snapshot)


def test_today_empty_db_is_no_plan(tmp_path) -> None:
    from api.routers.today import today_view

    db = Database(str(tmp_path / "empty.db"))
    payload = today_view(db=db)

    assert payload["state"] == "no_plan"
    assert payload["pending_proposal"] is None
    assert payload["session"] is None
    assert payload["reason"]
    assert payload["readiness_source"] == "canonical_snapshot"
    assert payload["operational_state"]["status"] == "empty"


def test_today_data_gap_names_reason_without_proposal(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "gap.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    _patch_report(monkeypatch, _report(today, data_gap=True))
    _patch_snapshot(monkeypatch, _snapshot(score=None))

    payload = today_view(db=db)

    assert payload["state"] == "data_gap"
    assert "Недостаточно" in payload["reason"]
    assert payload["pending_proposal"] is None
    assert payload["readiness"] is None


def test_today_silence_projects_day_session_and_canonical_readiness(
    tmp_path, monkeypatch
) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "silence.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    day_session = _session(today, days_until=0, role="easy")
    _patch_report(monkeypatch, _report(today, sessions=[day_session]))
    _patch_snapshot(monkeypatch, _snapshot(score=72.0))

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["date"] == today.isoformat()
    assert payload["session"]["role"] == "easy"
    assert payload["session"]["role_label"] == "лёгкая"
    assert payload["session"]["is_key"] is False
    assert payload["readiness"]["score"] == 72.0
    assert payload["readiness"]["drivers"], "evidence-раскрытие требует drivers"
    assert payload["readiness_source"] == "canonical_snapshot"
    assert payload["pending_proposal"] is None
    assert payload["loop_outcome"] == "silence"


def test_today_conflict_exposes_pending_proposal_idempotently(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "conflict.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(
        today,
        sessions=[day_session],
        conflicts=[_conflict_for(day_session)],
        score=35.0,
        status="low",
    )
    _patch_report(monkeypatch, report)
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    first = today_view(db=db)
    second = today_view(db=db)

    assert first["state"] == "conflict"
    assert first["session"]["is_key"] is True
    assert first["pending_proposal"] is not None
    assert first["pending_proposal"]["action"] == "recovery_replan"
    assert first["pending_proposal"]["status"] == "pending"
    assert second["pending_proposal"]["id"] == first["pending_proposal"]["id"]
    assert len(db.get_coach_proposals(days=36500)) == 1


def test_today_resolved_conflict_returns_to_silence(tmp_path, monkeypatch) -> None:
    """Решение принято сегодня → экран не возвращает пользователя в тревогу."""
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "resolved.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    day_session = _session(today, days_until=0, role="quality", tss=60.0)
    report = _report(
        today,
        sessions=[day_session],
        conflicts=[_conflict_for(day_session)],
        score=35.0,
        status="low",
    )
    _patch_report(monkeypatch, report)
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    first = today_view(db=db)
    db.update_coach_proposal_status(
        first["pending_proposal"]["id"], "rejected", result={"message": "rejected by user"}
    )

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["loop_outcome"] == "conflict"
    assert payload["pending_proposal"] is None


def test_today_summarizes_yesterday_fact(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = datetime.now().date()
    yesterday = (today - timedelta(days=1)).isoformat()
    db = Database(str(tmp_path / "yesterday.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    db.save_activities(
        [
            {
                "activity_id": "y1",
                "date": yesterday,
                "sport": "cycling",
                "duration_minutes": 37,
                "distance_km": 15.0,
                "tss": 21.0,
            },
            {
                "activity_id": "y2",
                "date": yesterday,
                "sport": "cycling",
                "duration_minutes": 39,
                "distance_km": 16.0,
                "tss": 16.0,
            },
        ]
    )
    _patch_report(monkeypatch, _report(today))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["yesterday"]["activities"] == 2
    assert payload["yesterday"]["minutes"] == 76
    assert payload["yesterday"]["tss"] == 37
    assert payload["yesterday"]["sports"] == ["cycling"]


def test_today_route_is_wired_into_app() -> None:
    """FastAPI этой версии включает роутеры лениво (_IncludedRouter без .path),
    поэтому проверяем резолвинг по имени эндпоинта."""
    from api.main import app

    assert app.url_path_for("today_view") == "/api/today"
