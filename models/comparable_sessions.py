"""Pure, deterministic comparable-session selection for post-workout evidence.

One result compares one canonical activity with one prior canonical activity.
It never infers adaptation, recalculates load, or mutates source data.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Mapping, Sequence

from utils.product_semantics import normalize_sport_key


COMPARABLE_SESSION_RULE_VERSION = "comparable_session_v1"
SUPPORTED_SPORTS = {"bike", "run", "swim"}
MIN_DURATION_SIMILARITY = 0.50
MIN_INTENSITY_SIMILARITY = 0.65
MIN_STRUCTURE_SIMILARITY = 0.50


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _positive(value: Any) -> float | None:
    parsed = _number(value)
    return parsed if parsed is not None and parsed > 0 else None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _instant(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ratio_similarity(first: float, second: float) -> float:
    return min(first, second) / max(first, second)


def _structure_features(
    intervals: Mapping[str, Any] | None,
    *,
    duration_minutes: float | None,
) -> dict[str, Any]:
    payload = dict(intervals or {})
    groups = payload.get("groups")
    raw_segments = groups if isinstance(groups, list) and groups else payload.get("intervals")
    if not isinstance(raw_segments, list):
        raw_segments = []
    durations: list[float] = []
    for raw in raw_segments:
        if not isinstance(raw, Mapping):
            continue
        seconds = _positive(raw.get("moving_time")) or _positive(raw.get("elapsed_time"))
        if seconds is not None:
            durations.append(seconds)
    if not durations:
        return {
            "available": False,
            "segment_count": 0,
            "duration_coverage": None,
            "source": _text(payload.get("source")) or None,
        }
    total_seconds = (duration_minutes or 0.0) * 60.0
    coverage = min(1.0, sum(durations) / total_seconds) if total_seconds > 0 else None
    return {
        "available": True,
        "segment_count": len(durations),
        "duration_coverage": round(coverage, 3) if coverage is not None else None,
        "source": _text(payload.get("source")) or "local_interval_cache",
    }


def _sport_metric(activity: Mapping[str, Any], sport: str) -> dict[str, Any] | None:
    if sport == "bike":
        normalized_power = _positive(activity.get("normalized_power"))
        if normalized_power is not None:
            return {
                "kind": "power_watts",
                "value": round(normalized_power, 1),
                "source": "normalized_power",
            }
        average_power = _positive(activity.get("avg_power"))
        if average_power is not None:
            return {
                "kind": "power_watts",
                "value": round(average_power, 1),
                "source": "average_power_fallback",
            }
        return None

    duration = _positive(activity.get("duration_minutes"))
    distance_km = _positive(activity.get("distance_km"))
    tss_threshold = _positive(activity.get("tss_pace_used"))
    profile_threshold = _positive(activity.get("pace_threshold_used"))
    threshold = tss_threshold or profile_threshold
    if duration is None or distance_km is None or threshold is None:
        return None
    if sport == "run":
        pace = duration * 60.0 / distance_km
        kind = "pace_seconds_per_km"
    elif sport == "swim":
        pace = duration * 60.0 / (distance_km * 10.0)
        kind = "pace_seconds_per_100m"
    else:
        return None
    threshold_source = (
        "tss_pace_used"
        if tss_threshold is not None
        else _text(activity.get("pace_threshold_source")) or "athlete_profile"
    )
    threshold_observed_at = (
        None
        if tss_threshold is not None
        else _text(activity.get("pace_threshold_observed_at"))
    )
    return {
        "kind": kind,
        "value": round(pace, 1),
        "source": "distance_duration",
        "threshold_value": round(threshold, 1),
        "threshold_source": threshold_source,
        **(
            {"threshold_observed_at": threshold_observed_at}
            if threshold_observed_at
            else {}
        ),
        "relative_to_threshold": round(threshold / pace, 4),
    }


def project_activity_features(
    activity: Mapping[str, Any],
    *,
    stimulus_family: str | None,
    intervals: Mapping[str, Any] | None = None,
    subjective_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project only persisted, source-labelled features used by the selector."""
    sport = normalize_sport_key(activity.get("sport")) or _text(activity.get("sport"))
    duration = _positive(activity.get("duration_minutes"))
    tss = _positive(activity.get("tss"))
    tss_per_hour = (
        round(tss * 60.0 / duration, 3)
        if duration is not None and tss is not None
        else None
    )
    return {
        "activity_id": _text(activity.get("activity_id")),
        "date": str(activity.get("date") or "")[:10] or None,
        "started_at_utc": _text(activity.get("started_at_utc")),
        "sport": sport,
        "stimulus_family": _text(stimulus_family),
        "duration_minutes": round(duration, 1) if duration is not None else None,
        "tss": round(tss, 1) if tss is not None else None,
        "tss_per_hour": tss_per_hour,
        "structure": _structure_features(intervals, duration_minutes=duration),
        "sport_metric": _sport_metric(activity, str(sport or "")),
        "subjective_evidence": (
            dict(subjective_evidence) if isinstance(subjective_evidence, Mapping) else None
        ),
    }


