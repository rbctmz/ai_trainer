from __future__ import annotations

import pytest

from ui.components import render_chat_management


pytestmark = pytest.mark.smoke


def test_ui_components_export_chat_management_renderer():
    assert callable(render_chat_management)
