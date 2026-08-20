"""Future-only correction preview for steady-state bike plan TSS."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
from typing import Any, Mapping

from models.session_identity import ensure_session_identities
from models.workout_catalog import (
    catalog_definitions,
    materialize_workout,
    planned_bike_tss_from_steps,
)


BIKE_TSS_REBALANCE_RULE_VERSION = "bike_tss_rebalance_v1"
SUPPORTED_BIKE_TEMPLATE_KEYS = frozenset(
    {
        "bike_recovery_spin",
        "bike_aerobic_endurance",
        "bike_aerobic_progression",
    }
)
MAX_TSS_ROUNDING_GAP = 1.0


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _definition(template_key: str):
    return next(
        (item for item in catalog_definitions() if item.template_key == template_key),
        None,
    )


def _session_date(template: Mapping[str, Any]) -> date | None:
    return _date_value(template.get("date"))


def _week_key(value: date) -> str:
    return (value - timedelta(days=value.weekday())).isoformat()


def _iter_sessions(goal_plan: Mapping[str, Any]):
    for template_index, template in enumerate(list(goal_plan.get("session_templates") or [])):
        if not isinstance(template, Mapping):
            continue
        for session_index, session in enumerate(list(template.get("sessions") or [])):
            if isinstance(session, Mapping):
                yield template_index, session_index, template, session


def _supported_session(session: Mapping[str, Any]) -> bool:
    return (
        str(session.get("kind") or "single") == "single"
        and str(session.get("sport") or "") == "bike"
        and str(session.get("materialization_status") or "") == "materialized"
        and str(session.get("template_key") or "") in SUPPORTED_BIKE_TEMPLATE_KEYS
    )


def _description_with_values(description: str, *, total_tss: float, duration_minutes: int) -> str:
    replacements = {
        "Total TSS:": f"Total TSS: {round(total_tss, 1)}",
        "Оценка длительности:": f"Оценка длительности: {duration_minutes} мин",
    }
    lines: list[str] = []
    found = set()
    for line in str(description or "").splitlines():
        replaced = False
        for prefix, value in replacements.items():
            if line.startswith(prefix):
                lines.append(value)
                found.add(prefix)
                replaced = True
                break
        if not replaced:
            lines.append(line)
    if "Total TSS:" not in found:
        lines.append(replacements["Total TSS:"])
    if "Оценка длительности:" not in found:
        lines.append(replacements["Оценка длительности:"])
    return "\n".join(lines)


def _rebuild_future_session(
    session: Mapping[str, Any],
    *,
    after_duration_minutes: int,
    requested_tss: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    template_key = str(session.get("template_key") or "")
    definition = _definition(template_key)
    provenance = dict(session.get("target_provenance") or {})
    if definition is None or str(provenance.get("kind") or "") != "ftp":
        return None, {"status": "data_gap", "reason": "unsupported_prescription"}
    materialized = _materialize_for_bike_duration(
        definition,
        duration_minutes=int(after_duration_minutes),
        requested_tss=float(requested_tss),
        ftp=float(provenance["value"]),
    )
    if materialized.get("materialization_status") != "materialized":
        return None, {"status": "capacity_gap", "reason": "duration_outside_catalog_bounds"}
    parameter_snapshot = dict(materialized.get("parameter_snapshot") or {})
    after_tss = float(parameter_snapshot.get("target_tss") or 0.0)
    # The catalog budget is audit evidence for the prescription.  It may be
    # outside the old density window after the power-zone correction; the
    # executable TSS is derived from the persisted power targets below.
    parameter_snapshot["requested_tss"] = round(float(requested_tss), 1)
    parameter_snapshot["requested_tss_source"] = "bike_tss_rebalance"
    materialized["parameter_snapshot"] = parameter_snapshot
    updated = deepcopy(dict(session))
    # ``materialize_workout`` returns executable steps under ``steps``.  The
    # persisted plan contract calls the same field ``materialized_steps``;
    # copying only metadata here silently left the old step durations in place
    # after a volume-only rebalance (the UI showed 104 min while export still
    # delivered the previous 65 min workout).
    updated["materialized_steps"] = deepcopy(materialized.get("steps") or [])
    for key in (
        "definition_snapshot",
        "parameter_snapshot",
        "target_provenance",
        "structure_status",
        "structure_evidence",
        "materializer_rule_version",
        "catalog_version",
    ):
        if key in materialized:
            updated[key] = deepcopy(materialized[key])
    updated["duration_minutes"] = int(after_duration_minutes)
    updated["total_tss"] = round(after_tss, 1)
    # Keep the provider event identity across this future-only replacement so
    # an already delivered calendar workout is updated in place.  The plan
    # session identity remains new (it is used by reconciliation lineage), but
    # delivery has a stable identity for the provider's upsert contract.
    updated["delivery_session_id"] = (
        str(
            session.get("delivery_session_id")
            or session.get("replaces_session_id")
            or session.get("session_id")
            or ""
        ).strip()
        or None
    )
    updated["description"] = _description_with_values(
        str(updated.get("description") or ""),
        total_tss=after_tss,
        duration_minutes=int(after_duration_minutes),
    )
    return updated, {
        "status": "ready",
        "after_tss": round(after_tss, 1),
        "after_duration_minutes": int(after_duration_minutes),
    }


def _repair_current_rebalanced_session(
    session: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Re-materialize an already-rebalanced session at its saved duration.

    Checkpoint #126 predates the persisted-step fix.  Its accounting fields are
    already correct, but the serialized steps still describe the old shorter
    workout.  Rebuilding at the *current* duration repairs that representation
    without proposing another duration change.
    """
    parameters = dict(session.get("parameter_snapshot") or {})
    if str(parameters.get("requested_tss_source") or "") != "bike_tss_rebalance":
        return None, {"status": "not_applicable"}
    try:
        duration_minutes = int(round(float(session.get("duration_minutes") or 0)))
        requested_tss = float(
            parameters.get("requested_tss")
            or session.get("total_tss")
            or 0.0
        )
    except (TypeError, ValueError):
        return None, {"status": "data_gap"}
    if duration_minutes <= 0 or requested_tss <= 0:
        return None, {"status": "data_gap"}
    expected_seconds = duration_minutes * 60
    actual_seconds = sum(
        int(round(float(step.get("duration_seconds") or 0)))
        for step in list(session.get("materialized_steps") or [])
    )
    if actual_seconds == expected_seconds:
        return deepcopy(dict(session)), {"status": "already_consistent"}
    return _rebuild_future_session(
        session,
        after_duration_minutes=duration_minutes,
        requested_tss=requested_tss,
    )


