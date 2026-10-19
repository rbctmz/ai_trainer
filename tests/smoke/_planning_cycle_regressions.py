"""Synthetic pre-S2 database and clock; never opens the athlete cache."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import sqlite3

from fastapi.testclient import TestClient

from config.settings import Settings
from data.database import Database
from data.data_processor import ActivityProcessor
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities
from tests import athlete_clock
from utils import athlete_time

TODAY = date(2026, 10, 16)
CYCLE_A = "00000000-0000-4000-8000-000000000001"
CYCLE_B = "00000000-0000-4000-8000-000000000002"


def pin_clock(monkeypatch, *, observed=None, zone="Europe/Moscow"):
    observed = observed or datetime(2026, 10, 16, 9, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return observed.astimezone(tz) if tz else observed.replace(tzinfo=None)

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", zone)
    # Keep planning_service.datetime intact: restored daily rows use the real
    # datetime class, including overview isinstance checks.
    monkeypatch.setattr(athlete_time, "datetime", Clock)
    monkeypatch.setattr(athlete_clock, "datetime", Clock)


def plan(start=date(2026, 9, 28), days=7):
    daily, templates = [], []
    for offset in range(days):
        day = start + timedelta(days=offset)
        daily.append((datetime.combine(day, datetime.min.time()), 20.0, {"run": 20.0}))
        templates.append({
            "date": day.isoformat(), "sport": "run", "kind": "single",
            "phase": "Race Week", "session_role": "easy",
            "session_focus": "Synthetic endurance", "duration_minutes": 30,
            "materialized_steps": [{"name": "Easy", "duration_seconds": 1800,
                                    "target": {"type": "heart_rate", "low": 120, "high": 135}}],
        })
    end = start + timedelta(days=days - 1)
    return {
        "goal_type": "Триатлон", "distance": "Олимпийка",
        "planning_mode": "event_goal", "planning_intent": "develop",
        "planning_focus": "balanced_triathlon", "event_date": end.isoformat(),
        "events": [{"date": end.isoformat(), "priority": "A", "confirmed": True,
                    "label": "Synthetic Olympic"}],
        "start_week": start, "weeks_to_race": 1, "horizon_weeks": 1,
        "weekly_tss_plan": [20 * days], "phases": ["Race Week"],
        "daily_plan": daily, "session_templates": templates,
        "weekly_summary": [{"week_start": start, "phase": "Race Week",
                            "weekly_tss": 20 * days, "run": 20 * days}],
        "constraint_summary": {"available_hours": 10.0,
                               "available_day_indices": list(range(7))},
        "weekly_target_breakdown": {"demand": {"level": "moderate", "factor": 1.0}},
    }


def legacy_db(tmp_path, monkeypatch, *, payloads=None, start=date(2026, 9, 28), days=7,
              constraint_kind=None, before_init=None):
    """Create legacy rows BEFORE Database initialization/migration, not after it.

    Only the old table is declared here. Future cycle tables/selection must be
    created by production migration, never by a fabricated test-side selector.
    """
    pin_clock(monkeypatch)
    if payloads is None:
        payloads = [build_planning_checkpoint(plan(start, days))]
    with sqlite3.connect(tmp_path / "plan.db") as conn:
        conn.execute("""CREATE TABLE planning_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, goal_type TEXT, distance TEXT,
            weeks_to_race INTEGER, checkpoint_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        for payload in payloads:
            raw = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            conn.execute("""INSERT INTO planning_checkpoints
                (goal_type, distance, weeks_to_race, checkpoint_data) VALUES (?, ?, ?, ?)""",
                         ("Триатлон", "Олимпийка", 1, raw))
        if constraint_kind:
            conn.execute("""CREATE TABLE coach_constraints (
                id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
                kind TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
                note TEXT, plan_id TEXT, session_id TEXT, metadata_json TEXT,
                resolved_at TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sport TEXT)""")
            conn.execute("""INSERT INTO coach_constraints
                (date, kind, status, source, metadata_json) VALUES (?, ?, 'active', 'test', '{}')""",
                         (TODAY.isoformat(), constraint_kind))
        if before_init:
            before_init(conn)
    db = Database(str(tmp_path / "plan.db"))
    rows = []
    for offset in range(28):
        activity = {"activity_id": f"s{offset}", "date": (TODAY - timedelta(days=offset)).isoformat(),
                    "sport": "running" if offset % 2 == 0 else "cycling",
                    "duration_minutes": 60, "distance_km": 25.0}
        # Seed already-resolved synthetic loads: Database initialization has an
        # existing TSS backfill unrelated to S2. Measuring that normalization as
        # a lifecycle mutation would give a false characterization failure.
        rows.append({**activity, **ActivityProcessor.resolve_tss(activity)})
    db.save_activities(rows)
    return db


