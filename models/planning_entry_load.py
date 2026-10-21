"""Frozen, sport-specific recorded exposure and entry limits (not suitability)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import json
import math
from statistics import median
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from models.activity_lineage import identify_multisport_groups
from utils.product_semantics import SPORT_KEY_ALIASES, normalize_sport_key

ENTRY_LOAD_POLICY_VERSION = "entry-load-v1"
SPORTS = ("bike", "run", "swim")
_ENVELOPES = {"multisport", "multi_sport"}
_NON_ENDURANCE = set(SPORT_KEY_ALIASES.values()) - set(SPORTS) - {"other"}


def _sport(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return raw if raw in _ENVELOPES else normalize_sport_key(value)


def _iso_day(value: Any) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Expected an ISO calendar date")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Expected an ISO calendar date")
    return parsed


def _number(value: Any, *, zero: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and (result >= 0 if zero else result > 0) else None


def normalize_entry_inputs(
    coverage: Mapping[str, Any] | None,
    declared_limits: Mapping[str, Any] | None,
    *, as_of: date | None = None,
) -> dict[str, Any]:
    """Validate explicit intent for HTTP and non-HTTP callers, without I/O."""
    result: dict[str, Any] = {}
    if coverage is not None:
        if not isinstance(coverage, Mapping) or set(coverage) - {"status", "start_date", "end_date_exclusive"}:
            raise ValueError("Invalid history coverage fields")
        status = coverage.get("status")
        if status not in {"unknown", "partial", "user_reported_complete"}:
            raise ValueError("Invalid history coverage status")
        start, end = coverage.get("start_date"), coverage.get("end_date_exclusive")
        if (start is None) != (end is None) or (status != "unknown" and start is None):
            raise ValueError("History coverage requires an explicit interval")
        if start is not None:
            first, last = _iso_day(start), _iso_day(end)
            if first >= last:
                raise ValueError("History coverage interval must be nonempty")
            if status == "user_reported_complete" and as_of is not None and (
                first > as_of - timedelta(days=28) or last < as_of
            ):
                raise ValueError("Complete coverage must include the 28 completed local days")
        result["history_coverage"] = {"status": status, "start_date": start, "end_date_exclusive": end}
    if declared_limits is not None:
        if not isinstance(declared_limits, Mapping) or set(declared_limits) - set(SPORTS):
            raise ValueError("Starting limits require canonical endurance sport keys")
        limits = {}
        for sport, raw in sorted(declared_limits.items()):
            if not isinstance(raw, Mapping) or set(raw) != {
                "source", "weekly_minutes", "weekly_sessions", "max_session_minutes"
            } or raw.get("source") != "athlete_declared":
                raise ValueError("Starting limits require their athlete_declared source and units")
            weekly, longest = _number(raw["weekly_minutes"]), _number(raw["max_session_minutes"])
            count = raw["weekly_sessions"]
            if weekly is None or longest is None or longest > weekly or type(count) is not int or count <= 0:
                raise ValueError("Starting limits must be finite, positive and internally consistent")
            limits[sport] = {"source": "athlete_declared", "weekly_minutes": weekly,
                             "weekly_sessions": count, "max_session_minutes": longest}
        result["initial_dose_limits"] = limits
    return result


def _local_day(value: Any, zone: ZoneInfo) -> date | None:
    if value is None or value is pd.NaT:
        return None
    try:
        if isinstance(value, str):
            if len(value) == 10:
                return _iso_day(value)
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, datetime):
            return value.astimezone(zone).date() if value.tzinfo is not None else value.date()
        if isinstance(value, date):
            return value
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _sum(values: Sequence[float]) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("Exposure aggregate is not finite") from exc
    if not math.isfinite(result):
        raise ValueError("Exposure aggregate is not finite")
    return result


def build_entry_exposure_profile(
    rows: Sequence[Mapping[str, Any]], *, as_of: date, timezone: str,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project observed physical exposure; absent rows never imply coverage."""
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("as_of must be a frozen local calendar date")
    zone = ZoneInfo(timezone)
    normalized = normalize_entry_inputs(coverage, None, as_of=as_of).get("history_coverage")
    complete = bool(normalized and normalized["status"] == "user_reported_complete")
    start, context_start = as_of - timedelta(days=28), as_of - timedelta(days=84)
    quality: list[dict[str, Any]] = []
    unresolved: set[str] = set()

    def note(code: str, row: Mapping[str, Any], *, uncertain: bool = False, field: str | None = None) -> None:
        sport = _sport(row.get("sport"))
        item = {"code": code, "activity_id": str(row.get("activity_id") or "") or None,
                "sport": sport if sport in SPORTS else None, "field": field}
        quality.append(item)
        if uncertain:
            unresolved.update([sport] if sport in SPORTS else SPORTS)

    # Identity conflict is not resolved by row order or date proximity. Only
    # fields already in the captured frame are compared; no external lookup.
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        identity = str(row.get("activity_id") or "").strip()
        if not identity:
            day = _local_day(row.get("date"), zone)
            note("activity_identity_missing", row, uncertain=day is None or start <= day < as_of, field="activity_id")
        else:
            by_id[identity].append(row)
    unique = []
    conflicted_ids: set[str] = set()
    for identity, group in sorted(by_id.items()):
        signatures = {json.dumps(r, sort_keys=True, default=str, allow_nan=True) for r in group}
        if len(signatures) > 1:
            conflicted_ids.add(identity)
            for row in group:
                day = _local_day(row.get("date"), zone)
                note("activity_identity_conflict", row, uncertain=day is None or start <= day < as_of, field="activity_id")
            continue
        row = group[0]
        row["_day"] = _local_day(row.get("date"), zone)
        unique.append(row)

    for row in unique:
        day = row["_day"]
        if str(row.get("provider_external_id") or "") in conflicted_ids and (day is None or start <= day < as_of):
            note("lineage_identity_conflict", row, uncertain=True, field="provider_external_id")

    # Reuse explicit provider identity grouping, but NOT its TSS-based complete
    # flag: zero-TSS observed legs remain physical duration evidence here.
    frame = pd.DataFrame([{**{k: r.get(k) for k in ("activity_id", "sport", "provider_external_id", "started_at_utc")},
                           "tss": _number(r.get("tss"), zero=True)} for r in unique], dtype=object)
    groups = identify_multisport_groups(frame)
    keyed = {str(r["activity_id"]): r for r in unique}
    envelopes = {str(r["activity_id"]) for r in unique if _sport(r.get("sport")) in _ENVELOPES}
    for envelope_id in sorted(envelopes):
        envelope = keyed[envelope_id]
        group = next((g for g in groups if g.envelope_id == envelope_id), None)
        legs = [keyed[i] for i in group.stage_ids] if group else []
        known = {_sport(r.get("sport")) for r in legs
                 if _number(r.get("duration_minutes")) is not None and r["_day"] is not None
                 and context_start <= r["_day"] < as_of}
        all_valid = all(_number(r.get("duration_minutes")) is not None and r["_day"] is not None
                        and context_start <= r["_day"] < as_of for r in legs if _sport(r.get("sport")) in SPORTS)
        day = envelope["_day"]
        if not set(SPORTS).issubset(known) or not all_valid:
            if day is None or start <= day < as_of or any(r["_day"] and start <= r["_day"] < as_of for r in legs):
                note("multisport_remainder_unknown", envelope, uncertain=True, field="provider_external_id")

    observed: dict[str, list[dict[str, Any]]] = {s: [] for s in SPORTS}
    recent: dict[str, list[dict[str, Any]]] = {s: [] for s in SPORTS}
    for row in unique:
        sport, day = _sport(row.get("sport")), row["_day"]
        if day is None:
            note("activity_date_invalid", row, uncertain=sport in SPORTS or sport in _ENVELOPES, field="date")
            continue
        if day >= as_of:
            note("partial_today_excluded" if day == as_of else "future_activity_excluded", row, field="date")
            continue
        if day < context_start:
            note("outside_context_excluded", row, field="date")
            continue
        if sport in _ENVELOPES:
            continue  # Never assign envelope time/TSS to a discipline.
        if sport not in SPORTS:
            if sport not in _NON_ENDURANCE and day >= start:
                note("activity_sport_unknown", row, uncertain=True, field="sport")
            continue
        observed[sport].append(row)
        if day >= start:
            recent[sport].append(row)
            if _number(row.get("duration_minutes")) is None:
                note("duration_missing_or_invalid", row, uncertain=True, field="duration_minutes")
            if _number(row.get("tss"), zero=True) is None:
                note("tss_missing_or_invalid", row, field="tss")

    sports = {}
    for sport in SPORTS:
        history = sorted(recent[sport], key=lambda r: (r["_day"], str(r["activity_id"])))
        valid = [r for r in history if _number(r.get("duration_minutes")) is not None]
        minutes = [float(r["duration_minutes"]) for r in valid]
        reference_complete = complete and sport not in unresolved
        bins = []
        for index in range(4):
            first, last = start + timedelta(days=7 * index), start + timedelta(days=7 * (index + 1))
            items = [r for r in history if first <= r["_day"] < last]
            eligible = [r for r in items if _number(r.get("duration_minutes")) is not None]
            total = _sum([float(r["duration_minutes"]) for r in eligible])
            bins.append({"start_date": first.isoformat(), "end_date_exclusive": last.isoformat(),
                         "session_count": len(items), "eligible_duration_session_count": len(eligible),
                         "observed_minutes": total, "total_minutes": total if reference_complete else None})
        tss_values = [_number(r.get("tss"), zero=True) for r in history]
        methods = sorted({str(r.get("tss_method")) for r in history if r.get("tss_method")})
        known_tss = [n for n in tss_values if n is not None]
        # Even power/HR-derived training stress is a load estimate, not measured
        # tissue tolerance. Unrecognised/missing provenance remains unverified.
        known_methods = {"power_tss_bike", "hr_zone_tss_bike", "hr_tss_bike", "pace_tss_swim",
                         "hr_zone_tss_swim", "hr_tss_swim", "hr_zone_tss_run", "hr_tss_run",
                         "heuristic_duration_walk", "heuristic_duration_swim", "heuristic_duration_run",
                         "heuristic_duration_bike", "intervals_icu_provider_fallback"}
        method_known = [r.get("tss_method") in known_methods for r in history]
        provenance = ("estimated" if method_known and all(method_known)
                      else "mixed" if any(method_known) else "unverified")
        last = max((r["_day"] for r in observed[sport]), default=None)
        context_valid = [r for r in observed[sport] if _number(r.get("duration_minutes")) is not None]
        sports[sport] = {
            "session_count": len(history), "eligible_duration_session_count": len(valid),
            "training_days": len({r["_day"] for r in history}),
            "observed_minutes": _sum(minutes),
            "total_minutes": _sum(minutes) if reference_complete else None,
            "session_minutes": minutes, "longest_minutes": max(minutes, default=None),
            "last_exposure_date": last.isoformat() if last else None,
            "days_since_last": (as_of - last).days if last else None,
            "reference_complete": reference_complete, "bins": bins,
            "context": {"session_count": len(observed[sport]),
                        "observed_minutes": _sum([float(r["duration_minutes"]) for r in context_valid])},
            "tss": {"total": _sum(known_tss) if known_tss else (0.0 if not history and reference_complete else None),
                    "known_session_count": len(known_tss), "unknown_session_count": len(history) - len(known_tss),
                    "methods": methods, "provenance": provenance,
                    "coverage": "complete" if (history or reference_complete) and len(known_tss) == len(history) else "partial" if known_tss else "missing"},
        }
    return {"as_of": as_of.isoformat(), "timezone": timezone, "window_start": start.isoformat(),
            "window_end_exclusive": as_of.isoformat(), "context_start": context_start.isoformat(),
            "completeness": {"status": normalized["status"] if normalized else "unknown",
                             "source": "user_report" if normalized else "unknown",
                             "claimed_interval": ({"start_date": normalized["start_date"],
                                                   "end_date_exclusive": normalized["end_date_exclusive"]}
                                                  if normalized and normalized["start_date"] else None)},
            "sports": sports,
            "quality_limits": sorted(quality, key=lambda q: (q["code"], q["activity_id"] or "", q["sport"] or ""))}


