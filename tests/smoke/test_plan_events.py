from __future__ import annotations

import pytest

from models.plan_events import (
    macrocycle_event,
    normalize_intervals_event,
    primary_event,
    synchronize_goal_plan_events,
)


pytestmark = pytest.mark.smoke


def test_primary_event_prefers_priority_then_nearest_date() -> None:
    event = primary_event(
        [
            {"date": "2026-07-10", "priority": "B", "label": "Контроль"},
            {"date": "2026-09-01", "priority": "A", "label": "Главный поздний"},
            {"date": "2026-08-20", "priority": "A", "label": "Главный ранний"},
        ]
    )

    assert event == {"date": "2026-08-20", "priority": "A", "label": "Главный ранний"}


def test_single_b_event_is_primary_without_ui_specific_rule() -> None:
    plan = synchronize_goal_plan_events(
        {
            "goal_type": "Бег",
            "distance": "Марафон",
            "events": [{"date": "2026-08-10", "priority": "B", "label": "Подводящий старт"}],
        }
    )

    assert plan["event_date"] == "2026-08-10"
    assert plan["events"] == [{"date": "2026-08-10", "priority": "B", "label": "Подводящий старт"}]


def test_legacy_event_date_synthesizes_one_a_event() -> None:
    plan = synchronize_goal_plan_events(
        {"goal_type": "Триатлон", "distance": "Олимпийка", "event_date": "2026-08-10"}
    )

    assert plan["event_date"] == "2026-08-10"
    assert plan["events"] == [
        {
            "date": "2026-08-10",
            "priority": "A",
            "label": "Триатлон Олимпийка",
            "source": "legacy_checkpoint",
            "priority_provenance": "legacy_assumed",
            "confirmed": False,
            "requires_confirmation": True,
        }
    ]


def test_macrocycle_event_uses_only_confirmed_a_anchor() -> None:
    events = [
        {"date": "2026-07-26", "priority": "B", "label": "Minsk", "confirmed": True},
        {"date": "2026-10-04", "priority": "A", "label": "Sirius", "confirmed": True},
    ]

    assert macrocycle_event(events)["date"] == "2026-10-04"
    assert macrocycle_event(events[:1]) is None


def test_intervals_other_triathlon_keeps_priority_and_evidence() -> None:
    event = normalize_intervals_event(
        {
            "id": 404,
            "category": "RACE_A",
            "start_date_local": "2026-10-04T09:00:00",
            "name": "IRONSTAR OLYMPIC SIRIUS 2026",
            "type": "Other",
            "distance": 51500,
            "description": "Olympic triathlon: swim 1.5 km, bike 40 km, run 10 km",
        }
    )

    assert event is not None
    assert event["priority"] == "A"
    assert event["discipline"] == "triathlon"
    assert event["source"] == "intervals_icu"
    assert event["source_id"] == "404"
    assert event["priority_provenance"] == "explicit_category"
    assert event["discipline_provenance"] == "name_description_evidence"
    assert event["discipline_confidence"] >= 0.8
    assert event["requires_confirmation"] is False


def test_intervals_ambiguous_other_requires_confirmation() -> None:
    event = normalize_intervals_event(
        {
            "id": 12,
            "category": "RACE_B",
            "start_date_local": "2026-08-01T09:00:00",
            "name": "Local challenge",
            "type": "Other",
        }
    )

    assert event is not None
    assert event["priority"] == "B"
    assert event["discipline"] is None
    assert event["requires_confirmation"] is True
