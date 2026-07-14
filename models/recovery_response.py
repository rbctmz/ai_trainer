"""Pure rules for prospective personal recovery-response analytics.

The module intentionally has no database, provider, FastAPI, or UI imports.
It turns frozen scientific evidence into deterministic eligibility, temporal
anchors, outcomes, and cohort projections for Issue #176.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
import hashlib
import math
import random
from statistics import median
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


RECOVERY_RESPONSE_RULE_VERSION = "recovery_response_v1"
READINESS_SNAPSHOT_RULE_VERSION = "readiness_snapshot_v2"
BOOTSTRAP_RULE_VERSION = "iso_week_cluster_bootstrap_v1"
BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_BASE_SEED = 176


def _valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(str(value))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return False
    return True


def _iso_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def evaluate_snapshot_eligibility(
    snapshot: Mapping[str, Any], *, athlete_timezone: str
) -> dict[str, Any]:
    """Fail closed when a readiness fact is not safe for prospective science."""
    reasons: list[str] = []
    if not _valid_timezone(athlete_timezone):
        return {"eligible": False, "reasons": ["invalid_timezone"]}

    as_of = _iso_date(snapshot.get("as_of_date") or snapshot.get("computed_at"))
    if as_of is None:
        reasons.append("missing_as_of")
    if snapshot.get("score") is None:
        reasons.append("missing_score")
    try:
        confidence = float(snapshot.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.60:
        reasons.append("low_confidence")
    if bool(snapshot.get("stale")):
        reasons.append("stale_snapshot")

    for factor in snapshot.get("factors") or []:
        if not isinstance(factor, Mapping):
            continue
        if factor.get("stale_input"):
            reasons.append("stale_factor")
        factor_date = _iso_date(factor.get("as_of"))
        if as_of is not None and factor_date is not None and factor_date > as_of:
            reasons.append("future_factor")

    return {"eligible": not reasons, "reasons": list(dict.fromkeys(reasons))}


def select_daily_anchor(
    snapshots: Sequence[Mapping[str, Any]],
    activities: Sequence[Mapping[str, Any]],
    *,
    local_date: date,
    athlete_timezone: str,
) -> dict[str, Any]:
    """Choose the latest eligible snapshot before activity start or local noon."""
    if not _valid_timezone(athlete_timezone):
        return {"snapshot": None, "reason": "invalid_timezone", "cutoff_at_utc": None}
    zone = ZoneInfo(athlete_timezone)
    relevant_activities = [
        row for row in activities if _iso_date(row.get("date")) == local_date
    ]
    if relevant_activities:
        starts = [_utc_datetime(row.get("started_at_utc")) for row in relevant_activities]
        if any(value is None for value in starts):
            return {
                "snapshot": None,
                "reason": "activity_start_missing",
                "cutoff_at_utc": None,
            }
        cutoff = min(value for value in starts if value is not None)
    else:
        cutoff = datetime.combine(local_date, time(12, 0), zone).astimezone(timezone.utc)

    candidates: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in snapshots:
        observed = _utc_datetime(row.get("observed_at_utc"))
        if (
            row.get("capture_mode") == "prospective"
            and row.get("eligibility_status") == "eligible"
            and _iso_date(row.get("local_date")) == local_date
            and observed is not None
            and observed <= cutoff
        ):
            candidates.append((observed, row))
    candidates.sort(key=lambda item: (item[0], int(item[1].get("revision") or 0), int(item[1].get("id") or 0)))
    return {
        "snapshot": dict(candidates[-1][1]) if candidates else None,
        "reason": None if candidates else "no_eligible_pre_anchor_snapshot",
        "cutoff_at_utc": _utc_text(cutoff),
    }


def actual_load_bucket(tss: float) -> str:
    value = float(tss)
    if value <= 0:
        raise ValueError("actual TSS must be positive")
    if value < 40:
        return "low"
    if value < 80:
        return "moderate"
    return "high"


def rpe_band(rpe: int | None) -> str | None:
    if rpe is None:
        return None
    value = int(rpe)
    if not 1 <= value <= 10:
        raise ValueError("RPE must be between 1 and 10")
    if value <= 3:
        return "low"
    if value <= 6:
        return "moderate"
    return "high"


def build_episode_outcomes(
    *,
    pre: Mapping[str, Any],
    d1: Mapping[str, Any] | None,
    d2: Mapping[str, Any] | None,
    d3: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep each observation independently missing; never impute a zero."""
    pre_score = float(pre["score"])
    deltas: dict[str, float | None] = {}
    missing: list[int] = []
    recovered: int | None = None
    for day_number, row in enumerate((d1, d2, d3), start=1):
        score = row.get("score") if row else None
        if score is None:
            deltas[f"d{day_number}"] = None
            missing.append(day_number)
            continue
        delta = round(float(score) - pre_score, 1)
        deltas[f"d{day_number}"] = delta
        if recovered is None and delta >= -5.0:
            recovered = day_number
    return {
        "readiness_deltas": deltas,
        "recovered_by_day": recovered,
        "missing_days": missing,
    }


def _quantile(values: Sequence[float], probability: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 2)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        result = ordered[lower]
    else:
        result = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(result, 2)


def _maturity(n: int, distinct_weeks: int) -> tuple[str, bool]:
    if n < 10:
        return "collection_only", False
    if n < 20:
        return "early_signal", True
    if n < 30 or distinct_weeks < 8:
        return "exploratory", True
    return "shadow_pattern", True


