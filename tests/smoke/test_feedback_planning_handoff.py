"""Executable web contract for Issue #185 feedback-to-Planning handoff."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_today_deep_links_pending_match_by_stable_session_id() -> None:
    source = _source("web/app/today/page.tsx")

    assert "/planning?session_id=" in source
    assert "encodeURIComponent(pendingMatch.session_id)" in source


def test_planning_target_opens_adjust_scrolls_highlights_and_focuses() -> None:
    source = _source("web/app/planning/page.tsx")

    assert 'searchParams.get("session_id")' in source
    assert 'setTab("adjust")' in source
    assert "scrollIntoView" in source
    assert ".focus(" in source
    assert "targetSessionId === r.session_id" in source
    assert "ring-accent" in source


def test_feedback_substitution_presentation_is_localized() -> None:
    component = _source("web/components/today/PostWorkoutFeedbackCard.tsx")
    types = _source("web/lib/types.ts")

    assert "planned_sport: string" in types
    assert '"athlete-entered": "введено спортсменом"' in component
    assert 'run: "бег"' in component
    assert 'bike: "вело"' in component
    assert "Подтверждённая замена" in component
    assert "Фактическая сессия" in component


def test_feedback_brick_presentation_separates_structure_from_load() -> None:
    component = _source("web/components/today/PostWorkoutFeedbackCard.tsx")

    assert 'prompt.kind === "composite"' in component
    assert 'prompt.match_status === "matched"' in component
    assert "Brick сопоставлен по структуре" in component
    assert "loadAdherenceLabel(prompt.adherence)" in component
    assert "вместо {plannedCompositeSportLabel}" in component
    assert "prompt.composite_execution?.structure_match === true" in component
    assert "actualSportKeys.length >= 2" not in component


def test_generic_substituted_labels_do_not_claim_replacement() -> None:
    adherence = _source("web/lib/adherence.ts")
    planning = _source("web/app/planning/page.tsx")
    today = _source("web/app/today/page.tsx")

    assert 'substituted: { label: "Изменено"' in adherence
    assert 'substituted: "изменено"' in planning
    assert 'substituted: "изменено"' in today
