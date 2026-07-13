from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


CATALOG_VERSION = "workout_catalog_v1"
SELECTOR_RULE_VERSION = "workout_selector_v1"
MATERIALIZER_RULE_VERSION = "workout_materializer_v1"


@dataclass(frozen=True)
class WorkoutTemplateDefinition:
    template_key: str
    version: int
    display_name: str
    kind: str
    sport: str
    roles: tuple[str, ...]
    stimulus: str
    phase_eligibility: tuple[str, ...]
    goal_eligibility: tuple[str, ...]
    min_duration_minutes: int
    max_duration_minutes: int
    min_tss: float
    max_tss: float
    min_tss_per_hour: float
    max_tss_per_hour: float
    fatigue_cost: tuple[int, int, int]
    expected_recovery_hours: int
    target_preference: tuple[str, ...]
    requirements: tuple[str, ...]
    contraindications: tuple[str, ...]
    step_builder_key: str


_ALL_TRAINING_PHASES = ("Base", "Build", "Peak", "Taper", "Race Week", "Maintenance")
_TRIATHLON_GOALS = ("triathlon", "триатлон")


def _definition(
    template_key: str,
    display_name: str,
    sport: str,
    roles: tuple[str, ...],
    stimulus: str,
    phases: tuple[str, ...],
    duration: tuple[int, int],
    tss: tuple[float, float],
    density: tuple[float, float],
    fatigue: tuple[int, int, int],
    recovery_hours: int,
    targets: tuple[str, ...],
    builder: str,
    *,
    kind: str = "single",
    goals: tuple[str, ...] = ("any",),
    requirements: tuple[str, ...] = (),
    contraindications: tuple[str, ...] = (),
) -> WorkoutTemplateDefinition:
    return WorkoutTemplateDefinition(
        template_key=template_key,
        version=1,
        display_name=display_name,
        kind=kind,
        sport=sport,
        roles=roles,
        stimulus=stimulus,
        phase_eligibility=phases,
        goal_eligibility=goals,
        min_duration_minutes=duration[0],
        max_duration_minutes=duration[1],
        min_tss=tss[0],
        max_tss=tss[1],
        min_tss_per_hour=density[0],
        max_tss_per_hour=density[1],
        fatigue_cost=fatigue,
        expected_recovery_hours=recovery_hours,
        target_preference=targets,
        requirements=requirements,
        contraindications=contraindications,
        step_builder_key=builder,
    )


