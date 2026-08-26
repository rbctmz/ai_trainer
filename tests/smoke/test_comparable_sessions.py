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
    moving_duration_minutes: float | None = None,
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
        "moving_duration_minutes": moving_duration_minutes,
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


def test_tss_density_uses_moving_duration_with_elapsed_fallback() -> None:
    target = _features(
        "target",
        "2026-08-24",
        sport="run",
        duration=40,
        moving_duration_minutes=40,
        tss=70,
        normalized_power=None,
        avg_power=None,
        distance_km=10,
        tss_pace_used=300,
    )
    paused = _features(
        "paused",
        "2026-08-01",
        sport="run",
        duration=75,
        moving_duration_minutes=40,
        tss=70,
        normalized_power=None,
        avg_power=None,
        distance_km=10,
        tss_pace_used=300,
    )

    result = select_comparable_session(target, [paused])

    assert target["tss_per_hour"] == 105.0
    assert paused["tss_per_hour"] == 105.0
    assert result["status"] == "available"


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


def test_cross_provider_structure_counts_are_not_hard_compared() -> None:
    target = _features("target", "2026-08-24", interval_count=3)
    candidate = _features("candidate", "2026-08-01", interval_count=10)
    target["structure"]["source"] = "intervals"
    candidate["structure"]["source"] = "garmin"

    result = select_comparable_session(target, [candidate])

    assert result["status"] == "available"
    structure = next(
        row
        for row in result["similarity"]["evidence"]
        if row["dimension"] == "structure"
    )
    assert structure["status"] == "missing"
    assert structure["target_source"] == "intervals"
    assert structure["comparator_source"] == "garmin"


def test_partial_interval_coverage_is_missing_not_incompatible() -> None:
    target = _features("target", "2026-08-24")
    candidate = _features("candidate", "2026-08-01")
    target["structure"] = project_activity_features(
        _activity("target", "2026-08-24"),
        stimulus_family="threshold",
        intervals={
            "source": "intervals",
            "intervals": [{"moving_time": 300}],
        },
    )["structure"]

    result = select_comparable_session(target, [candidate])

    assert result["status"] == "available"
    structure = next(
        row
        for row in result["similarity"]["evidence"]
        if row["dimension"] == "structure"
    )
    assert target["structure"]["duration_coverage"] == 0.083
    assert structure["status"] == "missing"


def test_complete_same_provider_structure_remains_a_hard_gate() -> None:
    target = _features("target", "2026-08-24", interval_count=10)
    candidate = _features("candidate", "2026-08-01", interval_count=2)

    result = select_comparable_session(target, [candidate])

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "NO_COMPATIBLE_STRUCTURE"


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


