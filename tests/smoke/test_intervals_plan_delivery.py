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
