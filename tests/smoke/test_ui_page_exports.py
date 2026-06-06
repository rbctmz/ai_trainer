from __future__ import annotations

import pytest

from ui.pages import render_activities_page, render_dashboard_page


pytestmark = pytest.mark.smoke


def test_ui_pages_export_activities_renderer():
    assert callable(render_activities_page)


def test_ui_pages_export_dashboard_renderer():
    assert callable(render_dashboard_page)
