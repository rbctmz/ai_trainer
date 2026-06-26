"""Smoke tests for the welcome-page Garmin path gating.

P1a-full regression: when acceptance mode runs with real Garmin login
explicitly allowed (ACCEPTANCE_DISABLE_GARMIN=0), the welcome surface must
still present the real Garmin onboarding path instead of hiding it behind a
demo-only block that claims login is disabled.

The resolver reads its state through ``services.acceptance_mode``, which in
turn reads ``config.settings.Settings``. Tests mock those Settings flags at
the source so they stay valid regardless of what ``ui.pages.welcome`` imports.
"""
from __future__ import annotations

import pytest

from ui.pages.welcome import resolve_welcome_garmin_mode


pytestmark = pytest.mark.smoke


def test_real_garmin_path_offered_in_acceptance_mode_when_login_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACCEPTANCE_DISABLE_GARMIN=0 inside acceptance mode must surface the
    real Garmin path, not a demo-only block."""
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_MODE", True)
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_DISABLE_GARMIN", False)

    mode = resolve_welcome_garmin_mode()

    assert mode.is_acceptance_mode is True
    assert mode.garmin_login_allowed is True
    assert mode.show_real_garmin_path is True
    assert mode.show_demo_only_acceptance_block is False


def test_demo_only_block_shown_when_garmin_disabled_in_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default acceptance contract (login disabled) keeps the demo-only block."""
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_MODE", True)
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_DISABLE_GARMIN", True)

    mode = resolve_welcome_garmin_mode()

    assert mode.is_acceptance_mode is True
    assert mode.garmin_login_allowed is False
    assert mode.show_real_garmin_path is False
    assert mode.show_demo_only_acceptance_block is True


def test_normal_mode_offers_real_garmin_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside acceptance mode, the real Garmin path is always offered."""
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_MODE", False)

    mode = resolve_welcome_garmin_mode()

    assert mode.is_acceptance_mode is False
    assert mode.show_real_garmin_path is True
    assert mode.show_demo_only_acceptance_block is False


def test_garmin_status_text_reflects_real_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user-facing garmin-status line must not claim login is disabled when
    it is in fact allowed."""
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_MODE", True)
    monkeypatch.setattr("config.settings.Settings.ACCEPTANCE_DISABLE_GARMIN", False)

    mode = resolve_welcome_garmin_mode()

    assert mode.garmin_login_allowed is True
    assert "отключ" not in mode.garmin_status_text.lower()
    assert mode.garmin_status_text  # non-empty guidance
