"""BDD source gates for UI beta v2 M1 (#265): dashboard cards -> drill-downs.

The athlete enters /activities, /sleep, /hrv through clickable cards on
«Обзор», always sees «← Обзор» on the detail pages, and the primary nav keeps
«Обзор» active. The technical SectionLinks row must be gone.
"""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]

DASHBOARD = REPO_ROOT / "web/app/dashboard/page.tsx"
NAV = REPO_ROOT / "web/components/Nav.tsx"
SLEEP_WIDGET = REPO_ROOT / "web/components/dashboard/SleepWidget.tsx"
STATUS_ROW = REPO_ROOT / "web/components/dashboard/StatusRow.tsx"
ACTIVITIES_WIDGET = REPO_ROOT / "web/components/dashboard/ActivitiesWidget.tsx"
DRILL_HEADER = REPO_ROOT / "web/components/ui/DrillDownHeader.tsx"
DETAIL_PAGES = [
    REPO_ROOT / "web/app/activities/page.tsx",
    REPO_ROOT / "web/app/sleep/page.tsx",
    REPO_ROOT / "web/app/hrv/page.tsx",
]


def test_section_links_row_is_removed_and_activities_card_rendered():
    source = DASHBOARD.read_text(encoding="utf-8")

    assert "Разделы" not in source
    assert "SectionLinks" not in source
    assert "ActivitiesWidget" in source


def test_sleep_card_is_a_link_to_sleep():
    source = SLEEP_WIDGET.read_text(encoding="utf-8")

    assert "Link" in source
    assert 'href="/sleep"' in source


def test_hrv_metric_card_is_a_link_to_hrv():
    source = STATUS_ROW.read_text(encoding="utf-8")

    assert "Link" in source
    assert 'href="/hrv"' in source


def test_activities_card_exists_with_totals():
    assert ACTIVITIES_WIDGET.exists()
    source = ACTIVITIES_WIDGET.read_text(encoding="utf-8")

    assert "/api/activities?days=30" in source
    assert 'href="/activities"' in source
    assert "Link" in source
    assert "TSS" in source


def test_drill_down_header_component_exists():
    assert DRILL_HEADER.exists()
    source = DRILL_HEADER.read_text(encoding="utf-8")

    assert "←" in source
    assert "Обзор" in source
    assert 'href="/dashboard"' in source


def test_detail_pages_use_drill_down_header():
    for page in DETAIL_PAGES:
        source = page.read_text(encoding="utf-8")
        assert "DrillDownHeader" in source
        assert "<DrillDownHeader" in source


def test_nav_keeps_overview_active_for_detail_routes():
    source = NAV.read_text(encoding="utf-8")

    assert '"/activities"' in source
    assert '"/sleep"' in source
    assert '"/hrv"' in source
    assert "pathname.startsWith(l.href" in source
