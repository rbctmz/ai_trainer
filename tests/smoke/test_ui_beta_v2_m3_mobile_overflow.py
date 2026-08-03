"""BDD source gates for UI beta v2 M3 (#267): mobile overflow repair.

At 390px the primary nav, planning tabs/tables and the Coach layout must not
expand the document body: the nav keeps its four destinations visible, wide
tables scroll inside their own container, and Coach grid children cannot blow
out the viewport.
"""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]

NAV = REPO_ROOT / "web/components/Nav.tsx"
PLANNING = REPO_ROOT / "web/app/planning/page.tsx"
BUILDER = REPO_ROOT / "web/components/planning/PlanBuilder.tsx"
COACH = REPO_ROOT / "web/app/coach/page.tsx"
ACTIVITIES = REPO_ROOT / "web/app/activities/page.tsx"


def test_nav_keeps_destinations_visible_on_mobile():
    source = NAV.read_text(encoding="utf-8")

    assert "hidden" in source and "sm:inline" in source  # бренд прячется на телефоне
    assert "sm:px-3" in source  # компактные ссылки на mobile
    assert "overflow-x-auto" in source  # страховочный локальный скролл навбара


def test_planning_wide_tables_scroll_locally():
    page = PLANNING.read_text(encoding="utf-8")
    builder = BUILDER.read_text(encoding="utf-8")

    assert page.count("overflow-x-auto rounded-card") >= 3
    assert "overflow-x-auto rounded-card" in builder


def test_activities_table_scrolls_locally():
    source = ACTIVITIES.read_text(encoding="utf-8")

    assert "overflow-x-auto rounded-card" in source


def test_coach_grid_children_cannot_blow_out_viewport():
    source = COACH.read_text(encoding="utf-8")

    assert "lg:grid-cols-[260px_1fr]" in source
    assert source.count("min-w-0") >= 2
