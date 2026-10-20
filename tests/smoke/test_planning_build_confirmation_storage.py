"""#685 / #677 S3 M2: whole-payload oracle for the explicit catalog version.

Baseline hashes cover every field of the complete checkpoint and legacy public
response, not only TSS. The fixture is synthetic and clocks are pinned. It is
not regenerated automatically: inspect any changed component before accepting
new hashes. The pre-extraction v3 fixture remains unchanged; S3 M2 uses a
separate catalog-v4 oracle after reproducing all six old cases on M1 source. DB row creation time and assigned response plan ID are excluded;
plan_revision, prescriptions and all provenance inside checkpoint_data are not.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.smoke._planning_build_confirmation import (
    MODES,
    REVISION,
    characterization,
    checkpoint_payload,
    internal_build,
    parameters,
    pin_clock,
    protected_state,
    seeded_db,
)

BASELINE = Path(__file__).resolve().parents[1] / "fixtures/planning_build_confirmation_catalog_v4_baseline.json"


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    pin_clock(monkeypatch)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("existing", [False, True], ids=["first-plan", "existing-plan"])
def test_internal_build_complete_payload_matches_versioned_catalog_baseline(tmp_path, mode, existing):
    db = seeded_db(tmp_path, existing=existing, rested=True)
    before = protected_state(db)
    result = internal_build(db, parameters(mode))
    checkpoint = checkpoint_payload(db)
    plan = checkpoint["goal_plan_snapshot"]
    expected = json.loads(BASELINE.read_text())
    key = f"{mode}:{'existing' if existing else 'first'}"
    actual = characterization(result, checkpoint)
    assert actual == expected["cases"][key]
    assert len(protected_state(db)["checkpoints"]) == len(before["checkpoints"]) + 1
    assert plan["plan_revision"] == REVISION.isoformat()
    assert plan["checkpoint_parent_id"] == (1 if existing else None)
    assert plan["events"] and plan["science_audit"]["policy_version"]
    assert result["constraint_application"]["applied_count"] == 1
    assert any(template.get("prescription_fingerprint") for template in plan["session_templates"])
    if mode == "training_goal":
        assert any(template.get("kind") == "composite" for template in plan["session_templates"])
    nested = [session for template in plan["session_templates"]
              for session in template.get("sessions", [])]
    assert nested and all(session.get("session_id") for session in nested)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("existing", [False, True], ids=["first-plan", "existing-plan"])
def test_trusted_preview_preserves_history_settings_and_calculation(tmp_path, mode, existing):
    db = seeded_db(tmp_path, existing=existing, rested=True)
    before = protected_state(db)
    preview = internal_build(db, parameters(mode), persist=False)
    assert protected_state(db) == before
    saved = internal_build(db, parameters(mode))
    assert preview["plan_id"] is None
    assert preview["confirmation_required"] is True
    assert saved["confirmation_required"] is False
    # Unlike a TSS-only check, this compares the entire returned semantic view.
    excluded = {"plan_id", "confirmation_required"}
    assert {k: v for k, v in preview.items() if k not in excluded} == {
        k: v for k, v in saved.items() if k not in excluded
    }
    after = protected_state(db)
    assert after["checkpoints"][:-1] == before["checkpoints"]
    # Trusted persist rewrites the explicitly supplied demand setting today;
    # its SQLite updated_at may change, while the saved values must not.
    assert [row[:2] for row in after["settings"]] == [row[:2] for row in before["settings"]]