_CATALOG = (
    _definition(
        "bike_recovery_spin", "Recovery Spin", "bike", ("recovery", "easy"),
        "circulation and low-cost aerobic recovery", _ALL_TRAINING_PHASES,
        (20, 75), (5, 45), (15, 45), (1, 0, 0), 8, ("ftp", "relative_rpe"), "recovery",
    ),
    _definition(
        "bike_aerobic_endurance", "Aerobic Endurance Ride", "bike", ("easy", "long"),
        "durable aerobic endurance", _ALL_TRAINING_PHASES,
        (40, 240), (20, 180), (35, 75), (1, 1, 0), 18, ("ftp", "relative_rpe"), "endurance",
    ),
    _definition(
        "bike_aerobic_progression", "Aerobic Progression Ride", "bike", ("quality", "long"),
        "progressive aerobic durability", ("Base", "Build", "Maintenance"),
        (45, 180), (25, 160), (45, 85), (2, 1, 0), 24, ("ftp", "relative_rpe"), "progression",
    ),
    _definition(
        "bike_tempo_sweet_spot", "Tempo / Sweet Spot", "bike", ("quality",),
        "sustained sub-threshold work", ("Build", "Peak", "Maintenance"),
        (45, 150), (35, 180), (60, 95), (2, 1, 1), 30, ("ftp", "relative_rpe"), "tempo",
    ),
    _definition(
        "bike_threshold_intervals", "Threshold Intervals", "bike", ("quality",),
        "lactate-threshold development", ("Build", "Peak"),
        (40, 120), (35, 160), (70, 110), (3, 1, 1), 36, ("ftp", "relative_rpe"), "threshold",
    ),
    _definition(
        "bike_vo2max_intervals", "VO2max Intervals", "bike", ("quality",),
        "maximal aerobic power", ("Build", "Peak", "Taper", "Race Week"),
        (35, 90), (30, 125), (75, 120), (3, 1, 2), 42, ("ftp", "relative_rpe"), "vo2",
    ),
    _definition(
        "bike_neuromuscular_sprints", "Neuromuscular Sprints", "bike", ("quality", "easy"),
        "neuromuscular recruitment", ("Base", "Build", "Peak", "Taper", "Race Week", "Maintenance"),
        (30, 75), (20, 85), (40, 90), (1, 1, 3), 30, ("ftp", "relative_rpe"), "neuromuscular",
    ),
    _definition(
        "run_recovery", "Recovery Run", "run", ("recovery", "easy"),
        "low-cost running frequency", _ALL_TRAINING_PHASES,
        (20, 60), (8, 55), (20, 65), (1, 1, 0), 12, ("threshold_pace", "lthr", "relative_rpe"), "recovery",
    ),
    _definition(
        "run_aerobic_endurance", "Aerobic Endurance Run", "run", ("easy", "long"),
        "aerobic endurance and durability", _ALL_TRAINING_PHASES,
        (30, 150), (20, 150), (35, 80), (1, 2, 0), 24, ("threshold_pace", "lthr", "relative_rpe"), "endurance",
    ),
    _definition(
        "run_progression", "Progression Run", "run", ("quality", "long"),
        "progressive aerobic durability", ("Base", "Build", "Maintenance"),
        (35, 120), (25, 130), (45, 90), (2, 2, 0), 30, ("threshold_pace", "lthr", "relative_rpe"), "progression",
    ),
    _definition(
        "run_tempo_threshold", "Tempo / Threshold Run", "run", ("quality",),
        "sustained threshold running", ("Build", "Peak"),
        (35, 100), (30, 125), (55, 105), (3, 2, 1), 42, ("threshold_pace", "lthr", "relative_rpe"), "threshold",
    ),
    _definition(
        "run_vo2_neuromuscular", "VO2 / Neuromuscular Run", "run", ("quality",),
        "maximal aerobic power and economy", ("Build", "Peak", "Taper", "Race Week"),
        (30, 75), (25, 95), (60, 115), (3, 2, 3), 48, ("threshold_pace", "lthr", "relative_rpe"), "vo2",
    ),
    _definition(
        "run_race_pace", "Race Pace Run", "run", ("quality", "race"),
        "event-specific pace", ("Peak", "Taper", "Race Week"),
        (30, 100), (30, 120), (55, 105), (2, 2, 1), 36, ("threshold_pace", "lthr", "relative_rpe"), "race_pace",
    ),
    _definition(
        "swim_technique_aerobic", "Technique + Aerobic Swim", "swim", ("recovery", "easy", "quality"),
        "technique under low aerobic load", _ALL_TRAINING_PHASES,
        (25, 75), (10, 65), (20, 60), (1, 0, 1), 12, ("css", "relative_rpe"), "technique",
    ),
    _definition(
        "swim_endurance", "Endurance Swim", "swim", ("easy", "long"),
        "aerobic swim endurance", _ALL_TRAINING_PHASES,
        (35, 120), (20, 110), (30, 75), (1, 1, 0), 18, ("css", "relative_rpe"), "endurance",
    ),
    _definition(
        "swim_threshold_repeats", "Threshold Swim Repeats", "swim", ("quality",),
        "critical-speed endurance", ("Build", "Peak", "Taper", "Race Week"),
        (35, 90), (25, 100), (45, 95), (2, 1, 1), 30, ("css", "relative_rpe"), "threshold",
    ),
    _definition(
        "walk_recovery", "Recovery Walk", "walk", ("recovery", "easy"),
        "low-impact circulation", _ALL_TRAINING_PHASES,
        (20, 120), (3, 40), (8, 30), (0, 1, 0), 6, ("relative_rpe",), "recovery",
    ),
    _definition(
        "brick_endurance", "Endurance Brick", "brick", ("long",),
        "bike-to-run endurance transfer", ("Build",),
        (60, 240), (40, 220), (35, 85), (2, 2, 1), 36, ("ftp", "threshold_pace", "lthr", "relative_rpe"),
        "brick_endurance", kind="composite", goals=_TRIATHLON_GOALS, requirements=("bike", "run"),
    ),
    _definition(
        "brick_race_pace", "Race Pace Brick", "brick", ("long", "quality"),
        "event-specific bike-to-run transfer", ("Peak",),
        (50, 150), (45, 180), (50, 110), (3, 2, 2), 48, ("ftp", "threshold_pace", "lthr", "relative_rpe"),
        "brick_race_pace", kind="composite", goals=_TRIATHLON_GOALS, requirements=("bike", "run"),
    ),
)


