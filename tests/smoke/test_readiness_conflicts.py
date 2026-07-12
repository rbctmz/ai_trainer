"""Smoke: salience-gate конфликтов «готовность × плановая сессия» (issue #141).

ExecPlan: docs/readiness_conflict_gate_execplan.md.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.readiness_conflicts import (
    DEFAULT_HORIZON_DAYS,
    MAX_QUALITY_LOOKAHEAD_DAYS,
    MIN_CONFIDENCE,
    detect_readiness_conflicts,
    resolve_effective_horizon,
    upcoming_plan_sessions,
)


pytestmark = pytest.mark.smoke

TODAY = date(2026, 7, 9)


def _readiness(score: float | None, status: str, confidence: float = 1.0) -> dict:
    return {
        "score": score,
        "status": status,
        "confidence": confidence,
        "drivers": [
            {"key": "hrv", "label": "HRV", "score": 40.0, "evidence": "HRV 30.0 мс против базовых 37.0 (−18.9%)"}
        ],
        "as_of_date": TODAY.isoformat(),
    }


def _session(days_until: int, role: str, tss: float = 25.0, name: str = "Сессия") -> dict:
    return {
        "date": (TODAY + timedelta(days=days_until)).isoformat(),
        "days_until": days_until,
        "role": role,
        "tss": tss,
        "name": name,
        "sport_label": "вело",
        "phase": "Base",
    }


# ---------------------------------------------------------------------------
# Матрица severity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("status", "role", "expected_severity"),
    [
        ("low", "quality", "high"),
        ("low", "long", "high"),
        ("low", "easy", "medium"),
        ("limited", "quality", "medium"),
        ("limited", "long", "medium"),
    ],
)
def test_matrix_conflicts(status: str, role: str, expected_severity: str) -> None:
    report = detect_readiness_conflicts(
        _readiness(35.0 if status == "low" else 50.0, status),
        [_session(1, role, tss=29.0, name="Качество • вело")],
        today=TODAY,
    )

    assert report["silence"] is False
    assert len(report["conflicts"]) == 1
    conflict = report["conflicts"][0]
    assert conflict["severity"] == expected_severity
    assert conflict["days_until"] == 1
    assert conflict["kind"] == f"{status}_readiness_{role}_session"


@pytest.mark.parametrize(
    ("status", "role"),
    [
        ("ready", "quality"),
        ("strong", "quality"),
        ("strong", "long"),
        ("limited", "easy"),
        ("low", "recovery"),
        ("ready", "easy"),
    ],
)
def test_matrix_silence(status: str, role: str) -> None:
    report = detect_readiness_conflicts(
        _readiness(80.0 if status == "strong" else 65.0 if status == "ready" else 50.0 if status == "limited" else 35.0, status),
        [_session(1, role)],
        today=TODAY,
    )

    assert report["conflicts"] == []
    assert report["silence"] is True
    assert report["data_gap"] is False
    assert report["reason"]


# ---------------------------------------------------------------------------
# Гейт данных и горизонт
# ---------------------------------------------------------------------------

def test_low_confidence_gives_data_gap_silence() -> None:
    report = detect_readiness_conflicts(
        _readiness(35.0, "low", confidence=MIN_CONFIDENCE - 0.1),
        [_session(1, "quality")],
        today=TODAY,
    )

    assert report["silence"] is True
    assert report["data_gap"] is True
    assert report["conflicts"] == []


def test_unknown_readiness_gives_data_gap_silence() -> None:
    report = detect_readiness_conflicts(
        _readiness(None, "unknown", confidence=0.0),
        [_session(0, "quality")],
        today=TODAY,
    )

    assert report["silence"] is True
    assert report["data_gap"] is True


def test_sessions_beyond_horizon_are_not_evaluated() -> None:
    report = detect_readiness_conflicts(
        _readiness(35.0, "low"),
        [_session(5, "quality")],
        today=TODAY,
        horizon_days=3,
    )

    assert report["conflicts"] == []
    assert report["silence"] is True
    assert report["sessions_evaluated"] == []


def test_today_session_is_in_horizon() -> None:
    report = detect_readiness_conflicts(
        _readiness(35.0, "low"),
        [_session(0, "quality", name="Качество • вело")],
        today=TODAY,
    )

    assert len(report["conflicts"]) == 1
    assert report["conflicts"][0]["days_until"] == 0


def test_conflict_evidence_carries_numbers_and_session_facts() -> None:
    report = detect_readiness_conflicts(
        _readiness(35.0, "low"),
        [_session(1, "quality", tss=29.0, name="Качество • вело")],
        today=TODAY,
    )

    evidence = " | ".join(report["conflicts"][0]["evidence"])
    assert "35" in evidence  # readiness score
    assert "Качество • вело" in evidence
    assert "29" in evidence  # session TSS
    assert "HRV" in evidence  # драйвер готовности


# ---------------------------------------------------------------------------
# upcoming_plan_sessions
# ---------------------------------------------------------------------------

def _goal_plan_for_sessions() -> dict:
    days = []
    templates = []
    specs = [
        (0, 8.0, "easy", "Легкая • бег"),
        (1, 0.0, "recovery", "Отдых"),          # день отдыха: TSS 0 — пропускается
        (2, 29.0, "quality", "Качество • вело"),
        (5, 20.0, "long", "Длительная • вело"),  # за горизонтом 3
    ]
    for offset, tss, role, focus in specs:
        dt = datetime.combine(TODAY + timedelta(days=offset), datetime.min.time())
        days.append((dt, tss, {"bike": tss}))
        templates.append(
            {
                "date": (TODAY + timedelta(days=offset)).isoformat(),
                "session_role": role,
                "session_focus": focus,
                "sport_label": "вело",
                "phase": "Base",
                "export_name": f"Триатлон — {focus}",
            }
        )
    return {"daily_plan": days, "session_templates": templates}


def test_upcoming_plan_sessions_respects_horizon_and_skips_rest() -> None:
    sessions = upcoming_plan_sessions(_goal_plan_for_sessions(), today=TODAY, horizon_days=3)

    assert [s["days_until"] for s in sessions] == [0, 2]
    assert sessions[0]["role"] == "easy"
    assert sessions[1]["role"] == "quality"
    assert sessions[1]["tss"] == 29
    assert "Качество" in sessions[1]["name"]


def test_upcoming_plan_sessions_unknown_role_falls_back_to_easy() -> None:
    plan = _goal_plan_for_sessions()
    plan["session_templates"][0]["session_role"] = "mystery"
    sessions = upcoming_plan_sessions(plan, today=TODAY, horizon_days=1)

    assert sessions[0]["role"] == "easy"


def _goal_plan_with_key_session(
    days_until: int,
    role: str = "quality",
    *,
    today: date = TODAY,
) -> dict:
    session_date = today + timedelta(days=days_until)
    return {
        "daily_plan": [
            (
                datetime.combine(session_date, datetime.min.time()),
                41.0,
                {"bike": 41.0},
            )
        ],
        "session_templates": [
            {
                "date": session_date.isoformat(),
                "session_role": role,
                "session_focus": "Качество • вело" if role == "quality" else "Длительная • вело",
                "sport_label": "вело",
                "phase": "Build",
            }
        ],
    }


@pytest.mark.parametrize(
    ("days_until", "expected_horizon"),
    [(4, 5), (6, MAX_QUALITY_LOOKAHEAD_DAYS)],
)
def test_effective_horizon_extends_through_nearest_quality_session(
    days_until: int,
    expected_horizon: int,
) -> None:
    policy = resolve_effective_horizon(
        _goal_plan_with_key_session(days_until),
        today=TODAY,
    )

    assert policy["effective_horizon_days"] == expected_horizon
    assert policy["extended_for_quality"] is True
    assert policy["quality_session"]["days_until"] == days_until


def test_effective_horizon_does_not_extend_beyond_cap_or_for_long_session() -> None:
    beyond_cap = resolve_effective_horizon(
        _goal_plan_with_key_session(MAX_QUALITY_LOOKAHEAD_DAYS),
        today=TODAY,
    )
    long_only = resolve_effective_horizon(
        _goal_plan_with_key_session(4, role="long"),
        today=TODAY,
    )

    assert beyond_cap["effective_horizon_days"] == DEFAULT_HORIZON_DAYS
    assert beyond_cap["extended_for_quality"] is False
    assert long_only["effective_horizon_days"] == DEFAULT_HORIZON_DAYS
    assert long_only["extended_for_quality"] is False


# ---------------------------------------------------------------------------
# Сборка из БД и SSE meta коуча
# ---------------------------------------------------------------------------

def _seed_fresh_recovery(db, *, rmssd_today: float, rhr_today: float) -> None:
    today = datetime.now().date()
    hrv, health, sleep = {}, {}, {}
    for offset in range(0, 29):
        d = (today - timedelta(days=offset)).isoformat()
        hrv[d] = {"rmssd": rmssd_today if offset == 0 else 40.0, "stress_score": 25.0}
        health[d] = {"resting_hr": rhr_today if offset == 0 else 50.0, "steps": 8000}
    sleep[today.isoformat()] = {"total_sleep_minutes": 300, "sleep_score": 35.0}
    db.sync_hrv_data(hrv)
    db.sync_daily_health(health)
    db.sync_sleep_data(sleep)


def _seed_plan_with_quality_tomorrow(db) -> None:
    from models.planning_checkpoints import build_planning_checkpoint

    today = datetime.now().date()
    start_week = today - timedelta(days=today.weekday())
    days, templates = [], []
    # 8 дней (Пн–следующий Пн): в воскресенье «завтра» — уже следующая неделя,
    # и quality-сессия обязана попасть в засеянный план (issue #163).
    for offset in range(0, 8):
        d = start_week + timedelta(days=offset)
        is_quality = d == today + timedelta(days=1)
        tss = 45.0 if is_quality else 10.0
        days.append((datetime.combine(d, datetime.min.time()), tss, {"bike": tss}))
        templates.append(
            {
                "date": d.isoformat(),
                "session_role": "quality" if is_quality else "easy",
                "session_focus": "Качество • вело" if is_quality else "Легкая • вело",
                "sport_label": "вело",
                "phase": "Build",
                "export_name": "Триатлон — Качество • вело" if is_quality else "Триатлон — Легкая • вело",
            }
        )
    goal_plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": 4,
        "start_week": start_week,
        "weekly_tss_plan": [110],
        "base_weekly_tss_plan": [110],
        "phases": ["Build"],
        "daily_plan": days,
        "session_templates": templates,
        "weekly_summary": [
            {"week_start": start_week, "phase": "Build", "weekly_tss": 110, "capacity_tss": 400}
        ],
        "constraint_summary": {},
    }
    db.save_planning_checkpoint(build_planning_checkpoint(goal_plan))


def test_build_report_from_db_detects_quality_conflict(tmp_path) -> None:
    from api.readiness_conflicts import build_readiness_conflict_report
    from data.database import Database

    db = Database(str(tmp_path / "conflicts.db"))
    # низкий HRV (−25% к базлайну 40), RHR +8, короткий сон → готовность low/limited
    _seed_fresh_recovery(db, rmssd_today=30.0, rhr_today=58.0)
    _seed_plan_with_quality_tomorrow(db)

    report = build_readiness_conflict_report(db)

    assert report["data_gap"] is False
    assert report["silence"] is False
    kinds = {c["kind"] for c in report["conflicts"]}
    assert any("quality_session" in kind for kind in kinds)


def test_build_report_extends_to_quality_session_on_day_four(tmp_path, monkeypatch) -> None:
    from api import readiness_conflicts as api_conflicts
    from data.database import Database

    monkeypatch.setattr(
        api_conflicts,
        "get_active_plan",
        lambda _db: _goal_plan_with_key_session(4, today=datetime.now().date()),
    )
    monkeypatch.setattr(
        api_conflicts,
        "compute_readiness_today",
        lambda *args, **kwargs: _readiness(35.0, "low"),
    )

    report = api_conflicts.build_readiness_conflict_report(
        Database(str(tmp_path / "quality-lookahead.db"))
    )

    assert report["horizon_days"] == 5
    assert report["base_horizon_days"] == DEFAULT_HORIZON_DAYS
    assert report["lookahead_policy"] == "base_plus_nearest_quality"
    assert report["horizon_extended_for_quality"] is True
    assert report["sessions_evaluated"][0]["name"] == "Качество • вело"
    assert report["conflicts"][0]["severity"] == "high"


def test_build_report_without_plan_is_silent(tmp_path) -> None:
    from api.readiness_conflicts import build_readiness_conflict_report
    from data.database import Database

    db = Database(str(tmp_path / "noplan.db"))
    _seed_fresh_recovery(db, rmssd_today=40.0, rhr_today=50.0)

    report = build_readiness_conflict_report(db)

    assert report["silence"] is True
    assert report["conflicts"] == []
    assert "план" in report["reason"].lower()


def test_build_report_empty_db_is_data_gap(tmp_path) -> None:
    from api.readiness_conflicts import build_readiness_conflict_report
    from data.database import Database

    report = build_readiness_conflict_report(Database(str(tmp_path / "empty.db")))

    assert report["silence"] is True
    assert report["data_gap"] is True


def test_coach_stream_meta_exposes_readiness_conflicts(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod
    from data.database import Database

    db = Database(str(tmp_path / "coach.db"))
    _seed_fresh_recovery(db, rmssd_today=40.0, rhr_today=50.0)

    async def collect(resp):
        out = []
        async for raw in resp.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    req = coach_mod.ChatRequest(message="Как восстановление?", provider="mock")
    events = asyncio.run(collect(coach_mod.coach_chat(req, db)))

    assert events[0]["type"] == "meta"
    report = events[0]["readiness_conflicts"]
    assert "silence" in report and "conflicts" in report and "reason" in report
    assert events[0]["recovery_replan"]["outcome"] in {"silence", "data_gap", "conflict"}
    assert events[0]["recovery_replan"]["decision"]["id"]
