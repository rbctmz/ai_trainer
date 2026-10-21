"""M4b frozen input/HTTP shape: temporary synthetic databases only."""
from copy import deepcopy

import pytest

from api import planning_service as ps
from api.routers.planning import BuildRequest
from models.planning_build_confirmation import BuildParameters
from tests.smoke._planning_build_confirmation import pin_clock, protected_state
from tests.smoke._planning_entry_dose import entry_request, exposure_db


LIMITS = {sport: {"source": "athlete_declared", "weekly_minutes": minutes,
                  "weekly_sessions": 2, "max_session_minutes": minutes / 2}
          for sport, minutes in (("run", 90), ("bike", 120), ("swim", 60))}


@pytest.fixture
def captured(tmp_path, monkeypatch):
    pin_clock(monkeypatch)
    db = exposure_db(tmp_path, ["running"] * 4)
    raw = entry_request(db, limits=deepcopy(LIMITS))
    return db, raw, ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))


def test_capture_retains_normalized_declarations_and_policy_stamp(captured):
    db, raw, snapshot = captured
    before = protected_state(db)
    values = snapshot.parameters.as_dict()
    assert values.get("initial_dose_limits") == LIMITS
    assert values.get("history_coverage") == raw["history_coverage"]
    assert snapshot.context()["versions"].get("entry_load") == "entry-load-v1"
    assert protected_state(db) == before
    # These fields must enter the frozen digest, not only the response.
    changed = deepcopy(raw)
    changed["initial_dose_limits"]["run"]["weekly_minutes"] += 1
    fresh = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(changed))
    assert fresh.dependency_digest != snapshot.dependency_digest


def test_http_build_request_accepts_typed_starting_information(captured):
    _, raw, _ = captured
    request = BuildRequest.model_validate(raw)
    assert request.model_dump(mode="json")["initial_dose_limits"] == LIMITS
    assert request.model_dump(mode="json")["history_coverage"] == raw["history_coverage"]


def test_existing_preparation_echoes_inputs_without_early_entry_publish_claim(captured):
    db, raw, snapshot = captured
    before = protected_state(db)
    response = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui")
    assert response["parameters"].get("history_coverage") == raw["history_coverage"]
    assert response["parameters"].get("initial_dose_limits") == LIMITS
    # Generation/final assignment publication guard is M4c, not implemented here.
    assert response.get("entry_load") is None
    assert protected_state(db) == before


def all_tables(db):
    with db._connect() as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in names}


def test_profile_uses_the_frozen_frame_after_database_and_request_change(captured):
    from datetime import date
    from models.planning_entry_load import build_entry_exposure_profile

    db, raw, snapshot = captured
    frame = snapshot.sources()["activities"]
    rows = [dict(zip(frame["columns"], values, strict=True)) for values in frame["data"]]
    before = all_tables(db)
    frozen = build_entry_exposure_profile(rows, as_of=date.fromisoformat(snapshot.context()["athlete_day"]),
                                         timezone=snapshot.context()["athlete_timezone"],
                                         coverage=snapshot.parameters.as_dict()["history_coverage"])
    assert {s: e["session_count"] for s, e in frozen["sports"].items()} == {"bike": 0, "run": 4, "swim": 0}
    assert all_tables(db) == before
    with db._connect() as conn:
        conn.execute("UPDATE activities SET sport='cycling' WHERE activity_id LIKE 'recent-%'")
    raw["initial_dose_limits"]["run"]["weekly_minutes"] = 1000
    assert build_entry_exposure_profile(rows, as_of=date.fromisoformat(snapshot.context()["athlete_day"]),
                                       timezone=snapshot.context()["athlete_timezone"],
                                       coverage=snapshot.parameters.as_dict()["history_coverage"]) == frozen
    assert snapshot.parameters.as_dict()["initial_dose_limits"] == LIMITS
    assert ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw)).dependency_digest != snapshot.dependency_digest


@pytest.mark.parametrize("change", ["coverage", "policy", "lineage", "duration"])
def test_each_new_named_dependency_changes_digest_without_active_writes(captured, monkeypatch, change):
    db, raw, snapshot = captured
    if change == "coverage":
        raw["history_coverage"]["status"] = "partial"
    elif change == "policy":
        monkeypatch.setattr(ps, "ENTRY_LOAD_POLICY_VERSION", "entry-load-test-next")
    else:
        with db._connect() as conn:
            if change == "duration":
                conn.execute("UPDATE activities SET duration_minutes=duration_minutes+1 WHERE activity_id='recent-0'")
            else:
                conn.execute("INSERT INTO activity_provider_links(canonical_activity_id,provider,provider_activity_id,"
                             "external_provider,external_id) VALUES ('recent-0','intervals','synthetic-lineage','garmin','envelope')")
    before = all_tables(db)
    assert ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw)).dependency_digest != snapshot.dependency_digest
    assert all_tables(db) == before


@pytest.mark.parametrize("invalid", [
    {"initial_dose_limits": {"run": {**LIMITS["run"], "weekly_sessions": True}}},
    {"initial_dose_limits": {"run": {**LIMITS["run"], "weekly_minutes": -1}}},
    {"initial_dose_limits": {"cycling": LIMITS["bike"]}},
    {"history_coverage": {"status": "user_reported_complete", "start_date": "2026-10-15", "end_date_exclusive": "2026-10-16"}},
])
def test_non_http_prepare_rejects_invalid_declarations_before_any_table_write(captured, invalid):
    db, raw, _ = captured
    before = all_tables(db)
    with pytest.raises(ValueError):
        ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({**raw, **invalid}), origin="coach")
    assert all_tables(db) == before


def test_typed_limits_survive_prepare_confirm_and_applied_replay(captured):
    db, raw, _ = captured
    shown = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui")
    applied = ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui")
    assert applied["parameters"]["initial_dose_limits"] == LIMITS
    assert applied["parameters"]["history_coverage"] == raw["history_coverage"]
    before = all_tables(db)
    replay = ps.confirm_plan_build(db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui")
    assert replay["confirmation"]["replayed"] is True
    assert replay["parameters"] == applied["parameters"]
    assert all_tables(db) == before


@pytest.mark.parametrize("mode", ["event_goal", "training_goal", "manual"])
@pytest.mark.parametrize("existing", [False, True])
def test_added_policy_stamp_changes_only_readiness_binding_not_prescription(tmp_path, monkeypatch, mode, existing):
    from dataclasses import replace
    import json
    from tests.smoke._planning_build_confirmation import parameters, seeded_db
    from models.planning_build_confirmation import canonical_json

    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, existing=existing, rested=True)
    current = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(parameters(mode)))
    context = current.context()
    assert context["versions"].pop("entry_load") == "entry-load-v1"
    historical_context = replace(current, context_json=canonical_json(context))
    before = ps._calculate_plan_build(historical_context)
    after = ps._calculate_plan_build(current)
    for field in ("checkpoint_json", "response_json"):
        old, new = json.loads(getattr(before, field)), json.loads(getattr(after, field))
        left, right = old.get("goal_plan_snapshot", old), new.get("goal_plan_snapshot", new)
        assert left["build_readiness"].pop("candidate_fingerprint") != right["build_readiness"].pop("candidate_fingerprint")
        assert old == new