@contextmanager
def client_for(db):
    from api.deps import get_database
    from api.main import app

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def evidence_bytes(db):
    """Compare complete persisted rows, including raw JSON/IDs/timestamps."""
    tables = ("planning_checkpoints", "activities", "plan_actual_matches",
              "session_feedback", "intervals_plan_deliveries", "user_settings")
    conn = db._connect()
    try:
        return {table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in tables}
    finally:
        conn.close()


def seed_evidence(db, session_id):
    checkpoint_id = db.get_latest_planning_checkpoint()["id"]
    match = db.save_plan_actual_match({
        "fingerprint": "synthetic-match", "target_key": f"session:{session_id}",
        "session_id": session_id, "base_checkpoint_id": checkpoint_id,
        "session_date": "2026-09-28", "match_status": "matched",
        "match_method": "manual", "confidence": 1.0,
        "planned_snapshot": {"session_id": session_id}, "actual_activity_ids": ["s0"],
        "actual_snapshot": {"tss": 55.0}, "evidence": {"source": "synthetic"},
        "rule_version": "synthetic-v1",
    })
    feedback = db.save_session_feedback({
        "fingerprint": "synthetic-feedback", "target_key": f"session:{session_id}",
        "session_id": session_id, "match_snapshot": match, "actual_activity_ids": ["s0"],
        "completion_status": "completed", "source": "test", "session_end_provenance": "manual",
        "status": "active", "rule_version": "synthetic-v1",
        "submitted_at": "2026-10-16T09:00:00+00:00",
    })["feedback"]
    delivery = db.save_intervals_plan_delivery({
        "source": "manual", "checkpoint_id": checkpoint_id, "dates": ["2026-09-28"],
        "status": "success", "provider_event_ids": ["synthetic-provider-id"],
        "desired_count": 1, "executable_count": 1,
    })
    return match, feedback, delivery


def namespaced_plan(namespace, *, kind="single"):
    result = plan()
    result["identity_namespace"] = namespace
    if kind == "multisport":
        template = result["session_templates"][0]
        run = {**template, "total_tss": 20.0}
        bike = {**template, "sport": "bike", "total_tss": 30.0}
        template["sessions"] = [run, bike]
        result["daily_plan"][0] = (result["daily_plan"][0][0], 50.0, {"run": 20.0, "bike": 30.0})
    elif kind == "brick":
        template = result["session_templates"][0]
        template.update(kind="composite", sport="brick", session_role="brick", legs=[
            {"leg_index": 1, "sport": "bike", "target_tss": 30.0, "duration_minutes": 30,
             "materialized_steps": [{"duration_seconds": 1800,
                                     "target": {"type": "power", "low": 110, "high": 140}}]},
            {"leg_index": 2, "sport": "run", "target_tss": 20.0, "duration_minutes": 30,
             "materialized_steps": template["materialized_steps"]},
        ])
        result["daily_plan"][0] = (result["daily_plan"][0][0], 50.0, {"run": 20.0, "bike": 30.0})
    return result


def identity_keys(goal_plan):
    """All public day/session/leg identifiers, including non-top-level leaves."""
    keys = set()
    for template in goal_plan["session_templates"]:
        for session in [template, *template.get("sessions", [])]:
            keys.add(session["session_id"])
            keys.update(leg["leg_id"] for leg in session.get("legs", []))
    return keys


def first_session_id(goal_plan):
    return ensure_session_identities(goal_plan)["session_templates"][0]["sessions"][0]["session_id"]