def catalog_definitions() -> tuple[WorkoutTemplateDefinition, ...]:
    """Return the immutable v1 catalog in stable declaration order."""
    return _CATALOG


def definition_snapshot(definition: WorkoutTemplateDefinition) -> dict[str, Any]:
    snapshot = asdict(definition)
    snapshot["catalog_version"] = CATALOG_VERSION
    return snapshot


_PHASE_PREFERENCE = {
    "Recovery": ("recovery", "technique", "endurance"),
    "Base": ("progression", "endurance", "technique", "neuromuscular", "recovery"),
    "Maintenance": ("progression", "endurance", "tempo", "technique", "neuromuscular", "recovery"),
    "Build": ("threshold", "tempo", "vo2", "progression", "endurance", "technique", "recovery"),
    "Peak": ("race_pace", "threshold", "vo2", "tempo", "endurance", "technique", "recovery"),
    "Taper": ("vo2", "race_pace", "technique", "recovery", "endurance"),
    "Race Week": ("race_pace", "vo2", "technique", "recovery", "endurance"),
}


def _failed_bounds(
    definition: WorkoutTemplateDefinition,
    duration_minutes: float,
    target_tss: float,
) -> list[str]:
    density = target_tss * 60.0 / duration_minutes if duration_minutes > 0 else math.inf
    failed: list[str] = []
    if duration_minutes < definition.min_duration_minutes:
        failed.append("duration_below_minimum")
    if duration_minutes > definition.max_duration_minutes:
        failed.append("duration_above_maximum")
    if target_tss < definition.min_tss:
        failed.append("tss_below_minimum")
    if target_tss > definition.max_tss:
        failed.append("tss_above_maximum")
    if density < definition.min_tss_per_hour:
        failed.append("density_below_minimum")
    if density > definition.max_tss_per_hour:
        failed.append("density_above_maximum")
    return failed


def _goal_matches(definition: WorkoutTemplateDefinition, goal_type: str) -> bool:
    if "any" in definition.goal_eligibility:
        return True
    normalized = goal_type.strip().lower()
    return any(item in normalized or normalized in item for item in definition.goal_eligibility)


def select_workout_template(context: Mapping[str, Any]) -> dict[str, Any]:
    """Select one feasible definition from explicit context with inspectable evidence."""
    sport = str(context.get("sport") or "").strip().lower()
    role = str(context.get("session_role") or "easy").strip().lower()
    phase = str(context.get("phase") or "Base").strip()
    goal_type = str(context.get("goal_type") or "").strip().lower()
    duration = float(context.get("duration_minutes") or 0.0)
    target_tss = float(context.get("target_tss") or 0.0)
    load_state = str(context.get("load_state") or "balanced").strip().lower()
    recent = {str(item) for item in context.get("recent_template_keys", []) or []}
    excluded_reasons: list[str] = []
    candidates: list[WorkoutTemplateDefinition] = []

    for definition in _CATALOG:
        if definition.kind != "single" or definition.sport != sport:
            continue
        if role not in definition.roles or phase not in definition.phase_eligibility:
            continue
        if not _goal_matches(definition, goal_type):
            continue
        if _failed_bounds(definition, duration, target_tss):
            continue
        if load_state == "deep_fatigue" and max(definition.fatigue_cost) >= 3:
            excluded_reasons.append("deep_fatigue")
            continue
        candidates.append(definition)

    fresh = [item for item in candidates if item.template_key not in recent]
    if fresh:
        if len(fresh) != len(candidates):
            excluded_reasons.append("recent_exposure")
        candidates = fresh

    preferences = _PHASE_PREFERENCE.get(phase, _PHASE_PREFERENCE["Base"])
    preference_rank = {stimulus: index for index, stimulus in enumerate(preferences)}
    candidates.sort(
        key=lambda item: (
            preference_rank.get(item.step_builder_key, len(preferences)),
            item.fatigue_cost,
            item.template_key,
        )
    )
    evidence = {
        "rule_version": SELECTOR_RULE_VERSION,
        "phase": phase,
        "role": role,
        "sport": sport,
        "load_state": load_state,
        "recent_template_keys": sorted(recent),
        "excluded_reasons": sorted(set(excluded_reasons)),
        "candidate_keys": [item.template_key for item in candidates],
    }
    if not candidates:
        return {"status": "no_feasible_template", "definition": None, "selection_evidence": evidence}
    return {
        "status": "selected",
        "definition": definition_snapshot(candidates[0]),
        "selection_evidence": evidence,
    }


