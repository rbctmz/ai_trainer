"""Contract-first tests for deterministic Intervals.icu plan delivery."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities


def _single_plan() -> dict:
    return {
        "goal_type": "Триатлон",
        "distance": "Olympic",
        "daily_plan": [
            (datetime(2026, 7, 15), 40.0, {"bike": 40.0, "run": 0.0, "swim": 0.0}),
            (datetime(2026, 7, 16), 0.0, {"bike": 0.0, "run": 0.0, "swim": 0.0}),
        ],
        "session_templates": [
            {
                "session_id": "ats_material_v1",
                "date": "2026-07-15",
                "sport": "bike",
                "session_role": "quality",
                "phase": "Build",
                "export_name": "Bike threshold",
                "duration_minutes": 60,
                "kind": "single",
                "materialized_steps": [],
            },
            {"date": "2026-07-16", "session_role": "off", "kind": "single"},
        ],
        "weekly_tss_plan": [40],
        "phases": ["Build"],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def _legacy_run_plan() -> dict:
    return {
        "goal_type": "Триатлон",
        "distance": "Olympic",
        "daily_plan": [
            (datetime(2026, 7, 16), 20.0, {"bike": 0.0, "run": 20.0, "swim": 0.0}),
        ],
        "session_templates": [
            {
                "session_id": "ats_legacy_run_v1",
                "date": "2026-07-16",
                "sport": "run",
                "session_role": "easy",
                "phase": "Build",
                "export_name": "Easy run",
                "duration_minutes": 30,
                "kind": "single",
                "materialized_steps": [],
            },
        ],
        "weekly_tss_plan": [20],
        "phases": ["Build"],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def _pace_run_plan() -> dict:
    return {
        "goal_type": "run",
        "distance": "10k",
        "daily_plan": [
            (datetime(2026, 7, 16), 20.0, {"bike": 0.0, "run": 20.0, "swim": 0.0}),
        ],
        "session_templates": [
            {
                "session_id": "ats_pace_run_v1",
                "date": "2026-07-16",
                "sport": "run",
                "session_role": "easy",
                "phase": "Build",
                "export_name": "Pace run",
                "duration_minutes": 20,
                "kind": "single",
                "materialized_steps": [
                    {
                        "name": "Warm-up",
                        "duration_seconds": 300,
                        "target": {
                            "type": "pace",
                            "unit": "seconds_per_km",
                            "fast": 360.0,
                            "slow": 420.0,
                        },
                    },
                    {
                        "name": "Steady",
                        "duration_seconds": 900,
                        "target": {
                            "type": "pace",
                            "unit": "seconds_per_km",
                            "fast": 330.0,
                            "slow": 350.0,
                        },
                    },
                ],
            },
        ],
        "weekly_tss_plan": [20],
        "phases": ["Build"],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def _brick_plan() -> dict:
    return {
        "goal_type": "Триатлон",
        "distance": "Olympic",
        "daily_plan": [
            (datetime(2026, 7, 18), 65.0, {"bike": 45.0, "run": 20.0, "swim": 0.0})
        ],
        "session_templates": [
            {
                "session_id": "ats_brick_v1",
                "date": "2026-07-18",
                "kind": "composite",
                "sport": "brick",
                "session_role": "brick",
                "phase": "Build",
                "export_name": "Race brick",
                "legs": [
                    {
                        "leg_index": 1,
                        "sport": "bike",
                        "target_tss": 45.0,
                        "duration_minutes": 60,
                        "template_name": "Bike endurance",
                        "materialized_steps": [
                            {
                                "name": "Endurance",
                                "intensity": "moderate",
                                "duration_seconds": 3600,
                                "target": {"type": "power", "low": 110, "high": 125},
                            }
                        ],
                    },
                    {
                        "leg_index": 2,
                        "sport": "run",
                        "target_tss": 20.0,
                        "duration_minutes": 25,
                        "template_name": "Transition run",
                        "materialized_steps": [
                            {
                                "name": "Steady run",
                                "intensity": "moderate",
                                "duration_seconds": 1500,
                                "target": {"type": "heart_rate", "low": 125, "high": 140},
                            }
                        ],
                    },
                ],
            }
        ],
        "weekly_tss_plan": [65],
        "phases": ["Build"],
        "weekly_summary": [],
        "constraint_summary": {},
    }


class _FakeClient:
    def __init__(self, existing=None, executable=True, configured=True):
        self.existing = list(existing or [])
        self.executable = executable
        self.configured = configured
        self.list_calls = []
        self.upsert_calls = []
        self.delete_calls = []

    def is_configured(self):
        return self.configured

    def list_workout_events(self, oldest, newest):
        self.list_calls.append((oldest, newest))
        return list(self.existing)

    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        return [
            {
                **row,
                "id": index + 100,
                "uid": f"provider-generated-{index}",
                "workout_doc": {"steps": [{"duration": 600}]} if self.executable else None,
            }
            for index, row in enumerate(rows)
        ]

    def delete_events(self, payloads):
        rows = [dict(row) for row in payloads]
        self.delete_calls.append(rows)
        return len(rows)


class _PartialUpsertClient(_FakeClient):
    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        if not rows:
            return []
        return [
            {
                **rows[0],
                "id": 100,
                "uid": "provider-generated-0",
                "workout_doc": {"steps": [{"duration": 600}]},
            }
        ]


class _PaceReadBackClient(_FakeClient):
    def __init__(self, *, pace_steps):
        super().__init__()
        self.pace_steps = list(pace_steps)
        self.stored = []

    def list_workout_events(self, oldest, newest):
        self.list_calls.append((oldest, newest))
        return [dict(row) for row in self.stored]

    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        self.stored = [
            {
                **row,
                "id": index + 100,
                "uid": f"provider-generated-{index}",
                "workout_doc": {"steps": [dict(step) for step in self.pace_steps]},
            }
            for index, row in enumerate(rows)
        ]
        return [dict(row) for row in self.stored]


def test_legacy_single_session_builds_owned_executable_native_payload() -> None:
    from models.intervals_workout_delivery import build_delivery_events

    plan = ensure_session_identities(_single_plan())
    events = build_delivery_events(plan, ["2026-07-15"])

    assert len(events) == 1
    event = events[0]
    assert event["external_id"] == (
        f"ai_trainer:{plan['session_templates'][0]['session_id']}"
    )
    assert event["category"] == "WORKOUT"
    assert event["type"] == "Ride"
    assert event["moving_time"] > 0
    assert event["icu_training_load"] == 40
    assert "uid" not in event
    assert "- Warmup" in event["description"]
    assert "m" in event["description"]
    assert "95-105%" in event["description"]
    assert "95-105% HR" not in event["description"]


def test_legacy_run_marks_percentage_targets_as_heart_rate() -> None:
    from models.intervals_workout_delivery import build_delivery_events

    events = build_delivery_events(_legacy_run_plan(), ["2026-07-16"])

    assert len(events) == 1
    assert events[0]["type"] == "Run"
    lines = events[0]["description"].splitlines()
    assert any(line.endswith("65-80% HR") for line in lines)
    assert any(line.endswith("75-90% HR") for line in lines)
    assert any(line.endswith("60-70% HR") for line in lines)
    assert not any(line.endswith(("65-80%", "75-90%", "60-70%")) for line in lines)


def test_explicit_plan_build_round_trips_running_pace_to_intervals_description(
    tmp_path,
) -> None:
    from api import planning_service as ps
    from models.intervals_workout_delivery import build_delivery_events

    db = Database(str(tmp_path / "pace-delivery.db"))
    db.save_athlete_profile(
        {
            "ftp": 200.0,
            "weight_kg": 80.0,
            "lthr": 165.0,
            "threshold_pace_seconds_per_km": 300.0,
            "threshold_pace_source": "intervals_icu",
            "source": "intervals_icu",
        }
    )
    ps.build_plan(
        db,
        goal_type="run",
        distance="10k",
        event_date=None,
        planning_mode="training_goal",
        intent="develop",
        horizon_weeks=8,
        events=[],
        available_hours=8,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )
    plan = ps.get_active_plan(db)
    from models.workout_catalog import require_executable_planned_session

    selected_dates = []
    for template in plan["session_templates"]:
        sessions = template.get("sessions") or [template]
        if not any(
            session.get("sport") == "run"
            or any(leg.get("sport") == "run" for leg in session.get("legs") or [])
            for session in sessions
        ):
            continue
        try:
            for session in sessions:
                require_executable_planned_session(session)
        except ValueError:
            continue
        selected_dates = [str(template["date"])]
        break
    assert selected_dates

    events = build_delivery_events(plan, selected_dates)
    run_events = [event for event in events if event["type"] == "Run"]

    assert run_events
    assert all("/km" in event["description"] for event in run_events)
    assert all("% LTHR" not in event["description"] for event in run_events)
    assert all("bpm" not in event["description"] for event in run_events)


def test_delivery_fails_closed_when_provider_drops_or_changes_pace_targets(
    tmp_path,
) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "pace-mismatch.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_pace_run_plan()))
    stale_owned = {
        "id": 2,
        "uid": "old-ai-slot",
        "external_id": "ai_trainer:ats_old",
        "category": "WORKOUT",
        "start_date_local": "2026-07-16T07:00:00",
    }
    client = _PaceReadBackClient(
        pace_steps=[
            {"text": "Warm-up", "duration": 300},
            {
                "text": "Steady",
                "duration": 900,
                "pace": {"start": 300, "end": 320, "units": "secs/km"},
            },
        ]
    )
    client.stored = [stale_owned]

    result = deliver_active_plan(
        db,
        dates=["2026-07-16"],
        source="manual",
        client=client,
    )

    assert result["status"] == "partial"
    assert result["target_mismatch_count"] == 1
    assert result["failed_count"] == 1
    assert result["retryable"] is True
    assert result["executable_count"] == 0
    assert result["calendar_only_count"] == 0
    assert result["deleted_count"] == 0
    assert client.delete_calls == []
    assert len(client.list_calls) == 2


def test_delivery_accepts_equivalent_pace_targets_from_bounded_readback(
    tmp_path,
) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "pace-match.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_pace_run_plan()))
    client = _PaceReadBackClient(
        pace_steps=[
            {
                "text": "Warm-up",
                "duration": 300,
                "pace": {"start": 360, "end": 420, "units": "secs/km"},
            },
            {
                "text": "Steady",
                "duration": 900,
                "pace": {"start": 350, "end": 330, "units": "secs/km"},
            },
        ]
    )

    result = deliver_active_plan(
        db,
        dates=["2026-07-16"],
        source="manual",
        client=client,
    )

    assert result["status"] == "success"
    assert result["target_mismatch_count"] == 0
    assert result["failed_count"] == 0
    assert result["retryable"] is False
    assert result["executable_count"] == 1
    assert len(client.list_calls) == 2


def test_transferred_pace_run_keeps_targets_through_delivery_readback(
    tmp_path,
) -> None:
    from models.session_transfer import apply_session_transfer
    from services.intervals_plan_delivery import deliver_active_plan

    plan = _pace_run_plan()
    plan["daily_plan"].append(
        (datetime(2026, 7, 17), 0.0, {"bike": 0.0, "run": 0.0, "swim": 0.0})
    )
    plan["session_templates"].append(
        {"date": "2026-07-17", "session_role": "off", "kind": "single"}
    )
    plan = ensure_session_identities(plan)
    old_session_id = plan["session_templates"][0]["sessions"][0]["session_id"]
    transferred = apply_session_transfer(
        plan,
        session_id=old_session_id,
        target_date="2026-07-17",
    )

    db = Database(str(tmp_path / "pace-transfer.db"))
    db.save_planning_checkpoint(
        build_planning_checkpoint(transferred["goal_plan"])
    )
    client = _PaceReadBackClient(
        pace_steps=[
            {
                "text": "Warm-up",
                "duration": 300,
                "pace": {"start": 420, "end": 360, "units": "secs/km"},
            },
            {
                "text": "Steady",
                "duration": 900,
                "pace": {"start": 330, "end": 350, "units": "secs/km"},
            },
        ]
    )

    result = deliver_active_plan(
        db,
        dates=["2026-07-17"],
        source="recovery_approve",
        client=client,
    )

    assert result["status"] == "success"
    assert result["target_mismatch_count"] == 0
    assert len(client.upsert_calls) == 1
    delivered = client.upsert_calls[0][0]
    assert delivered["external_id"] == (
        f"ai_trainer:{transferred['new_session_id']}"
    )
    assert delivered["description"].count("/km Pace") == 2


def test_power_target_delivery_keeps_existing_single_read_contract(tmp_path) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "power-regression.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_brick_plan()))
    client = _FakeClient()

    result = deliver_active_plan(
        db,
        dates=["2026-07-18"],
        source="manual",
        client=client,
    )

    assert result["status"] == "success"
    assert result["executable_count"] == 2
    assert result["target_mismatch_count"] == 0
    assert len(client.list_calls) == 1
    delivered = client.upsert_calls[0]
    assert "110-125w" in delivered[0]["description"]


def test_composite_brick_builds_two_ordered_leg_events() -> None:
    from models.intervals_workout_delivery import build_delivery_events

    plan = ensure_session_identities(_brick_plan())
    events = build_delivery_events(plan, ["2026-07-18"])
    session_id = plan["session_templates"][0]["session_id"]

    assert [row["external_id"] for row in events] == [
        f"ai_trainer:{session_id}:leg:1",
        f"ai_trainer:{session_id}:leg:2",
    ]
    assert [row["type"] for row in events] == ["Ride", "Run"]
    assert events[0]["start_date_local"] < events[1]["start_date_local"]
    assert "110-125w" in events[0]["description"]
    assert "125-140bpm" in events[1]["description"]


def test_delivery_refuses_shifted_template_dates_before_provider_payload() -> None:
    from models.intervals_workout_delivery import build_delivery_events

    plan = _single_plan()
    plan["session_templates"][0]["date"] = "2026-07-16"
    plan["session_templates"][1]["date"] = "2026-07-15"

    with pytest.raises(ValueError, match="template date"):
        build_delivery_events(plan, ["2026-07-15"])


def test_delivery_upserts_desired_slots_and_deletes_only_owned_stale_events(tmp_path) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "delivery.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))
    foreign = {
        "id": 1,
        "uid": "foreign-slot",
        "external_id": None,
        "category": "WORKOUT",
        "start_date_local": "2026-07-15T08:00:00",
    }
    stale_owned = {
        "id": 2,
        "uid": "old-ai-slot",
        "external_id": "ai_trainer:ats_old",
        "category": "WORKOUT",
        "start_date_local": "2026-07-15T07:00:00",
    }
    client = _FakeClient(existing=[foreign, stale_owned])

    result = deliver_active_plan(
        db,
        days=7,
        today=date(2026, 7, 15),
        source="manual",
        client=client,
    )

    assert result["status"] == "success"
    assert result["checkpoint_id"] == checkpoint["id"]
    assert result["executable_count"] == 1
    assert result["calendar_only_count"] == 0
    assert result["deleted_count"] == 1
    assert len(client.upsert_calls) == 1
    assert "uid" not in client.upsert_calls[0][0]
    assert client.delete_calls == [[{"id": 2, "external_id": "ai_trainer:ats_old"}]]
    assert all(row.get("id") != 1 for call in client.delete_calls for row in call)


def test_explicit_dates_do_not_delete_owned_events_on_unselected_days(tmp_path) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    plan = _single_plan()
    plan["daily_plan"].append(
        (datetime(2026, 7, 17), 30.0, {"bike": 30.0, "run": 0.0, "swim": 0.0})
    )
    plan["session_templates"].append(
        {
            "session_id": "ats_material_v2",
            "date": "2026-07-17",
            "sport": "bike",
            "session_role": "easy",
            "phase": "Build",
            "export_name": "Bike endurance",
            "kind": "single",
            "materialized_steps": [],
        }
    )
    db = Database(str(tmp_path / "explicit-dates.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(plan))
    unselected_owned = {
        "id": 22,
        "uid": "owned-middle-day",
        "external_id": "ai_trainer:ats_middle",
        "category": "WORKOUT",
        "start_date_local": "2026-07-16T07:00:00",
    }
    client = _FakeClient(existing=[unselected_owned])

    result = deliver_active_plan(
        db,
        dates=["2026-07-15", "2026-07-17"],
        source="recovery_approve",
        client=client,
    )

    assert result["status"] == "success"
    assert result["deleted_count"] == 0
    assert client.delete_calls == []


def test_partial_upsert_never_deletes_previous_owned_slots(tmp_path) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "partial-upsert.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_brick_plan()))
    previous_single = {
        "id": 31,
        "uid": "previous-single-slot",
        "external_id": "ai_trainer:ats_previous",
        "category": "WORKOUT",
        "start_date_local": "2026-07-18T07:00:00",
    }
    client = _PartialUpsertClient(existing=[previous_single])

    result = deliver_active_plan(
        db,
        dates=["2026-07-18"],
        source="recovery_approve",
        client=client,
    )

    assert result["status"] == "partial"
    assert result["failed_count"] == 1
    assert result["deleted_count"] == 0
    assert client.delete_calls == []


def test_delivery_reports_calendar_only_and_missing_configuration_without_writes(tmp_path) -> None:
    from services.intervals_plan_delivery import deliver_active_plan

    db = Database(str(tmp_path / "delivery-status.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))
    calendar_client = _FakeClient(executable=False)

    calendar_only = deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="recovery_approve",
        client=calendar_client,
    )
    missing_client = _FakeClient(configured=False)
    missing = deliver_active_plan(
        db,
        days=7,
        today=date(2026, 7, 15),
        source="manual",
        client=missing_client,
    )

    assert calendar_only["status"] == "calendar_only"
    assert calendar_only["calendar_only_count"] == 1
    assert missing["status"] == "not_configured"
    assert missing_client.list_calls == []
    assert missing_client.upsert_calls == []


def test_empty_explicit_delivery_dates_are_skipped_without_provider_access(tmp_path) -> None:
    from services.intervals_plan_delivery import safe_deliver_active_plan

    db = Database(str(tmp_path / "empty-dates.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))
    client = _FakeClient()

    result = safe_deliver_active_plan(
        db,
        dates=[],
        source="recovery_rollback",
        client=client,
    )

    assert result["status"] == "skipped"
    assert result["dates"] == []
    assert result["failed_count"] == 0
    assert result["retryable"] is False
    assert client.list_calls == []
    assert client.upsert_calls == []
    assert client.delete_calls == []


def test_default_delivery_window_uses_athlete_timezone(monkeypatch) -> None:
    from config.settings import Settings
    from services.intervals_plan_delivery import athlete_local_date

    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Pacific/Kiritimati")
    observed = datetime(2026, 7, 14, 12, 30, tzinfo=timezone.utc)

    assert athlete_local_date(observed) == date(2026, 7, 15)


def test_safe_delivery_sanitizes_provider_failure(tmp_path) -> None:
    from services.intervals_icu import IntervalsICUError
    from services.intervals_plan_delivery import safe_deliver_active_plan

    class FailingClient(_FakeClient):
        def list_workout_events(self, oldest, newest):
            raise IntervalsICUError("HTTP 429: retry later secret-token")

    db = Database(str(tmp_path / "failed-delivery.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))

    result = safe_deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="recovery_approve",
        client=FailingClient(),
        secrets=["secret-token"],
    )

    assert result["status"] == "failed"
    assert result["retryable"] is True
    assert "secret-token" not in result["error"]


def test_safe_delivery_marks_history_failure_as_retryable(
    tmp_path, monkeypatch
) -> None:
    from services.intervals_plan_delivery import safe_deliver_active_plan

    db = Database(str(tmp_path / "history-failure.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))

    def fail_history(_payload):
        raise RuntimeError("ledger unavailable secret-token")

    monkeypatch.setattr(db, "save_intervals_plan_delivery", fail_history)
    result = safe_deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="manual",
        client=_FakeClient(),
        secrets=["secret-token"],
    )

    assert result["status"] == "success"
    assert result["retryable"] is True
    assert result["history_status"] == "failed"
    assert result["history_retryable"] is True
    assert "secret-token" not in result["history_error"]


def test_safe_delivery_keeps_provider_and_history_failures_distinct(
    tmp_path, monkeypatch
) -> None:
    from services.intervals_icu import IntervalsICUError
    from services.intervals_plan_delivery import safe_deliver_active_plan

    class FailingClient(_FakeClient):
        def list_workout_events(self, oldest, newest):
            raise IntervalsICUError("provider unavailable")

    db = Database(str(tmp_path / "double-failure.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))
    monkeypatch.setattr(
        db,
        "save_intervals_plan_delivery",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("ledger unavailable")),
    )

    result = safe_deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="manual",
        client=FailingClient(),
    )

    assert result["status"] == "failed"
    assert result["error"] == "provider unavailable"
    assert result["history_status"] == "failed"
    assert result["history_error"] == "ledger unavailable"
    assert result["retryable"] is result["history_retryable"] is True


def test_delivery_history_failure_is_typed_and_visible_in_export_ui() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    types_source = (root / "web" / "lib" / "types.ts").read_text(encoding="utf-8")
    page_source = (root / "web" / "app" / "planning" / "page.tsx").read_text(
        encoding="utf-8"
    )

    assert "history_status:" in types_source
    assert "history_retryable:" in types_source
    assert "deliveryResult.history_retryable" in page_source
    assert "Результат попытки доставки не сохранён" in page_source
    assert "План отправлен провайдеру, но локальная история" not in page_source


def test_manual_safe_delivery_is_persisted_idempotently(tmp_path) -> None:
    """A manual delivery is durable evidence, not only recovery-proposal metadata."""
    from services.intervals_plan_delivery import safe_deliver_active_plan

    db = Database(str(tmp_path / "manual-delivery-ledger.db"))
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(_single_plan()))
    client = _FakeClient()

    first = safe_deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="manual",
        client=client,
    )
    second = safe_deliver_active_plan(
        db,
        dates=["2026-07-15"],
        source="manual",
        client=client,
    )

    assert first["status"] == second["status"] == "success"
    deliveries = db.get_approved_recovery_replan_deliveries()
    assert len(deliveries) == 1
    assert deliveries[0]["proposal_id"] is None
    assert deliveries[0]["checkpoint_id"] == checkpoint["id"]
    assert deliveries[0]["dates"] == ["2026-07-15"]
    assert deliveries[0]["status"] == "success"
    assert deliveries[0]["source"] == "manual"

    from models.plan_vs_fact import plan_replanned_after_delivery

    warning = plan_replanned_after_delivery(
        {"session_date": "2026-07-15", "base_checkpoint_id": checkpoint["id"] + 1},
        {"checkpoint_source": "recovery_replan"},
        deliveries,
    )
    assert warning is not None
    assert warning["delivery_checkpoint_id"] == checkpoint["id"]


def test_delivery_ledger_fingerprint_ignores_provider_id_order_and_scalar_type(
    tmp_path,
) -> None:
    db = Database(str(tmp_path / "delivery-id-order.db"))
    payload = {
        "source": "manual",
        "checkpoint_id": 9,
        "dates": ["2026-07-15"],
        "status": "success",
        "provider_event_ids": [101, "102"],
        "desired_count": 2,
        "executable_count": 2,
    }

    first = db.save_intervals_plan_delivery(payload)
    second = db.save_intervals_plan_delivery(
        {**payload, "provider_event_ids": [102, "101"]}
    )

    assert first["id"] == second["id"]
    assert db.get_intervals_plan_deliveries() == [first]
