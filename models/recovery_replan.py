"""Deterministic recovery variants built from salience-gate conflicts."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from models.planning_near_term import (
    apply_near_term_day_edits,
    build_near_term_edit_draft_rows,
    build_near_term_edit_rows,
    summarize_near_term_draft_rows,
)

_SEVERITY_RANK = {"high": 2, "medium": 1}
_HIGH_LOAD_FACTOR = 0.40
_MEDIUM_LOAD_FACTOR = 0.60
_EASY_LOW_LOAD_FACTOR = 0.50
_RECOVERY_BACKING_HORIZON_MAX = 14


def _round_to_five(value: float) -> int:
    return int(round(float(value) / 5.0) * 5)


def _iso_date(value: Any) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    text = str(value or "")
    return text[:10]


def _selected_conflict(report: Mapping[str, Any]) -> dict[str, Any] | None:
    conflicts = [dict(item) for item in (report.get("conflicts") or []) if isinstance(item, dict)]
    if not conflicts:
        return None
    return min(
        conflicts,
        key=lambda item: (
            -_SEVERITY_RANK.get(str(item.get("severity") or ""), 0),
            int(item["days_until"]) if item.get("days_until") is not None else 999,
            str(item.get("date") or ""),
        ),
    )


def _recommendation(role: str, severity: str, current_tss: float) -> tuple[str, int]:
    if role == "easy":
        return "recovery", max(0, _round_to_five(current_tss * _EASY_LOW_LOAD_FACTOR))
    if severity == "high":
        return "recovery", max(0, _round_to_five(current_tss * _HIGH_LOAD_FACTOR))
    return "easy", max(0, _round_to_five(current_tss * _MEDIUM_LOAD_FACTOR))


def _day_safety_profile(
    goal_plan: Mapping[str, Any],
    target_index: int,
) -> dict[str, Any] | None:
    templates = list(goal_plan.get("session_templates") or [])
    if target_index < 0 or target_index >= len(templates):
        return None
    template = dict(templates[target_index] or {})
    sessions = [
        dict(session or {})
        for session in list(template.get("sessions") or [])
    ]
    if not sessions:
        sessions = [template]

    fatigue_vectors: list[tuple[int, int, int]] = []
    recovery_hours: list[int] = []
    template_keys: list[str] = []
    for session in sessions:
        if float(session.get("total_tss") or 0.0) <= 0:
            continue
        fatigue = tuple(int(value) for value in session.get("fatigue_cost") or [])
        recovery = session.get("expected_recovery_hours")
        if len(fatigue) != 3 or recovery is None:
            return None
        fatigue_vectors.append(fatigue)
        recovery_hours.append(int(recovery))
        key = str(session.get("template_key") or "").strip()
        if key:
            template_keys.append(key)
    if not fatigue_vectors:
        return None
    return {
        "fatigue_cost": [
            max(vector[component] for vector in fatigue_vectors)
            for component in range(3)
        ],
        "expected_recovery_hours": max(recovery_hours),
        "template_keys": template_keys,
    }


def _profile_is_nonincreasing(
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> bool:
    candidate_fatigue = [
        int(value) for value in candidate.get("fatigue_cost") or []
    ]
    baseline_fatigue = [
        int(value) for value in baseline.get("fatigue_cost") or []
    ]
    return (
        len(candidate_fatigue) == len(baseline_fatigue) == 3
        and all(
            candidate_cost <= baseline_cost
            for candidate_cost, baseline_cost in zip(
                candidate_fatigue,
                baseline_fatigue,
            )
        )
        and int(candidate.get("expected_recovery_hours") or 0)
        <= int(baseline.get("expected_recovery_hours") or 0)
    )


def assert_recovery_replan_safety(
    original_plan: Mapping[str, Any],
    updated_plan: Mapping[str, Any],
    *,
    target_indices: list[int],
    expected_guard: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed when a recovery edit materializes a harder prescription."""
    guard = dict(expected_guard or {})
    guarded_index = int(guard.get("target_index", -1))
    for target_index in target_indices:
        baseline = _day_safety_profile(original_plan, target_index)
        if baseline is None:
            # Legacy checkpoints without catalog fatigue metadata keep their
            # established behavior. Modern structured sessions are guarded.
            continue
        candidate = _day_safety_profile(updated_plan, target_index)
        if candidate is None or not _profile_is_nonincreasing(candidate, baseline):
            raise ValueError(
                "recovery downgrade produced a harder stimulus than the original"
            )
        if target_index == guarded_index:
            expected = dict(guard.get("expected_profile") or {})
            if expected and candidate != expected:
                raise ValueError(
                    "recovery downgrade no longer matches its materialized preview"
                )


def _preview_recovery_edit(
    goal_plan: Mapping[str, Any],
    draft_rows: list[dict[str, Any]],
    *,
    horizon_days: int,
) -> dict[str, Any] | None:
    try:
        return apply_near_term_day_edits(
            goal_plan,
            draft_rows,
            horizon_days=horizon_days,
            post_edit_strategy="protect_recovery",
            max_horizon_days=_RECOVERY_BACKING_HORIZON_MAX,
        )
    except ValueError:
        return None


def _primary_session_for_day(
    goal_plan: Mapping[str, Any],
    target_index: int,
) -> dict[str, Any]:
    template = dict(
        (list(goal_plan.get("session_templates") or [])[target_index] or {})
    )
    sessions = [
        dict(session or {})
        for session in list(template.get("sessions") or [])
    ]
    return sessions[0] if sessions else template


