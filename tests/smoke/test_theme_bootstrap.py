"""Smoke tests for theme bootstrap resolution.

Stage 3 of theme consolidation. The resolution of the initial dark-mode
choice is a pure preference cascade (stored > system > default) that must be
unit-testable without rendering. The JS roundtrip feeds stored/system
values in; this function decides.
"""
from __future__ import annotations

import pytest

from ui.theme_bootstrap import resolve_initial_dark_mode


pytestmark = pytest.mark.smoke


def test_stored_preference_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit stored choice overrides the system preference."""
    assert resolve_initial_dark_mode(stored="true", system_prefers_dark=False) is True
    assert resolve_initial_dark_mode(stored="false", system_prefers_dark=True) is False


def test_system_preference_used_when_nothing_stored() -> None:
    """With no stored choice, fall back to the OS prefers-color-scheme."""
    assert resolve_initial_dark_mode(stored=None, system_prefers_dark=True) is True
    assert resolve_initial_dark_mode(stored=None, system_prefers_dark=False) is False


def test_defaults_to_light_when_no_signal() -> None:
    """No stored choice and no system signal -> light (not dark)."""
    assert resolve_initial_dark_mode(stored=None, system_prefers_dark=None) is False


def test_invalid_stored_value_falls_back_to_system() -> None:
    """A corrupt localStorage entry must not crash; fall back to system."""
    assert resolve_initial_dark_mode(stored="garbage", system_prefers_dark=True) is True
    assert resolve_initial_dark_mode(stored="", system_prefers_dark=False) is False