def derive_entry_limits(
    profile: Mapping[str, Any], declared_limits: Mapping[str, Any] | None,
    *, cycle_scope: Mapping[str, str], target_sports: Sequence[str],
) -> dict[str, Any]:
    """Resolve sourced limits; final prescriptions are still unassessed (M4c)."""
    if not target_sports or set(target_sports) - set(SPORTS):
        raise ValueError("Explicit targeted endurance sports are required")
    first, last = _iso_day(cycle_scope["start_date"]), _iso_day(cycle_scope["end_date"])
    if last != first + timedelta(days=13):
        raise ValueError("Entry scope must retain the actual cycle's first 14 days")
    scope = {"start_date": first.isoformat(), "end_date": last.isoformat()}
    declared = normalize_entry_inputs(None, declared_limits).get("initial_dose_limits", {})
    limits, blockers = {}, []
    for sport in sorted(set(target_sports)):
        evidence = profile["sports"][sport]
        observed = None
        if evidence["reference_complete"] and evidence["bins"][-1]["eligible_duration_session_count"]:
            weekly = float(median(b["observed_minutes"] for b in evidence["bins"]))
            count = math.floor(median(b["eligible_duration_session_count"] for b in evidence["bins"]))
            longest = float(median(evidence["session_minutes"])) if evidence["session_minutes"] else 0
            if weekly > 0 and count > 0 and longest > 0:
                observed = {"source": "observed_reference", "weekly_minutes": weekly,
                            "weekly_sessions": count, "max_session_minutes": min(longest, weekly),
                            "source_window": {"start_date": profile["window_start"],
                                              "end_date_exclusive": profile["window_end_exclusive"]},
                            "scope": scope, "declared_ceiling": declared.get(sport)}
        if observed:
            # A human-supplied cap still binds when an observed reference exists;
            # it does not silently enlarge that recorded reference envelope.
            for field in ("weekly_minutes", "weekly_sessions", "max_session_minutes"):
                if sport in declared:
                    observed[field] = min(observed[field], declared[sport][field])
            observed["max_session_minutes"] = min(observed["max_session_minutes"], observed["weekly_minutes"])
            limits[sport] = observed
        elif sport in declared:
            limits[sport] = {**declared[sport], "source_window": None, "scope": scope, "declared_ceiling": None}
        else:
            blockers.append({"code": "entry_dose_required", "sport": sport, "date": None,
                             "field": "initial_dose_limits", "expected": "athlete_declared starting limits",
                             "observed": None})
    return {"policy_version": ENTRY_LOAD_POLICY_VERSION, "status": "needs_baseline" if blockers else "unassessed",
            "can_publish": False, "scope": scope, "profile": dict(profile), "limits": limits,
            "blockers": blockers, "warnings": [{"code": "final_prescription_unassessed", "sport": None,
                                                 "field": "entry_load"}]}
