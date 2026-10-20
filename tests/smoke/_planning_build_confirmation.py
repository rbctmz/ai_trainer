"""Synthetic, pinned inputs shared by the #685 confirmation regressions."""
from __future__ import annotations
from tests.planning_fixtures import build_plan as fixture_build_plan

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any

from api import planning_service as ps
from config.settings import Settings
from data import database as database_module
from data.database import Database
from tests import athlete_clock
from tests.smoke.test_api_planning import _seeded_db
from utils import athlete_time

TODAY = date(2026, 10, 16)
START = date(2026, 10, 12)
REVISION = datetime(2026, 10, 16, 12, 0)
MODES = ("event_goal", "training_goal", "manual")


class PinnedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return datetime(2026, 10, 16, 9, tzinfo=timezone.utc).astimezone(tz)
        return cls(2026, 10, 16, 12)

    @classmethod
    def utcnow(cls):
        return cls(2026, 10, 16, 9)


def pin_clock(monkeypatch) -> None:
    """Pin athlete day, host activity cutoff, fixture history and plan revision."""
    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")
    for module in (ps, database_module, athlete_clock, athlete_time):
        monkeypatch.setattr(module, "datetime", PinnedDateTime)


def parameters(mode: str = "training_goal") -> dict[str, Any]:
    return {
        "goal_type": "triathlon",
        "distance": "olympic",
        "event_date": None,
        "start_week": START.isoformat(),
        "planning_mode": mode,
        "intent": "develop",
        "focus": "balanced_triathlon",
        "horizon_weeks": 8,
        "available_hours": 12.0,
        "available_days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "demand": "moderate",
        "events": [
            {"date": "2026-11-01", "priority": "B", "label": "Synthetic B", "confirmed": True},
            {"date": "2026-12-06", "priority": "A", "label": "Synthetic A", "confirmed": True},
        ],
        "manual_phases": (
            ["Base", "Build", "Peak", "Taper", "Base", "Build", "Peak", "Recovery"]
            if mode == "manual" else None
        ),
    }


def ready_parameters(mode: str = "training_goal") -> dict[str, Any]:
    """Protocol controls use feasible assignments; original oracle inputs stay intact.

    Deliberately incompatible pre-race overlays in parameters() remain explicit
    S3 rejection fixtures. A protocol/CAS test must first have a valid preview.
    """
    values = parameters(mode)
    values["events"] = ([{"date": "2027-02-13", "priority": "A", "label": "Synthetic A", "confirmed": True}]
                        if mode == "event_goal" else [])
    if mode == "event_goal":
        values["available_hours"] = 10
    if mode == "manual":
        values["manual_phases"] = ["Base", "Base", "Build", "Recovery"] * 2
    return values


def internal_build(db: Database, request: dict[str, Any], *, persist: bool = True):
    """Trusted legacy facade remains the characterization target during extraction."""
    return fixture_build_plan(
        db,
        **{**request, "start_week": date.fromisoformat(request["start_week"])},
        persist=persist,
    )


def cycle_fields(db: Database) -> dict[str, Any]:
    """Explicit current context for v2 fixtures; never inferred in the public API."""
    from services.planning_cycles import current_cycle_context
    context = current_cycle_context(db)
    return {"action": "start_new", "base_cycle_id": context["cycle_id"],
            "base_cycle_revision": context["cycle_revision"],
            "base_selection_revision": context["selection_revision"],
            "base_checkpoint_id": context["checkpoint_id"] or 0,
            "replace_current_cycle": context["cycle_id"] is not None,
            "start_date": athlete_time.athlete_local_date().isoformat()}


def seeded_db(tmp_path, *, existing: bool = False, rested: bool = False) -> Database:
    db = _seeded_db(tmp_path)
    if rested:
        # Same synthetic rows with a rest interval: retain history and allow
        # balanced-load catalog/brick coverage alongside the fatigued RED fixture.
        conn = db._connect()
        try:
            with conn:
                conn.execute("UPDATE activities SET date = date(date, '-21 days')")
        finally:
            conn.close()
    db.save_athlete_profile({
        "ftp": 220.0,
        "lthr": 168.0,
        "weight_kg": 75.0,
        "threshold_pace_seconds_per_km": 300.0,
        "threshold_pace_source": "intervals_icu",
        "threshold_pace_synced_at": REVISION.isoformat(),
        "source": "synthetic_test",
    })
    db.save_coach_constraint(
        date="2026-10-14", kind="forced_rest", source="test", note="Synthetic rest",
    )
    db.set_user_setting("planning_demand_level", "moderate")
    db.set_user_setting("planning_profile", json.dumps({
        "planning_mode": "training_goal", "intent": "maintain", "goal_type": "run",
        "distance": "10k", "available_hours": 6.0, "available_days": ["mon", "wed", "sat"],
        "horizon_weeks": 4, "source": "planning_form",
    }, sort_keys=True))
    _pin_source_timestamps(db)
    if existing:
        original = parameters()
        original["available_hours"] = 8.0
        internal_build(db, original)
        # Explicit test-side synthetic initialization owns this legacy cycle;
        # production raw saves never select/reimport it.
    # The known synthetic forced-rest row is an explicit athlete restriction.
    # Production unresolved rows still fail prepare with constraint_scope_required.
    conn = db._connect()
    try:
        with conn:
            conn.execute("UPDATE coach_constraints SET cycle_scope='athlete',cycle_id=NULL")
    finally:
        conn.close()
    _pin_source_timestamps(db)
    return db


def _pin_source_timestamps(db: Database) -> None:
    """Freeze fixture provenance as well as athlete/revision clocks for hashes."""
    conn = db._connect()
    try:
        with conn:
            for table, column in (("activities", "created_at"), ("athlete_profile", "synced_at"),
                                  ("coach_constraints", "created_at"), ("planning_checkpoints", "created_at")):
                conn.execute(f"UPDATE {table} SET {column}=?", (REVISION.isoformat(),))
    finally:
        conn.close()


def add_late_activity(db: Database) -> None:
    db.save_activities([{
        "activity_id": "synthetic-late-sync",
        "date": TODAY.isoformat(), "sport": "cycling",
        "duration_minutes": 120, "distance_km": 50.0, "tss": 180.0,
    }])


def protected_state(db: Database) -> dict[str, Any]:
    """Exact active/history/settings bytes; pending-preview rows are not active state."""
    conn = db._connect()
    try:
        return {
            "checkpoints": conn.execute("SELECT * FROM planning_checkpoints ORDER BY id").fetchall(),
            "settings": conn.execute("SELECT * FROM user_settings ORDER BY key").fetchall(),
        }
    finally:
        conn.close()


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_payload(db: Database) -> dict[str, Any]:
    """Read exactly persisted JSON, without row ID/creation-time projection."""
    conn = db._connect()
    try:
        raw = conn.execute(
            "SELECT checkpoint_data FROM planning_checkpoints ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return json.loads(raw[0])
    finally:
        conn.close()


def characterization(response: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, str]:
    """Hash complete semantic payloads; omit only the assigned response plan ID."""
    public = {key: value for key, value in response.items() if key != "plan_id"}
    plan = checkpoint["goal_plan_snapshot"]
    return {
        "checkpoint": digest(checkpoint),
        "response": digest(public),
        "session_templates": digest(plan["session_templates"]),
        "daily_plan": digest(plan["daily_plan"]),
        "events": digest(plan["events"]),
        "science_audit": digest(plan["science_audit"]),
        "forecast": digest(public["forecast"]),
    }
