"""BDD/TDD contract for comparable-session engine v1 (#500)."""
from __future__ import annotations

from itertools import permutations
from pathlib import Path
from datetime import datetime, timezone

import pytest

from models.comparable_sessions import (
    COMPARABLE_SESSION_RULE_VERSION,
    project_activity_features,
    select_comparable_session,
)
from services.comparable_sessions import project_comparable_session


pytestmark = pytest.mark.smoke


def _intervals(count: int, *, minutes: float = 60.0) -> dict:
    seconds = minutes * 60 / count
    return {
        "source": "intervals",
        "intervals": [
            {"moving_time": seconds, "zone": 3 if index % 2 else 2}
            for index in range(count)
        ],
        "groups": [],
    }


def _activity(
    activity_id: str,
    date: str,
    *,
    sport: str = "bike",
    duration: float = 60.0,
    tss: float = 70.0,
    normalized_power: float | None = 210.0,
    avg_power: float | None = 190.0,
    distance_km: float | None = 30.0,
    tss_pace_used: float | None = None,
) -> dict:
    return {
        "activity_id": activity_id,
        "date": date,
        "started_at_utc": f"{date}T08:00:00Z",
        "sport": sport,
        "duration_minutes": duration,
        "tss": tss,
        "normalized_power": normalized_power,
        "avg_power": avg_power,
        "distance_km": distance_km,
        "tss_pace_used": tss_pace_used,
    }


def _features(
    activity_id: str,
    date: str,
    *,
    stimulus: str = "threshold",
    interval_count: int = 4,
    subjective: dict | None = None,
    **activity_overrides,
) -> dict:
    activity = _activity(activity_id, date, **activity_overrides)
    return project_activity_features(
        activity,
        stimulus_family=stimulus,
        intervals=_intervals(interval_count, minutes=activity["duration_minutes"]),
        subjective_evidence=subjective,
    )


def test_best_candidate_is_not_merely_the_newest() -> None:
    target = _features("target", "2026-08-24")
    older_close = _features(
        "older-close", "2026-08-01", duration=58, tss=68, normalized_power=207
    )
    newest_wrong_intensity = _features(
        "newest-hard", "2026-08-20", duration=30, tss=75, normalized_power=260
    )
    wrong_sport = _features(
        "run", "2026-08-10", sport="run", distance_km=10, normalized_power=None,
        avg_power=None, tss_pace_used=270,
    )
    wrong_stimulus = _features("endurance", "2026-08-18", stimulus="endurance")

    result = select_comparable_session(
        target,
        [newest_wrong_intensity, wrong_sport, wrong_stimulus, older_close],
    )

    assert result["status"] == "available"
    assert result["rule_version"] == COMPARABLE_SESSION_RULE_VERSION
    assert result["comparator"]["activity_id"] == "older-close"
    assert [item["dimension"] for item in result["similarity"]["evidence"]] == [
        "sport",
        "stimulus",
        "duration",
        "overall_intensity",
        "structure",
    ]
    assert result["guardrails"] == {
        "one_comparison_only": True,
        "trend_claim_allowed": False,
        "causal_claim_allowed": False,
    }


def test_bike_metric_prefers_normalized_power_with_named_fallback() -> None:
    target = _features("target", "2026-08-24", normalized_power=212, avg_power=188)
    candidate = _features("candidate", "2026-08-01", normalized_power=204, avg_power=190)

    result = select_comparable_session(target, [candidate])

    metric = result["comparison"]["sport_metric"]
    assert metric["kind"] == "power_watts"
    assert metric["target"] == {"value": 212.0, "source": "normalized_power"}
    assert metric["comparator"] == {"value": 204.0, "source": "normalized_power"}
    assert metric["delta"] == 8.0

    fallback_target = _features(
        "fallback-target", "2026-08-24", normalized_power=None, avg_power=188
    )
    fallback_candidate = _features(
        "fallback-candidate", "2026-08-01", normalized_power=None, avg_power=184
    )

    fallback = select_comparable_session(fallback_target, [fallback_candidate])
    fallback_metric = fallback["comparison"]["sport_metric"]
    assert fallback_metric["target"]["source"] == "average_power_fallback"
    assert fallback_metric["comparator"]["source"] == "average_power_fallback"
    assert fallback_metric["delta"] == 4.0


