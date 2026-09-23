"""Behavior contract for issue #610's server-owned decision story."""
from __future__ import annotations

import pytest

def _compose(**kwargs):
    from models.today_decision_story import compose_today_decision_story

    return compose_today_decision_story(**kwargs)


def _session(status: str = "matched") -> dict:
    ambiguous = status == "needs_confirmation"
    partial = status == "partial"
    plan = {
        "date": "2026-09-23",
        "name": "Quality bike → run",
        "load_tss": 60,
        "legs": [
            {"leg_id": "plan-session-1:1", "leg_index": 1, "sport": "bike", "load_tss": 40},
            {"leg_id": "plan-session-1:2", "leg_index": 2, "sport": "run", "load_tss": 20},
        ] if partial else [],
        "transition": {"planned_minutes": 5} if partial else None,
    }
    fact = {
        "completion_status": (
            "needs_confirmation" if ambiguous else "incomplete" if partial else "complete"
        ),
        "actual_activity_ids": [] if ambiguous else ["activity-1"],
        "load_tss": None if ambiguous else 24 if partial else 58,
        "legs": (
            [
                {
                    "planned_leg_id": "plan-session-1:1",
                    "leg_index": 1,
                    "activity_id": "activity-bike",
                    "sport": "bike",
                    "duration_minutes": 70,
                    "load_tss": 24,
                }
            ]
            if partial
            else []
        ),
        "transition": {"actual_minutes": None} if partial else None,
    }
    return {
        "schema_version": "session_projection_v1",
        "session_id": "plan-session-1",
        "projection_status": status,
        "evidence_revision": {
            "planning_checkpoint_id": 7,
            "match_revision_id": 11,
            "match_revision": 2,
            "reconciliation_rule_version": "reconciliation_v1",
            "as_of": "2026-09-23",
            "provider_status": "disabled",
        },
        "plan": plan,
        "fact": fact,
        "deviation": {
            "adherence": "unknown" if ambiguous else "partial" if partial else "exact",
            "transition_delta_minutes": None if partial else 0,
        },
        "cause": {
            "status": "needs_confirmation" if ambiguous else "unknown",
            "code": "ambiguous_match" if ambiguous else "no_explicit_cause_evidence",
            "evidence_refs": [],
        },
    }


def _readiness() -> dict:
    return {
        "score": 82,
        "status": "ready",
        "stale": False,
        "intervention_score": 82,
        "intervention_confidence": 0.9,
        "eligible_inputs": ["sleep", "hrv"],
        "freshness": {
            "state": "confirmed_today",
            "anchor": "2026-09-23",
            "confirmed_today": ["sleep", "hrv"],
            "outdated": [],
            "missing": [],
        },
    }


def _wellness(
    *,
    status: str = "current",
    injury: int | None = 1,
    day: str | None = "2026-09-23",
    other_current_answer: bool = False,
) -> dict:
    if injury is None:
        injury_state = "missing"
        injury_label = "Нет ответа"
    elif type(injury) is not int or not 1 <= injury <= 4:
        injury_state = "invalid"
        injury_label = "Неизвестное значение источника"
    else:
        injury_state = "present"
        injury_label = "Нет" if injury == 1 else "Дискомфорт"
    items = [
        {
            "key": "injury",
            "label": "Травма — самооценка",
            "value": injury if injury_state == "present" else None,
            "state": injury_state,
            "value_label": injury_label,
        }
    ]
    if other_current_answer:
        items.append(
            {
                "key": "sleepQuality",
                "label": "Качество сна",
                "value": 2,
                "state": "present",
                "value_label": "Хорошее",
            }
        )
    return {
        "status": status,
        "source": "intervals",
        "date": day,
        "mapping_version": "intervals_subjective_v1",
        "items": items,
    }


def _inputs(*, session: dict | None = None, wellness: dict | None = None) -> dict:
    return {
        "as_of": "2026-09-23",
        "session_projection": session or _session(),
        "readiness": _readiness(),
        "subjective_wellness": wellness or _wellness(),
        "primary_action": {
            "kind": "follow_plan",
            "enabled": True,
            "reason": "План и состояние согласны.",
        },
        "rule_versions": {
            "readiness": "readiness_snapshot_v1",
            "gate": "readiness_conflicts_v2",
        },
    }


def test_today_story_separates_fact_interpretation_and_recommendation() -> None:
    story = _compose(**_inputs())

    assert story["schema_version"] == "today_decision_story_v1"
    assert story["fact"]["session_id"] == "plan-session-1"
    assert story["fact"]["plan"]["load_tss"] == 60
    assert story["fact"]["actual"]["load_tss"] == 58
    assert story["interpretation"]["status"] == "consistent"
    assert story["recommendation"]["kind"] == "follow_plan"
    assert story["next_action"]["kind"] == "follow_plan"
    assert {item["kind"] for item in story["evidence"]} >= {"session", "readiness"}


