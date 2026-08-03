"""Regression lock for #323: the modern-session detector contract.

Issue #323 considered using lineage markers to catch a hypothetical
catalog-lost modern stub. That fix is NOT applicable: `ensure_session_identities`
stamps lineage markers onto ANY legacy record, so they cannot distinguish
«modern stub that lost catalog markers» from «legacy that gained identity via
migration». Using them would break the pre-catalog legacy fallback (#299).
These tests pin the current contract so neither direction can flip silently.
"""
from __future__ import annotations

import pytest

from models.workout_catalog import (
    planned_session_is_executable,
    planned_session_requires_repair,
)


pytestmark = pytest.mark.smoke


def _legacy_like_session(**overrides):
    base = {
        "sport": "run",
        "session_role": "easy",
        "kind": "single",
        "session_id": "legacy_x",
        # Lineage markers that ensure_session_identities adds to ANY record:
        "session_material_fingerprint": "abc",
        "session_identity_rule_version": "v1",
        "replaces_session_id": None,
    }
    base.update(overrides)
    return base


def test_lineage_markers_alone_do_not_mark_session_modern():
    session = _legacy_like_session()

    assert not planned_session_is_executable(session)
    assert not planned_session_requires_repair(session)


def test_manual_prefix_stub_is_modern_and_requires_repair():
    session = _legacy_like_session(template_key="manual:broken")

    assert planned_session_requires_repair(session)


def test_materialization_status_marks_modern_stub():
    session = _legacy_like_session(materialization_status="broken")

    assert planned_session_requires_repair(session)


def test_catalog_version_marks_modern_stub():
    session = _legacy_like_session(catalog_version="2026.1")

    assert planned_session_requires_repair(session)


def test_executable_modern_session_does_not_require_repair():
    session = _legacy_like_session(
        template_key="manual:x",
        materialized_steps=[{"name": "step"}],
    )

    assert planned_session_is_executable(session)
    assert not planned_session_requires_repair(session)


def test_event_off_and_race_sessions_never_require_repair():
    for kind, sport, role in (
        ("event", "run", "easy"),
        ("single", "off", "easy"),
        ("single", "run", "race"),
    ):
        session = _legacy_like_session(kind=kind, sport=sport, session_role=role)
        assert not planned_session_requires_repair(session)
