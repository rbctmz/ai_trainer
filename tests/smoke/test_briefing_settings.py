"""Behavior contract for issue #235: briefing frequency setting.

The athlete can choose between the full daily briefing on /today ("daily",
current behavior, default) and a compact rendering on days the salience gate
has nothing to say ("conflicts_only"). Persisted in the existing generic
key/value table (data/database.py::get_user_setting / set_user_setting)
under key "briefing_frequency" — no new table.

GET /api/today gains a `briefing={frequency, is_quiet_day}` field.
`is_quiet_day` is computed straight off the payload's own already-collected
`gate` + `pending_proposal` (api/briefing_settings.py::is_quiet_day) — no
new queries — and is deliberately conservative: gate outcome silence/no
data AND no pending proposal AND no open conflict. Any doubt keeps the
full brief (a false "not quiet" is cheap; a hidden conflict is not).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint

pytestmark = pytest.mark.smoke


def _goal_plan(today: date, *, target_role: str = "easy") -> dict:
    monday = today - timedelta(days=today.weekday())
    daily_plan = []
    templates = []
    for index in range(7):
        session_date = monday + timedelta(days=index)
        is_target = session_date == today
        role = target_role if is_target else "easy"
        sport = "bike" if is_target else "run"
        total_tss = 60.0 if is_target else 20.0
        daily_plan.append(
            (datetime.combine(session_date, datetime.min.time()), total_tss, {sport: total_tss})
        )
        templates.append(
            {
                "date": session_date.isoformat(),
                "week_index": 0,
                "day_index": index,
                "phase": "Build",
                "session_role": role,
                "session_focus": "Качество • вело" if is_target else "Лёгкая • бег",
                "sport": sport,
                "sport_label": "вело" if is_target else "бег",
                "duration_minutes": 60 if is_target else 30,
                "export_name": "Quality bike" if is_target else "Easy run",
            }
        )
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "event_date": (today + timedelta(days=70)).isoformat(),
        "weeks_to_race": 10,
        "start_week": monday,
        "weekly_tss_plan": [int(sum(row[1] for row in daily_plan))],
        "base_weekly_tss_plan": [int(sum(row[1] for row in daily_plan))],
        "phases": ["Build"],
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": [
            {
                "week_start": monday,
                "phase": "Build",
                "weekly_tss": int(sum(row[1] for row in daily_plan)),
                "capacity_tss": 250,
                "adjustment_note": "—",
            }
        ],
        "constraint_summary": {
            "current_tsb": -10.0,
            "load_state": "stable",
            "load_state_label": "Стабильно",
            "notes": [],
        },
        "near_term_edit_version": 0,
        "near_term_edit_rollback_target_checkpoint_id": None,
    }


def _session(today: date, *, role: str, tss: float = 20.0) -> dict:
    return {
        "date": today.isoformat(),
        "days_until": 0,
        "role": role,
        "tss": tss,
        "name": "Качество • вело" if role == "quality" else "Лёгкая • бег",
        "sport_label": "вело" if role == "quality" else "бег",
        "phase": "Build",
    }


def _conflict_for(session: dict) -> dict:
    return {
        "date": session["date"],
        "days_until": session["days_until"],
        "severity": "high",
        "kind": f"low_readiness_{session['role']}_session",
        "session": {
            "name": session["name"],
            "role": session["role"],
            "tss": session["tss"],
            "sport_label": session["sport_label"],
        },
        "evidence": ["Готовность 35/100 (low)"],
    }


def _report(
    today: date,
    *,
    sessions: list[dict] | None = None,
    conflicts: list[dict] | None = None,
) -> dict:
    sessions = sessions or []
    conflicts = conflicts or []
    return {
        "as_of": today.isoformat(),
        "horizon_days": 4,
        "readiness": {"score": 72.0, "status": "ready", "confidence": 0.8},
        "sessions_evaluated": sessions,
        "conflicts": conflicts,
        "silence": not conflicts,
        "data_gap": False,
        "reason": "Конфликт." if conflicts else "План и состояние согласны.",
    }


def _snapshot(*, score: float = 72.0, status: str = "ready") -> dict:
    return {
        "score": score,
        "status": status,
        "computed_at": None,
        "is_provisional": False,
        "source_completeness": 1.0,
        "factors": [{"key": "hrv", "label": "HRV", "evidence": "HRV 41"}],
        "missing_inputs": [],
        "stale": False,
        "reason": "ok",
        "drivers": [{"key": "hrv", "evidence": "HRV 41"}],
        "tsb": {"ctl": 18.7, "atl": 36.2, "tsb": -17.5, "window_days": 90},
        "confidence": 0.8,
    }


def _patch_report(monkeypatch, report: dict) -> None:
    from api import recovery_replan_loop as loop_module

    monkeypatch.setattr(loop_module, "build_readiness_conflict_report", lambda _db: report)


def _patch_snapshot(monkeypatch, snapshot: dict) -> None:
    from api import today_snapshot as today_module

    monkeypatch.setattr(today_module, "build_readiness_snapshot", lambda _db: snapshot)


def test_briefing_defaults_to_daily_and_marks_a_silent_day_quiet(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "quiet-default.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    day_session = _session(today, role="easy")
    _patch_report(monkeypatch, _report(today, sessions=[day_session]))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["state"] == "silence"
    assert payload["briefing"] == {"frequency": "daily", "is_quiet_day": True}


def test_briefing_frequency_setting_persists_and_reflects_in_today(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "quiet-conflicts-only.db"))
    db.set_user_setting("briefing_frequency", "conflicts_only")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="easy")))
    day_session = _session(today, role="easy")
    _patch_report(monkeypatch, _report(today, sessions=[day_session]))
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["briefing"]["frequency"] == "conflicts_only"
    assert payload["briefing"]["is_quiet_day"] is True


def test_briefing_is_never_quiet_on_a_conflict_day(tmp_path, monkeypatch) -> None:
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "quiet-conflict.db"))
    db.set_user_setting("briefing_frequency", "conflicts_only")
    db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today, target_role="quality")))
    day_session = _session(today, role="quality", tss=60.0)
    report = _report(today, sessions=[day_session], conflicts=[_conflict_for(day_session)])
    _patch_report(monkeypatch, report)
    _patch_snapshot(monkeypatch, _snapshot(score=35.0, status="low"))

    payload = today_view(db=db)

    assert payload["state"] == "conflict_actionable"
    assert payload["pending_proposal"] is not None
    assert payload["briefing"]["is_quiet_day"] is False


def test_briefing_is_never_quiet_while_a_pending_proposal_survives_a_later_silent_loop(
    tmp_path, monkeypatch
) -> None:
    """Mirrors test_today_keeps_current_pending_proposal_visible_when_latest_loop_is_silent
    in tests/smoke/test_api_today.py: the gate itself now looks silent, but an
    unresolved proposal from an earlier conflict is still pending — the day
    must not read as quiet."""
    from api import today_snapshot as snapshot_module
    from api.routers.today import today_view

    today = date(2026, 7, 10)
    db = Database(str(tmp_path / "quiet-pending-proposal.db"))
    db.set_user_setting("briefing_frequency", "conflicts_only")
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_goal_plan(today)))
    db.save_coach_proposal(
        action="recovery_replan",
        params={"base_checkpoint_id": checkpoint["id"]},
        preview={"reason": "earlier conflict"},
        source="recovery_replan",
        source_key="earlier-conflict",
        active_key="same-session",
    )
    report = _report(today)
    monkeypatch.setattr(
        snapshot_module,
        "_run_loop",
        lambda _db, **_kwargs: {
            "outcome": "silence",
            "decision": {"id": 1, "fingerprint": "later-silence"},
            "proposal": None,
            "readiness_conflicts": report,
        },
    )
    _patch_snapshot(monkeypatch, _snapshot())

    payload = today_view(db=db)

    assert payload["state"] == "conflict_actionable"
    assert payload["pending_proposal"] is not None
    assert payload["briefing"]["is_quiet_day"] is False


def test_briefing_settings_get_defaults_to_daily(tmp_path) -> None:
    from api.routers.settings import get_briefing_settings

    db = Database(str(tmp_path / "settings-default.db"))

    response = get_briefing_settings(db=db)

    assert response.frequency == "daily"


def test_briefing_settings_put_updates_and_persists(tmp_path) -> None:
    from api.routers.settings import (
        BriefingFrequencyRequest,
        get_briefing_settings,
        put_briefing_settings,
    )

    db = Database(str(tmp_path / "settings-put.db"))

    put_response = put_briefing_settings(BriefingFrequencyRequest(frequency="conflicts_only"), db=db)
    get_response = get_briefing_settings(db=db)

    assert put_response.frequency == "conflicts_only"
    assert get_response.frequency == "conflicts_only"
    assert db.get_user_setting("briefing_frequency") == "conflicts_only"


def test_briefing_settings_rejects_invalid_frequency_and_body_is_never_constructed(tmp_path) -> None:
    """FastAPI validates the request body against this exact pydantic model
    before the handler runs, so an invalid value 422s without ever reaching
    (or mutating) the database — proven here by the model refusing to
    construct at all."""
    from api.routers.settings import BriefingFrequencyRequest

    with pytest.raises(ValidationError):
        BriefingFrequencyRequest(frequency="hourly")


def test_briefing_settings_put_rejecting_invalid_value_leaves_stored_setting_unchanged(
    tmp_path,
) -> None:
    from api.routers.settings import (
        BriefingFrequencyRequest,
        get_briefing_settings,
        put_briefing_settings,
    )

    db = Database(str(tmp_path / "settings-reject.db"))
    put_briefing_settings(BriefingFrequencyRequest(frequency="conflicts_only"), db=db)

    with pytest.raises(ValidationError):
        BriefingFrequencyRequest(frequency="hourly")

    assert get_briefing_settings(db=db).frequency == "conflicts_only"


def test_briefing_settings_demo_and_real_databases_stay_isolated(tmp_path) -> None:
    from api.routers.settings import (
        BriefingFrequencyRequest,
        get_briefing_settings,
        put_briefing_settings,
    )

    real_db = Database(str(tmp_path / "real.db"))
    demo_db = Database(str(tmp_path / "demo.db"))

    put_briefing_settings(BriefingFrequencyRequest(frequency="conflicts_only"), db=demo_db)

    assert get_briefing_settings(db=demo_db).frequency == "conflicts_only"
    assert get_briefing_settings(db=real_db).frequency == "daily"


def test_briefing_settings_routes_are_wired_into_app() -> None:
    from api.main import app

    assert app.url_path_for("get_briefing_settings") == "/api/settings/briefing"
    assert app.url_path_for("put_briefing_settings") == "/api/settings/briefing"