_STEP_PATTERNS: dict[str, tuple[tuple[str, str, float, float], ...]] = {
    "recovery": (("Warm-up", "easy", 0.15, 0.35), ("Recovery", "steady", 0.70, 0.50), ("Cool-down", "easy", 0.15, 0.30)),
    "endurance": (("Warm-up", "easy", 0.15, 0.45), ("Aerobic endurance", "steady", 0.70, 0.68), ("Cool-down", "easy", 0.15, 0.35)),
    "progression": (("Warm-up", "easy", 0.15, 0.45), ("Aerobic", "steady", 0.40, 0.68), ("Progression", "work", 0.30, 0.82), ("Cool-down", "easy", 0.15, 0.35)),
    "tempo": (("Warm-up", "easy", 0.20, 0.45), ("Tempo blocks", "work", 0.50, 0.88), ("Easy reset", "easy", 0.10, 0.45), ("Cool-down", "easy", 0.20, 0.35)),
    "threshold": (("Warm-up", "easy", 0.20, 0.45), ("Threshold intervals", "work", 0.45, 1.00), ("Recoveries", "easy", 0.15, 0.45), ("Cool-down", "easy", 0.20, 0.35)),
    "vo2": (("Warm-up", "easy", 0.25, 0.45), ("VO2 intervals", "work", 0.30, 1.15), ("Recoveries", "easy", 0.20, 0.40), ("Cool-down", "easy", 0.25, 0.35)),
    "neuromuscular": (("Warm-up", "easy", 0.30, 0.45), ("Sprints", "work", 0.15, 1.30), ("Full recoveries", "easy", 0.30, 0.35), ("Cool-down", "easy", 0.25, 0.30)),
    "technique": (("Easy warm-up", "easy", 0.20, 0.45), ("Technique drills", "steady", 0.45, 0.55), ("Aerobic swim", "work", 0.20, 0.70), ("Easy cool-down", "easy", 0.15, 0.40)),
    "race_pace": (("Warm-up", "easy", 0.20, 0.45), ("Race-pace blocks", "work", 0.50, 0.95), ("Easy reset", "easy", 0.10, 0.45), ("Cool-down", "easy", 0.20, 0.35)),
}