@pytest.mark.parametrize(
    ("location", "field"),
    [
        ("fact", "actual_activity_ids"),
        ("fact", "legs"),
        ("readiness", "eligible_inputs"),
    ],
)
def test_malformed_list_dto_fails_closed_to_data_gap(location: str, field: str) -> None:
    inputs = _inputs()
    if location == "fact":
        inputs["session_projection"]["fact"][field] = 7
    else:
        inputs["readiness"][field] = {"unexpected": "shape"}

    story = _compose(**inputs)

    assert story["fact"]["projection_status"] == "data_gap"
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert story["next_action"]["changes_plan"] is False
    if field == "actual_activity_ids":
        assert story["fact"]["actual"]["activity_ids"] == []
    elif field == "legs":
        assert story["fact"]["actual"]["legs"] == []
    else:
        readiness = next(row for row in story["evidence"] if row["kind"] == "readiness")
        assert readiness["eligible_inputs"] == []


def test_current_injury_self_report_overrides_clearance_with_review_only() -> None:
    story = _compose(**_inputs(wellness=_wellness(injury=2)))

    assert story["interpretation"]["status"] == "conflicting_evidence"
    assert story["recommendation"]["kind"] == "non_prescriptive_review"
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert story["next_action"]["changes_plan"] is False
    injury = next(
        item for item in story["evidence"]
        if item.get("kind") == "subjective_wellness" and item.get("key") == "injury"
    )
    assert injury["observation_date"] == "2026-09-23"
    assert injury["eligible_for_clearance"] is False


def test_stale_or_missing_self_report_is_not_current_evidence() -> None:
    stale = _compose(**_inputs(wellness=_wellness(status="stale", injury=2, day="2026-09-21")))
    missing = _compose(**_inputs(wellness=_wellness(status="missing", injury=None, day=None)))
    invalid = _compose(**_inputs(wellness=_wellness(status="invalid", injury=9)))
    unavailable = _compose(**_inputs(wellness=_wellness(status="unavailable", injury=None, day=None)))

    for story in (stale, missing, invalid, unavailable):
        assert story["interpretation"]["status"] != "conflicting_evidence"
        assert story["next_action"]["kind"] == "follow_plan"
        assert story["next_action"]["clearance_claim"] is False
        assert story["interpretation"]["caveat"] == "no_current_injury_response"
    stale_injury = next(
        item for item in stale["evidence"]
        if item.get("kind") == "subjective_wellness" and item.get("key") == "injury"
    )
    missing_injury = next(
        item for item in missing["evidence"]
        if item.get("kind") == "subjective_wellness" and item.get("key") == "injury"
    )
    assert stale_injury["freshness"] == "stale"
    assert missing_injury["freshness"] == "missing"


def test_current_wellness_from_other_answer_does_not_imply_no_injury() -> None:
    missing_injury = _wellness(
        status="current", injury=None, other_current_answer=True
    )
    invalid_injury = _wellness(
        status="current", injury=9, other_current_answer=True
    )

    for wellness in (missing_injury, invalid_injury):
        assert wellness["status"] == "current"
        story = _compose(**_inputs(wellness=wellness))
        injury = next(
            item for item in story["evidence"]
            if item.get("kind") == "subjective_wellness" and item.get("key") == "injury"
        )
        assert injury["state"] in {"missing", "invalid"}
        assert injury["freshness"] == injury["state"]
        assert injury["value_label"] != "Нет"
        assert injury["eligible_for_clearance"] is False
        assert story["next_action"]["kind"] == "follow_plan"
        assert story["next_action"]["clearance_claim"] is False
        assert story["interpretation"]["caveat"] == "no_current_injury_response"


def test_ambiguous_session_requires_confirmation_without_deviation_cause() -> None:
    story = _compose(**_inputs(session=_session("needs_confirmation")))

    assert story["fact"]["completion_status"] == "needs_confirmation"
    assert story["fact"]["actual"]["activity_ids"] == []
    assert story["interpretation"]["status"] == "needs_confirmation"
    assert story["next_action"]["kind"] == "confirm_match"
    assert story["fact"]["cause"]["status"] == "needs_confirmation"


def test_partial_session_preserves_known_fact_without_inventing_leg() -> None:
    story = _compose(**_inputs(session=_session("partial")))

    assert story["fact"]["completion_status"] == "incomplete"
    assert story["fact"]["actual"]["load_tss"] == 24
    assert story["fact"]["plan"]["legs"] == [
        {"leg_id": "plan-session-1:1", "leg_index": 1, "sport": "bike", "load_tss": 40},
        {"leg_id": "plan-session-1:2", "leg_index": 2, "sport": "run", "load_tss": 20},
    ]
    assert story["fact"]["actual"]["legs"] == [
        {
            "planned_leg_id": "plan-session-1:1",
            "leg_index": 1,
            "activity_id": "activity-bike",
            "sport": "bike",
            "duration_minutes": 70,
            "load_tss": 24,
        }
    ]
    assert story["fact"]["actual"]["legs"][0]["planned_leg_id"] == "plan-session-1:1"
    assert story["fact"]["deviation"]["transition_delta_minutes"] is None


