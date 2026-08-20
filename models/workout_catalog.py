from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


CATALOG_VERSION = "workout_catalog_v3"
SELECTOR_RULE_VERSION = "workout_selector_v1"
MATERIALIZER_RULE_VERSION = "workout_materializer_v2"
STRUCTURE_RULE_VERSION = "workout_structure_v2"


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


@dataclass(frozen=True)
class _StepSpec:
    name: str
    intensity: str
    duration_seconds: int
    target_fraction: float
    segment_kind: str
    repeat_index: int | None = None


@dataclass(frozen=True)
class _RepeatTier:
    name: str
    min_duration_minutes: int
    repeat_count: int
    work_seconds: int
    recovery_seconds: int


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
    version: int | None = None,
) -> WorkoutTemplateDefinition:
    resolved_version = version
    if resolved_version is None:
        resolved_version = 2 if sport in {"bike", "run"} or kind == "composite" else 1
    return WorkoutTemplateDefinition(
        template_key=template_key,
        version=resolved_version,
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
        "bike_race_pace", "Race Pace Ride", "bike", ("quality", "race"),
        "event-specific cycling pace", ("Peak", "Taper", "Race Week"),
        (40, 150), (30, 180), (50, 105), (2, 1, 1), 36,
        ("ftp", "relative_rpe"), "race_pace", version=1,
    ),
    _definition(
        "bike_activation", "Race Openers Ride", "bike", ("activation",),
        "pre-race sharpening openers", _ALL_TRAINING_PHASES,
        (20, 50), (5, 45), (15, 75), (1, 1, 1), 12,
        ("ftp", "relative_rpe"), "activation", version=1,
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
        "run_activation", "Race Strides Run", "run", ("activation",),
        "pre-race sharpening strides", _ALL_TRAINING_PHASES,
        (20, 45), (4, 35), (10, 70), (1, 1, 1), 12,
        ("threshold_pace", "lthr", "relative_rpe"), "activation", version=1,
    ),
    _definition(
        "swim_recovery_technique", "Recovery Technique Swim", "swim", ("recovery", "easy"),
        "low-load technique and circulation", _ALL_TRAINING_PHASES,
        (15, 45), (3, 30), (8, 40), (1, 0, 0), 8, ("css", "relative_rpe"), "technique",
        version=1,
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
    """Return the immutable current catalog in stable declaration order."""
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


_REPEAT_PRESCRIPTIONS: dict[
    str,
    tuple[str, float, float, tuple[_RepeatTier, ...]],
] = {
    "bike_tempo": (
        "Tempo",
        0.88,
        0.50,
        (
            _RepeatTier("short", 45, 2, 8 * 60, 4 * 60),
            _RepeatTier("medium", 70, 3, 10 * 60, 4 * 60),
            _RepeatTier("long", 100, 3, 15 * 60, 5 * 60),
        ),
    ),
    "bike_threshold": (
        "Threshold",
        1.00,
        0.50,
        (
            _RepeatTier("short", 40, 3, 5 * 60, 3 * 60),
            _RepeatTier("medium", 60, 3, 8 * 60, 4 * 60),
            _RepeatTier("long", 85, 4, 8 * 60, 4 * 60),
        ),
    ),
    "bike_vo2": (
        "VO2",
        1.15,
        0.45,
        (
            _RepeatTier("short", 35, 4, 2 * 60, 2 * 60),
            _RepeatTier("medium", 50, 5, 3 * 60, 3 * 60),
            _RepeatTier("long", 75, 5, 4 * 60, 4 * 60),
        ),
    ),
    "bike_neuromuscular": (
        "Sprint",
        1.30,
        0.35,
        (
            _RepeatTier("short", 30, 6, 20, 100),
            _RepeatTier("medium", 45, 8, 30, 150),
            _RepeatTier("long", 60, 10, 30, 150),
        ),
    ),
    "bike_race_pace": (
        "Race pace",
        0.92,
        0.50,
        (
            _RepeatTier("short", 40, 2, 8 * 60, 4 * 60),
            _RepeatTier("medium", 60, 3, 10 * 60, 4 * 60),
            _RepeatTier("long", 90, 3, 15 * 60, 5 * 60),
        ),
    ),
    "run_threshold": (
        "Threshold",
        1.00,
        0.70,
        (
            _RepeatTier("short", 35, 3, 5 * 60, 2 * 60),
            _RepeatTier("medium", 55, 3, 8 * 60, 3 * 60),
            _RepeatTier("long", 80, 4, 8 * 60, 3 * 60),
        ),
    ),
    "run_vo2": (
        "VO2",
        1.08,
        0.68,
        (
            _RepeatTier("short", 30, 6, 30, 90),
            _RepeatTier("medium", 45, 5, 2 * 60, 2 * 60),
            _RepeatTier("long", 60, 5, 3 * 60, 3 * 60),
        ),
    ),
    "run_race_pace": (
        "Race pace",
        0.92,
        0.70,
        (
            _RepeatTier("short", 30, 2, 8 * 60, 3 * 60),
            _RepeatTier("medium", 55, 3, 10 * 60, 4 * 60),
            _RepeatTier("long", 80, 3, 15 * 60, 5 * 60),
        ),
    ),
    # Issue #205 M4: pre-race activations are short sharpening openers/strides
    # at race effort — never a fallback block (roles come from race-microcycle
    # overlays, #202).
    "bike_activation": (
        "Opener",
        1.00,
        0.50,
        (
            _RepeatTier("short", 20, 2, 60, 120),
            _RepeatTier("medium", 30, 3, 60, 120),
            _RepeatTier("long", 40, 4, 60, 120),
        ),
    ),
    "run_activation": (
        "Stride",
        1.00,
        0.65,
        (
            _RepeatTier("short", 20, 3, 20, 70),
            _RepeatTier("medium", 28, 4, 25, 95),
            _RepeatTier("long", 38, 5, 30, 90),
        ),
    ),
}


_STAGE_PRESCRIPTIONS: dict[
    tuple[str, str],
    tuple[tuple[str, str, float, float, str], ...],
] = {
    ("bike", "recovery"): (
        ("Warm-up", "easy", 0.15, 0.45, "warmup"),
        ("Recovery", "steady", 0.70, 0.50, "stage"),
        ("Cool-down", "easy", 0.15, 0.35, "cooldown"),
    ),
    ("run", "recovery"): (
        ("Warm-up", "easy", 0.15, 0.65, "warmup"),
        ("Recovery", "steady", 0.70, 0.68, "stage"),
        ("Cool-down", "easy", 0.15, 0.60, "cooldown"),
    ),
    ("bike", "endurance"): (
        ("Warm-up", "easy", 0.15, 0.50, "warmup"),
        ("Aerobic endurance", "steady", 0.55, 0.68, "stage"),
        ("Steady finish", "steady", 0.15, 0.75, "stage"),
        ("Cool-down", "easy", 0.15, 0.40, "cooldown"),
    ),
    ("run", "endurance"): (
        ("Warm-up", "easy", 0.15, 0.65, "warmup"),
        ("Aerobic endurance", "steady", 0.55, 0.72, "stage"),
        ("Steady finish", "steady", 0.15, 0.80, "stage"),
        ("Cool-down", "easy", 0.15, 0.60, "cooldown"),
    ),
    ("bike", "progression"): (
        ("Warm-up", "easy", 0.15, 0.50, "warmup"),
        ("Aerobic", "steady", 0.35, 0.65, "stage"),
        ("Moderate", "steady", 0.25, 0.75, "stage"),
        ("Strong finish", "work", 0.15, 0.85, "work"),
        ("Cool-down", "easy", 0.10, 0.40, "cooldown"),
    ),
    ("run", "progression"): (
        ("Warm-up", "easy", 0.15, 0.65, "warmup"),
        ("Aerobic", "steady", 0.35, 0.70, "stage"),
        ("Moderate", "steady", 0.25, 0.80, "stage"),
        ("Strong finish", "work", 0.15, 0.90, "work"),
        ("Cool-down", "easy", 0.10, 0.60, "cooldown"),
    ),
}


def _prescription_key(definition: WorkoutTemplateDefinition) -> str:
    return f"{definition.sport}_{definition.step_builder_key}"


def _repeat_specs(
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> tuple[list[_StepSpec], dict[str, Any]] | None:
    prescription_key = _prescription_key(definition)
    prescription = _REPEAT_PRESCRIPTIONS.get(prescription_key)
    if prescription is None:
        return None
    work_name, work_fraction, recovery_fraction, tiers = prescription
    feasible: list[_RepeatTier] = []
    for tier in tiers:
        core_seconds = (
            tier.repeat_count * tier.work_seconds
            + (tier.repeat_count - 1) * tier.recovery_seconds
        )
        if (
            definition.min_duration_minutes <= total_seconds / 60.0
            and tier.min_duration_minutes * 60 <= total_seconds
            and total_seconds - core_seconds >= 10 * 60
        ):
            feasible.append(tier)
    if not feasible:
        return _simplified_specs(definition, total_seconds)

    tier = feasible[-1]
    core_seconds = (
        tier.repeat_count * tier.work_seconds
        + (tier.repeat_count - 1) * tier.recovery_seconds
    )
    remaining = total_seconds - core_seconds
    minimum_bookend_seconds = 5 * 60
    warmup_seconds = min(
        remaining - minimum_bookend_seconds,
        max(
            minimum_bookend_seconds,
            int(math.floor(remaining * 0.55)),
        ),
    )
    cooldown_seconds = remaining - warmup_seconds
    easy_fraction = 0.50 if definition.sport == "bike" else 0.68
    cooldown_fraction = 0.40 if definition.sport == "bike" else 0.60
    specs = [
        _StepSpec(
            "Warm-up",
            "easy",
            warmup_seconds,
            easy_fraction,
            "warmup",
        )
    ]
    for repeat_index in range(1, tier.repeat_count + 1):
        specs.append(
            _StepSpec(
                f"{work_name} {repeat_index}/{tier.repeat_count}",
                "work",
                tier.work_seconds,
                work_fraction,
                "work",
                repeat_index,
            )
        )
        if repeat_index < tier.repeat_count:
            specs.append(
                _StepSpec(
                    f"Recovery {repeat_index}/{tier.repeat_count - 1}",
                    "easy",
                    tier.recovery_seconds,
                    recovery_fraction,
                    "recovery",
                    repeat_index,
                )
            )
    specs.append(
        _StepSpec(
            "Cool-down",
            "easy",
            cooldown_seconds,
            cooldown_fraction,
            "cooldown",
        )
    )
    return specs, {
        "rule_version": STRUCTURE_RULE_VERSION,
        "prescription_key": prescription_key,
        "tier": tier.name,
        "repeat_count": tier.repeat_count,
        "simplification_reason": None,
    }


_BOOKEND_FLOOR_SECONDS = 5 * 60


def _apply_bookend_floor(
    seconds: list[int],
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> list[int]:
    """Issue #205 M4: full-size structures (>= 30 min) honour a five-minute
    warm-up and cool-down; very short activation sessions are the explicit
    exception. The deficit is taken from the largest middle stage."""
    if (
        total_seconds < 30 * 60
        or "activation" in definition.roles
        or len(seconds) < 3
    ):
        return seconds
    adjusted = list(seconds)
    for edge in (0, len(adjusted) - 1):
        deficit = _BOOKEND_FLOOR_SECONDS - adjusted[edge]
        while deficit > 0:
            donor = max(range(1, len(adjusted) - 1), key=lambda i: adjusted[i])
            take = min(deficit, adjusted[donor] - 60)
            if take <= 0:
                break
            adjusted[donor] -= take
            adjusted[edge] += take
            deficit -= take
    return adjusted


def _stage_specs(
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> tuple[list[_StepSpec], dict[str, Any]] | None:
    pattern = _STAGE_PRESCRIPTIONS.get(
        (definition.sport, definition.step_builder_key)
    )
    if pattern is None:
        return None
    seconds = [
        int(value)
        for value in _exact_distribution(
            total_seconds,
            [item[2] for item in pattern],
            0,
        )
    ]
    seconds = _apply_bookend_floor(seconds, definition, total_seconds)
    specs = [
        _StepSpec(
            name,
            intensity,
            seconds[index],
            target_fraction,
            segment_kind,
        )
        for index, (name, intensity, _share, target_fraction, segment_kind) in enumerate(pattern)
    ]
    return specs, {
        "rule_version": STRUCTURE_RULE_VERSION,
        "prescription_key": _prescription_key(definition),
        "tier": None,
        "repeat_count": None,
        "simplification_reason": None,
    }


def _simplified_specs(
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> tuple[list[_StepSpec], dict[str, Any]]:
    if total_seconds < 3:
        raise ValueError("materialized workout must have at least three seconds")
    seconds = [
        int(value)
        for value in _exact_distribution(total_seconds, (0.20, 0.60, 0.20), 0)
    ]
    seconds = _apply_bookend_floor(seconds, definition, total_seconds)
    easy_fraction = 0.50 if definition.sport == "bike" else 0.68
    controlled_fraction = 0.72 if definition.sport == "bike" else 0.78
    cooldown_fraction = 0.40 if definition.sport == "bike" else 0.60
    specs = [
        _StepSpec("Warm-up", "easy", seconds[0], easy_fraction, "warmup"),
        _StepSpec(
            "Controlled aerobic",
            "steady",
            seconds[1],
            controlled_fraction,
            "stage",
        ),
        _StepSpec("Cool-down", "easy", seconds[2], cooldown_fraction, "cooldown"),
    ]
    return specs, {
        "rule_version": STRUCTURE_RULE_VERSION,
        "prescription_key": _prescription_key(definition),
        "tier": None,
        "repeat_count": None,
        "simplification_reason": "repeat_budget_below_short_tier",
    }


def _legacy_specs(
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> tuple[list[_StepSpec], dict[str, Any]]:
    pattern_key = definition.step_builder_key
    if pattern_key.startswith("brick_"):
        pattern_key = "race_pace" if pattern_key == "brick_race_pace" else "endurance"
    pattern = _STEP_PATTERNS[pattern_key]
    seconds = [
        int(value)
        for value in _exact_distribution(
            total_seconds,
            [item[2] for item in pattern],
            0,
        )
    ]
    # Issue #205 M4: the bookend floor is ONE contract for every full-size
    # structure, including the v1 legacy pattern path (swim/walk).
    seconds = _apply_bookend_floor(seconds, definition, total_seconds)
    specs = [
        _StepSpec(
            name,
            intensity,
            seconds[index],
            target_fraction,
            "work" if intensity == "work" else "stage",
        )
        for index, (name, intensity, _share, target_fraction) in enumerate(pattern)
    ]
    return specs, {
        "rule_version": STRUCTURE_RULE_VERSION,
        "prescription_key": _prescription_key(definition),
        "tier": None,
        "repeat_count": None,
        "simplification_reason": None,
    }


def _structured_specs(
    definition: WorkoutTemplateDefinition,
    total_seconds: int,
) -> tuple[list[_StepSpec], str, dict[str, Any]]:
    repeated = _repeat_specs(definition, total_seconds)
    if repeated is not None:
        specs, evidence = repeated
        status = "simplified" if evidence["simplification_reason"] else "structured"
        return specs, status, evidence
    staged = _stage_specs(definition, total_seconds)
    if staged is not None:
        specs, evidence = staged
        return specs, "structured", evidence
    specs, evidence = _legacy_specs(definition, total_seconds)
    return specs, "legacy_pattern", evidence


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
            scale = {
                "ftp": "absolute_power_from_ftp",
                "lthr": "absolute_hr_from_lthr",
                "threshold_pace": "absolute_pace_from_threshold",
                "css": "absolute_pace_from_css",
            }[kind]
            source = {
                "ftp": "athlete_profile.ftp",
                "lthr": "athlete_profile.lthr",
                "threshold_pace": (
                    "athlete_profile.threshold_pace_seconds_per_km"
                ),
                "css": "athlete_profile.css",
            }[kind]
            return {
                "kind": kind,
                "source": source,
                "value": value,
                "fallback": False,
                "scale": scale,
            }
    missing = [item for item in definition.target_preference if item != "relative_rpe"]
    return {
        "kind": "relative_rpe",
        "source": "catalog.relative_rpe",
        "value": None,
        "fallback": True,
        "missing": missing,
        "scale": "relative_rpe",
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
            "reference": "lthr",
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

    specs, structure_status, structure_evidence = _structured_specs(
        definition,
        duration * 60,
    )
    duration_shares = [
        spec.duration_seconds / (duration * 60)
        for spec in specs
    ]
    tss_values = _exact_distribution(target_tss, duration_shares, 1)
    provenance = _resolve_provenance(definition, zone_snapshot)
    steps = []
    for index, spec in enumerate(specs):
        step = {
            "index": index,
            "name": spec.name,
            "intensity": spec.intensity,
            "duration_seconds": spec.duration_seconds,
            "tss": tss_values[index],
            "target": _target_for_step(
                provenance,
                spec.intensity,
                spec.target_fraction,
            ),
            "segment_kind": spec.segment_kind,
        }
        if spec.repeat_index is not None:
            step["repeat_index"] = spec.repeat_index
        steps.append(step)
    base["steps"] = steps
    base["target_provenance"] = provenance
    base["structure_status"] = structure_status
    base["structure_evidence"] = structure_evidence
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


# Issue #475 / spike #471 (VALIDATED): the generic key above predates staged
# bike structures and overshot their own power bands — steady-state bike steps
# imply ~22/~40/~45 TSS/h at 22/40/70 targets, i.e. plans ran 23-37% hotter
# than the workout could honestly deliver. Sport-scoped overrides carry the
# zone-derived values so run/swim/walk definitions keep their (separately
# validated) shared numbers. Pinned by tests/smoke/test_catalog_target_density.py.
_TARGET_DENSITY_BY_SPORT = {
    ("bike", "recovery"): 22.28,
    ("bike", "endurance"): 40.11,
    ("bike", "progression"): 44.97,
}


def _resolve_target_density(definition: WorkoutTemplateDefinition) -> float:
    """Duration-estimate density: sport scope wins, generic builder key falls back."""
    scoped = _TARGET_DENSITY_BY_SPORT.get((definition.sport, definition.step_builder_key))
    if scoped is not None:
        return scoped
    return _TARGET_DENSITY.get(definition.step_builder_key, 60.0)


def _prescription_fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate_duration(
    definition: WorkoutTemplateDefinition,
    target_tss: float,
    estimated_duration_minutes: int,
) -> int | None:
    estimated = int(round(float(estimated_duration_minutes or 0) / 5.0) * 5)
    scoped_density = _TARGET_DENSITY_BY_SPORT.get(
        (definition.sport, definition.step_builder_key)
    )
    # The planner's estimate is a generic seed, not an explicit duration
    # constraint. For validated sport-scoped definitions, derive duration from
    # the zone-implied density even when that generic seed passes broad bounds.
    if (
        scoped_density is None
        and estimated > 0
        and not _failed_bounds(definition, estimated, target_tss)
    ):
        return estimated
    target_density = (
        scoped_density
        if scoped_density is not None
        else _resolve_target_density(definition)
    )
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
        sharpening_override = (
            phase in {"Taper", "Race Week"}
            and session_role == "long"
            and any(role in definition.roles for role in ("quality", "easy"))
        )
        if (
            session_role not in definition.roles and not sharpening_override
        ) or phase not in definition.phase_eligibility:
            continue
        if not _goal_matches(definition, goal_type):
            continue
        if load_state == "deep_fatigue" and max(definition.fatigue_cost) >= 3:
            continue
        duration = _candidate_duration(definition, target_tss, estimated_duration_minutes)
        if duration is not None and phase in {"Taper", "Race Week"} and duration > 60:
            duration = 60 if not _failed_bounds(definition, 60, target_tss) else None
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
        "role_override": (
            "long_to_sharpening"
            if phase in {"Taper", "Race Week"} and session_role == "long"
            else None
        ),
    }
    prescription = {
        "definition_snapshot": materialized["definition_snapshot"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized.get("target_provenance"),
        "structure_status": materialized.get("structure_status"),
        "structure_evidence": materialized.get("structure_evidence"),
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
        "structure_status": materialized.get("structure_status"),
        "structure_evidence": materialized.get("structure_evidence"),
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
    bike_template_key = "bike_race_pace" if phase == "Peak" else "bike_aerobic_endurance"
    run_template_key = "run_race_pace" if phase == "Peak" else "run_aerobic_endurance"
    bike_definition = next(item for item in _CATALOG if item.template_key == bike_template_key)
    run_definition = next(item for item in _CATALOG if item.template_key == run_template_key)
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
                "structure_status": materialized.get("structure_status"),
                "structure_evidence": materialized.get("structure_evidence"),
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
        "structure_status": parent_check.get("structure_status"),
        "structure_evidence": parent_check.get("structure_evidence"),
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


def _rescale_steps(
    steps: Sequence[Mapping[str, Any]],
    *,
    target_seconds: int,
    target_tss: float,
) -> list[dict[str, Any]]:
    copied = [deepcopy(dict(step or {})) for step in steps]
    if not copied:
        return copied
    old_seconds = [max(0.0, float(step.get("duration_seconds") or 0.0)) for step in copied]
    old_tss = [max(0.0, float(step.get("tss") or 0.0)) for step in copied]
    seconds_total = sum(old_seconds)
    tss_total = sum(old_tss)
    seconds_shares = (
        [value / seconds_total for value in old_seconds]
        if seconds_total > 0
        else [1.0 / len(copied)] * len(copied)
    )
    tss_shares = (
        [value / tss_total for value in old_tss]
        if tss_total > 0
        else [1.0 / len(copied)] * len(copied)
    )
    seconds = [int(value) for value in _exact_distribution(target_seconds, seconds_shares, 0)]
    tss_values = _exact_distribution(round(float(target_tss), 1), tss_shares, 1)
    for index, step in enumerate(copied):
        step["index"] = index
        step["duration_seconds"] = seconds[index]
        step["tss"] = tss_values[index]
    return copied


def rescale_materialized_session(
    template: Mapping[str, Any],
    *,
    target_tss: float,
    parts: Mapping[str, float],
) -> dict[str, Any]:
    """Rescale one persisted prescription without re-selecting its stimulus."""
    updated = deepcopy(dict(template))
    if updated.get("materialization_status") != "materialized":
        return updated
    old_parameters = dict(updated.get("parameter_snapshot") or {})
    old_tss = float(old_parameters.get("target_tss") or 0.0)
    target_tss = round(float(target_tss or 0.0), 1)
    if old_tss <= 0 or target_tss <= 0:
        return updated
    scale = target_tss / old_tss

    if str(updated.get("kind") or "single") == "composite":
        transition = int(updated.get("transition_minutes") or 0)
        legs: list[dict[str, Any]] = []
        for raw_leg in list(updated.get("legs") or []):
            leg = deepcopy(dict(raw_leg or {}))
            sport = str(leg.get("sport") or "")
            old_leg_tss = float(leg.get("target_tss") or 0.0)
            new_leg_tss = round(float(parts.get(sport, 0.0) or 0.0), 1)
            leg_scale = new_leg_tss / old_leg_tss if old_leg_tss > 0 else scale
            old_minutes = int(leg.get("duration_minutes") or 0)
            new_minutes = max(1, int(round(old_minutes * leg_scale)))
            leg["target_tss"] = new_leg_tss
            leg["duration_minutes"] = new_minutes
            leg["parameter_snapshot"] = {
                "duration_minutes": new_minutes,
                "target_tss": new_leg_tss,
                "tss_per_hour": round(new_leg_tss * 60.0 / new_minutes, 1),
            }
            leg["materialized_steps"] = _rescale_steps(
                list(leg.get("materialized_steps") or []),
                target_seconds=new_minutes * 60,
                target_tss=new_leg_tss,
            )
            legs.append(leg)
        updated["legs"] = legs
        duration = sum(int(leg.get("duration_minutes") or 0) for leg in legs) + transition
        updated["duration_minutes"] = duration
        updated["parameter_snapshot"] = {
            "duration_minutes": duration,
            "target_tss": target_tss,
            "tss_per_hour": round(target_tss * 60.0 / duration, 1),
        }
        updated["materialized_steps"] = []
        fingerprint_legs = []
        for leg in legs:
            clean_leg = dict(leg)
            clean_leg.pop("leg_id", None)
            fingerprint_legs.append(clean_leg)
        prescription = {
            "definition_snapshot": updated.get("definition_snapshot"),
            "parameter_snapshot": updated.get("parameter_snapshot"),
            "transition_minutes": transition,
            "legs": fingerprint_legs,
        }
    else:
        old_minutes = int(old_parameters.get("duration_minutes") or updated.get("duration_minutes") or 0)
        duration = max(1, int(round(old_minutes * scale)))
        updated["duration_minutes"] = duration
        updated["parameter_snapshot"] = {
            "duration_minutes": duration,
            "target_tss": target_tss,
            "tss_per_hour": round(target_tss * 60.0 / duration, 1),
        }
        updated["materialized_steps"] = _rescale_steps(
            list(updated.get("materialized_steps") or []),
            target_seconds=duration * 60,
            target_tss=target_tss,
        )
        prescription = {
            "definition_snapshot": updated.get("definition_snapshot"),
            "parameter_snapshot": updated.get("parameter_snapshot"),
            "materialized_steps": updated.get("materialized_steps"),
            "target_provenance": updated.get("target_provenance"),
        }
    updated["mutation_evidence"] = {
        "kind": "proportional_rescale",
        "from_tss": round(old_tss, 1),
        "to_tss": target_tss,
        "scale": round(scale, 4),
        "rule_version": MATERIALIZER_RULE_VERSION,
    }
    updated["prescription_fingerprint"] = _prescription_fingerprint(prescription)
    return updated


def extract_zone_snapshot(templates: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Recover explicit immutable zone values from persisted prescriptions."""
    zones: dict[str, float] = {}
    for template in templates:
        candidates = [template.get("target_provenance")]
        candidates += [
            leg.get("target_provenance")
            for leg in list(template.get("legs") or [])
            if isinstance(leg, Mapping)
        ]
        for raw in candidates:
            if not isinstance(raw, Mapping) or raw.get("fallback"):
                continue
            kind = str(raw.get("kind") or "")
            if kind not in {"ftp", "lthr", "threshold_pace", "css"}:
                continue
            try:
                value = float(raw.get("value"))
            except (TypeError, ValueError):
                continue
            if value > 0:
                zones.setdefault(kind, value)
    return zones


def planned_session_is_executable(session: Mapping[str, Any]) -> bool:
    """Return whether a persisted modern session owns an exact prescription."""
    if str(session.get("kind") or "single") == "composite":
        legs = list(session.get("legs") or [])
        return bool(legs) and all(list((leg or {}).get("materialized_steps") or []) for leg in legs)
    return bool(list(session.get("materialized_steps") or []))


def planned_session_requires_repair(session: Mapping[str, Any]) -> bool:
    """Distinguish broken modern sessions from pre-catalog legacy records."""
    kind = str(session.get("kind") or "single").strip().lower()
    sport = str(session.get("sport") or "").strip().lower()
    role = str(session.get("session_role") or "").strip().lower()
    if (
        kind == "event"
        or sport in {"off", "race"}
        or role in {"off", "race"}
    ):
        return False
    template_key = str(session.get("template_key") or "").strip()
    status = str(session.get("materialization_status") or "").strip()
    # #323: lineage-маркеры (session_material_fingerprint,
    # session_identity_rule_version, replaces_session_id) НЕЛЬЗЯ использовать
    # как признак modern — ensure_session_identities добавляет их любой legacy,
    # и детектор перестал бы отличать catalog-lost stub от identity-migrated
    # legacy (#299). Контракт закреплён регрессионным тестом
    # tests/smoke/test_workout_catalog_modern_detector.py.
    is_modern = (
        template_key.startswith("manual:")
        or bool(status)
        or bool(session.get("catalog_version"))
    )
    return is_modern and not planned_session_is_executable(session)


def require_executable_planned_session(session: Mapping[str, Any]) -> None:
    """Fail closed when current planning code persisted no executable steps."""
    if planned_session_requires_repair(session):
        session_id = str(session.get("session_id") or "unknown")
        raise ValueError(f"planned session {session_id} is not executable; repair the active plan")


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
    # Issue #205 (readiness bounding, precedent #201/#202): current deep
    # fatigue suppresses bricks only within the seven-day readiness window from
    # the plan start — it is not a forecast for Build/Peak weeks months away.
    deep_fatigue = str(load_state or "").lower() == "deep_fatigue"
    plan_start = None
    if original and deep_fatigue:
        first = original[0][0]
        plan_start = first.date() if hasattr(first, "date") else first

    protected = {_date_key(item) for item in protected_dates}
    working = deepcopy(original)
    brick_indices: list[int] = []
    eligible_seen = False
    failed_for_capacity = False

    for week_index, week in enumerate(weekly_summary):
        phase = str(week.get("phase") or "Base")
        if phase not in {"Build", "Peak"}:
            continue
        if deep_fatigue and plan_start is not None:
            week_start_item = working[week_index * 7][0] if week_index * 7 < len(working) else None
            if week_start_item is not None:
                week_start = week_start_item.date() if hasattr(week_start_item, "date") else week_start_item
                if (week_start - plan_start).days < 7:
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
    "STRUCTURE_RULE_VERSION",
    "WorkoutTemplateDefinition",
    "catalog_definitions",
    "definition_snapshot",
    "select_workout_template",
    "materialize_workout",
    "materialize_session_template",
    "materialize_brick_session",
    "rescale_materialized_session",
    "extract_zone_snapshot",
    "prepare_weekly_brick_allocations",
]