def _identity_projection(features: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(features, Mapping):
        return None
    return {
        key: features.get(key)
        for key in (
            "activity_id",
            "date",
            "sport",
            "stimulus_family",
            "duration_minutes",
            "tss",
            "tss_per_hour",
            "sport_metric",
        )
    }


def build_comparison_data_gap(
    reason_code: str,
    *,
    target: Mapping[str, Any] | None = None,
    candidate_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Return the stable fail-closed shape shared by model and service."""
    return {
        "status": "data_gap",
        "reason_code": str(reason_code),
        "rule_version": COMPARABLE_SESSION_RULE_VERSION,
        "target": _identity_projection(target),
        "comparator": None,
        "similarity": None,
        "comparison": None,
        "candidate_counts": dict(candidate_counts or {}),
        "guardrails": {
            "one_comparison_only": True,
            "trend_claim_allowed": False,
            "causal_claim_allowed": False,
        },
    }


def _target_gap(target: Mapping[str, Any]) -> str | None:
    if not target.get("activity_id") or _day(target.get("date")) is None:
        return "TARGET_ACTIVITY_INCOMPLETE"
    if target.get("sport") not in SUPPORTED_SPORTS:
        return "TARGET_SPORT_UNSUPPORTED"
    if not target.get("stimulus_family"):
        return "TARGET_STIMULUS_MISSING"
    if target.get("duration_minutes") is None or target.get("tss_per_hour") is None:
        return "TARGET_ACTIVITY_INCOMPLETE"
    return None


def _metric_comparison(
    target: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any] | None:
    target_metric = target.get("sport_metric")
    candidate_metric = candidate.get("sport_metric")
    if not isinstance(target_metric, Mapping) or not isinstance(candidate_metric, Mapping):
        return None
    if target_metric.get("kind") != candidate_metric.get("kind"):
        return None
    target_value = _number(target_metric.get("value"))
    candidate_value = _number(candidate_metric.get("value"))
    if target_value is None or candidate_value is None:
        return None
    return {
        "kind": target_metric.get("kind"),
        "target": {
            key: target_metric.get(key)
            for key in (
                "value",
                "source",
                "threshold_value",
                "threshold_source",
                "threshold_observed_at",
                "relative_to_threshold",
            )
            if target_metric.get(key) is not None
        },
        "comparator": {
            key: candidate_metric.get(key)
            for key in (
                "value",
                "source",
                "threshold_value",
                "threshold_source",
                "threshold_observed_at",
                "relative_to_threshold",
            )
            if candidate_metric.get(key) is not None
        },
        "delta": (
            round(target_value - candidate_value, 1)
            if target_metric.get("source") == candidate_metric.get("source")
            else None
        ),
    }


def select_comparable_session(
    target: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Select one prior compatible candidate with transparent stable evidence."""
    frozen_target = dict(target)
    gap = _target_gap(frozen_target)
    if gap:
        return build_comparison_data_gap(gap, target=frozen_target)

    target_day = _day(frozen_target.get("date"))
    target_duration = float(frozen_target["duration_minutes"])
    target_intensity = float(frozen_target["tss_per_hour"])
    counts = {
        "considered": 0,
        "same_sport_stimulus": 0,
        "duration_incompatible": 0,
        "intensity_incompatible": 0,
        "structure_incompatible": 0,
        "eligible": 0,
    }
    target_instant = _instant(frozen_target.get("started_at_utc"))
    ranked: list[tuple[float, float, str, dict[str, Any], list[dict[str, Any]]]] = []
    for raw in candidates:
        candidate = dict(raw)
        counts["considered"] += 1
        candidate_day = _day(candidate.get("date"))
        if candidate_day is None or target_day is None or candidate_day > target_day:
            continue
        candidate_instant = _instant(candidate.get("started_at_utc"))
        if candidate_day == target_day and not (
            candidate_instant is not None
            and target_instant is not None
            and candidate_instant < target_instant
        ):
            continue
        if candidate.get("sport") != frozen_target.get("sport"):
            continue
        if candidate.get("stimulus_family") != frozen_target.get("stimulus_family"):
            continue
        counts["same_sport_stimulus"] += 1
        candidate_duration = _positive(candidate.get("duration_minutes"))
        candidate_intensity = _positive(candidate.get("tss_per_hour"))
        if candidate_duration is None or candidate_intensity is None:
            continue
        duration_similarity = _ratio_similarity(target_duration, candidate_duration)
        intensity_similarity = _ratio_similarity(target_intensity, candidate_intensity)
        if duration_similarity < MIN_DURATION_SIMILARITY:
            counts["duration_incompatible"] += 1
            continue
        if intensity_similarity < MIN_INTENSITY_SIMILARITY:
            counts["intensity_incompatible"] += 1
            continue

        target_structure = dict(frozen_target.get("structure") or {})
        candidate_structure = dict(candidate.get("structure") or {})
        structure_similarity: float | None = None
        structure_status = "missing"
        if target_structure.get("available") and candidate_structure.get("available"):
            target_count = int(target_structure.get("segment_count") or 0)
            candidate_count = int(candidate_structure.get("segment_count") or 0)
            if target_count > 0 and candidate_count > 0:
                structure_similarity = _ratio_similarity(target_count, candidate_count)
                if structure_similarity < MIN_STRUCTURE_SIMILARITY:
                    counts["structure_incompatible"] += 1
                    continue
                structure_status = "compatible"

        if structure_similarity is None:
            score = (duration_similarity + intensity_similarity) / 2.0
        else:
            score = (
                duration_similarity * 0.4
                + intensity_similarity * 0.4
                + structure_similarity * 0.2
            )
        evidence = [
            {
                "dimension": "sport",
                "status": "exact",
                "target": frozen_target.get("sport"),
                "comparator": candidate.get("sport"),
            },
            {
                "dimension": "stimulus",
                "status": "exact",
                "target": frozen_target.get("stimulus_family"),
                "comparator": candidate.get("stimulus_family"),
            },
            {
                "dimension": "duration",
                "status": "compatible",
                "similarity": round(duration_similarity, 4),
            },
            {
                "dimension": "overall_intensity",
                "status": "compatible",
                "metric": "tss_per_hour",
                "similarity": round(intensity_similarity, 4),
            },
            {
                "dimension": "structure",
                "status": structure_status,
                "similarity": (
                    round(structure_similarity, 4)
                    if structure_similarity is not None
                    else None
                ),
                "target_segments": target_structure.get("segment_count") or 0,
                "comparator_segments": candidate_structure.get("segment_count") or 0,
            },
        ]
        counts["eligible"] += 1
        ranked.append(
            (
                round(score, 6),
                (
                    candidate_instant.timestamp()
                    if candidate_instant is not None
                    else datetime.combine(
                        candidate_day, time.min, tzinfo=timezone.utc
                    ).timestamp()
                ),
                str(candidate.get("activity_id") or ""),
                candidate,
                evidence,
            )
        )

    if not ranked:
        if counts["same_sport_stimulus"] and counts["intensity_incompatible"]:
            reason = "NO_COMPATIBLE_INTENSITY"
        elif counts["same_sport_stimulus"] and counts["duration_incompatible"]:
            reason = "NO_COMPATIBLE_DURATION"
        elif counts["same_sport_stimulus"] and counts["structure_incompatible"]:
            reason = "NO_COMPATIBLE_STRUCTURE"
        else:
            reason = "NO_ELIGIBLE_CANDIDATE"
        return build_comparison_data_gap(reason, target=frozen_target, candidate_counts=counts)

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    score, _ordinal, _activity_id, comparator, evidence = ranked[0]
    return {
        "status": "available",
        "reason_code": None,
        "rule_version": COMPARABLE_SESSION_RULE_VERSION,
        "target": _identity_projection(frozen_target),
        "comparator": _identity_projection(comparator),
        "similarity": {"score": round(score, 4), "evidence": evidence},
        "comparison": {
            "duration_minutes_delta": round(
                float(frozen_target["duration_minutes"])
                - float(comparator["duration_minutes"]),
                1,
            ),
            "tss_delta": round(float(frozen_target["tss"]) - float(comparator["tss"]), 1),
            "overall_intensity_tss_per_hour_delta": round(
                float(frozen_target["tss_per_hour"])
                - float(comparator["tss_per_hour"]),
                1,
            ),
            "sport_metric": _metric_comparison(frozen_target, comparator),
            "subjective_evidence": {
                "target": frozen_target.get("subjective_evidence"),
                "comparator": comparator.get("subjective_evidence"),
            },
        },
        "candidate_counts": counts,
        "guardrails": {
            "one_comparison_only": True,
            "trend_claim_allowed": False,
            "causal_claim_allowed": False,
        },
    }


__all__ = [
    "COMPARABLE_SESSION_RULE_VERSION",
    "build_comparison_data_gap",
    "project_activity_features",
    "select_comparable_session",
]