def test_service_includes_stable_auto_reconciled_history_without_ledger() -> None:
    class AutoReconciledDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return []

        def get_latest_planning_checkpoint(self):
            return self.get_planning_checkpoint(3)

        def get_latest_session_feedbacks(self):
            return []

    result = project_comparable_session(
        AutoReconciledDb(),
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

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"


def test_service_restores_auto_match_stimulus_after_plan_rollover() -> None:
    class RolledOverAutoDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return []

        def get_latest_planning_checkpoint(self):
            return {
                "id": 4,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-24",
                            "total_tss": 40,
                            "parts": {"bike": 40},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-plan-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "endurance"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

        def get_planning_checkpoints_for_session(self, session_id):
            assert session_id == "prior-session"
            return [self.get_planning_checkpoint(3)]

        def get_latest_session_feedbacks(self):
            return [
                {
                    "status": "active",
                    "session_id": "prior-session",
                    "match_revision_id": None,
                    "actual_activity_ids": ["candidate"],
                    "match_snapshot": {
                        "planned": {
                            "session_id": "prior-session",
                            "date": "2026-08-01",
                            "sport": "bike",
                        },
                        "match_status": "matched",
                        "match_method": "date_sport_heuristic",
                        "confidence": 0.75,
                        "actual_activity_ids": ["candidate"],
                    },
                    "source": "user_web",
                }
            ]

    result = project_comparable_session(
        RolledOverAutoDb(),
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

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"


def test_service_restores_rollover_auto_match_without_feedback() -> None:
    class RolledOverPreFeedbackDb(_ComparableDb):
        def __init__(self) -> None:
            super().__init__()
            self.historical_reads = 0

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return []

        def get_latest_planning_checkpoint(self):
            return {
                "id": 4,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-24",
                            "total_tss": 40,
                            "parts": {"bike": 40},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-plan-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "endurance"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

        def get_latest_planning_checkpoints_for_dates(self, dates):
            self.historical_reads += 1
            assert dates == ["2026-08-01"]
            return {"2026-08-01": self.get_planning_checkpoint(3)}

        def get_latest_session_feedbacks(self):
            return []

    database = RolledOverPreFeedbackDb()
    result = project_comparable_session(
        database,
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

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"
    assert database.historical_reads == 1


def test_historical_rollover_recovery_fails_closed_on_same_day_ambiguity() -> None:
    class AmbiguousHistoricalDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return []

        def get_latest_planning_checkpoint(self):
            return {
                "id": 4,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-24",
                            "total_tss": 40,
                            "parts": {"bike": 40},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-plan-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "endurance"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

        def get_latest_planning_checkpoints_for_dates(self, dates):
            assert dates == ["2026-08-01"]
            historical = self.get_planning_checkpoint(3)
            historical["goal_plan_snapshot"]["session_templates"][0][
                "sessions"
            ].append(
                {
                    "session_id": "second-bike-session",
                    "sport": "bike",
                    "definition_snapshot": {"step_builder_key": "threshold"},
                }
            )
            return {"2026-08-01": historical}

        def get_latest_session_feedbacks(self):
            return []

    result = project_comparable_session(
        AmbiguousHistoricalDb(),
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


def test_service_suppresses_legacy_auto_feedback_after_manual_rematch() -> None:
    class ManuallyRematchedDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return [
                {
                    "id": 30,
                    "target_key": "session:prior-session",
                    "session_id": "prior-session",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "match_method": "user_confirmed",
                    "confidence": 1.0,
                    "actual_activity_ids": ["replacement-activity"],
                }
            ]

        def get_latest_planning_checkpoint(self):
            return self.get_planning_checkpoint(3)

        def get_latest_session_feedbacks(self):
            return [
                {
                    "status": "active",
                    "session_id": "prior-session",
                    "match_revision_id": None,
                    "actual_activity_ids": ["candidate"],
                    "match_snapshot": {
                        "planned": {
                            "session_id": "prior-session",
                            "date": "2026-08-01",
                            "sport": "bike",
                        },
                        "match_status": "matched",
                        "match_method": "date_sport_heuristic",
                        "confidence": 0.75,
                        "actual_activity_ids": ["candidate"],
                    },
                    "source": "user_web",
                }
            ]

    result = project_comparable_session(
        ManuallyRematchedDb(),
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


def test_service_prefilters_incompatible_candidates_before_interval_reads() -> None:
    class IncompatibleHistoryDb(_ComparableDb):
        def __init__(self) -> None:
            super().__init__()
            self.candidates = [
                _activity(f"candidate-{index}", "2026-08-01", duration=10, tss=68)
                for index in range(100)
            ]
            self.interval_reads: list[str] = []

        def get_activities_between(self, _start, _end):
            return self.candidates

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "session_id": f"prior-session-{index}",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": [f"candidate-{index}"],
                }
                for index in range(100)
            ]

        def get_planning_checkpoint(self, checkpoint_id):
            assert checkpoint_id == 3
            return {
                "id": 3,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-01",
                            "total_tss": 6800,
                            "parts": {"bike": 6800},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-01",
                            "sessions": [
                                {
                                    "session_id": f"prior-session-{index}",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                                for index in range(100)
                            ],
                        }
                    ],
                },
            }

        def get_activity_intervals(self, activity_id):
            self.interval_reads.append(activity_id)
            return _intervals(4)

        def get_latest_session_feedbacks(self):
            return []

    database = IncompatibleHistoryDb()
    result = project_comparable_session(
        database,
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
    assert result["reason_code"] == "NO_COMPATIBLE_DURATION"
    assert result["candidate_counts"]["duration_incompatible"] == 100
    assert database.interval_reads == ["target"]


def test_service_caches_run_threshold_history_for_enriched_candidates() -> None:
    class RunHistoryDb(_ComparableDb):
        def __init__(self) -> None:
            super().__init__()
            self.target = _activity(
                "target",
                "2026-08-24",
                sport="run",
                normalized_power=None,
                avg_power=None,
                distance_km=10,
            )
            self.candidates = [
                _activity(
                    "candidate-1",
                    "2026-08-01",
                    sport="run",
                    duration=58,
                    tss=68,
                    normalized_power=None,
                    avg_power=None,
                    distance_km=10,
                ),
                _activity(
                    "candidate-2",
                    "2026-08-02",
                    sport="run",
                    duration=59,
                    tss=69,
                    normalized_power=None,
                    avg_power=None,
                    distance_km=10,
                ),
            ]
            self.threshold_reads: list[str] = []

        def get_activities_between(self, _start, _end):
            return self.candidates

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return [
                {
                    "session_id": f"prior-session-{index}",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": [f"candidate-{index}"],
                }
                for index in (1, 2)
            ]

        def get_planning_checkpoint(self, checkpoint_id):
            assert checkpoint_id == 3
            return {
                "id": 3,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-01",
                            "total_tss": 137,
                            "parts": {"run": 137},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": f"2026-08-0{index}",
                            "sessions": [
                                {
                                    "session_id": f"prior-session-{index}",
                                    "sport": "run",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                            ],
                        }
                        for index in (1, 2)
                    ],
                },
            }

        def get_athlete_pace_threshold_history(self, sport):
            self.threshold_reads.append(sport)
            return [
                {
                    "snapshot_at": "2026-07-01T00:00:00Z",
                    "value": 300,
                    "source": "intervals_icu",
                }
            ]

        def get_latest_session_feedbacks(self):
            return []

    database = RunHistoryDb()
    result = project_comparable_session(
        database,
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

    assert result["status"] == "available"
    assert database.threshold_reads == ["run"]


def test_service_keeps_newest_feedback_for_rebound_activity() -> None:
    class ReboundFeedbackDb(_ComparableDb):
        def get_latest_session_feedbacks(self):
            return [
                {
                    "id": 20,
                    "status": "active",
                    "actual_activity_ids": ["candidate"],
                    "note": "новая оценка",
                    "source": "user_web",
                    "submitted_at": "2026-08-02T10:00:00Z",
                },
                {
                    "id": 10,
                    "status": "active",
                    "actual_activity_ids": ["candidate"],
                    "note": "устаревшая оценка",
                    "source": "user_web",
                    "submitted_at": "2026-08-02T09:00:00Z",
                },
            ]

    result = project_comparable_session(
        ReboundFeedbackDb(),
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

    assert result["comparison"]["subjective_evidence"]["comparator"]["value"] == (
        "новая оценка"
    )


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


def test_service_follows_constraint_rebind_match_lineage() -> None:
    class ReboundComparatorDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "id": 10,
                    "session_id": "prior-session",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate"],
                },
                {
                    "id": 11,
                    "session_id": "restamped-prior-session",
                    "base_checkpoint_id": 3,
                    "supersedes_match_id": 10,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate"],
                },
            ]

    result = project_comparable_session(
        ReboundComparatorDb(),
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

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"


def test_service_hydrates_missing_match_lineage_ancestors() -> None:
    class MultiRevisionReboundDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "id": 1,
                    "session_id": "prior-session",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate"],
                },
                {
                    "id": 3,
                    "session_id": "restamped-prior-session-v2",
                    "base_checkpoint_id": 3,
                    "supersedes_match_id": 2,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate"],
                },
            ]

        def get_plan_actual_match(self, match_id):
            assert match_id == 2
            return {
                "id": 2,
                "session_id": "restamped-prior-session",
                "base_checkpoint_id": 3,
                "supersedes_match_id": 1,
                "match_status": "matched",
                "actual_activity_ids": ["candidate"],
            }

    result = project_comparable_session(
        MultiRevisionReboundDb(),
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

    assert result["status"] == "available"
    assert result["comparator"]["activity_id"] == "candidate"


def test_service_honors_unmatched_leaf_across_rebind_lineage() -> None:
    class UnmatchedReboundDb(_ComparableDb):
        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2024-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "id": 10,
                    "session_id": "prior-session",
                    "base_checkpoint_id": 3,
                    "match_status": "matched",
                    "actual_activity_ids": ["candidate"],
                },
                {
                    "id": 11,
                    "session_id": "restamped-prior-session",
                    "base_checkpoint_id": 3,
                    "supersedes_match_id": 10,
                    "match_status": "unmatched",
                    "actual_activity_ids": [],
                },
            ]

    result = project_comparable_session(
        UnmatchedReboundDb(),
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


def test_match_index_allows_new_owner_after_old_lineage_is_unmatched() -> None:
    from services.comparable_sessions import _match_by_activity

    matches = [
        {
            "id": 10,
            "session_id": "old-session",
            "match_status": "matched",
            "actual_activity_ids": ["candidate"],
        },
        {
            "id": 11,
            "session_id": "old-session",
            "supersedes_match_id": 10,
            "match_status": "unmatched",
            "actual_activity_ids": [],
        },
        {
            "id": 20,
            "session_id": "new-session",
            "match_status": "matched",
            "actual_activity_ids": ["candidate"],
        },
    ]

    result = _match_by_activity(object(), matches)

    assert result["candidate"]["id"] == 20


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


def test_service_requires_current_revision_for_versioned_feedback() -> None:
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
        },
        feedback={
            "status": "active",
            "match_revision_id": 21,
            "actual_activity_ids": ["target"],
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


def test_utc_timestamp_precedes_conflicting_local_dates() -> None:
    target = _features("target", "2026-08-24")
    target["started_at_utc"] = "2026-08-23T22:00:00Z"
    candidate = _features("candidate", "2026-08-23", duration=58, tss=68)
    candidate["started_at_utc"] = "2026-08-24T01:00:00Z"

    result = select_comparable_session(target, [candidate])

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "NO_ELIGIBLE_CANDIDATE"


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


def test_run_pace_prefers_moving_duration_with_elapsed_fallback() -> None:
    activity = _activity(
        "run",
        "2026-08-24",
        sport="run",
        duration=60,
        distance_km=10,
        normalized_power=None,
        avg_power=None,
        tss_pace_used=300,
    )
    activity["moving_duration_minutes"] = 40

    projected = project_activity_features(
        activity,
        stimulus_family="threshold",
    )

    assert projected["sport_metric"]["value"] == 240.0
    assert projected["sport_metric"]["relative_to_threshold"] == 1.25


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


def test_threshold_snapshot_requires_known_precedence_without_activity_time() -> None:
    from services.comparable_sessions import _with_profile_pace_threshold

    class ThresholdDb:
        def get_athlete_pace_threshold_history(self, sport):
            assert sport == "run"
            return [
                {
                    "snapshot_at": "2026-07-31T20:00:00Z",
                    "value": 300.0,
                    "source": "athlete_profile",
                },
                {
                    "snapshot_at": "2026-08-01T20:00:00Z",
                    "value": 285.0,
                    "source": "athlete_profile",
                },
            ]

    activity = _activity(
        "legacy-run",
        "2026-08-01",
        sport="run",
        normalized_power=None,
        avg_power=None,
        tss_pace_used=None,
    )
    activity["started_at_utc"] = None

    projected = _with_profile_pace_threshold(ThresholdDb(), activity)

    assert projected["pace_threshold_used"] == 300.0
    assert projected["pace_threshold_observed_at"] == "2026-07-31T20:00:00Z"


def test_feedback_primary_prompt_exposes_the_bounded_comparison(monkeypatch) -> None:
    from api import session_feedback

    class PromptDb:
        def get_latest_session_feedbacks(self):
            return []

        def get_latest_session_feedback_prompt_events(self):
            return []

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2026-08-24"
            assert end_date == "2026-08-24"
            return [
                {
                    "id": 22,
                    "target_key": "session:target-session",
                    "session_id": "target-session",
                }
            ]

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
    assert observed["match_revision_id"] == 22


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


def test_saved_auto_feedback_finds_historical_checkpoint_after_rollover() -> None:
    from api.session_feedback import _evidence_from_saved_feedback

    feedback = {
        "status": "active",
        "session_id": "historical-session",
        "match_revision_id": None,
        "actual_activity_ids": ["historical-activity"],
        "match_snapshot": {
            "planned": {
                "session_id": "historical-session",
                "date": "2026-08-01",
                "sport": "bike",
            },
            "match_status": "matched",
            "match_method": "date_sport_heuristic",
            "confidence": 0.75,
        },
    }
    historical = {
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
                            "sport": "bike",
                            "definition_snapshot": {
                                "step_builder_key": "threshold"
                            },
                        }
                    ],
                }
            ],
        },
    }

    class RolledOverFeedbackDb:
        def get_latest_planning_checkpoint(self):
            return {
                "id": 8,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-24",
                            "total_tss": 40,
                            "parts": {"bike": 40},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-session",
                                    "sport": "bike",
                                }
                            ],
                        }
                    ],
                },
            }

        def get_planning_checkpoints_for_session(self, session_id):
            assert session_id == "historical-session"
            return [historical]

    evidence = _evidence_from_saved_feedback(
        RolledOverFeedbackDb(),
        feedback,
        as_of="2026-08-24",
    )

    assert evidence is not None
    assert evidence["template"]["definition_snapshot"]["step_builder_key"] == (
        "threshold"
    )