def _cohort_id(dimensions: Mapping[str, Any]) -> str:
    source = "|".join(str(dimensions[key]) for key in sorted(dimensions))
    return "rc_" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _bootstrap_interval(
    rows: Sequence[Mapping[str, Any]], *, day: int, cohort_id: str
) -> dict[str, float] | None:
    observed = [
        row for row in rows if (row.get("outcome") or {}).get("readiness_deltas", {}).get(f"d{day}") is not None
    ]
    if len(observed) < 20:
        return None
    clusters: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in observed:
        clusters[str(row.get("iso_week") or "unknown")].append(row)
    keys = sorted(clusters)
    if not keys:
        return None
    seed_source = f"{BOOTSTRAP_BASE_SEED}:{cohort_id}:d{day}"
    seed = int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    medians: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled: list[float] = []
        for _cluster in keys:
            selected = keys[rng.randrange(len(keys))]
            sampled.extend(
                float((row.get("outcome") or {})["readiness_deltas"][f"d{day}"])
                for row in clusters[selected]
            )
        if sampled:
            medians.append(float(median(sampled)))
    return {"low": _quantile(medians, 0.025), "high": _quantile(medians, 0.975)}


def _points(
    rows: Sequence[Mapping[str, Any]], *, maturity: str, cohort_id: str
) -> list[dict[str, Any]]:
    if maturity == "collection_only":
        return []
    points: list[dict[str, Any]] = []
    for day_number in (1, 2, 3):
        values = [
            float(value)
            for row in rows
            if (value := (row.get("outcome") or {}).get("readiness_deltas", {}).get(f"d{day_number}")) is not None
        ]
        points.append(
            {
                "day": day_number,
                "n_observed": len(values),
                "missing": len(rows) - len(values),
                "median": _quantile(values, 0.5),
                "q1": _quantile(values, 0.25),
                "q3": _quantile(values, 0.75),
                "interval": _bootstrap_interval(rows, day=day_number, cohort_id=cohort_id)
                if len(values) >= 20
                else None,
            }
        )
    return points


def _project_group(
    rows: Sequence[Mapping[str, Any]], *, cohort_id: str
) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (str(row.get("session_date")), str(row.get("target_key")), int(row.get("revision") or 0)))
    weeks = {str(row.get("iso_week") or "") for row in ordered if row.get("iso_week")}
    maturity, publishable = _maturity(len(ordered), len(weeks))
    return {
        "n": len(ordered),
        "distinct_weeks": len(weeks),
        "maturity": maturity,
        "publishable": publishable,
        "points": _points(ordered, maturity=maturity, cohort_id=cohort_id),
    }


def build_recovery_analytics(
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a stable read projection from latest frozen episode revisions."""
    ordered_input = sorted(
        (dict(row) for row in episodes),
        key=lambda row: (str(row.get("target_key")), int(row.get("revision") or 0), int(row.get("id") or 0)),
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in ordered_input:
        key = str(row.get("target_key") or row.get("session_id") or row.get("id"))
        previous = latest.get(key)
        if previous is None or (int(row.get("revision") or 0), int(row.get("id") or 0)) > (
            int(previous.get("revision") or 0), int(previous.get("id") or 0)
        ):
            latest[key] = row

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in latest.values():
        if row.get("capture_mode") == "prospective" and row.get("status") == "eligible":
            selected.append(row)
        else:
            excluded.append(row)

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        groups[(
            str(row.get("stimulus_family") or "unknown"),
            str(row.get("sport") or "unknown"),
            str(row.get("load_bucket") or "unknown"),
            str(row.get("adherence") or "unknown"),
        )].append(row)

    registry: list[dict[str, Any]] = []
    for dimensions_tuple in sorted(groups):
        dimensions = dict(zip(("stimulus_family", "sport", "load_bucket", "adherence"), dimensions_tuple))
        cohort_id = _cohort_id(dimensions)
        rows = groups[dimensions_tuple]
        projected = _project_group(rows, cohort_id=cohort_id)
        overlays: dict[str, dict[str, Any]] = {}
        for band in ("low", "moderate", "high"):
            subset = [row for row in rows if row.get("rpe_band") == band]
            overlays[band] = _project_group(subset, cohort_id=f"{cohort_id}:rpe:{band}")
        registry.append(
            {
                "cohort_id": cohort_id,
                "dimensions": dimensions,
                **projected,
                "last_observation": max((str(row.get("session_date")) for row in rows), default=None),
                "rpe_overlays": overlays,
                "included_episode_ids": sorted(int(row["id"]) for row in rows if row.get("id") is not None),
            }
        )

    exclusion_counts = Counter(
        reason
        for row in excluded
        for reason in (row.get("exclusion_reasons") or (["backfilled"] if row.get("capture_mode") != "prospective" else [str(row.get("status") or "excluded")]))
    )
    return {
        "rule_version": RECOVERY_RESPONSE_RULE_VERSION,
        "bootstrap_rule_version": BOOTSTRAP_RULE_VERSION,
        "capture_mode": "prospective",
        "maturity": max((row["maturity"] for row in registry), default="collection_only", key=lambda value: ("collection_only", "early_signal", "exploratory", "shadow_pattern").index(value)),
        "coverage": {
            "total_latest": len(latest),
            "eligible": len(selected),
            "excluded": len(excluded),
            "backfilled_excluded": sum(row.get("capture_mode") != "prospective" for row in excluded),
            "exclusion_counts": dict(sorted(exclusion_counts.items())),
        },
        "registry": registry,
    }
