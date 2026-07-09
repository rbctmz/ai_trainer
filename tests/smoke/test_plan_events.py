from __future__ import annotations

import pytest

from models.plan_events import primary_event, synchronize_goal_plan_events


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
        {"date": "2026-08-10", "priority": "A", "label": "Триатлон Олимпийка"}
    ]