@pytest.mark.parametrize(
    ("sport", "distance_km", "duration", "threshold", "kind", "pace"),
    [
        ("run", 10.0, 50.0, 270.0, "pace_seconds_per_km", 300.0),
        ("swim", 2.0, 40.0, 105.0, "pace_seconds_per_100m", 120.0),
    ],
)
def test_run_and_swim_pace_evidence_uses_pace_threshold_context(
    sport: str,
    distance_km: float,
    duration: float,
    threshold: float,
    kind: str,
    pace: float,
) -> None:
    projected = project_activity_features(
        _activity(
            "pace",
            "2026-08-24",
            sport=sport,
            duration=duration,
            distance_km=distance_km,
            normalized_power=None,
            avg_power=None,
            tss_pace_used=threshold,
        ),
        stimulus_family="endurance",
        intervals=_intervals(4, minutes=duration),
    )

    assert projected["sport_metric"]["kind"] == kind
    assert projected["sport_metric"]["value"] == pace
    assert projected["sport_metric"]["threshold_value"] == threshold
    assert projected["sport_metric"]["threshold_source"] == "tss_pace_used"
    assert "ftp" not in projected["sport_metric"]


def test_qualitative_feedback_survives_without_numeric_rpe() -> None:
    target = _features("target", "2026-08-24")
    note = {
        "kind": "athlete_note",
        "value": "ровно, но последние интервалы тяжело",
        "provenance": "athlete-entered",
    }
    candidate = _features("candidate", "2026-08-01", subjective=note)
    without_note = _features("candidate", "2026-08-01")

    result = select_comparable_session(target, [candidate])
    baseline = select_comparable_session(target, [without_note])

    assert result["comparison"]["subjective_evidence"]["comparator"] == note
    assert result["similarity"]["score"] == baseline["similarity"]["score"]


def test_incompatible_intensity_and_missing_stimulus_fail_closed() -> None:
    target = _features("target", "2026-08-24")
    incompatible = _features("too-hard", "2026-08-01", duration=30, tss=90)

    result = select_comparable_session(target, [incompatible])

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "NO_COMPATIBLE_INTENSITY"
    assert result["comparator"] is None

    missing = project_activity_features(
        _activity("missing", "2026-08-24"),
        stimulus_family=None,
        intervals=_intervals(4),
    )
    missing_result = select_comparable_session(missing, [])
    assert missing_result["status"] == "data_gap"
    assert missing_result["reason_code"] == "TARGET_STIMULUS_MISSING"


def test_selection_is_deterministic_for_any_candidate_order() -> None:
    target = _features("target", "2026-08-24")
    candidates = [
        _features("b", "2026-08-01", duration=58, tss=68),
        _features("a", "2026-08-01", duration=58, tss=68),
        _features("c", "2026-07-01", duration=55, tss=65),
    ]

    selected = {
        (
            result["comparator"]["activity_id"],
            result["similarity"]["score"],
            tuple(
                (item["dimension"], item["status"])
                for item in result["similarity"]["evidence"]
            ),
        )
        for order in permutations(candidates)
        for result in [select_comparable_session(target, list(order))]
    }

    assert selected == {
        (
            "a",
            next(iter(selected))[1],
            (
                ("sport", "exact"),
                ("stimulus", "exact"),
                ("duration", "compatible"),
                ("overall_intensity", "compatible"),
                ("structure", "compatible"),
            ),
        )
    }


class _ComparableDb:
    def __init__(self) -> None:
        self.target = _activity("target", "2026-08-24")
        self.candidate = _activity("candidate", "2026-08-01", duration=58, tss=68)

    def get_activity(self, activity_id):
        return self.target if activity_id == "target" else None

    def get_activities_between(self, _start, _end):
        return [self.candidate]

    def get_latest_plan_actual_matches(self, *, start_date, end_date):
        assert start_date == "2024-08-24"
        assert end_date == "2026-08-24"
        return [
            {
                "session_id": "prior-session",
                "base_checkpoint_id": 3,
                "match_status": "matched",
                "actual_activity_ids": ["candidate"],
            }
        ]

    def get_planning_checkpoint(self, checkpoint_id):
        assert checkpoint_id == 3
        return {
            "id": 3,
            "goal_plan_snapshot": {
                "daily_plan": [
                    {"date": "2026-08-01", "total_tss": 68, "parts": {"bike": 68}}
                ],
                "session_templates": [
                    {
                        "date": "2026-08-01",
                        "sessions": [
                            {
                                "session_id": "prior-session",
                                "sport": "bike",
                                "total_tss": 68,
                                "duration_minutes": 58,
                                "definition_snapshot": {
                                    "step_builder_key": "threshold"
                                },
                            }
                        ],
                    }
                ],
            },
        }

    def get_activity_intervals(self, activity_id):
        return _intervals(4, minutes=60 if activity_id == "target" else 58)

    def get_latest_session_feedbacks(self):
        return [
            {
                "status": "active",
                "actual_activity_ids": ["candidate"],
                "session_rpe_1_10": None,
                "note": "держал технику",
                "source": "user_web",
            }
        ]