def _effective_rebalanced_steps(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return steps suitable for TSS evidence, including legacy repair."""
    repaired, evidence = _repair_current_rebalanced_session(session)
    if evidence.get("status") == "ready" and repaired is not None:
        return [dict(step or {}) for step in list(repaired.get("materialized_steps") or [])]
    return [dict(step or {}) for step in list(session.get("materialized_steps") or [])]


def _materialize_for_bike_duration(
    definition: Any,
    *,
    duration_minutes: int,
    requested_tss: float,
    ftp: float,
) -> dict[str, Any]:
    """Materialize a valid structure while retaining the requested budget.

    ``requested_tss`` is no longer a safe materializer input for this
    correction: the old catalog density bounds were authored before planned
    bike TSS was derived from power zones.  Pick a feasible structural proxy,
    then overwrite the audit budget after materialization.  Power targets are
    duration/zone based, so the proxy does not alter intensity.
    """
    duration = int(duration_minutes)
    low_tss = max(
        float(definition.min_tss),
        float(definition.min_tss_per_hour) * duration / 60.0,
    )
    high_tss = min(
        float(definition.max_tss),
        float(definition.max_tss_per_hour) * duration / 60.0,
    )
    if low_tss > high_tss:
        return {"materialization_status": "infeasible", "failed_bounds": ["no_feasible_catalog_budget"]}
    proxy = min(high_tss, max(low_tss, float(requested_tss)))
    candidates = [proxy, low_tss, high_tss, (low_tss + high_tss) / 2.0]
    for candidate in candidates:
        materialized = materialize_workout(
            definition,
            {
                "duration_minutes": duration,
                "target_tss": round(float(candidate), 1),
            },
            {"ftp": ftp},
        )
        if materialized.get("materialization_status") == "materialized":
            return materialized
    return {"materialization_status": "infeasible", "failed_bounds": ["no_feasible_catalog_budget"]}


def _candidate_duration(
    session: Mapping[str, Any],
    honest_tss: float,
    before_tss: float,
) -> tuple[int | None, dict[str, Any] | None, dict[str, Any]]:
    current_duration = int(round(float(session.get("duration_minutes") or 0)))
    definition = _definition(str(session.get("template_key") or ""))
    provenance = dict(session.get("target_provenance") or {})
    if (
        definition is None
        or current_duration <= 0
        or honest_tss <= 0
        or before_tss <= honest_tss
        or str(provenance.get("kind") or "") != "ftp"
    ):
        return None, None, {"status": "data_gap", "reason": "unsupported_prescription"}
    try:
        float(provenance["value"])
    except (KeyError, TypeError, ValueError):
        return None, None, {"status": "data_gap", "reason": "missing_ftp"}

    best: tuple[float, int, dict[str, Any], dict[str, Any]] | None = None
    for candidate in range(current_duration + 1, definition.max_duration_minutes + 1):
        updated, rebuild = _rebuild_future_session(
            session,
            after_duration_minutes=candidate,
            requested_tss=before_tss,
        )
        if updated is None or rebuild.get("status") != "ready":
            continue
        gap = abs(float(rebuild["after_tss"]) - before_tss)
        score = (gap, candidate, updated, rebuild)
        if best is None or score[:2] < best[:2]:
            best = score
    if best is None:
        return None, None, {"status": "capacity_gap", "reason": "duration_outside_catalog_bounds"}
    _gap, candidate, updated, rebuild = best
    return candidate, updated, rebuild


def build_bike_tss_rebalance_preview(
    goal_plan: Mapping[str, Any],
    *,
    as_of: date,
    base_checkpoint_id: int,
) -> dict[str, Any]:
    """Build a read-only, future-only volume correction preview."""
    changes: list[dict[str, Any]] = []
    capacity_gaps: list[dict[str, Any]] = []
    for _template_index, _session_index, template, session in _iter_sessions(goal_plan):
        current_date = _session_date(template)
        if current_date is None or current_date <= as_of or not _supported_session(session):
            continue
        steps = _effective_rebalanced_steps(session)
        provenance = dict(session.get("target_provenance") or {})
        evidence = planned_bike_tss_from_steps(steps, provenance)
        honest_tss = evidence.get("planned_tss")
        parameters = dict(session.get("parameter_snapshot") or {})
        before_tss = round(
            float(parameters.get("requested_tss") or session.get("total_tss") or 0.0),
            1,
        )
        before_duration = int(round(float(session.get("duration_minutes") or 0)))
        if (
            evidence.get("status") != "derived"
            or honest_tss is None
            or before_tss - float(honest_tss) <= MAX_TSS_ROUNDING_GAP
        ):
            continue
        after_duration, updated, rebuild = _candidate_duration(
            session,
            float(honest_tss),
            before_tss,
        )
        if after_duration is None or updated is None:
            capacity_gaps.append(
                {
                    "date": current_date.isoformat(),
                    "session_id": session.get("session_id"),
                    "reason": "duration_at_catalog_maximum",
                    "before_tss": before_tss,
                    "honest_tss": round(float(honest_tss), 1),
                }
            )
            continue
        if rebuild.get("status") != "ready":
            capacity_gaps.append(
                {
                    "date": current_date.isoformat(),
                    "session_id": session.get("session_id"),
                    "reason": rebuild.get("reason") or "capacity_gap",
                    "before_tss": before_tss,
                    "honest_tss": round(float(honest_tss), 1),
                }
            )
            continue
        after_tss = float(rebuild["after_tss"])
        change = {
            "date": current_date.isoformat(),
            "session_id": session.get("session_id"),
            "template_key": session.get("template_key"),
            "session_role": session.get("session_role"),
            "before_tss": before_tss,
            "honest_tss": round(float(honest_tss), 1),
            "after_tss": round(after_tss, 1),
            "delta_tss": round(after_tss - before_tss, 1),
            "before_duration_minutes": before_duration,
            "after_duration_minutes": after_duration,
            "delta_duration_minutes": after_duration - before_duration,
            "method": "volume_only_same_power_zones_v1",
        }
        if abs(after_tss - before_tss) > MAX_TSS_ROUNDING_GAP:
            capacity_gaps.append({**change, "reason": "tss_unreachable_within_catalog"})
        else:
            changes.append(change)

    before_by_week: dict[str, float] = {}
    after_by_week: dict[str, float] = {}
    for change in changes:
        week_key = _week_key(date.fromisoformat(change["date"]))
        before_by_week[week_key] = before_by_week.get(week_key, 0.0) + float(change["before_tss"])
        after_by_week[week_key] = after_by_week.get(week_key, 0.0) + float(change["after_tss"])
    weekly_budget_preserved = all(
        abs(after_by_week[key] - before_by_week[key]) <= MAX_TSS_ROUNDING_GAP
        for key in before_by_week
    )

    affected_weeks = set(before_by_week)
    weekly_duration_before: dict[str, int] = {key: 0 for key in affected_weeks}
    weekly_duration_after: dict[str, int] = {key: 0 for key in affected_weeks}
    changes_by_session = {str(item.get("session_id")): item for item in changes}
    for _template_index, _session_index, template, session in _iter_sessions(goal_plan):
        current_date = _session_date(template)
        if current_date is None:
            continue
        week_key = _week_key(current_date)
        if week_key not in affected_weeks:
            continue
        before_duration = int(round(float(session.get("duration_minutes") or 0)))
        change = changes_by_session.get(str(session.get("session_id") or ""))
        after_duration = int(change["after_duration_minutes"]) if change else before_duration
        weekly_duration_before[week_key] += before_duration
        weekly_duration_after[week_key] += after_duration

    constraints = dict(goal_plan.get("constraint_summary") or {})
    try:
        available_hours = float(constraints.get("available_hours"))
    except (TypeError, ValueError):
        available_hours = 0.0
    time_budget_status = "available" if available_hours > 0 else "data_gap"
    time_budget_reason = None if time_budget_status == "available" else "missing_weekly_available_hours"
    weekly_duration_budget = {
        key: int(round(available_hours * 60.0)) for key in affected_weeks
    }
    time_budget_gaps = [
        {
            "week_start": key,
            "before_minutes": weekly_duration_before[key],
            "after_minutes": weekly_duration_after[key],
            "budget_minutes": weekly_duration_budget[key],
            "delta_minutes": weekly_duration_after[key] - weekly_duration_before[key],
            "reason": "weekly_duration_over_budget",
        }
        for key in sorted(affected_weeks)
        if time_budget_status == "available"
        and weekly_duration_after[key] > weekly_duration_budget[key]
    ]
    time_budget_preserved = time_budget_status == "available" and not time_budget_gaps
    status = "proposal" if changes and not capacity_gaps and weekly_budget_preserved and time_budget_preserved else "no_change"
    reason = (
        "proposal_ready"
        if status == "proposal"
        else "capacity_gap"
        if capacity_gaps
        else "time_budget_gap"
        if time_budget_gaps
        else "time_budget_data_gap"
        if changes and time_budget_status != "available"
        else "no_inconsistent_future_bike_sessions"
    )
    payload: dict[str, Any] = {
        "rule_version": BIKE_TSS_REBALANCE_RULE_VERSION,
        "base_checkpoint_id": int(base_checkpoint_id),
        "as_of": as_of.isoformat(),
        "status": status,
        "reason": reason,
        "changes": changes,
        "capacity_gaps": capacity_gaps,
        "weekly_budget_preserved": weekly_budget_preserved,
        "time_budget_status": time_budget_status,
        "time_budget_reason": time_budget_reason,
        "time_budget_preserved": time_budget_preserved,
        "time_budget_gaps": time_budget_gaps,
        "future_tss_delta": round(sum(float(item["delta_tss"]) for item in changes), 1),
        "future_duration_delta_minutes": sum(int(item["delta_duration_minutes"]) for item in changes),
        "weekly_before_tss": {key: round(value, 1) for key, value in before_by_week.items()},
        "weekly_after_tss": {key: round(value, 1) for key, value in after_by_week.items()},
        "weekly_duration_before_minutes": weekly_duration_before,
        "weekly_duration_after_minutes": weekly_duration_after,
        "weekly_duration_budget_minutes": weekly_duration_budget,
    }
    payload["preview_fingerprint"] = _fingerprint(payload)
    return payload


def apply_bike_tss_rebalance_preview(
    goal_plan: Mapping[str, Any],
    preview: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply a validated future-only preview to a copied goal plan."""
    if preview.get("status") != "proposal":
        return ensure_session_identities(goal_plan)
    updated = deepcopy(dict(goal_plan))
    changes = {str(item.get("session_id")): item for item in preview.get("changes", []) or []}
    for template in list(updated.get("session_templates") or []):
        template_changed = False
        for index, session in enumerate(list(template.get("sessions") or [])):
            change = changes.get(str(session.get("session_id") or ""))
            if not change:
                continue
            rebuilt, evidence = _rebuild_future_session(
                session,
                after_duration_minutes=int(change["after_duration_minutes"]),
                requested_tss=float(change["before_tss"]),
            )
            if rebuilt is None or evidence.get("status") != "ready":
                raise ValueError("bike TSS preview could not be reproduced")
            template["sessions"][index] = rebuilt
            template_changed = True
        if template_changed and template.get("sessions"):
            primary = template["sessions"][0]
            for key in (
                "sport",
                "sport_label",
                "session_role",
                "session_focus",
                "duration_minutes",
                "total_tss",
                "template_key",
                "export_name",
                "description",
                "kind",
                "catalog_version",
                "selector_rule_version",
                "materializer_rule_version",
                "materialization_status",
                "definition_snapshot",
                "parameter_snapshot",
                "materialized_steps",
                "target_provenance",
                "structure_status",
                "structure_evidence",
                "selection_evidence",
                "prescription_fingerprint",
                "delivery_session_id",
            ):
                if key in primary:
                    template[key] = deepcopy(primary[key])

    from models.training_planner import project_daily_plan_from_session_templates

    updated["daily_plan"] = project_daily_plan_from_session_templates(
        list(updated.get("daily_plan") or []),
        list(updated.get("session_templates") or []),
    )
    weekly_summary = [dict(item or {}) for item in list(updated.get("weekly_summary") or [])]
    for week_index, row in enumerate(weekly_summary):
        week_days = updated["daily_plan"][week_index * 7 : week_index * 7 + 7]
        row["weekly_tss"] = int(round(sum(float(item[1] or 0.0) for item in week_days)))
        for sport in ("bike", "run", "swim"):
            row[sport] = round(sum(float((item[2] or {}).get(sport, 0.0) or 0.0) for item in week_days), 1)
    updated["weekly_summary"] = weekly_summary
    updated["weekly_tss_plan"] = [int(row.get("weekly_tss") or 0) for row in weekly_summary]
    updated["bike_tss_rebalance"] = {
        "rule_version": preview.get("rule_version"),
        "as_of": preview.get("as_of"),
        "base_checkpoint_id": preview.get("base_checkpoint_id"),
        "preview_fingerprint": preview.get("preview_fingerprint"),
        "changes": deepcopy(list(preview.get("changes") or [])),
    }
    return ensure_session_identities(updated, previous_goal_plan=goal_plan)


def repair_bike_tss_materialization(
    goal_plan: Mapping[str, Any],
    *,
    as_of: date,
) -> tuple[dict[str, Any], list[str]]:
    """Repair stale persisted steps for future bike-TSS-rebalanced sessions."""
    updated = deepcopy(dict(goal_plan))
    changed_dates: list[str] = []
    for template in list(updated.get("session_templates") or []):
        current_date = _session_date(template)
        if current_date is None or current_date <= as_of:
            continue
        template_changed = False
        sessions = list(template.get("sessions") or [])
        for index, session in enumerate(sessions):
            if not isinstance(session, Mapping) or not _supported_session(session):
                continue
            repaired, evidence = _repair_current_rebalanced_session(session)
            if evidence.get("status") != "ready" or repaired is None:
                continue
            sessions[index] = repaired
            template_changed = True
        if not template_changed:
            continue
        template["sessions"] = sessions
        primary = sessions[0] if sessions else None
        if primary is not None:
            for key in (
                "sport", "sport_label", "session_role", "session_focus",
                "duration_minutes", "total_tss", "template_key", "export_name",
                "description", "kind", "catalog_version", "selector_rule_version",
                "materializer_rule_version", "materialization_status",
                "definition_snapshot", "parameter_snapshot", "materialized_steps",
                "target_provenance", "structure_status", "structure_evidence",
                "selection_evidence", "prescription_fingerprint", "delivery_session_id",
            ):
                if key in primary:
                    template[key] = deepcopy(primary[key])
        changed_dates.append(current_date.isoformat())

    if not changed_dates:
        return ensure_session_identities(updated, previous_goal_plan=goal_plan), []

    from models.training_planner import project_daily_plan_from_session_templates

    updated["daily_plan"] = project_daily_plan_from_session_templates(
        list(updated.get("daily_plan") or []),
        list(updated.get("session_templates") or []),
    )
    weekly_summary = [dict(item or {}) for item in list(updated.get("weekly_summary") or [])]
    for week_index, row in enumerate(weekly_summary):
        week_days = updated["daily_plan"][week_index * 7 : week_index * 7 + 7]
        row["weekly_tss"] = int(round(sum(float(item[1] or 0.0) for item in week_days)))
        for sport in ("bike", "run", "swim"):
            row[sport] = round(
                sum(float((item[2] or {}).get(sport, 0.0) or 0.0) for item in week_days),
                1,
            )
    updated["weekly_summary"] = weekly_summary
    updated["weekly_tss_plan"] = [int(row.get("weekly_tss") or 0) for row in weekly_summary]
    return ensure_session_identities(updated, previous_goal_plan=goal_plan), changed_dates


__all__ = [
    "BIKE_TSS_REBALANCE_RULE_VERSION",
    "SUPPORTED_BIKE_TEMPLATE_KEYS",
    "apply_bike_tss_rebalance_preview",
    "build_bike_tss_rebalance_preview",
    "repair_bike_tss_materialization",
]