def test_saved_feedback_restores_rebound_session_through_match_lineage() -> None:
    from api.session_feedback import _evidence_from_saved_feedback

    feedback = {
        "session_id": "restamped-session",
        "match_revision_id": 42,
        "actual_activity_ids": ["historical-activity"],
        "match_snapshot": {
            "planned": {"date": "2026-08-01", "sport": "bike"},
            "match_status": "matched",
            "match_method": "constraint_repair_rebind",
            "confidence": 1.0,
        },
    }

    class ReboundFeedbackDb:
        def get_plan_actual_match(self, match_revision_id):
            return {
                42: {
                    "id": 42,
                    "session_id": "restamped-session",
                    "session_date": "2026-08-01",
                    "base_checkpoint_id": 7,
                    "supersedes_match_id": 41,
                    "match_status": "matched",
                },
                41: {
                    "id": 41,
                    "session_id": "historical-session",
                    "session_date": "2026-08-01",
                    "base_checkpoint_id": 7,
                    "match_status": "matched",
                },
            }.get(match_revision_id)

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
        ReboundFeedbackDb(), feedback, as_of="2026-08-24"
    )

    assert evidence is not None
    assert evidence["row"]["session_id"] == "restamped-session"
    assert evidence["template"]["definition_snapshot"]["step_builder_key"] == "threshold"