def test_coach_read_adapter_uses_shared_story_without_database_writes(tmp_path) -> None:
    from api.today_snapshot import build_today_decision_story_from_sources
    from tests.smoke.test_api_planning import _reconciliation_db
    from tests.smoke.test_reconciliation_service_migration import _table_snapshots

    db, plan = _reconciliation_db(tmp_path)
    session_id = plan["session_templates"][0]["session_id"]
    before = _table_snapshots(db)

    story = build_today_decision_story_from_sources(
        db,
        as_of="2026-07-08",
        session_id=session_id,
        readiness=_readiness(),
        subjective_wellness=_wellness(day="2026-07-08"),
        primary_action={"kind": "follow_plan", "enabled": True, "reason": "OK"},
        rule_versions={"readiness": "readiness_snapshot_v1", "gate": "gate_v1"},
    )

    assert story["schema_version"] == "today_decision_story_v1"
    assert story["fact"]["projection_status"] == "unmatched"
    assert story["next_action"]["kind"] == "inspect_evidence"
    assert _table_snapshots(db) == before


def test_projection_from_changed_checkpoint_fails_closed(monkeypatch) -> None:
    from api import today_snapshot

    monkeypatch.setattr(today_snapshot, "session_projection_at", lambda *a, **k: _session())
    story = today_snapshot.build_today_decision_story_from_sources(
        object(),  # type: ignore[arg-type]
        as_of="2026-09-23",
        session_id="session-1",
        readiness=_readiness(),
        subjective_wellness=_wellness(),
        primary_action={"kind": "follow_plan", "enabled": True},
        expected_checkpoint_id=6,
    )

    assert story["fact"]["projection_status"] == "data_gap"
    assert story["fact"]["plan"] == {}
    assert story["next_action"]["kind"] == "inspect_evidence"


def test_coach_plan_and_checkpoint_share_one_read_boundary(monkeypatch) -> None:
    from api.routers import coach

    checkpoint = {"id": 31, "goal_plan": {"name": "frozen"}}
    calls = []

    def latest(_db):
        calls.append("checkpoint")
        return checkpoint

    def restore(value):
        calls.append(("restore", value["id"]))
        return {"name": "frozen"}

    monkeypatch.setattr(coach, "_latest_checkpoint", latest)
    monkeypatch.setattr(coach, "restore_goal_plan_from_checkpoint", restore)
    frozen_checkpoint, plan = coach._load_coach_plan_boundary(object())

    assert frozen_checkpoint is checkpoint
    assert plan == {"name": "frozen"}
    assert calls == ["checkpoint", ("restore", 31)]


def test_coach_readiness_tool_includes_the_same_story_when_attached(tmp_path) -> None:
    from models.coach_tool_presenter import format_tool_result
    from models.ai_tools import AITools

    tool = object.__new__(AITools)
    wellness = _wellness(day="2026-09-23", injury=1)
    readiness = {"as_of_date": "2026-09-23", "subjective_wellness": wellness}
    expected = {
        "schema_version": "today_decision_story_v1",
        "date": "2026-09-23",
        "next_action": {"kind": "follow_plan"},
    }
    tool.today_decision_context = {
        "date": "2026-09-23",
        "readiness": readiness,
        "story": expected,
    }

    # Host/athlete time crossing midnight after the route captured its frozen
    # context must not pair that story with a newly computed day.
    result = tool.get_readiness_today()
    assert result["computed_for"] == "2026-09-23"
    assert result["subjective_wellness"] == wellness
    assert result["decision_story"] == expected
    assert '"decision_story"' in format_tool_result("get_readiness_today", result)
    assert '"kind": "follow_plan"' in format_tool_result("get_readiness_today", result)


def test_coach_story_action_uses_today_proposal_checkpoint_relation() -> None:
    from api.routers.coach import _resolve_coach_today_action

    class ProposalReader:
        def get_coach_proposals(self, *, days: int, limit: int) -> list[dict]:
            assert days == 36500
            assert limit == 500
            return [
                {
                    "id": 12,
                    "action": "recovery_replan",
                    "status": "pending",
                    "params": {"base_checkpoint_id": 1},
                }
            ]

    action = _resolve_coach_today_action(
        ProposalReader(),  # type: ignore[arg-type]
        checkpoint={"id": 2},
        loop_result={
            "outcome": "conflict",
            "proposal": {
                "id": 12,
                "action": "recovery_replan",
                "status": "pending",
                "params": {"base_checkpoint_id": 1},
            },
            "readiness_conflicts": {"reason": "Нужно проверить конфликт."},
        },
    )

    assert action["kind"] == "inspect_evidence"
    assert action["enabled"] is True
