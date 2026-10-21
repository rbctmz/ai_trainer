"""M4 spec RED: desired public behavior, not an implemented dose policy."""
from __future__ import annotations

import pytest

from api import planning_service as ps
from models.planning_build_confirmation import BuildParameters, PlanningBuildPreviewError
from tests.smoke._planning_build_confirmation import pin_clock, protected_state
from tests.smoke._planning_entry_dose import calculate, entry_request, exposure_db, first_week_dose


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    pin_clock(monkeypatch)


@pytest.mark.parametrize("sports,expected", [
    (["running"] * 4, {"run": 4, "bike": 0, "swim": 0}),
    (["running", "cycling", "swimming", "cycling"], {"run": 1, "bike": 2, "swim": 1}),
])
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="M4: per-discipline entry profile not implemented")
def test_build_exposes_frozen_recent_exposure_per_discipline(tmp_path, sports, expected):
    db = exposure_db(tmp_path, sports)
    response, _ = calculate(db)
    assessment = response.get("entry_load")
    assert isinstance(assessment, dict), "Build has no sport-specific entry-load assessment"
    assert assessment["profile"]["as_of"] == "2026-10-16"
    assert {key: value["session_count"] for key, value in assessment["profile"]["sports"].items()} == expected
    assert response["build_readiness"]["training_suitability"] == "not_assessed"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="M4: absent sport exposure must request an explicit baseline")
def test_absent_bike_swim_exposure_does_not_create_publishable_token(tmp_path):
    db = exposure_db(tmp_path, ["running"] * 4)
    before = protected_state(db)
    code = None
    try:
        ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(entry_request(db)), origin="planning_ui")
    except PlanningBuildPreviewError as error:
        code = error.code
    assert code == "entry_dose_required", f"Expected an explicit starting-dose request, got {code!r}"
    assert protected_state(db) == before
    with db._connect() as conn:
        assert conn.execute("SELECT count(*) FROM planning_build_previews").fetchone()[0] == 0


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="M4: declared per-sport limits are currently ignored")
def test_final_entry_dose_respects_declared_limits_or_explicitly_blocks(tmp_path):
    db = exposure_db(tmp_path, ["running"] * 4)
    limits = {sport: {"source": "athlete_declared", "weekly_minutes": minutes,
                      "weekly_sessions": 1, "max_session_minutes": minutes}
              for sport, minutes in (("bike", 20), ("swim", 20), ("run", 45))}
    response, plan = calculate(db, limits=limits)
    assessment = response.get("entry_load") or {}
    if assessment.get("status") == "blocked":
        assert assessment["can_publish"] is False
        assert assessment["blockers"]
    else:
        excess = {sport: dose for sport, dose in first_week_dose(plan).items()
                  if dose["minutes"] > limits[sport]["weekly_minutes"]
                  or dose["sessions"] > limits[sport]["weekly_sessions"]}
        assert not excess, f"Declared entry limits exceeded: {excess}"


def test_frozen_entry_characterization_never_changes_active_plan_or_settings(tmp_path):
    db = exposure_db(tmp_path, ["running"] * 4)
    before = protected_state(db)
    calculate(db)
    assert protected_state(db) == before