def test_service_joins_checkpoint_stimulus_and_local_feedback() -> None:
    result = project_comparable_session(
        _ComparableDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target"],
            },
            "template": {
                "session_id": "target-session",
                "definition_snapshot": {"step_builder_key": "threshold"},
            },
        },
    )

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"
    assert result["comparison"]["subjective_evidence"]["comparator"] == {
        "kind": "athlete_note",
        "value": "держал технику",
        "provenance": "athlete-entered",
    }


def test_service_refuses_to_aggregate_split_target_activities() -> None:
    result = project_comparable_session(
        _ComparableDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target", "ride-home"],
            },
            "template": {
                "definition_snapshot": {"step_builder_key": "threshold"}
            },
        },
    )

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "TARGET_ACTIVITY_COUNT_UNSUPPORTED"


def test_service_rejects_split_comparator_matches() -> None:
    class SplitComparatorDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "session_id": "prior-session",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate", "ride-home"],
                }
            ]

    result = project_comparable_session(
        SplitComparatorDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target"],
            },
            "template": {
                "definition_snapshot": {"step_builder_key": "threshold"}
            },
        },
    )

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "NO_ELIGIBLE_CANDIDATE"


def test_service_does_not_attach_feedback_from_a_superseded_activity() -> None:
    result = project_comparable_session(
        _ComparableDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target"],
            },
            "template": {
                "definition_snapshot": {"step_builder_key": "threshold"}
            },
            "match_revision_id": 22,
        },
        feedback={
            "status": "active",
            "match_revision_id": 21,
            "actual_activity_ids": ["old-target"],
            "session_rpe_1_10": 9,
            "source": "user_web",
        },
    )

    assert result["status"] == "available"
    assert result["comparison"]["subjective_evidence"]["target"] is None


def test_earlier_same_day_activity_can_be_selected() -> None:
    target = _features("target", "2026-08-24")
    target["started_at_utc"] = "2026-08-24T18:00:00Z"
    earlier = _features("earlier", "2026-08-24", duration=58, tss=68)
    earlier["started_at_utc"] = "2026-08-24T08:00:00Z"

    result = select_comparable_session(target, [earlier])

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "earlier"


def test_run_pace_uses_versioned_profile_threshold_when_tss_has_none() -> None:
    activity = _activity(
        "run",
        "2026-08-24",
        sport="run",
        duration=50,
        distance_km=10,
        normalized_power=None,
        avg_power=None,
        tss_pace_used=None,
    )
    activity.update(
        {
            "pace_threshold_used": 285.0,
            "pace_threshold_source": "intervals_icu",
            "pace_threshold_observed_at": "2026-08-20T06:00:00Z",
        }
    )

    projected = project_activity_features(
        activity,
        stimulus_family="threshold",
        intervals=_intervals(4, minutes=50),
    )

    assert projected["sport_metric"] == {
        "kind": "pace_seconds_per_km",
        "value": 300.0,
        "source": "distance_duration",
        "threshold_value": 285.0,
        "threshold_source": "intervals_icu",
        "threshold_observed_at": "2026-08-20T06:00:00Z",
        "relative_to_threshold": 0.95,
    }