def build_recovery_replan_variant(
    goal_plan: Mapping[str, Any] | None,
    gate_report: Mapping[str, Any],
    *,
    today: date,
) -> dict[str, Any] | None:
    """Build one bounded, explainable downgrade for the worst gate conflict."""
    if not goal_plan or gate_report.get("silence") or gate_report.get("data_gap"):
        return None

    conflict = _selected_conflict(gate_report)
    if conflict is None:
        return None

    conflict_date = str(conflict.get("date") or "")[:10]
    if conflict_date in {str(value)[:10] for value in (goal_plan.get("protected_dates") or [])}:
        return None
    daily_plan = list(goal_plan.get("daily_plan") or [])
    target_index = next(
        (
            index
            for index, item in enumerate(daily_plan)
            if isinstance(item, (list, tuple)) and item and _iso_date(item[0]) == conflict_date
        ),
        None,
    )
    if target_index is None:
        return None
    templates = list(goal_plan.get("session_templates") or [])
    if target_index < len(templates) and bool((templates[target_index] or {}).get("protected_by_event")):
        return None

    horizon_days = target_index + 1
    editable_rows = build_near_term_edit_rows(
        goal_plan,
        horizon_days=horizon_days,
        max_horizon_days=_RECOVERY_BACKING_HORIZON_MAX,
    )
    target_row = next(
        (row for row in editable_rows if int(row.get("index", -1)) == target_index),
        None,
    )
    if target_row is None:
        return None

    session = dict(conflict.get("session") or {})
    current_role = str(session.get("role") or target_row.get("current_role") or "easy")
    severity = str(conflict.get("severity") or "medium")
    current_tss = float(target_row.get("current_total_tss") or session.get("tss") or 0.0)
    target_role, target_tss = _recommendation(current_role, severity, current_tss)
    current_sport = str(target_row.get("current_sport") or "run")

    def build_draft_rows(role: str) -> list[dict[str, Any]]:
        return build_near_term_edit_draft_rows(
            editable_rows,
            goal_type=str(goal_plan.get("goal_type") or ""),
            distance=str(goal_plan.get("distance") or ""),
            overrides_by_index={
                target_index: {
                    "session_role": role,
                    "sport": current_sport,
                    "total_tss": target_tss,
                }
            },
        )

    draft_rows = build_draft_rows(target_role)
    preview_plan = _preview_recovery_edit(
        goal_plan,
        draft_rows,
        horizon_days=horizon_days,
    )
    if preview_plan is None:
        return None

    baseline_profile = _day_safety_profile(goal_plan, target_index)
    preview_profile = _day_safety_profile(preview_plan, target_index)
    if (
        baseline_profile is not None
        and (
            preview_profile is None
            or not _profile_is_nonincreasing(preview_profile, baseline_profile)
        )
    ):
        target_role = "recovery"
        draft_rows = build_draft_rows(target_role)
        preview_plan = _preview_recovery_edit(
            goal_plan,
            draft_rows,
            horizon_days=horizon_days,
        )
        preview_profile = (
            _day_safety_profile(preview_plan, target_index)
            if preview_plan is not None
            else None
        )
        if (
            preview_plan is None
            or preview_profile is None
            or not _profile_is_nonincreasing(
                preview_profile,
                baseline_profile,
            )
        ):
            return None

    draft_summary = summarize_near_term_draft_rows(draft_rows)
    recommended_row = next(row for row in draft_rows if int(row.get("index", -1)) == target_index)
    preview_session = _primary_session_for_day(preview_plan, target_index)
    current_session = {
        "date": conflict_date,
        "name": str(session.get("name") or target_row.get("current_focus") or "Сессия"),
        "role": current_role,
        "sport": current_sport,
        "sport_label": str(session.get("sport_label") or ""),
        "tss": int(round(current_tss)),
    }
    recommended_session = {
        "date": conflict_date,
        "name": str(
            preview_session.get("template_name")
            or preview_session.get("export_name")
            or recommended_row.get("target_focus")
            or "Восстановительная сессия"
        ),
        "role": str(preview_session.get("session_role") or target_role),
        "sport": current_sport,
        "sport_label": str(session.get("sport_label") or ""),
        "tss": target_tss,
        "delta_tss": target_tss - int(round(current_tss)),
        "template_key": preview_session.get("template_key"),
        "stimulus": preview_session.get("stimulus"),
        "fatigue_cost": list(preview_session.get("fatigue_cost") or []),
        "expected_recovery_hours": preview_session.get(
            "expected_recovery_hours"
        ),
    }
    options = [
        {
            "key": "keep",
            "label": "Оставить как есть",
            "session": current_session,
            "risk": severity,
        },
        {
            "key": "recommended",
            "label": "Снизить нагрузку",
            "session": recommended_session,
            "recommended": True,
        },
    ]

    result = {
        "selected_conflict": conflict,
        "horizon_days": horizon_days,
        "post_edit_strategy": "protect_recovery",
        "draft_rows": draft_rows,
        "draft_summary": draft_summary,
        "current_session": current_session,
        "recommended_session": recommended_session,
        "options": options,
        "reason": str(gate_report.get("reason") or ""),
        "evidence": list(conflict.get("evidence") or []),
        "as_of": str(gate_report.get("as_of") or today.isoformat()),
        "lookahead_policy": str(gate_report.get("lookahead_policy") or ""),
    }
    if baseline_profile is not None and preview_profile is not None:
        result["safety_guard"] = {
            "target_index": target_index,
            "baseline_profile": baseline_profile,
            "expected_profile": preview_profile,
        }
    return result


__all__ = [
    "assert_recovery_replan_safety",
    "build_recovery_replan_variant",
]
