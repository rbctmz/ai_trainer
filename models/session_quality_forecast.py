"""Pure pre-registered session-quality forecast and scoring rules (Issue D)."""
from __future__ import annotations

from typing import Any, Mapping

from utils.product_semantics import normalize_sport_key


RULE_VERSION = "session_quality_v1"
# Closed vocabulary shared by forecast resolution, post-workout feedback,
# explicit plan matching, and the Planning selector. It mirrors planner roles.
ACTUAL_SESSION_ROLES = frozenset(
    {"off", "race", "activation", "recovery", "easy", "quality", "long"}
)
MIN_CONFIDENCE = 0.60
MIN_PROBABILITY = 5.0
MAX_PROBABILITY = 95.0
DEMAND_ADJUSTMENT_CAP = 10.0
QUALITY_DENSITY_REFERENCE = 50.0
QUALITY_DENSITY_STEP = 5.0
LONG_DURATION_REFERENCE_MINUTES = 90.0
LONG_DURATION_STEP_MINUTES = 15.0
EXACT_LOAD_MIN = 0.80
EXACT_LOAD_MAX = 1.20
SUBSTITUTED_LOAD_MIN = 0.60
SUBSTITUTED_LOAD_MAX = 1.40


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _band(probability: int) -> str:
    if probability < 60:
        return "low"
    if probability < 75:
        return "uncertain"
    return "high"


def build_session_quality_forecast(
    readiness: Mapping[str, Any],
    session: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return the immutable v1 forecast without reading facts or persistence."""
    score = _float(readiness.get("score"))
    confidence = _float(readiness.get("confidence")) or 0.0
    if score is None or confidence < MIN_CONFIDENCE or bool(readiness.get("stale")):
        return None
    confidence = _clamp(confidence, 0.0, 1.0)
    role = str(session.get("role") or "").strip().lower()
    if role not in {"quality", "long"}:
        return None

    planned_tss = max(0.0, _float(session.get("tss")) or 0.0)
    duration = max(0.0, _float(session.get("duration_minutes")) or 0.0)
    base = 50.0 + (score - 50.0) * confidence
    density = None
    demand_adjustment = 0.0
    demand_reason = "planned duration unavailable; neutral demand adjustment"
    if duration > 0 and role == "quality":
        density = planned_tss / (duration / 60.0)
        demand_adjustment = _clamp(
            (QUALITY_DENSITY_REFERENCE - density) / QUALITY_DENSITY_STEP,
            -DEMAND_ADJUSTMENT_CAP,
            DEMAND_ADJUSTMENT_CAP,
        )
        demand_reason = f"quality density {density:.1f} TSS/h"
    elif duration > 0 and role == "long":
        demand_adjustment = _clamp(
            (LONG_DURATION_REFERENCE_MINUTES - duration) / LONG_DURATION_STEP_MINUTES,
            -DEMAND_ADJUSTMENT_CAP,
            DEMAND_ADJUSTMENT_CAP,
        )
        demand_reason = f"long duration {duration:.0f} min"

    probability = int(round(_clamp(base + demand_adjustment, MIN_PROBABILITY, MAX_PROBABILITY)))
    return {
        "rule_version": RULE_VERSION,
        "prediction_pct": probability,
        "prediction_band": _band(probability),
        "base_probability": round(base, 2),
        "demand_adjustment": round(demand_adjustment, 2),
        "demand": {
            "role": role,
            "planned_tss": round(planned_tss, 1),
            "planned_duration_minutes": int(round(duration)) if duration > 0 else None,
            "density_tss_per_hour": round(density, 1) if density is not None else None,
            "reason": demand_reason,
        },
        "evidence": [
            f"Readiness {score:.1f}/100 × confidence {confidence:.2f} → base {base:.1f}%",
            f"{demand_reason} → adjustment {demand_adjustment:+.1f} pp",
            f"Pre-registered {RULE_VERSION}: {probability}% ({_band(probability)})",
        ],
    }


def classify_plan_adherence(
    planned: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> str | None:
    """Classify comparability without inferring post-session quality."""
    planned_role = str(planned.get("role") or "").strip().lower()
    actual_role = str(actual.get("role") or "").strip().lower()
    planned_tss = _float(planned.get("tss"))
    actual_tss = _float(actual.get("tss"))
    if not planned_role or not actual_role or planned_tss is None or planned_tss <= 0 or actual_tss is None:
        return None
    if actual_role != planned_role:
        return "major_deviation"

    ratio = actual_tss / planned_tss
    planned_sport = normalize_sport_key(planned.get("sport"))
    actual_sport = normalize_sport_key(actual.get("sport"))
    same_sport = bool(planned_sport and actual_sport and planned_sport == actual_sport)
    if same_sport and EXACT_LOAD_MIN <= ratio <= EXACT_LOAD_MAX:
        return "exact"
    if SUBSTITUTED_LOAD_MIN <= ratio <= SUBSTITUTED_LOAD_MAX:
        return "substituted"
    return "major_deviation"


def brier_score(prediction_pct: float, quality_rating_1_5: int | None) -> float | None:
    """Score only an unambiguous 1–2 failure or 4–5 success rating."""
    if quality_rating_1_5 is None or quality_rating_1_5 == 3:
        return None
    if quality_rating_1_5 not in {1, 2, 4, 5}:
        raise ValueError("quality_rating_1_5 must be between 1 and 5")
    outcome = 1.0 if quality_rating_1_5 >= 4 else 0.0
    probability = _clamp(float(prediction_pct) / 100.0, 0.0, 1.0)
    return round((probability - outcome) ** 2, 4)


__all__ = [
    "RULE_VERSION",
    "brier_score",
    "build_session_quality_forecast",
    "classify_plan_adherence",
]