def _resolve_provenance(
    definition: WorkoutTemplateDefinition,
    zone_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    for kind in definition.target_preference:
        if kind == "relative_rpe":
            break
        raw = zone_snapshot.get(kind)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return {
                "kind": kind,
                "source": f"athlete_profile.{kind}",
                "value": value,
                "fallback": False,
            }
    missing = [item for item in definition.target_preference if item != "relative_rpe"]
    return {
        "kind": "relative_rpe",
        "source": "catalog.relative_rpe",
        "value": None,
        "fallback": True,
        "missing": missing,
    }


def _target_for_step(provenance: Mapping[str, Any], intensity: str, fraction: float) -> dict[str, Any]:
    kind = str(provenance.get("kind") or "relative_rpe")
    value = provenance.get("value")
    low_fraction = max(0.2, fraction - (0.03 if intensity == "work" else 0.08))
    high_fraction = fraction + (0.03 if intensity == "work" else 0.08)
    if kind == "ftp" and value:
        return {
            "type": "power",
            "unit": "watts",
            "low": int(round(float(value) * low_fraction)),
            "high": int(round(float(value) * high_fraction)),
            "relative_low": round(low_fraction, 2),
            "relative_high": round(high_fraction, 2),
        }
    if kind == "lthr" and value:
        return {
            "type": "heart_rate",
            "unit": "bpm",
            "low": int(round(float(value) * low_fraction)),
            "high": int(round(float(value) * high_fraction)),
            "relative_low": round(low_fraction, 2),
            "relative_high": round(high_fraction, 2),
        }
    if kind in {"threshold_pace", "css"} and value:
        unit = "seconds_per_km" if kind == "threshold_pace" else "seconds_per_100m"
        return {
            "type": "pace",
            "unit": unit,
            "fast": round(float(value) / max(high_fraction, 0.1), 1),
            "slow": round(float(value) / max(low_fraction, 0.1), 1),
            "relative_low": round(low_fraction, 2),
            "relative_high": round(high_fraction, 2),
        }
    rpe = max(1, min(10, int(round(fraction * 10))))
    return {
        "type": "relative_rpe",
        "unit": "rpe_1_10",
        "low": max(1, rpe - 1),
        "high": min(10, rpe + (1 if intensity == "work" else 0)),
    }


def _exact_distribution(total: float, shares: Sequence[float], decimals: int) -> list[float]:
    multiplier = 10**decimals
    units = int(round(float(total) * multiplier))
    distributed: list[int] = []
    assigned = 0
    for share in shares[:-1]:
        value = int(math.floor(units * float(share) + 1e-9))
        distributed.append(value)
        assigned += value
    distributed.append(units - assigned)
    return [value / multiplier for value in distributed]


def materialize_workout(
    definition: WorkoutTemplateDefinition,
    parameters: Mapping[str, Any],
    zone_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve one immutable definition into exact persisted steps."""
    duration = int(parameters.get("duration_minutes") or 0)
    target_tss = round(float(parameters.get("target_tss") or 0.0), 1)
    density = round(target_tss * 60.0 / duration, 1) if duration > 0 else 0.0
    parameter_snapshot = {
        "duration_minutes": duration,
        "target_tss": target_tss,
        "tss_per_hour": density,
    }
    failed = _failed_bounds(definition, duration, target_tss)
    base = {
        "materialization_status": "infeasible" if failed else "materialized",
        "rule_version": MATERIALIZER_RULE_VERSION,
        "catalog_version": CATALOG_VERSION,
        "definition_snapshot": definition_snapshot(definition),
        "parameter_snapshot": parameter_snapshot,
        "failed_bounds": failed,
        "steps": [],
    }
    if failed:
        return base

    pattern_key = definition.step_builder_key
    if pattern_key.startswith("brick_"):
        pattern_key = "race_pace" if pattern_key == "brick_race_pace" else "endurance"
    pattern = _STEP_PATTERNS[pattern_key]
    shares = [item[2] for item in pattern]
    seconds = [int(value) for value in _exact_distribution(duration * 60, shares, 0)]
    tss_values = _exact_distribution(target_tss, shares, 1)
    provenance = _resolve_provenance(definition, zone_snapshot)
    steps = []
    for index, (name, intensity, _share, target_fraction) in enumerate(pattern):
        steps.append(
            {
                "index": index,
                "name": name,
                "intensity": intensity,
                "duration_seconds": seconds[index],
                "tss": tss_values[index],
                "target": _target_for_step(provenance, intensity, target_fraction),
            }
        )
    base["steps"] = steps
    base["target_provenance"] = provenance
    return base


_TARGET_DENSITY = {
    "recovery": 35.0,
    "endurance": 55.0,
    "progression": 70.0,
    "tempo": 75.0,
    "threshold": 80.0,
    "vo2": 95.0,
    "neuromuscular": 70.0,
    "technique": 45.0,
    "race_pace": 80.0,
}


def _prescription_fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate_duration(
    definition: WorkoutTemplateDefinition,
    target_tss: float,
    estimated_duration_minutes: int,
) -> int | None:
    estimated = int(round(float(estimated_duration_minutes or 0) / 5.0) * 5)
    if estimated > 0 and not _failed_bounds(definition, estimated, target_tss):
        return estimated
    target_density = _TARGET_DENSITY.get(definition.step_builder_key, 60.0)
    raw = target_tss * 60.0 / target_density if target_density > 0 else estimated
    resolved = int(round(raw / 5.0) * 5)
    resolved = max(definition.min_duration_minutes, min(definition.max_duration_minutes, resolved))
    return resolved if not _failed_bounds(definition, resolved, target_tss) else None


def _single_candidates(
    *,
    phase: str,
    session_role: str,
    sport: str,
    goal_type: str,
    target_tss: float,
    estimated_duration_minutes: int,
    load_state: str,
    recent_template_keys: Sequence[str],
) -> list[tuple[WorkoutTemplateDefinition, int]]:
    recent = {str(item) for item in recent_template_keys}
    preferences = _PHASE_PREFERENCE.get(phase, _PHASE_PREFERENCE["Base"])
    preference_rank = {stimulus: index for index, stimulus in enumerate(preferences)}
    candidates: list[tuple[WorkoutTemplateDefinition, int]] = []
    for definition in _CATALOG:
        if definition.kind != "single" or definition.sport != sport:
            continue
        if session_role not in definition.roles or phase not in definition.phase_eligibility:
            continue
        if not _goal_matches(definition, goal_type):
            continue
        if load_state == "deep_fatigue" and max(definition.fatigue_cost) >= 3:
            continue
        duration = _candidate_duration(definition, target_tss, estimated_duration_minutes)
        if duration is not None:
            candidates.append((definition, duration))
    fresh = [item for item in candidates if item[0].template_key not in recent]
    if fresh:
        candidates = fresh
    candidates.sort(
        key=lambda item: (
            preference_rank.get(item[0].step_builder_key, len(preferences)),
            item[0].fatigue_cost,
            item[0].template_key,
        )
    )
    return candidates


def materialize_session_template(
    *,
    phase: str,
    session_role: str,
    sport: str,
    target_tss: float,
    estimated_duration_minutes: int,
    goal_type: str,
    zone_snapshot: Mapping[str, Any],
    load_state: str = "balanced",
    recent_template_keys: Sequence[str] = (),
) -> dict[str, Any]:
    """Select and persist one catalog prescription for a planned single session."""
    candidates = _single_candidates(
        phase=phase,
        session_role=session_role,
        sport=sport,
        goal_type=goal_type,
        target_tss=target_tss,
        estimated_duration_minutes=estimated_duration_minutes,
        load_state=load_state,
        recent_template_keys=recent_template_keys,
    )
    if not candidates:
        return {
            "kind": "single",
            "materialization_status": "legacy_role_fallback",
            "catalog_version": CATALOG_VERSION,
            "selection_evidence": {
                "rule_version": SELECTOR_RULE_VERSION,
                "phase": phase,
                "role": session_role,
                "sport": sport,
                "load_state": load_state,
                "reason": "no_feasible_catalog_definition",
            },
        }

    definition, duration = candidates[0]
    materialized = materialize_workout(
        definition,
        {"duration_minutes": duration, "target_tss": target_tss},
        zone_snapshot,
    )
    evidence = {
        "rule_version": SELECTOR_RULE_VERSION,
        "phase": phase,
        "role": session_role,
        "sport": sport,
        "load_state": load_state,
        "recent_template_keys": [str(item) for item in recent_template_keys],
        "candidate_keys": [item[0].template_key for item in candidates],
        "estimated_duration_minutes": int(estimated_duration_minutes),
        "selected_duration_minutes": duration,
    }
    prescription = {
        "definition_snapshot": materialized["definition_snapshot"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized.get("target_provenance"),
    }
    return {
        "kind": "single",
        "catalog_version": CATALOG_VERSION,
        "selector_rule_version": SELECTOR_RULE_VERSION,
        "materializer_rule_version": MATERIALIZER_RULE_VERSION,
        "template_key": definition.template_key,
        "template_version": definition.version,
        "template_name": definition.display_name,
        "stimulus": definition.stimulus,
        "fatigue_cost": list(definition.fatigue_cost),
        "expected_recovery_hours": definition.expected_recovery_hours,
        "duration_minutes": duration,
        "materialization_status": materialized["materialization_status"],
        "definition_snapshot": materialized["definition_snapshot"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized.get("target_provenance"),
        "selection_evidence": evidence,
        "prescription_fingerprint": _prescription_fingerprint(prescription),
    }


def materialize_brick_session(
    *,
    phase: str,
    target_tss: float,
    parts: Mapping[str, float],
    estimated_duration_minutes: int,
    goal_type: str,
    zone_snapshot: Mapping[str, Any],
    load_state: str = "balanced",
) -> dict[str, Any]:
    """Build one atomic bike→transition→run parent with independently exportable legs."""
    template_key = "brick_race_pace" if phase == "Peak" else "brick_endurance"
    definition = next(item for item in _CATALOG if item.template_key == template_key)
    if load_state == "deep_fatigue" or not _goal_matches(definition, goal_type):
        return {"kind": "single", "materialization_status": "legacy_role_fallback"}

    transition_minutes = 5
    target_tss = round(float(target_tss or 0.0), 1)
    bike_tss = round(float(parts.get("bike", 0.0) or 0.0), 1)
    run_tss = round(float(parts.get("run", 0.0) or 0.0), 1)
    if bike_tss <= 0 or run_tss <= 0 or abs((bike_tss + run_tss) - target_tss) > 0.1:
        return {"kind": "single", "materialization_status": "legacy_role_fallback"}

    duration = max(105, int(round(float(estimated_duration_minutes or 0) / 5.0) * 5))
    duration = min(definition.max_duration_minutes, max(definition.min_duration_minutes, duration))
    parent_check = materialize_workout(
        definition,
        {"duration_minutes": duration, "target_tss": target_tss},
        zone_snapshot,
    )
    if parent_check["materialization_status"] != "materialized":
        candidate = _candidate_duration(definition, target_tss, duration)
        if candidate is None:
            return {"kind": "single", "materialization_status": "legacy_role_fallback"}
        duration = max(candidate, 105)
        parent_check = materialize_workout(
            definition,
            {"duration_minutes": duration, "target_tss": target_tss},
            zone_snapshot,
        )
        if parent_check["materialization_status"] != "materialized":
            return {"kind": "single", "materialization_status": "legacy_role_fallback"}

    active_minutes = duration - transition_minutes
    bike_minutes = max(40, int(round((active_minutes * 0.70) / 5.0) * 5))
    run_minutes = active_minutes - bike_minutes
    if run_minutes < 30:
        run_minutes = 30
        bike_minutes = active_minutes - run_minutes
    bike_definition = next(item for item in _CATALOG if item.template_key == "bike_aerobic_endurance")
    run_definition = next(item for item in _CATALOG if item.template_key == "run_aerobic_endurance")
    bike = materialize_workout(
        bike_definition,
        {"duration_minutes": bike_minutes, "target_tss": bike_tss},
        zone_snapshot,
    )
    run = materialize_workout(
        run_definition,
        {"duration_minutes": run_minutes, "target_tss": run_tss},
        zone_snapshot,
    )
    if any(item["materialization_status"] != "materialized" for item in (bike, run)):
        return {"kind": "single", "materialization_status": "legacy_role_fallback"}

    legs = []
    for leg_index, (sport, leg_tss, leg_duration, leg_definition, materialized) in enumerate(
        (
            ("bike", bike_tss, bike_minutes, bike_definition, bike),
            ("run", run_tss, run_minutes, run_definition, run),
        ),
        start=1,
    ):
        legs.append(
            {
                "leg_index": leg_index,
                "sport": sport,
                "target_tss": leg_tss,
                "duration_minutes": leg_duration,
                "template_key": leg_definition.template_key,
                "template_version": leg_definition.version,
                "template_name": leg_definition.display_name,
                "definition_snapshot": materialized["definition_snapshot"],
                "parameter_snapshot": materialized["parameter_snapshot"],
                "materialized_steps": materialized["steps"],
                "target_provenance": materialized["target_provenance"],
            }
        )
    prescription = {
        "definition_snapshot": parent_check["definition_snapshot"],
        "parameter_snapshot": parent_check["parameter_snapshot"],
        "transition_minutes": transition_minutes,
        "legs": legs,
    }
    return {
        "kind": "composite",
        "sport": "brick",
        "sport_label": "вело → бег",
        "catalog_version": CATALOG_VERSION,
        "selector_rule_version": SELECTOR_RULE_VERSION,
        "materializer_rule_version": MATERIALIZER_RULE_VERSION,
        "template_key": definition.template_key,
        "template_version": definition.version,
        "template_name": definition.display_name,
        "stimulus": definition.stimulus,
        "fatigue_cost": list(definition.fatigue_cost),
        "expected_recovery_hours": definition.expected_recovery_hours,
        "duration_minutes": duration,
        "transition_minutes": transition_minutes,
        "materialization_status": "materialized",
        "definition_snapshot": parent_check["definition_snapshot"],
        "parameter_snapshot": parent_check["parameter_snapshot"],
        "materialized_steps": [],
        "legs": legs,
        "selection_evidence": {
            "rule_version": SELECTOR_RULE_VERSION,
            "phase": phase,
            "role": "long",
            "sport": "brick",
            "load_state": load_state,
            "reason": "eligible_triathlon_long_day",
        },
        "prescription_fingerprint": _prescription_fingerprint(prescription),
    }


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _weekly_totals(rows: Sequence[tuple[Any, float, Mapping[str, float]]]) -> dict[str, float]:
    return {
        sport: round(sum(float(row[2].get(sport, 0.0) or 0.0) for row in rows), 1)
        for sport in ("run", "bike", "swim")
    }


def prepare_weekly_brick_allocations(
    daily_plan: Sequence[tuple[Any, float, Mapping[str, float]]],
    weekly_summary: Sequence[Mapping[str, Any]],
    *,
    goal_type: str,
    protected_dates: set[str] | Sequence[str],
    load_state: str,
) -> dict[str, Any]:
    """Move a long day's swim bucket without changing any day or sport total."""
    original = deepcopy(list(daily_plan))
    normalized_goal = str(goal_type or "").lower()
    if "tri" not in normalized_goal and "триатлон" not in normalized_goal:
        return {"status": "unchanged", "daily_plan": original, "brick_day_indices": [], "reason": "non_triathlon_goal"}
    if str(load_state or "").lower() == "deep_fatigue":
        return {"status": "unchanged", "daily_plan": original, "brick_day_indices": [], "reason": "deep_fatigue"}

    protected = {_date_key(item) for item in protected_dates}
    working = deepcopy(original)
    brick_indices: list[int] = []
    eligible_seen = False
    failed_for_capacity = False

    for week_index, week in enumerate(weekly_summary):
        phase = str(week.get("phase") or "Base")
        if phase not in {"Build", "Peak"}:
            continue
        start = week_index * 7
        end = min(start + 7, len(working))
        roles = list(week.get("day_roles") or [])
        candidates = [
            index
            for index in range(start, end)
            if index - start < len(roles)
            and str(roles[index - start]) == "long"
            and _date_key(working[index][0]) not in protected
            and float(working[index][1] or 0.0) > 0
        ]
        if not candidates:
            continue
        target_index = candidates[0]
        eligible_seen = True
        target_dt, target_total, target_raw_parts = working[target_index]
        target_parts = dict(target_raw_parts)
        swim_to_move = round(float(target_parts.get("swim", 0.0) or 0.0), 1)
        if swim_to_move <= 0:
            brick_indices.append(target_index)
            continue

        donors = [
            index
            for index in range(start, end)
            if index != target_index
            and _date_key(working[index][0]) not in protected
            and index - start < len(roles)
            and str(roles[index - start]) in {"easy", "recovery"}
        ]
        donor_capacity = sum(
            float(working[index][2].get("bike", 0.0) or 0.0)
            + float(working[index][2].get("run", 0.0) or 0.0)
            for index in donors
        )
        if donor_capacity + 0.05 < swim_to_move:
            failed_for_capacity = True
            continue

        remaining = swim_to_move
        moved = {"bike": 0.0, "run": 0.0}
        for donor_index in donors:
            donor_dt, donor_total, donor_raw_parts = working[donor_index]
            donor_parts = dict(donor_raw_parts)
            for sport in ("bike", "run"):
                available = round(float(donor_parts.get(sport, 0.0) or 0.0), 1)
                take = round(min(available, remaining), 1)
                if take <= 0:
                    continue
                donor_parts[sport] = round(available - take, 1)
                donor_parts["swim"] = round(float(donor_parts.get("swim", 0.0) or 0.0) + take, 1)
                moved[sport] = round(moved[sport] + take, 1)
                remaining = round(remaining - take, 1)
                if remaining <= 0.05:
                    remaining = 0.0
                    break
            working[donor_index] = (donor_dt, donor_total, donor_parts)
            if remaining == 0.0:
                break

        if remaining > 0.05:
            failed_for_capacity = True
            working = deepcopy(original)
            brick_indices = []
            continue
        target_parts["swim"] = 0.0
        target_parts["bike"] = round(float(target_parts.get("bike", 0.0) or 0.0) + moved["bike"], 1)
        target_parts["run"] = round(float(target_parts.get("run", 0.0) or 0.0) + moved["run"], 1)
        working[target_index] = (target_dt, target_total, target_parts)
        brick_indices.append(target_index)

    if not brick_indices:
        reason = "insufficient_unprotected_donor_capacity" if eligible_seen and failed_for_capacity else "no_eligible_long_day"
        return {"status": "unchanged", "daily_plan": original, "brick_day_indices": [], "reason": reason}

    before_totals = _weekly_totals(original)
    after_totals = _weekly_totals(working)
    day_totals_preserved = all(abs(float(before[1]) - float(after[1])) <= 0.05 for before, after in zip(original, working))
    sports_preserved = all(abs(before_totals[sport] - after_totals[sport]) <= 0.1 for sport in before_totals)
    if not day_totals_preserved or not sports_preserved:
        return {"status": "unchanged", "daily_plan": original, "brick_day_indices": [], "reason": "conservation_check_failed"}
    return {
        "status": "allocated",
        "daily_plan": working,
        "brick_day_indices": brick_indices,
        "evidence": {
            "rule_version": MATERIALIZER_RULE_VERSION,
            "day_totals_preserved": day_totals_preserved,
            "weekly_totals_preserved": sports_preserved,
            "weekly_sport_totals_before": before_totals,
            "weekly_sport_totals_after": after_totals,
        },
    }


__all__ = [
    "CATALOG_VERSION",
    "SELECTOR_RULE_VERSION",
    "MATERIALIZER_RULE_VERSION",
    "WorkoutTemplateDefinition",
    "catalog_definitions",
    "definition_snapshot",
    "select_workout_template",
    "materialize_workout",
    "materialize_session_template",
    "materialize_brick_session",
    "prepare_weekly_brick_allocations",
]