def test_saved_feedback_revalidates_against_current_match_leaf() -> None:
    from api.session_feedback import _evidence_from_saved_feedback

    feedback = {
        "status": "active",
        "session_id": "rematched-session",
        "match_revision_id": 1,
        "actual_activity_ids": ["activity-a"],
        "match_snapshot": {
            "planned": {"date": "2026-08-01", "sport": "bike"},
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "actual_activity_ids": ["activity-a"],
        },
    }

    revision_one = {
        "id": 1,
        "target_key": "session:rematched-session",
        "session_id": "rematched-session",
        "session_date": "2026-08-01",
        "base_checkpoint_id": 7,
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "actual_activity_ids": ["activity-a"],
        "planned_snapshot": {"date": "2026-08-01", "sport": "bike"},
    }
    revision_two = {
        **revision_one,
        "id": 2,
        "supersedes_match_id": 1,
        "actual_activity_ids": ["activity-b"],
    }

    class RematchedFeedbackDb:
        def get_plan_actual_match(self, match_revision_id):
            return {1: revision_one, 2: revision_two}.get(match_revision_id)

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2026-08-01"
            assert end_date == "2026-08-01"
            return [revision_two]

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
                                    "session_id": "rematched-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

    evidence = _evidence_from_saved_feedback(
        RematchedFeedbackDb(), feedback, as_of="2026-08-24"
    )

    assert evidence is not None
    assert evidence["row"]["actual_activity_ids"] == ["activity-b"]
    assert evidence["match_revision_id"] == 2


