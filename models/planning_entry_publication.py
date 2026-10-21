"""Pure final entry-dose validation over frozen physical and assignment evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
import math
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from models.planning_build_confirmation import (
    canonical_json,
    fingerprint,
    PlanningBuildPreviewError,
)
from models.planning_entry_load import (
    SPORTS,
    _local_day,
    _number,
    _sport,
    build_entry_exposure_profile,
    derive_entry_limits,
)


def entry_base(context: Mapping, parameters: Mapping) -> dict:
    frozen = context["entry_inputs"]
    profile = build_entry_exposure_profile(
        frozen["rows"],
        as_of=date.fromisoformat(context["athlete_day"]),
        timezone=context["athlete_timezone"],
        coverage=parameters.get("history_coverage"),
    )
    start = date.fromisoformat(context["lifecycle"]["start_date"])
    result = derive_entry_limits(
        profile,
        parameters.get("initial_dose_limits"),
        cycle_scope={
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=13)).isoformat(),
        },
        target_sports=frozen["target_sports"],
    )
    retained = frozen.get("retained_limits")
    if retained is not None:
        # Current history remains dated separately from the original limit source.
        for cap in retained.values():
            if cap["scope"] != result["scope"] or cap["source"] not in {
                "observed_reference",
                "athlete_declared",
            }:
                raise ValueError("retained entry scope/source changed")
            if (
                _number(cap["weekly_minutes"]) is None
                or _number(cap["max_session_minutes"]) is None
                or cap["max_session_minutes"] > cap["weekly_minutes"]
                or type(cap["weekly_sessions"]) is not int
                or cap["weekly_sessions"] <= 0
            ):
                raise ValueError("invalid retained entry limit")
        result["limits"].update(deepcopy(retained))
        result["blockers"] = [
            b for b in result["blockers"] if b.get("sport") not in retained
        ]
        result["status"] = "needs_baseline" if result["blockers"] else "unassessed"
        result["warnings"].append(
            {"code": "entry_limits_retained", "sport": None, "field": "limits"}
        )
    return result


def entry_cap(cap: Mapping, day: str, scope: Mapping) -> dict:
    """Versioned existing max-ramp projection; no goal-floor reset after entry."""
    index = (
        date.fromisoformat(day) - date.fromisoformat(scope["start_date"])
    ).days // 7
    factor = 1.1 ** max(0, index - 1)
    return {
        **cap,
        "weekly_minutes": float(cap["weekly_minutes"]) * factor,
        "max_session_minutes": float(cap["max_session_minutes"]) * factor,
    }


def _reason(
    code: str, field: str, observed: Any = None, *, sport=None, day=None, expected=None
) -> dict:
    return {
        "code": code,
        "sport": sport,
        "date": day,
        "field": field,
        "expected": expected,
        "observed": observed,
    }


def execution_partition(context: Mapping) -> dict:
    """Count known physical leaves once; retire only explicitly owned matches."""
    frozen = context["entry_inputs"]
    zone = ZoneInfo(context["athlete_timezone"])
    today = date.fromisoformat(context["athlete_day"])
    start = date.fromisoformat(context["lifecycle"]["start_date"])
    first, entry_last = start - timedelta(days=6), start + timedelta(days=19)

    def relevant(day):
        return day is None or (
            day <= today
            and (first <= day <= entry_last or today - timedelta(days=6) <= day)
        )

    records, problems = {}, []
    # Quality checks reuse the same physical lineage projection; partial-today
    # rows are included for execution but not in the historical reference.
    qualities = []
    for anchor in sorted({today, min(today, entry_last)}):
        physical = build_entry_exposure_profile(
            frozen["rows"],
            as_of=anchor + timedelta(days=1),
            timezone=context["athlete_timezone"],
        )
        qualities.extend(physical["quality_limits"])
    by_id = {}
    for raw in frozen["rows"]:
        identity = str(raw.get("activity_id") or "")
        if identity in by_id and canonical_json(by_id[identity]) != canonical_json(raw):
            problems.append(
                _reason("execution_identity_ambiguous", "activity_id", identity)
            )
        by_id[identity] = raw
    for item in qualities:
        raw = by_id.get(item.get("activity_id"), {})
        day = _local_day(raw.get("date"), zone)
        if relevant(day) and item["code"] in {
            "activity_identity_missing",
            "activity_identity_conflict",
            "lineage_identity_conflict",
            "activity_date_invalid",
            "duration_missing_or_invalid",
            "multisport_remainder_unknown",
            "activity_sport_unknown",
        }:
            problems.append(
                _reason(
                    "execution_partition_ambiguous",
                    item.get("field") or "activity",
                    item["code"],
                    sport=item.get("sport"),
                    day=day.isoformat() if day else None,
                )
            )
    for identity, raw in sorted(by_id.items()):
        day, sport = _local_day(raw.get("date"), zone), _sport(raw.get("sport"))
        if day is not None and relevant(day) and day <= today and sport in SPORTS:
            minutes = _number(raw.get("duration_minutes"))
            if minutes is not None:
                records[identity] = {
                    "activity_id": identity,
                    "date": day.isoformat(),
                    "sport": sport,
                    "minutes": minutes,
                }
    retired, covered = set(), set()
    owned = frozen["owned_sessions"]
    for match in frozen["matches"]:
        identity = match.get("session_id")
        if (
            identity not in owned
            or match["base_checkpoint_id"] not in frozen["owned_checkpoint_ids"]
        ):
            continue
        if match.get("malformed"):
            problems.append(
                _reason("execution_partition_ambiguous", "matches", identity)
            )
            continue
        ids = []
        for actual_id in match["actual_activity_ids"]:
            if actual_id in records:
                ids.append(actual_id)
            else:
                linked = [
                    i
                    for i, raw in by_id.items()
                    if str(raw.get("provider_external_id") or "") == actual_id
                    and i in records
                ]
                if {records[i]["sport"] for i in linked} == set(SPORTS):
                    ids.extend(linked)
                else:
                    ids.append(actual_id)
        if match["match_status"] == "matched" and (
            match["match_method"]
            in {
                "user_confirmed",
                "ai_trainer_external_id",
                "provider_external_id",
                "external_id",
            }
            and ids
            and all(i in records for i in ids)
            and not (set(ids) & covered)
            and match["session_date"] == owned[identity]["date"]
        ):
            retired.add(identity)
            covered.update(ids)
        elif ids and any(i in records for i in ids):
            problems.append(
                _reason(
                    "execution_partition_ambiguous",
                    "matches",
                    identity,
                    day=match["session_date"],
                )
            )
    if frozen.get("truncated"):
        problems.append(
            _reason(
                "execution_partition_ambiguous", "entry_inputs", "truncated capture"
            )
        )
    return {
        "actuals": list(records.values()),
        "retired_session_ids": sorted(retired),
        "blockers": problems,
    }


def leaf_exposures(session: Mapping, day: str) -> list[dict]:
    leaves = (
        session.get("legs", []) if session.get("kind") == "composite" else [session]
    )
    return [
        {
            "date": day,
            "sport": leaf.get("sport"),
            "minutes": leaf.get("duration_minutes"),
            "session_id": session.get("session_id"),
            "replaces_session_id": session.get("replaces_session_id"),
        }
        for leaf in leaves
    ]


def window_excess(
    records: list[dict], assessment: Mapping, *, through: str | None = None
) -> list[dict]:
    """Validate every intersecting rolling window, including six adjacent days."""
    blockers = []
    first = date.fromisoformat(assessment["scope"]["start_date"]) - timedelta(days=6)
    last = date.fromisoformat(through or assessment["scope"]["end_date"])
    cursor = first
    while cursor <= last:
        end = cursor + timedelta(days=6)
        # A window touching entry uses entry caps throughout, even across its end.
        cap_day = max(cursor.isoformat(), assessment["scope"]["start_date"])
        for sport, cap in assessment["limits"].items():
            effective = entry_cap(cap, cap_day, assessment["scope"])
            selected = [
                r
                for r in records
                if r["sport"] == sport
                and cursor.isoformat() <= r["date"] <= end.isoformat()
            ]
            minutes = math.fsum(float(r["minutes"]) for r in selected)
            if (
                minutes > effective["weekly_minutes"] + 1e-7
                or len(selected) > effective["weekly_sessions"]
            ):
                blockers.append(
                    _reason(
                        "entry_window_exceeded",
                        "rolling_seven_days",
                        {"minutes": minutes, "sessions": len(selected)},
                        sport=sport,
                        day=cursor.isoformat(),
                        expected={
                            "minutes": effective["weekly_minutes"],
                            "sessions": effective["weekly_sessions"],
                        },
                    )
                )
        cursor += timedelta(days=1)
    return blockers


def assess_entry_assignments(
    plan: Mapping, assessment: Mapping, execution: Mapping, *, context: Mapping
) -> dict:
    """Final actual+remaining exposure, with no reads, clocks or plan rebuilding."""
    result = deepcopy(dict(assessment))
    blockers = list(result["blockers"]) + list(execution["blockers"])
    if assessment["status"] == "needs_baseline":
        result["can_publish"] = False
        result["warnings"] = [
            w
            for w in result["warnings"]
            if w["code"] != "final_prescription_unassessed"
        ]
        return result
    today = context["athlete_day"]
    records = list(execution["actuals"])
    retired = set(execution["retired_session_ids"])
    for actual in execution["actuals"]:
        cap = result["limits"].get(actual["sport"])
        if (
            cap
            and result["scope"]["start_date"]
            <= actual["date"]
            <= result["scope"]["end_date"]
        ):
            ceiling = cap["max_session_minutes"]
            if actual["minutes"] > ceiling + 1e-7:
                blockers.append(
                    _reason(
                        "entry_session_exceeded",
                        "completed_duration_minutes",
                        actual["minutes"],
                        sport=actual["sport"],
                        day=actual["date"],
                        expected=ceiling,
                    )
                )
    planned_presence = set()
    for template in plan["session_templates"]:
        day = str(template["date"])[:10]
        for session in template.get("sessions", []):
            exposures = leaf_exposures(session, day)
            if result["scope"]["start_date"] <= day <= result["scope"]["end_date"]:
                planned_presence.update(e["sport"] for e in exposures)
            if day < today:
                continue
            if (
                session.get("session_id") in retired
                or session.get("replaces_session_id") in retired
            ):
                blockers.append(
                    _reason(
                        "completed_session_reassigned",
                        "session_id",
                        session.get("session_id"),
                        day=day,
                    )
                )
                continue
            for item in exposures:
                sport, minutes = item["sport"], _number(item["minutes"])
                cap = result["limits"].get(sport)
                if minutes is None or cap is None:
                    blockers.append(
                        _reason(
                            "entry_dose_unverified",
                            "duration_minutes",
                            item["minutes"],
                            sport=sport,
                            day=day,
                        )
                    )
                    continue
                # All later projections remain anchored to the initial envelope.
                ceiling = entry_cap(cap, day, result["scope"])["max_session_minutes"]
                if minutes > ceiling + 1e-7:
                    blockers.append(
                        _reason(
                            "entry_session_exceeded",
                            "duration_minutes",
                            minutes,
                            sport=sport,
                            day=day,
                            expected=ceiling,
                        )
                    )
                if day == today and any(
                    r["date"] == day and r["sport"] == sport
                    for r in execution["actuals"]
                ):
                    blockers.append(
                        _reason(
                            "execution_partition_ambiguous",
                            "same_day_assignment",
                            session.get("session_id"),
                            sport=sport,
                            day=day,
                        )
                    )
                records.append({"date": day, "sport": sport, "minutes": minutes})
    if result["limits"]:
        blockers.extend(
            window_excess(records, result, through=context["lifecycle"]["end_date"])
        )
        for sport in context["entry_inputs"]["target_sports"]:
            if sport not in planned_presence and not any(
                r["sport"] == sport
                and result["scope"]["start_date"]
                <= r["date"]
                <= result["scope"]["end_date"]
                for r in execution["actuals"]
            ):
                blockers.append(
                    _reason(
                        "entry_sport_missing", "session_templates", sport, sport=sport
                    )
                )
    result["blockers"] = sorted(
        blockers,
        key=lambda r: (r["code"], r["date"] or "", r["sport"] or "", r["field"]),
    )
    result["status"] = (
        "needs_baseline"
        if assessment["status"] == "needs_baseline"
        else "blocked"
        if blockers
        else "supported"
    )
    result["can_publish"] = not blockers
    result["warnings"] = [
        w for w in result["warnings"] if w["code"] != "final_prescription_unassessed"
    ]
    return result


def entry_validation_context(plan: Mapping, context: Mapping) -> dict:
    evidence = plan.get("entry_evidence")
    if not isinstance(evidence, Mapping) or fingerprint(evidence) != context.get(
        "components", {}
    ).get("entry_inputs"):
        raise ValueError("frozen entry evidence is not bound to its source digest")
    return {**context, "entry_inputs": evidence}


def require_entry(prepared) -> None:
    context = prepared.snapshot.context()
    if not context.get("lifecycle"):
        return
    plan = json.loads(prepared.checkpoint_json)["goal_plan_snapshot"]
    response = json.loads(prepared.response_json)
    try:
        context = entry_validation_context(plan, context)
    except (ValueError, TypeError) as exc:
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Источники начальной нагрузки повреждены.", status=500
        ) from exc
    expected = assess_entry_assignments(
        plan,
        entry_base(context, prepared.snapshot.parameters.as_dict()),
        execution_partition(context),
        context=context,
    )
    if plan.get("entry_load") != expected or response.get("entry_load") != expected:
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Предпросмотр начальной нагрузки повреждён.", status=500
        )
    if not expected["can_publish"]:
        code = (
            "entry_dose_required"
            if expected["status"] == "needs_baseline"
            else "entry_dose_infeasible"
        )
        error = PlanningBuildPreviewError(
            code,
            "Уточните начальный объём по дисциплинам или ограничения плана.",
            status=422,
        )
        error.context = {"entry_load": expected}
        raise error


def validate_retained_entry(row: Mapping) -> None:
    context = json.loads(row["dependency_context_json"])
    plan = json.loads(row["checkpoint_json"])["goal_plan_snapshot"]
    response = json.loads(row["response_json"])
    if "entry_load" not in plan and "entry_load" not in response:
        raise PlanningBuildPreviewError(
            "preview_required", "Нужен новый предпросмотр с начальной нагрузкой."
        )
    try:
        context = entry_validation_context(plan, context)
        expected = assess_entry_assignments(
            plan,
            entry_base(context, json.loads(row["parameters_json"])),
            execution_partition(context),
            context=context,
        )
        if plan.get("entry_load") != expected or response.get("entry_load") != expected:
            raise ValueError("entry assessment mismatch")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Предпросмотр начальной нагрузки повреждён.", status=500
        ) from exc
    if not expected["can_publish"]:
        error = PlanningBuildPreviewError(
            "entry_dose_infeasible", "Начальная нагрузка не готова к сохранению."
        )
        error.context = {"entry_load": expected}
        raise error


def historical_entry_load(plan: Mapping) -> dict:
    return deepcopy(
        plan.get("entry_load")
        or {
            "policy_version": None,
            "status": "unassessed",
            "can_publish": False,
            "scope": None,
            "profile": None,
            "limits": {},
            "blockers": [],
            "warnings": [],
        }
    )