def test_service_reads_run_threshold_snapshot_at_each_activity_time() -> None:
    class RunComparableDb(_ComparableDb):
        def __init__(self) -> None:
            self.target = _activity(
                "target",
                "2026-08-24",
                sport="run",
                duration=50,
                tss=70,
                normalized_power=None,
                avg_power=None,
                distance_km=10,
            )
            self.candidate = _activity(
                "candidate",
                "2026-08-01",
                sport="run",
                duration=49,
                tss=68,
                normalized_power=None,
                avg_power=None,
                distance_km=10,
            )

        def get_athlete_pace_threshold_history(self, sport):
            assert sport == "run"
            return [
                {
                    "snapshot_at": "2026-07-01T06:00:00Z",
                    "observed_at": "2026-07-01T06:00:00Z",
                    "value": 300.0,
                    "source": "intervals_icu",
                },
                {
                    "snapshot_at": "2026-08-20T06:00:00Z",
                    "observed_at": "2026-08-20T06:00:00Z",
                    "value": 285.0,
                    "source": "intervals_icu",
                },
            ]

    result = project_comparable_session(
        RunComparableDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target"],
            },
            "template": {
                "definition_snapshot": {"step_builder_key": "threshold"}
            },
        },
    )

    metric = result["comparison"]["sport_metric"]
    assert metric["target"]["threshold_value"] == 285.0
    assert metric["comparator"]["threshold_value"] == 300.0
    assert metric["target"]["threshold_source"] == "intervals_icu"


def test_feedback_primary_prompt_exposes_the_bounded_comparison(monkeypatch) -> None:
    from api import session_feedback

    class PromptDb:
        def get_latest_session_feedbacks(self):
            return []

        def get_latest_session_feedback_prompt_events(self):
            return []

    expected = {
        "status": "available",
        "rule_version": COMPARABLE_SESSION_RULE_VERSION,
        "comparator": {"activity_id": "prior"},
    }
    observed = {}

    def project(_db, *, evidence, feedback=None, lookback_days=730):
        observed.update(evidence)
        return expected

    monkeypatch.setattr(session_feedback, "project_comparable_session", project)
    row = {
        "session_id": "target-session",
        "date": "2026-08-24",
        "name": "Threshold Ride",
        "role": "quality",
        "sport": "bike",
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "actual_activity_ids": ["target"],
        "actual_activities": [
            {
                "activity_id": "target",
                "started_at_utc": "2026-08-24T08:00:00Z",
                "duration_minutes": 60,
                "sport": "bike",
            }
        ],
    }
    template = {
        "date": "2026-08-24",
        "sessions": [
            {
                "session_id": "target-session",
                "session_role": "quality",
                "sport": "bike",
                "definition_snapshot": {"step_builder_key": "threshold"},
            }
        ],
    }

    result = session_feedback.feedback_from_today_evidence(
        PromptDb(),
        yesterday={"status": "available", "rows": [row]},
        goal_plan={"session_templates": [template]},
        forecasts=[],
        now_utc=datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc),
        as_of="2026-08-24",
    )

    assert result["primary"]["comparison"] == expected
    assert observed["row"]["session_id"] == "target-session"
    assert observed["template"]["definition_snapshot"]["step_builder_key"] == "threshold"


