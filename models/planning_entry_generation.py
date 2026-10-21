"""Constrain existing catalog assignments to frozen per-sport entry envelopes."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import math
from typing import Mapping

from models.planning_entry_publication import entry_cap, leaf_exposures, window_excess
from models.workout_catalog import materialize_session_template
from models.training_planner import project_day_scalars


def _fits(records: list, candidate: list, assessment: Mapping) -> bool:
    day = max(r["date"] for r in candidate)
    return not window_excess(records + candidate, assessment, through=day)


def _retime(
    session: Mapping, *, minutes: float, day: Mapping, plan: Mapping, zones: Mapping
) -> dict | None:
    original = float(session.get("duration_minutes") or 0)
    target = float(
        session.get("total_tss")
        or (session.get("parameter_snapshot") or {}).get("target_tss")
        or 0
    )
    if minutes < 1 or original <= 0 or target <= 0:
        return None
    role = session.get("session_role") or day.get("session_role") or "easy"
    for factor in (1.0, 0.9, 0.75, 0.5, 0.3):
        request = (
            math.floor(min(target, target * minutes / original) * factor * 10) / 10
        )
        if request <= 0:
            continue
        built = materialize_session_template(
            phase=day["phase"],
            session_role=role,
            sport=session["sport"],
            target_tss=request,
            estimated_duration_minutes=math.floor(minutes),
            goal_type=plan["goal_type"],
            zone_snapshot=zones,
        )
        if (
            built.get("materialization_status") != "materialized"
            or float(built["duration_minutes"]) > minutes + 1e-7
            or float(built["parameter_snapshot"]["target_tss"]) > target + 1e-7
        ):
            continue
        if (
            plan.get("planning_mode") == "manual"
            or day.get("protected_by_event")
            or day["phase"] in {"Peak", "Taper", "Race Week"}
        ) and (
            built["session_role"] != role
            or built["template_key"] != session.get("template_key")
        ):
            continue
        clean = {
            k: v
            for k, v in session.items()
            if k
            not in {
                "session_id",
                "session_material_fingerprint",
                "replaces_session_id",
                "load_provenance",
                "mutation_evidence",
            }
        }
        clean.update(built)
        clean["total_tss"] = float(built["parameter_snapshot"]["target_tss"])
        clean["session_focus"] = built.get("template_name", role)
        clean["export_name"] = built.get("template_name", clean.get("export_name"))
        clean["entry_adjustment"] = {
            "kind": "retimed",
            "from_minutes": original,
            "to_minutes": built["duration_minutes"],
            "from_role": role,
            "to_role": built["session_role"],
        }
        return clean
    return None


def constrain_entry_assignments(
    plan: dict,
    assessment: Mapping,
    execution: Mapping,
    *,
    context: Mapping,
    zones: Mapping,
) -> dict:
    """Only reduce existing assignments; never fill a target by moving allowance."""
    result = deepcopy(plan)
    if assessment["blockers"] or execution["blockers"]:
        return result
    records = list(execution["actuals"])
    retired = set(execution["retired_session_ids"])
    adjustments = []
    for index, template in enumerate(result["session_templates"]):
        day = str(template["date"])[:10]
        if day < context["athlete_day"] or template.get("is_race_event"):
            continue
        accepted = []
        for session in template.get("sessions", []):
            if (
                session.get("session_id") in retired
                or session.get("replaces_session_id") in retired
            ):
                adjustments.append(
                    {
                        "date": day,
                        "kind": "completed_assignment_retired",
                        "session_id": session.get("session_id"),
                    }
                )
                continue
            candidate = leaf_exposures(session, day)
            if any(e["sport"] not in assessment["limits"] for e in candidate):
                accepted.append(session)
                continue  # Final validation refuses the unknown targeted sport.
            fits_session = all(
                float(e["minutes"] or 0)
                <= entry_cap(
                    assessment["limits"][e["sport"]], day, assessment["scope"]
                )["max_session_minutes"]
                + 1e-7
                for e in candidate
            )
            if fits_session and _fits(records, candidate, assessment):
                accepted.append(session)
                records.extend(candidate)
                continue
            preserved_intent = (
                result.get("planning_mode") == "manual"
                or template.get("protected_by_event")
                or template["phase"] in {"Peak", "Taper", "Race Week"}
            )
            replacement = None
            if session.get("kind") != "composite":
                sport = session["sport"]
                cap = entry_cap(assessment["limits"][sport], day, assessment["scope"])
                minutes = min(
                    float(session["duration_minutes"]),
                    cap["max_session_minutes"],
                    cap["weekly_minutes"],
                )
                # Account for every overlapping window, not just calendar weeks.
                cursor = date.fromisoformat(day) - timedelta(days=6)
                while cursor <= date.fromisoformat(day):
                    end = cursor + timedelta(days=6)
                    ceiling = entry_cap(
                        assessment["limits"][sport],
                        max(cursor.isoformat(), assessment["scope"]["start_date"]),
                        assessment["scope"],
                    )
                    prior = [
                        r
                        for r in records
                        if r["sport"] == sport
                        and cursor.isoformat() <= r["date"] <= end.isoformat()
                    ]
                    minutes = min(
                        minutes,
                        ceiling["weekly_minutes"]
                        - sum(float(r["minutes"]) for r in prior),
                    )
                    if len(prior) >= ceiling["weekly_sessions"]:
                        minutes = 0
                    cursor += timedelta(days=1)
                replacement = _retime(
                    session, minutes=minutes, day=template, plan=result, zones=zones
                )
            if replacement and _fits(
                records, leaf_exposures(replacement, day), assessment
            ):
                accepted.append(replacement)
                records.extend(leaf_exposures(replacement, day))
                adjustments.append(
                    {
                        "date": day,
                        "sport": session.get("sport"),
                        **replacement["entry_adjustment"],
                    }
                )
            elif preserved_intent:
                # Keep an honest infeasible candidate so final validation names
                # the conflict rather than silently replacing manual/race intent.
                accepted.append(session)
                records.extend(candidate)
            else:
                adjustments.append(
                    {
                        "date": day,
                        "sport": session.get("sport"),
                        "kind": "removed_at_entry_limit",
                        "from_minutes": session.get("duration_minutes"),
                    }
                )
        if accepted != template.get("sessions", []):
            template["sessions"] = accepted
            project_day_scalars(template)
            parts = {}
            for session in accepted:
                for leaf in (
                    session.get("legs", [])
                    if session.get("kind") == "composite"
                    else [session]
                ):
                    sport = leaf["sport"]
                    parts[sport] = parts.get(sport, 0.0) + float(
                        leaf.get("target_tss")
                        or leaf.get("total_tss")
                        or (leaf.get("parameter_snapshot") or {}).get("target_tss")
                        or 0
                    )
            template["allocated_parts"] = parts
            template["total_tss"] = sum(parts.values())
            result["daily_plan"][index] = (
                result["daily_plan"][index][0],
                sum(parts.values()),
                parts,
            )
        for week in result["weekly_summary"]:
            first = str(week["week_start"])[:10]
            if (
                first
                <= day
                <= (date.fromisoformat(first) + timedelta(days=6)).isoformat()
            ):
                pos = date.fromisoformat(day).weekday()
                for key, value in (
                    ("day_roles", template.get("session_role", "off")),
                    ("day_focuses", template.get("session_focus", "—")),
                ):
                    if len(week.get(key, [])) == 7:
                        week[key][pos] = value
    result["entry_adjustments"] = adjustments
    return result
