"""Статические гейты web-поверхности первого плана (#271, M2-T5/T6)."""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

PAGE = Path(__file__).parents[2] / "web" / "app" / "planning" / "page.tsx"
BUILDER = Path(__file__).parents[2] / "web" / "components" / "planning" / "PlanBuilder.tsx"


def test_m2_t5_planning_uses_server_onboarding_without_fake_event_date():
    source = PAGE.read_text(encoding="utf-8") + BUILDER.read_text(encoding="utf-8")

    assert 'useSWR<PlanningOnboarding>("/api/onboarding/planning"' in source
    assert "defaultEventDate" not in source
    assert 'const [eventDate, setEventDate] = useState("");' in source
    assert "BasisChip" in source


def test_m2_t6_event_goal_requires_confirmed_a_race_or_manual_date():
    source = PAGE.read_text(encoding="utf-8") + BUILDER.read_text(encoding="utf-8")

    assert "hasSelectedARace" in source
    assert 'event.priority?.toUpperCase() === "A"' in source
    assert "event.confirmed !== false" in source
    assert 'planningMode === "event_goal" && !eventDate && !hasSelectedARace' in source
    assert 'planningMode === "event_goal" && !hasSelectedARace ? eventDate : null' in source


def test_m2_t5_confirm_persists_profile_without_hiding_partial_failure():
    source = PAGE.read_text(encoding="utf-8") + BUILDER.read_text(encoding="utf-8")

    assert 'putJSON("/api/onboarding/planning"' in source
    assert "setProfileWarning(" in source
    assert "План сохранён, но параметры профиля записать не удалось" in source