def test_saved_feedback_restores_target_from_immutable_match_checkpoint() -> None:
    from api.session_feedback import _evidence_from_saved_feedback

    feedback = {
        "session_id": "historical-session",
        "match_revision_id": 41,
        "actual_activity_ids": ["historical-activity"],
        "match_snapshot": {
            "planned": {"date": "2026-08-01", "sport": "bike"},
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "actual_activities": [_activity("historical-activity", "2026-08-01")],
        },
    }

    class SavedFeedbackDb:
        def get_plan_actual_match(self, match_revision_id):
            assert match_revision_id == 41
            return {
                "id": 41,
                "session_id": "historical-session",
                "session_date": "2026-08-01",
                "base_checkpoint_id": 7,
                "match_status": "matched",
                "match_method": "user_confirmed",
                "confidence": 1.0,
                "actual_activity_ids": ["historical-activity"],
                "planned_snapshot": {"date": "2026-08-01", "sport": "bike"},
            }

        def get_planning_checkpoint(self, checkpoint_id):
            assert checkpoint_id == 7
            return {
                "id": 7,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-01",
                            "total_tss": 70,
                            "parts": {"bike": 70},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-01",
                            "sessions": [
                                {
                                    "session_id": "historical-session",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

        def get_latest_planning_checkpoint(self):
            raise AssertionError("latest checkpoint must not be used")

    evidence = _evidence_from_saved_feedback(
        SavedFeedbackDb(), feedback, as_of="2026-08-24"
    )

    assert evidence is not None
    assert evidence["row"]["actual_activity_ids"] == ["historical-activity"]
    assert evidence["template"]["definition_snapshot"]["step_builder_key"] == "threshold"


def test_default_coach_target_uses_latest_workout_time_not_feedback_time(
    monkeypatch,
) -> None:
    from api import session_feedback

    older_late_feedback = {
        "id": 2,
        "session_id": "older-session",
        "status": "active",
        "actual_activity_ids": ["older"],
        "session_end_at_utc": "2026-08-01T09:00:00Z",
        "submitted_at": "2026-08-25T09:00:00Z",
    }
    latest_workout = {
        "id": 1,
        "session_id": "latest-session",
        "status": "active",
        "actual_activity_ids": ["latest"],
        "session_end_at_utc": "2026-08-24T09:00:00Z",
        "submitted_at": "2026-08-24T09:01:00Z",
    }

    class LatestDb:
        def get_latest_session_feedbacks(self):
            return [older_late_feedback, latest_workout]

    monkeypatch.setattr(
        session_feedback,
        "_evidence_from_saved_feedback",
        lambda _db, feedback, as_of=None: {
            "row": {"session_id": feedback["session_id"]},
            "template": {},
        },
    )
    monkeypatch.setattr(
        session_feedback,
        "_comparison_for_evidence",
        lambda _db, evidence, feedback=None: {
            "selected_session_id": evidence["row"]["session_id"]
        },
    )

    result = session_feedback.comparable_session_for_session(LatestDb())

    assert result["selected_session_id"] == "latest-session"


def test_coach_tool_and_presenter_expose_neutral_bounded_comparison(monkeypatch) -> None:
    from models.ai_tools import AITools
    from models.coach_tool_presenter import format_tool_result
    from api import session_feedback

    expected = {
        "status": "available",
        "rule_version": COMPARABLE_SESSION_RULE_VERSION,
        "target": {"activity_id": "target", "date": "2026-08-24", "sport": "bike"},
        "comparator": {"activity_id": "prior", "date": "2026-08-01", "sport": "bike"},
        "similarity": {"score": 0.92, "evidence": []},
        "comparison": {
            "duration_minutes_delta": 2.0,
            "tss_delta": 3.0,
            "overall_intensity_tss_per_hour_delta": 1.0,
            "sport_metric": None,
            "subjective_evidence": {
                "target": {
                    "kind": "session_rpe_1_10",
                    "value": 7,
                    "provenance": "athlete-entered",
                },
                "comparator": {
                    "kind": "athlete_note",
                    "value": "ровно и контролируемо",
                    "provenance": "athlete-entered",
                },
            },
        },
        "guardrails": {
            "one_comparison_only": True,
            "trend_claim_allowed": False,
            "causal_claim_allowed": False,
        },
    }
    monkeypatch.setattr(
        session_feedback,
        "comparable_session_for_session",
        lambda _db, session_id=None, as_of=None: expected,
    )

    tools = AITools(object())
    raw = tools.get_comparable_session(session_id="target-session")
    rendered = format_tool_result("get_comparable_session", raw)

    assert raw == expected
    assert "2026-08-01" in rendered
    assert "RPE 7" in rendered
    assert "ровно и контролируемо" in rendered
    assert "athlete-entered" in rendered
    assert "не доказывает тренд" in rendered.lower()
    assert "лучше" not in rendered.lower()
    schemas = {schema["name"]: schema for schema in tools.get_tool_schemas()}
    assert schemas["get_comparable_session"]["parameters"]["properties"][
        "session_id"
    ]["type"] == "string"


def test_web_contract_has_neutral_comparison_surface() -> None:
    root = Path(__file__).resolve().parents[2]
    types = (root / "web/lib/types.ts").read_text(encoding="utf-8")
    card = (root / "web/components/today/PostWorkoutFeedbackCard.tsx").read_text(
        encoding="utf-8"
    )

    assert "export interface ComparableSessionProjection" in types
    assert "comparison?: ComparableSessionProjection | null" in types
    assert "Сравнение с похожей сессией" in card
    assert "Одно сравнение не доказывает тренд" in card
    assert '"с/км"' in card
    assert '"с/100 м"' in card
    assert "threshold_source" in card
