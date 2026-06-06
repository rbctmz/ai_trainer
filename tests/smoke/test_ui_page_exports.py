from __future__ import annotations

import pytest

from ui.pages import render_activities_page


pytestmark = pytest.mark.smoke


def test_ui_pages_export_activities_renderer():
    assert callable(render_activities_page)