def test_saved_feedback_follows_rebound_descendant_to_unmatched_leaf() -> None:
    from api.session_feedback import _evidence_from_saved_feedback

    feedback = {
        "status": "active",
        "session_id": "old-session",
        "match_revision_id": 41,
        "actual_activity_ids": ["activity-a"],
        "match_snapshot": {
            "planned": {"date": "2026-08-01", "sport": "bike"},
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
        },
    }
    old_match = {
        "id": 41,
        "target_key": "session:old-session",
        "session_id": "old-session",
        "session_date": "2026-08-01",
        "base_checkpoint_id": 7,
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "actual_activity_ids": ["activity-a"],
        "planned_snapshot": {"date": "2026-08-01", "sport": "bike"},
    }
    rebound_match = {
        **old_match,
        "id": 42,
        "target_key": "session:new-session",
        "session_id": "new-session",
        "base_checkpoint_id": 8,
        "supersedes_match_id": 41,
    }
    unmatched_leaf = {
        **rebound_match,
        "id": 43,
        "supersedes_match_id": 42,
        "match_status": "unmatched",
        "match_method": "user_unmatched",
        "actual_activity_ids": [],
    }

    class ReboundDescendantDb:
        def get_plan_actual_match(self, match_revision_id):
            return {
                41: old_match,
                42: rebound_match,
                43: unmatched_leaf,
            }.get(match_revision_id)

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2026-08-01"
            assert end_date == "2026-08-01"
            return [old_match, unmatched_leaf]

        def get_planning_checkpoint(self, checkpoint_id):
            session_id = "old-session" if checkpoint_id == 7 else "new-session"
            return {
                "id": checkpoint_id,
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
                                    "session_id": session_id,
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

    evidence = _evidence_from_saved_feedback(
        ReboundDescendantDb(), feedback, as_of="2026-08-24"
    )

    assert evidence is not None
    assert evidence["row"]["match_status"] == "unmatched"
    assert evidence["row"]["actual_activity_ids"] == []
    assert evidence["match_revision_id"] == 43


def test_stimulus_lineage_stops_at_present_template_without_stimulus() -> None:
    from services.comparable_sessions import _stimulus_for_match

    checkpoints = {
        8: {
            "id": 8,
            "goal_plan_snapshot": {
                "daily_plan": [
                    {"date": "2026-08-01", "total_tss": 0, "parts": {}}
                ],
                "session_templates": [
                    {
                        "date": "2026-08-01",
                        "sessions": [
                            {
                                "session_id": "current-session",
                                "sport": "bike",
                                "definition_snapshot": {},
                            }
                        ],
                    }
                ]
            },
        },
        7: {
            "id": 7,
            "goal_plan_snapshot": {
                "daily_plan": [
                    {"date": "2026-08-01", "total_tss": 70, "parts": {"bike": 70}}
                ],
                "session_templates": [
                    {
                        "date": "2026-08-01",
                        "sessions": [
                            {
                                "session_id": "historical-session",
                                "sport": "bike",
                                "definition_snapshot": {
                                    "step_builder_key": "threshold"
                                },
                            }
                        ],
                    }
                ]
            },
        },
    }

    class LineageDb:
        def get_planning_checkpoint(self, checkpoint_id):
            return checkpoints[checkpoint_id]

    match = {
        "_stimulus_lineage": [
            {
                "id": 2,
                "session_id": "current-session",
                "base_checkpoint_id": 8,
            },
            {
                "id": 1,
                "session_id": "historical-session",
                "base_checkpoint_id": 7,
            },
        ]
    }

    assert _stimulus_for_match(LineageDb(), match, {}) is None


def test_stimulus_lineage_walks_when_current_identity_is_absent() -> None:
    from services.comparable_sessions import _stimulus_for_match

    checkpoints = {
        8: {
            "id": 8,
            "goal_plan_snapshot": {
                "daily_plan": [
                    {"date": "2026-08-01", "total_tss": 0, "parts": {}}
                ],
                "session_templates": [
                    {
                        "date": "2026-08-01",
                        "sessions": [
                            {
                                "session_id": "different-session",
                                "sport": "bike",
                            }
                        ],
                    }
                ]
            },
        },
        7: {
            "id": 7,
            "goal_plan_snapshot": {
                "daily_plan": [
                    {"date": "2026-08-01", "total_tss": 70, "parts": {"bike": 70}}
                ],
                "session_templates": [
                    {
                        "date": "2026-08-01",
                        "sessions": [
                            {
                                "session_id": "historical-session",
                                "sport": "bike",
                                "definition_snapshot": {
                                    "step_builder_key": "threshold"
                                },
                            }
                        ],
                    }
                ]
            },
        },
    }

    class LineageDb:
        def get_planning_checkpoint(self, checkpoint_id):
            return checkpoints[checkpoint_id]

    match = {
        "_stimulus_lineage": [
            {
                "id": 2,
                "session_id": "current-session",
                "base_checkpoint_id": 8,
            },
            {
                "id": 1,
                "session_id": "historical-session",
                "base_checkpoint_id": 7,
            },
        ]
    }

    assert _stimulus_for_match(LineageDb(), match, {}) == "threshold"


def test_service_batches_historical_checkpoint_recovery() -> None:
    candidate_count = 100

    class BatchedHistoryDb(_ComparableDb):
        def __init__(self) -> None:
            super().__init__()
            self.candidates = [
                _activity(
                    f"candidate-{index}",
                    "2026-08-01",
                    duration=58,
                    tss=68,
                )
                for index in range(candidate_count)
            ]
            self.batch_calls = 0
            self.single_calls = 0

        def get_activities_between(self, _start, _end):
            return self.candidates

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            return []

        def get_latest_planning_checkpoint(self):
            return {
                "id": 8,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {"date": "2026-08-24", "total_tss": 40, "parts": {"bike": 40}}
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "endurance"
                                    },
                                }
                            ],
                        }
                    ]
                },
            }

        def get_latest_session_feedbacks(self):
            return [
                {
                    "status": "active",
                    "session_id": f"prior-session-{index}",
                    "match_revision_id": None,
                    "actual_activity_ids": [f"candidate-{index}"],
                    "match_snapshot": {
                        "planned": {
                            "session_id": f"prior-session-{index}",
                            "date": "2026-08-01",
                            "sport": "bike",
                        },
                        "match_status": "matched",
                        "match_method": "date_sport_heuristic",
                        "confidence": 0.75,
                        "actual_activity_ids": [f"candidate-{index}"],
                    },
                }
                for index in range(candidate_count)
            ]

        def get_planning_checkpoints_for_sessions(self, session_ids):
            self.batch_calls += 1
            historical = {
                "id": 7,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {"date": "2026-08-01", "total_tss": 70, "parts": {"bike": 70}}
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-01",
                            "sessions": [
                                {
                                    "session_id": session_id,
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                                for session_id in session_ids
                            ],
                        }
                    ]
                },
            }
            return {session_id: [historical] for session_id in session_ids}

        def get_planning_checkpoints_for_session(self, session_id):
            self.single_calls += 1
            raise AssertionError("per-session checkpoint reads must not be used")

    database = BatchedHistoryDb()
    result = project_comparable_session(
        database,
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

    assert result["status"] == "available"
    assert database.batch_calls == 1
    assert database.single_calls == 0


def test_default_coach_target_uses_latest_workout_time_not_feedback_time(
    monkeypatch,
) -> None:
    from api import session_feedback

    older_late_feedback = {
        "id": 2,
        "session_id": "older-session",
        "status": "active",
        "completion_status": "completed",
        "actual_activity_ids": ["older"],
        "session_end_at_utc": "2026-08-01T09:00:00Z",
        "submitted_at": "2026-08-25T09:00:00Z",
    }
    latest_workout = {
        "id": 1,
        "session_id": "latest-session",
        "status": "active",
        "completion_status": "completed",
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


def test_default_coach_target_excludes_sessions_not_started(monkeypatch) -> None:
    from api import session_feedback

    did_not_start = {
        "id": 2,
        "session_id": "dns-session",
        "status": "active",
        "completion_status": "did_not_start",
        "actual_activity_ids": ["dns"],
        "session_end_at_utc": "2026-08-24T10:00:00Z",
    }
    completed = {
        "id": 1,
        "session_id": "completed-session",
        "status": "active",
        "completion_status": "completed",
        "actual_activity_ids": ["completed"],
        "session_end_at_utc": "2026-08-23T10:00:00Z",
    }

    class LatestDb:
        def get_latest_session_feedbacks(self):
            return [did_not_start, completed]

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

    assert result["selected_session_id"] == "completed-session"


def test_default_coach_target_respects_historical_as_of(monkeypatch) -> None:
    from api import session_feedback

    older = {
        "id": 1,
        "session_id": "older-session",
        "status": "active",
        "completion_status": "completed",
        "actual_activity_ids": ["older"],
        "session_end_at_utc": "2026-08-01T10:00:00Z",
    }
    future = {
        "id": 2,
        "session_id": "future-session",
        "status": "active",
        "completion_status": "completed",
        "actual_activity_ids": ["future"],
        "session_end_at_utc": "2026-08-24T10:00:00Z",
    }

    class HistoricalDb:
        def get_latest_session_feedbacks(self):
            return [future, older]

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

    result = session_feedback.comparable_session_for_session(
        HistoricalDb(), as_of="2026-08-10"
    )

    assert result["selected_session_id"] == "older-session"


def test_explicit_tombstone_target_revalidates_current_match(monkeypatch) -> None:
    from api import session_feedback

    tombstone = {
        "id": 8,
        "session_id": "session-1",
        "status": "tombstone",
        "match_revision_id": 1,
        "actual_activity_ids": ["removed-activity"],
    }

    class TombstoneDb:
        def get_latest_session_feedback(self, session_id):
            assert session_id == "session-1"
            return tombstone

    def reject_saved_evidence(*_args, **_kwargs):
        raise AssertionError("tombstone evidence must not be restored")

    monkeypatch.setattr(
        session_feedback,
        "_evidence_from_saved_feedback",
        reject_saved_evidence,
    )
    monkeypatch.setattr(
        session_feedback,
        "_feedback_evidence_for_session",
        lambda _db, session_id, as_of=None: {
            "row": {
                "session_id": session_id,
                "match_status": "matched",
                "actual_activity_ids": ["current-activity"],
            },
            "template": {},
        },
    )
    monkeypatch.setattr(
        session_feedback,
        "_comparison_for_evidence",
        lambda _db, evidence, feedback=None: {
            "match_status": evidence["row"]["match_status"],
            "activity_ids": evidence["row"]["actual_activity_ids"],
            "feedback": feedback,
        },
    )

    result = session_feedback.comparable_session_for_session(
        TombstoneDb(),
        session_id="session-1",
    )

    assert result == {
        "match_status": "matched",
        "activity_ids": ["current-activity"],
        "feedback": None,
    }


def test_service_returns_target_gap_before_history_reads() -> None:
    class MissingStimulusDb(_ComparableDb):
        def get_latest_session_feedbacks(self):
            raise AssertionError("feedback history must not be read")

        def get_activity_intervals(self, activity_id):
            raise AssertionError("interval history must not be read")

        def get_activities_between(self, _start, _end):
            raise AssertionError("candidate history must not be read")

    result = project_comparable_session(
        MissingStimulusDb(),
        evidence={
            "row": {
                "session_id": "target-session",
                "match_status": "matched",
                "actual_activity_ids": ["target"],
            },
            "template": {"definition_snapshot": {}},
        },
    )

    assert result["status"] == "data_gap"
    assert result["reason_code"] == "TARGET_STIMULUS_MISSING"


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
    assert "TSS/ч" in rendered
    assert "TSS ÷ время в движении" in rendered
    assert "+1.0" in rendered
    assert "не доказывает тренд" in rendered.lower()
    assert "лучше" not in rendered.lower()
    schemas = {schema["name"]: schema for schema in tools.get_tool_schemas()}
    assert schemas["get_comparable_session"]["parameters"]["properties"][
        "session_id"
    ]["type"] == "string"


def test_comparable_presenter_preserves_zero_intensity_delta() -> None:
    from models.coach_tool_presenter import format_tool_result

    rendered = format_tool_result(
        "get_comparable_session",
        {
            "status": "available",
            "target": {"tss_per_hour": 70.0},
            "comparator": {"tss_per_hour": 70.0},
            "comparison": {
                "overall_intensity_tss_per_hour_delta": 0.0,
            },
        },
    )

    assert "70.0 vs 70.0" in rendered
    assert "Δ +0.0" in rendered
    assert "время в движении" in rendered


def test_explicit_historical_target_without_feedback_uses_match_checkpoint(
    monkeypatch,
) -> None:
    from api import session_feedback

    historical_match = {
        "id": 7,
        "target_key": "session:historical-session",
        "session_id": "historical-session",
        "base_checkpoint_id": 3,
        "session_date": "2026-08-01",
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "planned_snapshot": {
            "session_id": "historical-session",
            "date": "2026-08-01",
            "sport": "bike",
        },
        "actual_activity_ids": ["historical-activity"],
        "actual_snapshot": {},
    }

    class HistoricalTargetDb:
        def get_latest_session_feedback(self, session_id):
            assert session_id == "historical-session"
            return None

        def get_latest_planning_checkpoint(self):
            return {
                "id": 4,
                "goal_plan_snapshot": {
                    "daily_plan": [
                        {
                            "date": "2026-08-24",
                            "total_tss": 40,
                            "parts": {"bike": 40},
                        }
                    ],
                    "session_templates": [
                        {
                            "date": "2026-08-24",
                            "sessions": [
                                {
                                    "session_id": "replacement-session",
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "endurance"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

        def get_latest_plan_actual_match_for_session(self, session_id):
            assert session_id == "historical-session"
            return historical_match

        def get_plan_actual_match(self, match_id):
            assert match_id == 7
            return historical_match

        def get_latest_plan_actual_matches(self, *, start_date, end_date):
            assert start_date == "2026-08-01"
            assert end_date == "2026-08-01"
            return [historical_match]

        def get_planning_checkpoint(self, checkpoint_id):
            assert checkpoint_id == 3
            return {
                "id": 3,
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
                                    "sport": "bike",
                                    "definition_snapshot": {
                                        "step_builder_key": "threshold"
                                    },
                                }
                            ],
                        }
                    ],
                },
            }

    observed = {}

    def compare(_db, evidence, feedback=None):
        observed.update(evidence)
        return {"status": "available"}

    monkeypatch.setattr(session_feedback, "_comparison_for_evidence", compare)

    result = session_feedback.comparable_session_for_session(
        HistoricalTargetDb(),
        session_id="historical-session",
        as_of="2026-08-24",
    )

    assert result["status"] == "available"
    assert observed["row"]["actual_activity_ids"] == ["historical-activity"]
    assert observed["template"]["definition_snapshot"]["step_builder_key"] == (
        "threshold"
    )


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
