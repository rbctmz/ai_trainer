"""#677 S3 M1: executable acceptance RED, not a runtime implementation.

Run --runxfail to expose the four publication failures. Strict AssertionError-only
XFAIL keeps this spec checkpoint reviewable; remove marks during M3 GREEN.
All inputs are synthetic; Database paths are pytest-owned temporary paths.
"""
from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from data.planning_build_preview_store import get_preview
from tests.smoke._planning_build_confirmation import (
    cycle_fields, ready_parameters as parameters, pin_clock, seeded_db,
)
from tests.smoke._planning_cycle_regressions import client_for
from tests.smoke.test_planning_cycle_writer_guards import writer_state


@pytest.fixture(params=[False, True], ids=["first-cycle", "replace-cycle"])
def scenario(tmp_path, monkeypatch, request):
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, existing=request.param, rested=True)
    with client_for(db) as client:
        yield client, db


def _candidate(db, token: str) -> dict:
    row = get_preview(db, token, origin="planning_ui")
    return json.loads(row["checkpoint_json"])["goal_plan_snapshot"]


def _invalid_prescriptions(plan: Mapping) -> list[tuple[str, str]]:
    """Only explicit persisted failures; this is not the proposed new assessor."""
    failures = []
    for day in plan["session_templates"]:
        for session in day.get("sessions") or [day]:
            if session.get("sport") in {"rest", "off", None}:
                continue
            rows = [session] + list(session.get("legs") or [])
            bad = any(row.get("materialization_status", "materialized") != "materialized"
                      or row.get("failed_bounds") for row in rows)
            if session.get("kind") == "composite":
                bad = bad or not session.get("legs") or any(
                    not leg.get("materialized_steps") for leg in session["legs"]
                )
            else:
                bad = bad or not session.get("materialized_steps")
            if bad:
                failures.append((str(day.get("date")), str(session.get("template_key"))))
    return failures


def _prepare(client, db):
    return client.post("/api/planning/build", json={
        **parameters(), **cycle_fields(db), "events": [], "available_hours": 10,
    })


def test_successful_preview_has_ready_prescriptions_or_explicit_block(scenario):
    client, db = scenario
    before = writer_state(db)
    response = _prepare(client, db)
    body = response.json()
    if response.status_code == 422:
        assert body["code"] == "plan_not_ready"
        assert body["build_readiness"]["status"] == "blocked"
        assert body["build_readiness"]["can_confirm"] is False
        assert body["build_readiness"]["blockers"]
        assert "confirmation" not in body and "preview_id" not in body
        assert writer_state(db) == before
        return
    assert response.status_code == 200, response.text
    failures = _invalid_prescriptions(_candidate(db, body["confirmation"]["preview_id"]))
    assert not failures, f"Usable preview contains {len(failures)} incomplete/infeasible prescriptions"
    assert isinstance(body.get("build_readiness"), dict), "M3 readiness assessment missing"
    assert body["build_readiness"]["status"] == "ready"
    assert body["build_readiness"]["training_suitability"] == "not_assessed"
    assert not body["build_readiness"]["blockers"]
    after = writer_state(db)
    assert {k: v for k, v in after.items() if k != "planning_build_previews"} == {
        k: v for k, v in before.items() if k != "planning_build_previews"
    }


def test_confirmation_cannot_publish_invalid_prescriptions(scenario):
    client, db = scenario
    before_prepare = writer_state(db)
    shown = _prepare(client, db)
    if shown.status_code == 422:
        assert shown.json()["code"] == "plan_not_ready"
        assert writer_state(db) == before_prepare
        return
    assert shown.status_code == 200, shown.text
    token = shown.json()["confirmation"]["preview_id"]
    failures = _invalid_prescriptions(_candidate(db, token))
    before_confirm = writer_state(db)
    payload = {"preview_id": token, "confirm": True}
    confirmed = client.post("/api/planning/build/confirm", json=payload)
    if failures:
        assert confirmed.status_code == 409, (
            f"Confirmation HTTP {confirmed.status_code} published a candidate with {len(failures)} invalid prescriptions"
        )
        assert confirmed.json()["code"] in {"plan_not_ready", "preview_required"}
        assert writer_state(db) == before_confirm
        return
    assert confirmed.status_code == 200, confirmed.text
    assert isinstance(confirmed.json().get("build_readiness"), dict), "M3 readiness assessment missing"
    assert confirmed.json()["build_readiness"]["status"] == "ready"
    after = writer_state(db)
    replay = client.post("/api/planning/build/confirm", json=payload)
    assert replay.status_code == 200
    assert replay.json()["confirmation"]["replayed"] is True
    assert replay.json()["plan_id"] == confirmed.json()["plan_id"]
    assert writer_state(db) == after
