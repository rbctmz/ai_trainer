"""Pure final-build projections and publication readiness (not training suitability)."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import math
from typing import Any, Mapping

from models.planning_build_confirmation import (
    canonical_json,
    fingerprint,
    PlanningBuildPreviewError,
    PreparedPlanBuild,
)
from models.workout_catalog import (
    RPE_POLICY_VERSION,
    planned_bike_tss_from_steps,
    catalog_definitions,
    definition_snapshot,
)

READINESS_POLICY_VERSION = "plan-build-readiness-v1"
_CURRENT_DEFINITIONS = {
    (d.template_key, d.version): canonical_json(definition_snapshot(d))
    for d in catalog_definitions()
}
SPORTS = ("bike", "run", "swim", "walk")


def _map(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _day(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value or "")[:10]


def _daily(value: Any) -> tuple[str, Any, Mapping]:
    if isinstance(value, Mapping):
        return _day(value.get("date")), value.get("total_tss"), _map(value.get("parts"))
    row = _list(value)
    return (_day(row[0]), row[1], _map(row[2])) if len(row) == 3 else ("", None, {})


def _scope(plan: Mapping, context: Mapping) -> tuple[str, str]:
    lifecycle = _map(context.get("lifecycle"))
    rows = [_daily(row)[0] for row in _list(plan.get("daily_plan"))]
    start = max(
        str(context["athlete_day"]),
        str(lifecycle.get("start_date") or min(rows, default=context["athlete_day"])),
    )
    return start, str(
        lifecycle.get("end_date") or max(rows, default=context["athlete_day"])
    )


def _leaf_load(leaf: Mapping) -> float:
    return float(
        leaf.get(
            "total_tss",
            leaf.get(
                "target_tss", _map(leaf.get("parameter_snapshot")).get("target_tss", 0)
            ),
        )
        or 0
    )


def _session_parts(sessions: list) -> dict[str, float]:
    buckets: dict[str, float] = defaultdict(float)
    for session in sessions:
        session = _map(session)
        for leaf in (
            _list(session.get("legs"))
            if session.get("kind") == "composite"
            else [session]
        ):
            leaf = _map(leaf)
            buckets[str(leaf.get("sport"))] += _leaf_load(leaf)
    return {
        sport: round(value, 1) for sport, value in buckets.items() if sport in SPORTS
    }


def effective_build_totals(plan: Mapping) -> dict[str, int]:
    """Round whole-plan raw sums once; weekly displays are never the input."""
    days = [_daily(row) for row in plan["daily_plan"]]
    weeks = _list(plan.get("weekly_summary"))
    sums = [
        math.fsum(
            float(total)
            for day, total, _ in days
            if _day(w["week_start"])
            <= day
            <= (
                date.fromisoformat(_day(w["week_start"])) + timedelta(days=6)
            ).isoformat()
        )
        for w in weeks
    ]
    return {
        "total_tss": round(math.fsum(float(total) for _, total, _ in days)),
        "peak_tss": round(max(sums, default=0)),
    }


def _load_provenance(leaf: Mapping) -> dict[str, str]:
    if leaf.get("kind") == "composite":
        return {"method": "sum_leg_tss_v1", "status": "aggregated", "source": "legs"}
    if (
        leaf.get("sport") == "bike"
        and _map(leaf.get("target_provenance")).get("kind") == "ftp"
    ):
        return {
            "method": "prescription_np_tss_v1",
            "status": "derived",
            "source": "ordered_power_steps",
        }
    return {
        "method": "catalog_budget_estimate_v1",
        "status": "estimated",
        "source": "catalog_tss_budget",
    }


def normalize_build_loads(plan: dict, context: Mapping) -> dict:
    """Project delivered future load; leave saved past assignments untouched."""
    result = deepcopy(plan)
    start, end = _scope(plan, context)
    templates = {_day(row.get("date")): row for row in result["session_templates"]}
    days = []
    for row in result["daily_plan"]:
        day, total, parts = _daily(row)
        template = templates.get(day, {})
        if start <= day <= end and template.get("sessions"):
            for session in template["sessions"]:
                session["load_provenance"] = _load_provenance(session)
                for leg in session.get("legs") or []:
                    leg["load_provenance"] = _load_provenance(leg)
            parts = _session_parts(template["sessions"])
            total = round(math.fsum(parts.values()), 1)
        days.append((row[0], total, dict(parts)))
    result["daily_plan"] = days
    for week in result["weekly_summary"]:
        first = _day(week["week_start"])
        last = (date.fromisoformat(first) + timedelta(days=6)).isoformat()
        members = [_daily(row) for row in days if first <= _daily(row)[0] <= last]
        week["weekly_tss"] = round(math.fsum(float(total) for _, total, _ in members))
        for sport in ("bike", "run", "swim"):
            week[sport] = round(
                math.fsum(float(parts.get(sport, 0)) for _, _, parts in members), 1
            )
    result["weekly_tss_plan"] = [
        week["weekly_tss"] for week in result["weekly_summary"]
    ]
    return result


def forecast_build_input(plan: Mapping, context: Mapping, metrics: Mapping) -> dict:
    """Freeze final planned load separately from forecast-only race effort."""
    days = {_daily(row)[0]: _daily(row)[1] for row in plan["daily_plan"]}
    lifecycle = _map(context.get("lifecycle"))
    start = str(context["athlete_day"]) if lifecycle else min(days)
    end = str(lifecycle.get("end_date") or max(days))
    races: dict[str, float] = defaultdict(float)
    for row in _list(plan.get("race_forecast_loads")):
        races[_day(row.get("date"))] += float(row.get("tss") or 0)
    rows = []
    current = date.fromisoformat(start)
    while current.isoformat() <= end:
        day = current.isoformat()
        planned, race = float(days.get(day, 0)), races.get(day, 0)
        rows.append(
            {
                "date": day,
                "planned_tss": planned,
                "race_tss": race,
                "total_tss": planned + race,
            }
        )
        current += timedelta(days=1)
    return {
        "start_date": start,
        "end_date": end,
        "initial_metrics": {key: metrics[key] for key in ("ctl", "atl", "tsb")},
        "daily_loads": rows,
    }


def _binding(plan: Mapping, response: Mapping, context: Mapping) -> str:
    # Receipt/transport decoration is assigned after the final assessment.
    excluded = {"build_readiness", "plan_id", "confirmation", "parameters"}
    return fingerprint(
        {
            "plan": {k: v for k, v in plan.items() if k != "build_readiness"},
            "response": {k: v for k, v in response.items() if k not in excluded},
            "context": context,
        }
    )


def assess_plan_build_readiness(
    plan: Mapping, response: Mapping, context: Mapping
) -> dict:
    """Assess one frozen final candidate without I/O, clocks, or Banister simulation."""
    blockers: list[dict] = []
    start, end = _scope(plan, context)
    address: dict[str, Any] = {"date": None, "session_id": None, "leg_index": None}

    def fail(code: str, field: str, expected: Any, observed: Any) -> None:
        # JSON cannot represent NaN/Infinity; keep the reason, not an invalid DTO.
        def safe(value):
            if isinstance(value, float) and not math.isfinite(value):
                return str(value)
            if isinstance(value, Mapping):
                return {str(k): safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [safe(v) for v in value]
            return value

        blockers.append(
            {
                "code": code,
                **address,
                "field": field,
                "expected": safe(expected),
                "observed": safe(observed),
            }
        )

    def equal(
        observed: Any,
        expected: float,
        field: str,
        *,
        decimals: int = 1,
        code="load_inconsistent",
    ) -> None:
        number = _num(observed)
        if number is None or round(number, decimals) != round(expected, decimals):
            fail(code, field, round(expected, decimals), observed)

    def target(
        leaf: Mapping, step: Mapping, index: int, count: int, field: str
    ) -> None:
        provenance = _map(leaf.get("target_provenance"))
        value = _map(step.get("target"))
        kind = provenance.get("kind")
        units = {
            "ftp": ("power", "watts"),
            "lthr": ("heart_rate", "bpm"),
            "threshold_pace": ("pace", "seconds_per_km"),
            "css": ("pace", "seconds_per_100m"),
            "relative_rpe": ("relative_rpe", "rpe_1_10"),
        }
        low_key, high_key = (
            ("fast", "slow") if value.get("type") == "pace" else ("low", "high")
        )
        low, high = _num(value.get(low_key)), _num(value.get(high_key))
        valid = (
            kind in units
            and kind in _list(_map(leaf.get("definition_snapshot")).get("target_preference"))
            and (value.get("type"), value.get("unit")) == units.get(kind)
            and low is not None
            and high is not None
            and 0 < low <= high
        )
        if kind == "relative_rpe":
            definition = _map(leaf.get("definition_snapshot"))
            policy_rows = _list(definition.get("rpe_stage_targets"))
            policy = {
                r[0]: (r[1], r[2])
                for r in policy_rows
                if isinstance(r, (list, tuple))
                and len(r) == 3
                and isinstance(r[0], str)
            }
            stage = (
                "warmup"
                if index == 0
                else "cooldown"
                if index == count - 1
                else step.get("segment_kind")
            )
            stage = (
                stage
                if stage in {"warmup", "cooldown", "work", "recovery"}
                else "stage"
            )
            valid = (
                valid
                and high <= 10
                and len(policy_rows) == len(policy) == 5
                and all(
                    _num(a) is not None and _num(b) is not None and 1 <= a <= b <= 10
                    for a, b in policy.values()
                )
                and provenance.get("policy_version") == RPE_POLICY_VERSION
                and definition.get("rpe_policy_version") == RPE_POLICY_VERSION
                and provenance.get("source") == "catalog.rpe_policy"
                and provenance.get("policy_key") == leaf.get("template_key")
                and set(policy) == {"warmup", "cooldown", "stage", "work", "recovery"}
                and policy.get(stage) == (low, high)
            )
        else:
            reference = _num(provenance.get("value"))
            valid = (
                valid
                and reference is not None
                and reference > 0
                and provenance.get("source")
                == {
                    "ftp": "athlete_profile.ftp",
                    "lthr": "athlete_profile.lthr",
                    "threshold_pace": "athlete_profile.threshold_pace_seconds_per_km",
                    "css": "athlete_profile.css",
                }.get(kind)
            )
        if kind != "relative_rpe" and valid:
            a, b = _num(value.get("relative_low")), _num(value.get("relative_high"))
            if a is None or b is None or not 0 < a <= b:
                valid = False
            elif kind in {"ftp", "lthr"}:
                valid = low == round(reference * a) and high == round(reference * b)
            else:
                valid = low == round(reference / b, 1) and high == round(
                    reference / a, 1
                )
        if not valid:
            fail(
                "target_semantics_unverified",
                field,
                "finite range, unit and frozen target provenance/policy",
                value,
            )

    def approved_definition(row: Mapping, field: str, *, leg: bool = False) -> None:
        definition = _map(row.get("definition_snapshot"))
        try:
            known = _CURRENT_DEFINITIONS.get(
                (row.get("template_key"), row.get("template_version"))
            )
            valid = known is not None and canonical_json(definition) == known
        except (TypeError, ValueError):
            valid = False
        if (
            not valid
            or row.get("sport") != definition.get("sport")
            or current_phase not in _list(definition.get("phase_eligibility"))
            or (
                not leg
                and row.get("session_role") not in _list(definition.get("roles"))
            )
        ):
            fail(
                "prescription_infeasible",
                field + ".definition_snapshot",
                "known version and matching sport/eligible phase/role",
                row.get("template_key"),
            )

    def leaf_check(
        leaf: Mapping, field: str, *, leg: bool = False
    ) -> tuple[float, float]:
        if leaf.get("materialization_status") != "materialized" or leaf.get(
            "failed_bounds"
        ):
            fail(
                "prescription_infeasible",
                field,
                "materialized without failed_bounds",
                leaf.get("materialization_status"),
            )
        steps = _list(leaf.get("materialized_steps"))
        if not steps:
            fail(
                "prescription_missing",
                field + ".materialized_steps",
                "nonempty steps",
                leaf.get("materialized_steps"),
            )
        approved_definition(leaf, field, leg=leg)
        if leaf.get("load_provenance") != _load_provenance(leaf):
            fail(
                "load_inconsistent",
                field + ".load_provenance",
                _load_provenance(leaf),
                leaf.get("load_provenance"),
            )
        params = _map(leaf.get("parameter_snapshot"))
        effective = leaf.get("target_tss") if leg else leaf.get("total_tss")
        load = _num(effective)
        minutes = _num(leaf.get("duration_minutes"))
        if load is None or load < 0:
            fail(
                "load_inconsistent",
                field + ".total_tss",
                "finite nonnegative effective load",
                effective,
            )
        if minutes is None or minutes <= 0:
            fail(
                "duration_inconsistent",
                field + ".duration_minutes",
                "positive finite minutes",
                leaf.get("duration_minutes"),
            )
        load, minutes = load or 0, minutes or 0
        definition = _map(leaf.get("definition_snapshot"))
        bounds = [
            ("min_duration_minutes", "max_duration_minutes", minutes),
            ("min_tss", "max_tss", load),
            (
                "min_tss_per_hour",
                "max_tss_per_hour",
                load * 60 / minutes if minutes > 0 else 0,
            ),
        ]
        valid_bounds = all(
            _num(definition.get(lo)) is not None
            and _num(definition.get(hi)) is not None
            and 0 <= definition[lo] <= value <= definition[hi]
            for lo, hi, value in bounds
        )
        if not valid_bounds or leaf.get("sport") not in SPORTS:
            fail(
                "prescription_infeasible",
                field + ".definition_bounds",
                "effective dose/time inside frozen catalog bounds",
                {"load": load, "minutes": minutes},
            )
        equal(params.get("target_tss"), load, field + ".parameter_snapshot.target_tss")
        equal(
            params.get("duration_minutes"),
            minutes,
            field + ".parameter_snapshot.duration_minutes",
            code="duration_inconsistent",
        )
        seconds, step_load = 0.0, 0.0
        numeric_steps = True
        for i, raw in enumerate(steps):
            step = _map(raw)
            secs, tss = _num(step.get("duration_seconds")), _num(step.get("tss"))
            if secs is None or secs <= 0:
                fail(
                    "duration_inconsistent",
                    f"{field}.materialized_steps[{i}].duration_seconds",
                    "positive finite seconds",
                    step.get("duration_seconds"),
                )
            if tss is None or tss < 0:
                fail(
                    "load_inconsistent",
                    f"{field}.materialized_steps[{i}].tss",
                    "finite nonnegative TSS",
                    step.get("tss"),
                )
                numeric_steps = False
            seconds += secs or 0
            step_load += tss or 0
            target(leaf, step, i, len(steps), f"{field}.materialized_steps[{i}].target")
        equal(
            seconds,
            minutes * 60,
            field + ".step_seconds",
            decimals=3,
            code="duration_inconsistent",
        )
        if numeric_steps:
            equal(step_load, load, field + ".step_tss")
        evidence = _map(params.get("planned_tss_evidence"))
        if (
            params.get("planned_tss_method")
            or evidence
            or (
                leaf.get("sport") == "bike"
                and _map(leaf.get("target_provenance")).get("kind") == "ftp"
            )
        ):
            equal(
                evidence.get("planned_tss"),
                load,
                field + ".planned_tss_evidence.planned_tss",
            )
            equal(
                params.get("planned_tss"),
                load,
                field + ".parameter_snapshot.planned_tss",
            )
            if (
                evidence.get("method") != "prescription_np_tss_v1"
                or evidence.get("status") != "derived"
                or params.get("planned_tss_method") != "prescription_np_tss_v1"
            ):
                fail(
                    "load_inconsistent",
                    field + ".planned_tss_method",
                    "prescription_np_tss_v1 derived evidence",
                    evidence.get("method"),
                )
            if (
                steps
                and all(isinstance(step, Mapping) for step in steps)
                and 0 < seconds <= 24 * 3600
                and all(
                    _num(step.get("duration_seconds")) is not None
                    and step["duration_seconds"] > 0
                    for step in steps
                )
                and all(
                    _map(s.get("target")).get("type") == "power"
                    for s in steps
                    if isinstance(s, Mapping)
                )
            ):
                derived = planned_bike_tss_from_steps(
                    steps, leaf.get("target_provenance")
                )
                equal(derived.get("planned_tss"), load, field + ".derived_power_tss")
        return load, minutes

    days = [_daily(row) for row in _list(plan.get("daily_plan"))]
    templates = _list(plan.get("session_templates"))
    by_day = {_day(_map(row).get("date")): _map(row) for row in templates}
    if len(by_day) != len(templates) or len({r[0] for r in days}) != len(days):
        fail("prescription_missing", "calendar", "unique dates", "duplicate dates")
    if {r[0] for r in days} != set(by_day):
        fail(
            "prescription_missing",
            "session_templates",
            "one day template per daily row",
            sorted(by_day),
        )
    lifecycle = _map(context.get("lifecycle"))
    if lifecycle and any(
        not lifecycle["start_date"] <= day <= lifecycle["end_date"]
        for day, _, _ in days
    ):
        fail(
            "prescription_infeasible",
            "calendar.scope",
            "days inside selected cycle",
            [day for day, _, _ in days],
        )
    expected_days = {
        (date.fromisoformat(start) + timedelta(days=i)).isoformat()
        for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)
    }
    if not expected_days <= {row[0] for row in days}:
        fail(
            "prescription_missing",
            "daily_plan",
            "complete future calendar",
            sorted(expected_days - {r[0] for r in days}),
        )
    count = 0
    seen_ids: set[str] = set()
    current_phase = ""
    minutes_by_day = {}
    for day, total, parts in days:
        if not (start <= day <= end):
            continue
        address.update(date=day, session_id=None, leg_index=None)
        template = by_day.get(day, {})
        current_phase = template.get("phase")
        sessions = _list(template.get("sessions"))
        is_rest = (
            template.get("session_role") in {"off", "race", "rest"}
            or template.get("is_race_event") is True
        )
        if not sessions and not is_rest:
            fail("prescription_missing", "sessions", "exercise or explicit rest", None)
        if is_rest and sessions:
            fail(
                "prescription_infeasible",
                "sessions",
                "no exercise on rest/event day",
                len(sessions),
            )
        day_load, day_minutes = 0.0, 0.0
        buckets: dict[str, float] = defaultdict(float)
        for i, raw in enumerate(sessions):
            session = _map(raw)
            count += 1
            identity = session.get("session_id")
            if not isinstance(identity, str) or not identity or identity in seen_ids:
                fail(
                    "prescription_missing",
                    f"sessions[{i}].session_id",
                    "unique stamped session identity",
                    identity,
                )
            else:
                seen_ids.add(identity)
            address.update(session_id=session.get("session_id"), leg_index=None)
            field = f"sessions[{i}]"
            if session.get("kind") not in {"single", "composite"}:
                fail(
                    "prescription_infeasible",
                    field + ".kind",
                    "single or composite",
                    session.get("kind"),
                )
            if session.get("kind") == "composite":
                approved_definition(session, field)
                if session.get("load_provenance") != _load_provenance(session):
                    fail(
                        "load_inconsistent",
                        field + ".load_provenance",
                        _load_provenance(session),
                        session.get("load_provenance"),
                    )
                legs = _list(session.get("legs"))
                if session.get(
                    "materialization_status"
                ) != "materialized" or session.get("failed_bounds"):
                    fail(
                        "prescription_infeasible",
                        field,
                        "materialized composite",
                        session.get("materialization_status"),
                    )
                if not legs:
                    fail(
                        "prescription_missing",
                        field + ".legs",
                        "nonempty legs",
                        session.get("legs"),
                    )
                required_sports = _list(_map(session.get("definition_snapshot")).get("requirements"))
                actual_sports = [_map(leg).get("sport") for leg in legs]
                if not required_sports or actual_sports != required_sports:
                    fail(
                        "prescription_missing",
                        field + ".legs",
                        required_sports,
                        actual_sports,
                    )
                load, minutes = 0.0, 0.0
                for j, raw_leg in enumerate(legs):
                    leg = _map(raw_leg)
                    address["leg_index"] = j + 1
                    identity = leg.get("leg_id")
                    if (
                        not isinstance(identity, str)
                        or not identity
                        or identity in seen_ids
                        or leg.get("leg_index") != j + 1
                    ):
                        fail(
                            "prescription_missing",
                            f"{field}.legs[{j}].leg_id",
                            "unique ordered leg identity",
                            identity,
                        )
                    else:
                        seen_ids.add(identity)
                    leg_load, leg_minutes = leaf_check(
                        leg, f"{field}.legs[{j}]", leg=True
                    )
                    buckets[str(leg.get("sport"))] += leg_load
                    load += leg_load
                    minutes += leg_minutes
                address["leg_index"] = None
                transition = _num(session.get("transition_minutes"))
                if transition is None or transition < 0:
                    fail(
                        "duration_inconsistent",
                        field + ".transition_minutes",
                        "explicit nonnegative transition",
                        session.get("transition_minutes"),
                    )
                minutes += transition or 0
                equal(
                    session.get("duration_minutes"),
                    minutes,
                    field + ".duration_minutes",
                    code="duration_inconsistent",
                )
                equal(session.get("total_tss"), load, field + ".total_tss")
                equal(
                    _map(session.get("parameter_snapshot")).get("target_tss"),
                    load,
                    field + ".parameter_snapshot.target_tss",
                )
                equal(
                    _map(session.get("parameter_snapshot")).get("duration_minutes"),
                    minutes,
                    field + ".parameter_snapshot.duration_minutes",
                    code="duration_inconsistent",
                )
            else:
                load, minutes = leaf_check(session, field)
                buckets[str(session.get("sport"))] += load
            day_load += load
            day_minutes += minutes
        address.update(session_id=None, leg_index=None)
        equal(total, day_load, "daily_plan.total_tss")
        for sport in set(parts) | set(buckets):
            equal(
                parts.get(sport, 0), buckets.get(sport, 0), "daily_plan.parts." + sport
            )
        minutes_by_day[day] = day_minutes
        if sessions:
            primary = _map(sessions[0])
            address["session_id"] = primary.get("session_id")
            for key in (
                "materialization_status",
                "session_role",
                "sport",
                "template_key",
                "kind",
                "definition_snapshot",
                "parameter_snapshot",
                "materialized_steps",
                "target_provenance",
                "legs",
                "transition_minutes",
            ):
                if key in template and template[key] != primary.get(key):
                    fail(
                        "prescription_infeasible",
                        "primary." + key,
                        "same primary-session projection",
                        "contradictory day mirror",
                    )
            address["session_id"] = None
            equal(
                template.get("duration_minutes"),
                float(sessions[0].get("duration_minutes") or 0),
                "primary.duration_minutes",
                code="duration_inconsistent",
            )
    address.update(date=None, session_id=None, leg_index=None)
    weeks = _list(plan.get("weekly_summary"))
    week_starts = [_day(_map(week).get("week_start")) for week in weeks]
    if len(set(week_starts)) != len(week_starts):
        fail(
            "load_inconsistent", "weekly_summary", "unique calendar weeks", week_starts
        )
    if any(
        sum(
            1
            for first in week_starts
            if first
            <= day
            <= (date.fromisoformat(first) + timedelta(days=6)).isoformat()
        )
        != 1
        for day, _, _ in days
    ):
        fail(
            "load_inconsistent",
            "weekly_summary",
            "each daily load counted by exactly one calendar week",
            week_starts,
        )
    effective_weeks = []
    params = _map(context.get("parameters"))
    for i, raw in enumerate(weeks):
        week = _map(raw)
        first = _day(week.get("week_start"))
        last = (date.fromisoformat(first) + timedelta(days=6)).isoformat()
        members = [
            (day, total, parts) for day, total, parts in days if first <= day <= last
        ]
        raw_total = math.fsum(_num(total) or 0 for _, total, _ in members)
        effective_weeks.append(round(raw_total))
        equal(
            week.get("weekly_tss"),
            raw_total,
            f"weekly_summary[{i}].weekly_tss",
            decimals=0,
        )
        for sport in ("bike", "run", "swim"):
            sport_sum = math.fsum(
                _num(parts.get(sport, 0)) or 0 for _, _, parts in members
            )
            equal(week.get(sport), sport_sum, f"weekly_summary[{i}].{sport}")
        public = _map((_list(response.get("weeks")) + [{}] * len(weeks))[i])
        equal(
            public.get("weekly_tss"),
            raw_total,
            f"response.weeks[{i}].weekly_tss",
            decimals=0,
        )
        for sport in ("bike", "run", "swim"):
            equal(
                public.get(sport),
                math.fsum(_num(parts.get(sport, 0)) or 0 for _, _, parts in members),
                f"response.weeks[{i}].{sport}",
                decimals=0,
            )
        hours = _num(params.get("available_hours"))
        used = math.fsum(minutes_by_day.get(day, 0) for day, _, _ in members)
        if hours is None or used > hours * 60 + 1e-6:
            fail(
                "availability_exceeded",
                f"weekly_summary[{i}].minutes",
                (hours or 0) * 60,
                used,
            )
    if (
        plan.get("weekly_tss_plan") != effective_weeks
        or any(_num(value) is None for value in _list(plan.get("weekly_tss_plan")))
    ) or len(_list(response.get("weeks"))) != len(weeks):
        fail(
            "load_inconsistent",
            "weekly_tss_plan",
            effective_weeks,
            plan.get("weekly_tss_plan"),
        )
    if not weeks:
        fail("load_inconsistent", "weekly_summary", "calendar weeks", weeks)
    for day, minutes in minutes_by_day.items():
        weekday = date.fromisoformat(day).weekday()
        if minutes > 0 and ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][
            weekday
        ] not in _list(params.get("available_days")):
            address["date"] = day
            fail(
                "availability_exceeded",
                "available_days",
                params.get("available_days"),
                weekday,
            )
    address["date"] = None
    total = round(math.fsum(_num(value) or 0 for _, value, _ in days))
    equal(
        _map(response.get("totals")).get("total_tss"),
        total,
        "response.totals.total_tss",
        decimals=0,
    )
    equal(
        _map(response.get("totals")).get("peak_tss"),
        max(effective_weeks, default=0),
        "response.totals.peak_tss",
        decimals=0,
    )
    preview = _map(response.get("preview"))
    equal(
        preview.get("total_tss_after"),
        total,
        "response.preview.total_tss_after",
        decimals=0,
    )
    before_total = _num(preview.get("total_tss_before"))
    if before_total is None or before_total < 0:
        fail(
            "load_inconsistent",
            "response.preview.total_tss_before",
            "finite nonnegative prior total",
            preview.get("total_tss_before"),
        )
    else:
        equal(
            preview.get("weekly_tss_delta"),
            total - before_total,
            "response.preview.weekly_tss_delta",
            decimals=0,
        )
    if preview.get("weekly_tss_after") != effective_weeks:
        fail(
            "load_inconsistent",
            "response.preview.weekly_tss_after",
            effective_weeks,
            preview.get("weekly_tss_after"),
        )
    frozen_input = _map(plan.get("forecast_input"))
    try:
        expected_input = forecast_build_input(
            plan, context, _map(frozen_input.get("initial_metrics"))
        )
        if frozen_input != expected_input or any(
            _num(value) is None
            for value in _map(frozen_input.get("initial_metrics")).values()
        ):
            fail(
                "load_inconsistent",
                "forecast_input",
                "final effective daily/race loads",
                frozen_input,
            )
        if _map(response.get("forecast")).get("input_fingerprint") != fingerprint(
            frozen_input
        ):
            fail(
                "load_inconsistent",
                "response.forecast.input_fingerprint",
                fingerprint(frozen_input),
                _map(response.get("forecast")).get("input_fingerprint"),
            )
    except (ValueError, TypeError, KeyError):
        fail(
            "load_inconsistent",
            "forecast_input",
            "finite final forecast inputs",
            "missing or invalid",
        )
    forecast = _map(response.get("forecast"))
    points = _list(forecast.get("points"))
    input_rows = _list(frozen_input.get("daily_loads"))
    point_dates = [_map(row).get("date") for row in input_rows]
    expected_points = [
        day
        for i, day in enumerate(point_dates)
        if i % 7 == 0 or i == len(point_dates) - 1
    ]
    if [_map(point).get("date") for point in points] != expected_points or not points:
        fail(
            "load_inconsistent",
            "response.forecast.points",
            expected_points,
            [_map(point).get("date") for point in points],
        )
    for i, row in enumerate(input_rows):
        if any(
            _num(_map(row).get(key)) is None or _map(row)[key] < 0
            for key in ("planned_tss", "race_tss", "total_tss")
        ):
            fail(
                "load_inconsistent",
                f"forecast_input.daily_loads[{i}]",
                "finite nonnegative loads",
                row,
            )
    if points:
        equal(
            forecast.get("final_tsb"),
            _num(_map(points[-1]).get("tsb")) or 0,
            "response.forecast.final_tsb",
        )
    for i, point in enumerate(points):
        if any(_num(_map(point).get(key)) is None for key in ("ctl", "atl", "tsb")):
            fail(
                "load_inconsistent",
                f"response.forecast.points[{i}]",
                "finite modeled load",
                point,
            )
    blockers.sort(
        key=lambda b: (
            b["date"] or "",
            b["session_id"] or "",
            b["leg_index"] or 0,
            b["field"],
            b["code"],
        )
    )
    try:
        binding = _binding(plan, response, context)
    except (ValueError, TypeError):
        binding = None
        fail(
            "load_inconsistent",
            "candidate",
            "finite serializable candidate",
            "invalid JSON values",
        )
    return {
        "policy_version": READINESS_POLICY_VERSION,
        "status": "blocked" if blockers else "ready",
        "can_confirm": not blockers,
        "scope": {"start_date": start, "end_date": end},
        "assessed_session_count": count,
        "candidate_fingerprint": binding,
        "blockers": blockers,
        "warnings": [],
        "training_suitability": "not_assessed",
    }


def require_prepared_readiness(prepared: PreparedPlanBuild) -> None:
    """Refuse before creating any pending row; never trust a stored ready flag."""
    import json

    checkpoint = json.loads(prepared.checkpoint_json)
    plan, response = (
        checkpoint["goal_plan_snapshot"],
        json.loads(prepared.response_json),
    )
    context = {
        **prepared.snapshot.context(),
        "parameters": prepared.snapshot.parameters.as_dict(),
    }
    assessment = assess_plan_build_readiness(plan, response, context)
    if (
        canonical_json(plan.get("build_readiness")) != canonical_json(assessment)
        or canonical_json(response.get("build_readiness")) != canonical_json(assessment)
        or any(checkpoint.get(k) != v for k, v in effective_build_totals(plan).items())
    ):
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Предпросмотр повреждён; требуется проверка.", status=500
        )
    if assessment["status"] != "ready":
        error = PlanningBuildPreviewError(
            "plan_not_ready",
            "План содержит неполные или несогласованные задания; проверьте причины.",
            status=422,
        )
        error.context = {"build_readiness": assessment}
        raise error


def validate_retained_readiness(row: Mapping) -> None:
    """Pending-only pure validation. The transaction owner replays old receipts first."""
    import json

    checkpoint, response = (
        json.loads(row["checkpoint_json"]),
        json.loads(row["response_json"]),
    )
    plan = checkpoint.get("goal_plan_snapshot")
    if not isinstance(plan, Mapping):
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Предпросмотр повреждён; требуется проверка.", status=500
        )
    assessment = plan.get("build_readiness")
    if assessment is None and response.get("build_readiness") is None:
        raise PlanningBuildPreviewError(
            "preview_required", "Нужен новый предпросмотр с проверкой готовности."
        )
    context = {
        **json.loads(row["dependency_context_json"]),
        "parameters": json.loads(row["parameters_json"]),
    }
    try:
        expected = assess_plan_build_readiness(plan, response, context)
        if canonical_json(assessment) != canonical_json(expected) or canonical_json(
            response.get("build_readiness")
        ) != canonical_json(expected):
            raise ValueError("retained assessment mismatch")
        for key, value in effective_build_totals(plan).items():
            if checkpoint.get(key) != value:
                raise ValueError("checkpoint header mismatch")
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise PlanningBuildPreviewError(
            "preview_corrupt", "Предпросмотр повреждён; требуется проверка.", status=500
        ) from exc
    if expected["status"] != "ready":
        error = PlanningBuildPreviewError(
            "plan_not_ready", "План не готов к сохранению; проверьте причины."
        )
        error.context = {"build_readiness": expected}
        raise error


def historical_build_readiness(plan: Mapping) -> dict:
    """Read-only provenance projection; no historical backfill or reassessment."""
    return dict(
        _map(plan.get("build_readiness"))
        or {
            "policy_version": None,
            "status": "unassessed",
            "can_confirm": False,
            "scope": None,
            "assessed_session_count": 0,
            "candidate_fingerprint": None,
            "blockers": [],
            "warnings": [],
            "training_suitability": "not_assessed",
        }
    )
