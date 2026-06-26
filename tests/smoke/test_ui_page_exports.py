from __future__ import annotations

import pytest

from ui.pages import render_activities_page, render_ai_coaching_page, render_dashboard_page, render_hrv_page, render_planning_page, render_sleep_page


pytestmark = pytest.mark.smoke


def test_ui_pages_export_activities_renderer():
    assert callable(render_activities_page)


def test_ui_pages_export_ai_coaching_renderer():
    assert callable(render_ai_coaching_page)


def test_ui_pages_export_dashboard_renderer():
    assert callable(render_dashboard_page)


def test_ui_pages_export_hrv_renderer():
    assert callable(render_hrv_page)


def test_ui_pages_export_planning_renderer():
    assert callable(render_planning_page)


def test_ui_pages_export_sleep_renderer():
    assert callable(render_sleep_page)
