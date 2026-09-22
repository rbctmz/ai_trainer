"""RED contract for Issue #609: one server-owned session projection.

The five fixtures pin the first bounded milestone: matched single, complete
brick, partial brick, ambiguous match, and provider-free/non-mutating read.
The composer and service do not exist at the RED checkpoint, so each test
fails at its local import without preventing collection of the other cases.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from tests.smoke.test_api_planning import _reconciliation_db
from tests.smoke.test_reconciliation_service_migration import _table_snapshots


pytestmark = pytest.mark.smoke


def _activity(
    activity_id: str,
    sport: str,
    tss: float,
    duration_minutes: float,
    started_at_utc: str,
) -> dict:
    return {
        "activity_id": activity_id,
        "date": "2026-07-08",
        "sport": sport,
        "tss": tss,
        "duration_minutes": duration_minutes,
        "started_at_utc": started_at_utc,
    }


def _single_row() -> dict:
    actual = _activity(
        "ride-main",
        "bike",
        52.0,
        61.0,
        "2026-07-08T06:00:00Z",
    )
    return {
        "session_id": "ats_single",
        "date": "2026-07-08",
        "sport": "bike",
        "role": "easy",
        "name": "Endurance ride",
        "tss": 50.0,
        "duration_minutes": 60,
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "evidence": ["athlete selected ride-main"],
        "actual_activity_ids": ["ride-main"],
        "actual_activities": [actual],
        "candidate_activities": [],
        "actual_total_tss": 52.0,
        "actual_duration_minutes": 61.0,
        "actual_sport": "bike",
        "actual_role": "easy",
        "adherence": "exact",
    }


def _reconciliation(row: dict, *, unplanned: list[dict] | None = None) -> dict:
    return {
        "has_plan": True,
        "rule_version": "plan_actual_match_v2",
        "base_checkpoint_id": 63,
        "as_of": "2026-07-08",
        "provider": {"status": "disabled"},
        "data_quality": {"status": "sufficient", "reasons": []},
        "rows": [row],
        "unplanned_activities": list(unplanned or []),
    }


def _build_projection(
    reconciliation: dict,
    *,
    session_id: str,
    match_revision: dict | None = None,
    feedback: dict | None = None,
) -> dict:
    from models.session_projection import build_session_projection

    return build_session_projection(
        reconciliation,
        session_id=session_id,
        match_revision=match_revision,
        feedback=feedback,
    )


def test_single_session_projection_keeps_identity_revisions_and_day_load() -> None:
    extra = _activity(
        "walk-extra",
        "other",
        8.0,
        25.0,
        "2026-07-08T18:00:00Z",
    )
    result = _build_projection(
        _reconciliation(_single_row(), unplanned=[extra]),
        session_id="ats_single",
        match_revision={"id": 17, "revision": 2},
    )

    assert result["schema_version"] == "session_projection_v1"
    assert result["session_id"] == "ats_single"
    assert result["projection_status"] == "matched"
    assert result["evidence_revision"] == {
        "planning_checkpoint_id": 63,
        "match_revision_id": 17,
        "match_revision": 2,
        "feedback_revision_id": None,
        "feedback_revision": None,
        "reconciliation_rule_version": "plan_actual_match_v2",
        "as_of": "2026-07-08",
        "provider_status": "disabled",
    }
    assert result["plan"]["duration_minutes"] == 60
    assert result["plan"]["load_tss"] == 50.0
    assert result["fact"]["completion_status"] == "complete"
    assert result["fact"]["actual_activity_ids"] == ["ride-main"]
    assert result["fact"]["duration_minutes"] == 61.0
    assert result["fact"]["load_tss"] == 52.0
    assert result["deviation"]["duration_delta_minutes"] == 1.0
    assert result["deviation"]["load_delta_tss"] == 2.0
    assert result["cause"] == {
        "status": "unknown",
        "code": "no_explicit_cause_evidence",
        "evidence_refs": [],
    }
    assert result["load"] == {
        "planned_tss": 50.0,
        "matched_tss": 52.0,
        "other_matched_tss": 0.0,
        "additional_unmatched_tss": 8.0,
        "day_total_tss": 60.0,
    }
    assert result["load"]["day_total_tss"] == (
        result["load"]["matched_tss"]
        + result["load"]["other_matched_tss"]
        + result["load"]["additional_unmatched_tss"]
    )


def _brick_row(*, activities: list[dict], match_status: str) -> dict:
    actual_tss = round(sum(float(item["tss"]) for item in activities), 1)
    actual_duration = round(
        sum(float(item["duration_minutes"]) for item in activities),
        1,
    )
    complete = len(activities) == 2
    return {
        "session_id": "ats_brick",
        "date": "2026-07-08",
        "kind": "composite",
        "sport": "brick",
        "role": "long",
        "name": "Bike to run",
        "tss": 76.0,
        "duration_minutes": 105,
        "transition_minutes": 5.0,
        "legs": [
            {
                "leg_id": "ats_brick:1",
                "leg_index": 1,
                "sport": "bike",
                "target_tss": 57.0,
                "duration_minutes": 70.0,
            },
            {
                "leg_id": "ats_brick:2",
                "leg_index": 2,
                "sport": "run",
                "target_tss": 19.0,
                "duration_minutes": 30.0,
            },
        ],
        "match_status": match_status,
        "match_method": "ai_trainer_external_id",
        "confidence": 1.0 if complete else 0.5,
        "evidence": [
            "both external leg ids matched"
            if complete
            else "only the bike external leg id matched"
        ],
        "actual_activity_ids": [item["activity_id"] for item in activities],
        "actual_activities": activities,
        "candidate_activities": [],
        "actual_total_tss": actual_tss,
        "actual_duration_minutes": actual_duration,
        "actual_sport": "" if complete else "bike",
        "actual_role": "long" if complete else None,
        "composite_execution": {
            "planned_sports": ["bike", "run"],
            "actual_sports": [item["sport"] for item in activities],
            "structure_match": True if complete else False,
            "planned_tss": 76.0,
            "actual_tss": actual_tss,
            "planned_transition_minutes": 5.0,
            "actual_transition_minutes": 6.0 if complete else None,
            "transition_delta_minutes": 1.0 if complete else None,
        },
        "adherence": "exact" if complete else "unknown",
    }


def test_two_leg_brick_is_one_parent_with_ordered_fact_and_no_double_count() -> None:
    bike = _activity(
        "brick-bike",
        "bike",
        55.0,
        70.0,
        "2026-07-08T08:00:00Z",
    )
    run = _activity(
        "brick-run",
        "run",
        18.0,
        30.0,
        "2026-07-08T09:16:00Z",
    )
    extra = _activity(
        "walk-extra",
        "other",
        5.0,
        20.0,
        "2026-07-08T18:00:00Z",
    )
    result = _build_projection(
        _reconciliation(
            _brick_row(activities=[bike, run], match_status="matched"),
            unplanned=[extra],
        ),
        session_id="ats_brick",
        match_revision={"id": 22, "revision": 1},
    )

    assert result["session_id"] == "ats_brick"
    assert result["projection_status"] == "matched"
    assert [item["leg_id"] for item in result["plan"]["legs"]] == [
        "ats_brick:1",
        "ats_brick:2",
    ]
    assert [item["sport"] for item in result["plan"]["legs"]] == ["bike", "run"]
    assert [item["activity_id"] for item in result["fact"]["legs"]] == [
        "brick-bike",
        "brick-run",
    ]
    assert [item["planned_leg_id"] for item in result["fact"]["legs"]] == [
        "ats_brick:1",
        "ats_brick:2",
    ]
    assert result["fact"]["transition"] == {"actual_minutes": 6.0}
    assert result["deviation"]["structure_match"] is True
    assert result["deviation"]["transition_delta_minutes"] == 1.0
    assert result["load"] == {
        "planned_tss": 76.0,
        "matched_tss": 73.0,
        "other_matched_tss": 0.0,
        "additional_unmatched_tss": 5.0,
        "day_total_tss": 78.0,
    }


def test_partial_brick_preserves_only_observed_leg() -> None:
    bike = _activity(
        "brick-bike",
        "bike",
        55.0,
        70.0,
        "2026-07-08T08:00:00Z",
    )
    result = _build_projection(
        _reconciliation(
            _brick_row(activities=[bike], match_status="ambiguous"),
        ),
        session_id="ats_brick",
    )

    assert result["projection_status"] == "partial"
    assert result["fact"]["completion_status"] == "incomplete"
    assert result["fact"]["actual_activity_ids"] == ["brick-bike"]
    assert result["fact"]["legs"] == [
        {
            "planned_leg_id": "ats_brick:1",
            "leg_index": 1,
            "activity_id": "brick-bike",
            "sport": "bike",
            "duration_minutes": 70.0,
            "load_tss": 55.0,
        }
    ]
    assert all(item["sport"] != "run" for item in result["fact"]["legs"])
    assert result["fact"]["transition"] == {"actual_minutes": None}
    assert result["deviation"]["structure_match"] is None
    assert result["cause"] == {
        "status": "unknown",
        "code": "no_explicit_cause_evidence",
        "evidence_refs": [],
    }
    assert result["confidence"]["status"] == "partial_evidence"
    assert result["data_quality"]["status"] == "data_gap"
    assert "missing_planned_leg" in result["data_quality"]["reasons"]
    assert result["load"]["matched_tss"] == 55.0
    assert result["load"]["day_total_tss"] == 55.0


def test_partial_run_leg_keeps_second_planned_identity() -> None:
    run = _activity(
        "brick-run",
        "run",
        18.0,
        30.0,
        "2026-07-08T09:16:00Z",
    )
    result = _build_projection(
        _reconciliation(
            _brick_row(activities=[run], match_status="ambiguous"),
        ),
        session_id="ats_brick",
    )

    assert result["projection_status"] == "partial"
    assert result["fact"]["legs"] == [
        {
            "planned_leg_id": "ats_brick:2",
            "leg_index": 2,
            "activity_id": "brick-run",
            "sport": "run",
            "duration_minutes": 30.0,
            "load_tss": 18.0,
        }
    ]


def test_ambiguous_match_needs_confirmation_without_cause_or_completion() -> None:
    row = deepcopy(_single_row())
    candidates = [
        _activity("ride-a", "bike", 30.0, 40.0, "2026-07-08T06:00:00Z"),
        _activity("ride-b", "bike", 34.0, 45.0, "2026-07-08T18:00:00Z"),
    ]
    row.update(
        {
            "match_status": "ambiguous",
            "match_method": "date_sport_heuristic",
            "confidence": 0.35,
            "evidence": ["two plausible rides require athlete confirmation"],
            "actual_activity_ids": [],
            "actual_activities": [],
            "candidate_activities": candidates,
            "actual_total_tss": 0.0,
            "actual_duration_minutes": 0.0,
            "actual_sport": "",
            "actual_role": None,
            "adherence": "unknown",
        }
    )
    result = _build_projection(
        _reconciliation(row, unplanned=candidates),
        session_id="ats_single",
    )

    assert result["projection_status"] == "needs_confirmation"
    assert result["fact"]["completion_status"] == "needs_confirmation"
    assert result["fact"]["actual_activity_ids"] == []
    assert result["fact"]["candidate_activity_ids"] == ["ride-a", "ride-b"]
    assert result["cause"] == {
        "status": "needs_confirmation",
        "code": "ambiguous_match",
        "evidence_refs": [],
    }
    assert result["confidence"]["status"] == "needs_confirmation"
    assert result["confidence"]["score"] == 0.35
    assert result["data_quality"] == {
        "status": "data_gap",
        "reasons": ["ambiguous_match"],
    }
    assert result["load"] == {
        "planned_tss": 50.0,
        "matched_tss": 0.0,
        "other_matched_tss": 0.0,
        "additional_unmatched_tss": 64.0,
        "day_total_tss": 64.0,
    }


def test_session_projection_read_is_provider_free_and_non_mutating(
    tmp_path,
    monkeypatch,
) -> None:
    from services import intervals_icu
    from services.session_projection import session_projection_at

    def _forbidden_get_client():
        raise AssertionError("session projection must not access a provider")

    monkeypatch.setattr(intervals_icu, "get_client", _forbidden_get_client)
    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item
        for item in plan["session_templates"]
        if item.get("date") == "2026-07-08"
    )
    before = _table_snapshots(db)

    first = session_projection_at(
        db,
        session_id=target["session_id"],
        as_of="2026-07-13",
        weeks=1,
    )
    second = session_projection_at(
        db,
        session_id=target["session_id"],
        as_of="2026-07-13",
        weeks=1,
    )

    assert first == second
    assert first["evidence_revision"]["provider_status"] == "disabled"
    assert _table_snapshots(db) == before


def test_latest_explicit_match_revision_wins_without_a_second_matcher(tmp_path) -> None:
    from services.session_projection import session_projection_at

    db, plan = _reconciliation_db(tmp_path)
    target = next(
        item
        for item in plan["session_templates"]
        if item.get("date") == "2026-07-08"
    )
    db.save_activities(
        [
            {
                "activity_id": "second-ride",
                "date": "2026-07-08",
                "started_at_utc": "2026-07-08T18:00:00Z",
                "sport": "cycling",
                "duration_minutes": 30,
                "tss": 18.0,
            }
        ]
    )
    common = {
        "target_key": f"session:{target['session_id']}",
        "session_id": target["session_id"],
        "base_checkpoint_id": 1,
        "session_date": "2026-07-08",
        "confidence": 1.0,
        "planned_snapshot": {
            "session_id": target["session_id"],
            "sport": "bike",
            "tss": 22.0,
        },
        "actual_snapshot": {"sport": "bike", "role": "easy"},
        "rule_version": "plan_actual_match_v2",
    }
    confirmed = db.save_plan_actual_match(
        {
            **common,
            "fingerprint": "session-projection-confirmed",
            "match_status": "matched",
            "match_method": "user_confirmed",
            "actual_activity_ids": ["actual-2026-07-08"],
            "evidence": ["athlete selected the morning ride"],
        }
    )

    selected = session_projection_at(
        db,
        session_id=target["session_id"],
        as_of="2026-07-13",
        weeks=1,
    )

    assert selected["projection_status"] == "matched"
    assert selected["fact"]["actual_activity_ids"] == ["actual-2026-07-08"]
    assert selected["confidence"]["match_method"] == "user_confirmed"
    assert selected["evidence_revision"]["match_revision_id"] == confirmed["id"]
    assert selected["evidence_revision"]["match_revision"] == 1

    unmatched = db.save_plan_actual_match(
        {
            **common,
            "fingerprint": "session-projection-unmatched",
            "supersedes_match_id": confirmed["id"],
            "match_status": "unmatched",
            "match_method": "user_unmatched",
            "actual_activity_ids": [],
            "actual_snapshot": {},
            "evidence": ["athlete rejected both candidates"],
        }
    )

    rejected = session_projection_at(
        db,
        session_id=target["session_id"],
        as_of="2026-07-13",
        weeks=1,
    )

    assert rejected["projection_status"] == "unmatched"
    assert rejected["fact"]["completion_status"] == "not_observed"
    assert rejected["fact"]["actual_activity_ids"] == []
    assert rejected["confidence"]["status"] == "confirmed"
    assert rejected["confidence"]["match_method"] == "user_unmatched"
    assert rejected["evidence_revision"]["match_revision_id"] == unmatched["id"]
    assert rejected["evidence_revision"]["match_revision"] == 2


def test_malformed_legacy_numbers_fail_closed_without_losing_known_facts() -> None:
    row = _single_row()
    row.update(
        {
            "tss": "legacy-not-a-number",
            "duration_minutes": None,
        }
    )

    result = _build_projection(
        _reconciliation(row),
        session_id="ats_single",
    )

    assert result["projection_status"] == "data_gap"
    assert result["plan"]["date"] == "2026-07-08"
    assert result["plan"]["sport"] == "bike"
    assert result["plan"]["name"] == "Endurance ride"
    assert result["plan"]["duration_minutes"] is None
    assert result["plan"]["load_tss"] is None
    assert result["fact"]["completion_status"] == "complete"
    assert result["fact"]["actual_activity_ids"] == ["ride-main"]
    assert result["fact"]["duration_minutes"] == 61.0
    assert result["fact"]["load_tss"] == 52.0
    assert result["deviation"]["duration_delta_minutes"] is None
    assert result["deviation"]["load_delta_tss"] is None
    assert result["data_quality"] == {
        "status": "data_gap",
        "reasons": ["invalid_planned_duration", "invalid_planned_load"],
    }


def test_day_load_keeps_other_matched_session_separate() -> None:
    target = _single_row()
    sibling_activity = _activity(
        "run-sibling",
        "run",
        20.0,
        30.0,
        "2026-07-08T12:00:00Z",
    )
    sibling = {
        **_single_row(),
        "session_id": "ats_sibling",
        "sport": "run",
        "tss": 20.0,
        "actual_activity_ids": ["run-sibling"],
        "actual_activities": [sibling_activity],
        "actual_total_tss": 20.0,
        "actual_duration_minutes": 30.0,
        "actual_sport": "run",
    }
    extra = _activity(
        "walk-extra",
        "other",
        8.0,
        25.0,
        "2026-07-08T18:00:00Z",
    )
    reconciliation = _reconciliation(target, unplanned=[extra])
    reconciliation["rows"].append(sibling)

    result = _build_projection(
        reconciliation,
        session_id="ats_single",
    )

    assert result["load"] == {
        "planned_tss": 50.0,
        "matched_tss": 52.0,
        "other_matched_tss": 20.0,
        "additional_unmatched_tss": 8.0,
        "day_total_tss": 80.0,
    }
