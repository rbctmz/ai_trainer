"""Evidence-first plan/actual reconciliation and future-only rebalance."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping, Sequence

from models.session_identity import ensure_session_identities
from models.plan_intervals import project_planned_intervals
from models.workout_catalog import rescale_materialized_session
from models.session_quality_forecast import (
    SUBSTITUTED_LOAD_MAX,
    SUBSTITUTED_LOAD_MIN,
    classify_plan_adherence,
)
from utils.product_semantics import normalize_sport_key


MATCH_RULE_VERSION = "plan_actual_match_v1"
REBALANCE_RULE_VERSION = "weekly_rebalance_v1"
MIN_MATCHED_SESSIONS = 3
MIN_MATCH_COVERAGE = 0.70


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if hasattr(value, "to_dict"):
        try:
            rows = value.to_dict("records")
        except Exception:
            rows = None
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, Mapping)]
    try:
        return [dict(item) for item in value if isinstance(item, Mapping)]
    except TypeError:
        return []


def _activity_snapshot(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    activity_id = str(raw.get("activity_id") or raw.get("external_id") or "").strip()
    activity_date = _date_value(raw.get("date") or raw.get("start_date_local") or raw.get("start_date"))
    if not activity_id or activity_date is None:
        return None
    sport_raw = raw.get("sport") or raw.get("type")
    return {
        "activity_id": activity_id,
        "date": activity_date.isoformat(),
        "started_at_utc": raw.get("started_at_utc") or raw.get("start_date"),
        "sport": normalize_sport_key(sport_raw) or str(sport_raw or "").strip().lower(),
        "tss": round(max(0.0, _float(raw.get("tss") if raw.get("tss") is not None else raw.get("icu_training_load"))), 1),
        "duration_minutes": round(
            max(0.0, _float(raw.get("duration_minutes") if raw.get("duration_minutes") is not None else raw.get("moving_time")) / (60.0 if raw.get("duration_minutes") is None and raw.get("moving_time") is not None else 1.0)),
            1,
        ),
        "name": str(raw.get("activity_name") or raw.get("name") or activity_id),
    }


def _session_parts(session: Mapping[str, Any]) -> dict[str, float]:
    """Per-sport TSS breakdown of one PARENT session's own content.

    A composite brick's parts come from its legs (evidence detail, never a
    separate feedback target — see `iter_parent_sessions`); a single session
    is one sport carrying its own total.
    """
    if str(session.get("kind") or "") == "composite":
        parts: dict[str, float] = {}
        for leg in list(session.get("legs") or []):
            sport = normalize_sport_key((leg or {}).get("sport")) or str((leg or {}).get("sport") or "").strip().lower()
            if not sport:
                continue
            parts[sport] = round(parts.get(sport, 0.0) + _float((leg or {}).get("target_tss")), 1)
        return parts
    sport = normalize_sport_key(session.get("sport")) or str(session.get("sport") or "").strip().lower()
    if not sport:
        return {}
    return {sport: round(max(0.0, _float(session.get("total_tss"))), 1)}


def iter_parent_sessions(
    templates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Ordered independent PARENT sessions across all day templates.

    Issue #209 M5: reconciliation/feedback targets are `sessions[]` entries,
    never the day-level scalar projection (which is only ever equal to an
    individual session's own identity when the day carries exactly one
    session) and never a composite brick's individual legs — a brick stays
    ONE parent target, unlike `training_planner.iter_leaf_sessions`, whose
    leg-level leaves are delivery/evidence detail, not feedback targets.
    """
    result: list[dict[str, Any]] = []
    for template in templates:
        if not isinstance(template, Mapping):
            continue
        date_iso = str(template.get("date") or "")[:10]
        for session in list(template.get("sessions") or []):
            if not isinstance(session, Mapping) or not session.get("session_id"):
                continue
            result.append({"date": date_iso, "session": dict(session), "template": dict(template)})
    return result


def find_planned_session(
    templates: Sequence[Mapping[str, Any]],
    session_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve one parent session's own day template and content by its
    content-derived id — never the day-level `session_id` projection, which
    only coincides with an individual session's id on a single-session day."""
    target = str(session_id or "")
    for entry in iter_parent_sessions(templates):
        if str(entry["session"].get("session_id") or "") == target:
            return entry["template"], entry["session"]
    return None, None


def _planned_snapshot(
    date_iso: str,
    session: Mapping[str, Any],
    template: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    # #383: carry the projected planned intervals so the card can match plan vs
    # actual by reps. project_planned_intervals is fail-closed at the session
    # boundary but graceful per step; a malformed session yields [].
    try:
        intervals = project_planned_intervals(session)
    except ValueError:
        intervals = []
    return {
        "index": index,
        "session_id": session.get("session_id"),
        "date": date_iso,
        "sport": normalize_sport_key(session.get("sport")) or str(session.get("sport") or ""),
        "role": str(session.get("session_role") or "").strip().lower(),
        "phase": str(template.get("phase") or ""),
        "name": str(session.get("export_name") or session.get("session_focus") or "Сессия"),
        "tss": round(max(0.0, _float(session.get("total_tss"))), 1),
        "duration_minutes": int(round(max(0.0, _float(session.get("duration_minutes"))))),
        "parts": _session_parts(session),
        "intervals": intervals,
    }


def _provider_indexes(
    provider_activities: Any,
    provider_events: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    activity_by_external = {
        str(row.get("external_id")): row
        for row in _records(provider_activities)
        if str(row.get("external_id") or "").strip()
    }
    event_by_id = {
        str(row.get("id")): row
        for row in _records(provider_events)
        if str(row.get("id") or "").strip()
    }
    return activity_by_external, event_by_id


def _adherence(
    planned: Mapping[str, Any],
    *,
    match_status: str,
    actual_tss: float,
    actual_sport: str,
    actual_role: str | None,
) -> str:
    if match_status != "matched" or planned.get("tss") in {None, 0}:
        return "unknown"
    ratio = actual_tss / float(planned["tss"])
    if ratio < SUBSTITUTED_LOAD_MIN or ratio > SUBSTITUTED_LOAD_MAX:
        return "major_deviation"
    if not actual_role:
        # Review #399 P1: never fabricate the actual role for an unconfirmed
        # heuristic match — a planned quality day matched to an easy same-sport
        # activity would be misreported as `exact`. Keep `unknown` until role
        # evidence exists; the outer load check above still yields
        # `major_deviation` for clearly out-of-bounds loads.
        return "unknown"
    return classify_plan_adherence(
        {"role": planned.get("role"), "sport": planned.get("sport"), "tss": planned.get("tss")},
        {"role": actual_role, "sport": actual_sport, "tss": actual_tss},
    ) or "unknown"


def build_reconciliation(
    goal_plan: Mapping[str, Any],
    activities: Any,
    *,
    as_of: date,
    weeks: int,
    base_checkpoint_id: int,
    provider_activities: Any | None = None,
    provider_events: Any | None = None,
    ledger_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one read-only evidence snapshot for the completed lookback."""
    resolved_plan = ensure_session_identities(goal_plan)
    end = as_of
    resolved_weeks = max(1, int(weeks or 1))
    start = end - timedelta(days=resolved_weeks * 7 - 1)
    activity_rows = [
        item
        for raw in _records(activities)
        if (item := _activity_snapshot(raw)) is not None
        and start <= date.fromisoformat(item["date"]) <= end
    ]
    activity_rows.sort(key=lambda item: (item["date"], str(item.get("started_at_utc") or ""), item["activity_id"]))
    activities_by_date: dict[str, list[dict[str, Any]]] = {}
    for item in activity_rows:
        activities_by_date.setdefault(item["date"], []).append(item)

    provider_activity_by_external, provider_event_by_id = _provider_indexes(
        provider_activities,
        provider_events,
    )
    latest_ledger = {
        str(row.get("target_key")): dict(row)
        for row in (ledger_rows or [])
        if isinstance(row, Mapping) and row.get("target_key")
    }
    reserved_user_activity_ids = {
        str(activity_id)
        for row in latest_ledger.values()
        if str(row.get("match_method") or "") in {"user_confirmed", "admin_resolve"}
        for activity_id in row.get("actual_activity_ids", []) or []
    }
    assigned_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    templates = list(resolved_plan.get("session_templates") or [])
    parent_sessions = iter_parent_sessions(templates)
    planned_signature_counts: dict[tuple[str, str], int] = {}
    for index, entry in enumerate(parent_sessions):
        planned = _planned_snapshot(entry["date"], entry["session"], entry["template"], index)
        if not planned["date"]:
            continue
        planned_date = date.fromisoformat(planned["date"])
        if start <= planned_date <= end and planned["tss"] > 0 and planned.get("session_id"):
            signature = (planned["date"], planned["sport"])
            planned_signature_counts[signature] = planned_signature_counts.get(signature, 0) + 1

    for index, entry in enumerate(parent_sessions):
        planned = _planned_snapshot(entry["date"], entry["session"], entry["template"], index)
        if not planned["date"]:
            continue
        planned_date = date.fromisoformat(planned["date"])
        if not (start <= planned_date <= end) or planned["tss"] <= 0 or not planned.get("session_id"):
            continue
        target_key = f"session:{planned['session_id']}"
        ledger = latest_ledger.get(target_key)
        ledger_selected_ids = {
            str(value)
            for value in (ledger or {}).get("actual_activity_ids", []) or []
        }
        day_activities = [
            item
            for item in activities_by_date.get(planned["date"], [])
            if item["activity_id"] not in assigned_ids
            and (
                item["activity_id"] not in reserved_user_activity_ids
                or item["activity_id"] in ledger_selected_ids
            )
        ]
        matched: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        evidence: list[str] = []
        match_status = "unmatched"
        match_method = "date_sport_heuristic"
        confidence = 0.0
        actual_role: str | None = None

        if ledger and str(ledger.get("match_method")) in {
            "user_confirmed",
            "user_rejected",
            "user_unmatched",
            "admin_resolve",
        }:
            match_method = str(ledger.get("match_method"))
            match_status = str(ledger.get("match_status") or "unmatched")
            matched = [item for item in day_activities if item["activity_id"] in ledger_selected_ids]
            confidence = float(ledger.get("confidence") or (1.0 if match_method == "user_confirmed" else 0.0))
            actual_role = str((ledger.get("actual_snapshot") or {}).get("role") or "").strip().lower() or None
            evidence.extend(str(value) for value in ledger.get("evidence", []) if value)
            if match_method in {"user_confirmed", "admin_resolve"} and len(matched) != len(ledger_selected_ids):
                match_status = "ambiguous"
                confidence = 0.0
                evidence.append("Сохранённое пользователем сопоставление ссылается на активность, которая больше недоступна однозначно")
            if match_method == "user_unmatched":
                # #405 review P2: keep replacement candidates visible so the
                # athlete can re-select a different activity instead of the
                # session being permanently locked as "отменено пользователем".
                candidates = list(day_activities)
        else:
            stable = []
            provider_pair_notes: list[str] = []
            for item in day_activities:
                provider_activity = provider_activity_by_external.get(item["activity_id"])
                if not provider_activity:
                    continue
                paired_id = str(provider_activity.get("paired_event_id") or "").strip()
                paired_event = provider_event_by_id.get(paired_id)
                if not paired_event:
                    continue
                external_id = str(paired_event.get("external_id") or "").strip()
                expected_external_id = f"ai_trainer:{planned['session_id']}"
                if external_id == expected_external_id or external_id.startswith(
                    f"{expected_external_id}:leg:"
                ):
                    stable.append(item)
                else:
                    provider_pair_notes.append(f"Парное событие провайдера {paired_id} не имеет identity сессии AI Trainer")
            if stable:
                matched = stable
                match_status = "matched"
                match_method = "ai_trainer_external_id"
                confidence = 1.0
                evidence.append("Внешний id Intervals и парное событие соответствуют сессии AI Trainer")
            else:
                same_sport = [item for item in day_activities if item.get("sport") == planned.get("sport")]
                signature_count = planned_signature_counts.get((planned["date"], planned["sport"]), 0)
                if same_sport and signature_count == 1:
                    matched = same_sport
                    match_status = "matched"
                    match_method = "date_sport_heuristic"
                    confidence = 0.75
                    evidence.append("Единственная плановая сессия сопоставлена со всеми активностями того же дня и вида спорта")
                    evidence.extend(provider_pair_notes)
                elif day_activities:
                    candidates = list(day_activities)
                    match_status = "ambiguous"
                    confidence = 0.35
                    if same_sport:
                        evidence.append("Несколько плановых сессий претендуют на активность того же дня и вида спорта")
                    else:
                        evidence.append("Есть активности за эту дату, но вид спорта не совпадает с плановой сессией")
                    evidence.extend(provider_pair_notes)
                else:
                    evidence.append("Нет завершённой активности для этой плановой сессии")

        for item in matched:
            assigned_ids.add(item["activity_id"])
        actual_tss = round(sum(float(item.get("tss") or 0.0) for item in matched), 1)
        actual_duration = round(sum(float(item.get("duration_minutes") or 0.0) for item in matched), 1)
        sports = {str(item.get("sport") or "") for item in matched if item.get("sport")}
        actual_sport = next(iter(sports)) if len(sports) == 1 else ""
        rows.append(
            {
                **planned,
                "target_key": target_key,
                "match_status": match_status,
                "match_method": match_method,
                "confidence": round(confidence, 2),
                "evidence": evidence,
                "actual_activity_ids": [item["activity_id"] for item in matched],
                "actual_activities": matched,
                "candidate_activities": candidates,
                "actual_total_tss": actual_tss,
                "actual_duration_minutes": actual_duration,
                "actual_sport": actual_sport,
                "actual_role": actual_role,
                "adherence": _adherence(
                    planned,
                    match_status=match_status,
                    actual_tss=actual_tss,
                    actual_sport=actual_sport,
                    actual_role=actual_role,
                ),
            }
        )

    unplanned = [item for item in activity_rows if item["activity_id"] not in assigned_ids]
    matched_count = sum(1 for row in rows if row["match_status"] == "matched")
    ambiguous_count = sum(1 for row in rows if row["match_status"] == "ambiguous")
    unmatched_count = sum(1 for row in rows if row["match_status"] == "unmatched")
    planned_count = len(rows)
    coverage = round(matched_count / planned_count, 4) if planned_count else 0.0
    reasons: list[str] = []
    if matched_count < MIN_MATCHED_SESSIONS:
        reasons.append("insufficient_matched_sessions")
    if coverage < MIN_MATCH_COVERAGE:
        reasons.append("low_match_coverage")
    if ambiguous_count:
        reasons.append("ambiguous_matches")
    data_status = "sufficient" if not reasons else "data_gap"
    planned_tss = round(sum(float(row["tss"]) for row in rows), 1)
    matched_actual_tss = round(sum(float(row["actual_total_tss"]) for row in rows), 1)
    unplanned_tss = round(sum(float(item.get("tss") or 0.0) for item in unplanned), 1)
    total_actual_tss = round(sum(float(item.get("tss") or 0.0) for item in activity_rows), 1)

    return {
        "rule_version": MATCH_RULE_VERSION,
        "base_checkpoint_id": int(base_checkpoint_id),
        "as_of": as_of.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "weeks": resolved_weeks},
        "rows": rows,
        "unplanned_activities": unplanned,
        "data_quality": {
            "status": data_status,
            "planned_session_count": planned_count,
            "matched_count": matched_count,
            "ambiguous_count": ambiguous_count,
            "unmatched_count": unmatched_count,
            "coverage": coverage,
            "minimum_matched_sessions": MIN_MATCHED_SESSIONS,
            "minimum_coverage": MIN_MATCH_COVERAGE,
            "reasons": reasons,
        },
        "metrics": {
            "planned_tss": planned_tss,
            "matched_actual_tss": matched_actual_tss,
            "unplanned_tss": unplanned_tss,
            "total_actual_tss": total_actual_tss,
            "exact_count": sum(1 for row in rows if row["adherence"] == "exact"),
            "substituted_count": sum(1 for row in rows if row["adherence"] == "substituted"),
            "major_deviation_count": sum(1 for row in rows if row["adherence"] == "major_deviation"),
            "unknown_count": sum(1 for row in rows if row["adherence"] == "unknown"),
        },
    }


def _round_to_5(value: float) -> int:
    return max(0, int(float(value) // 5.0) * 5)


def _canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _empty_preview(*, reason: str, reconciliation: Mapping[str, Any], as_of: date) -> dict[str, Any]:
    payload = {
        "rule_version": REBALANCE_RULE_VERSION,
        "base_checkpoint_id": reconciliation.get("base_checkpoint_id"),
        "as_of": as_of.isoformat(),
        "status": "no_change",
        "reason": reason,
        "reduction_budget_tss": 0,
        "future_tss_delta": 0,
        "unused_reduction_tss": 0,
        "changes": [],
    }
    payload["preview_fingerprint"] = _canonical_fingerprint(payload)
    return payload


def build_weekly_rebalance_preview(
    goal_plan: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
    *,
    as_of: date,
    protected_dates: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a deterministic suggestion that can only reduce future easy load."""
    quality = dict(reconciliation.get("data_quality") or {})
    if quality.get("status") != "sufficient" or int(quality.get("ambiguous_count") or 0) > 0:
        return _empty_preview(reason="data_gap", reconciliation=reconciliation, as_of=as_of)
    metrics = dict(reconciliation.get("metrics") or {})
    overage = float(metrics.get("total_actual_tss") or 0.0) - float(metrics.get("planned_tss") or 0.0)
    if overage <= 0:
        return _empty_preview(reason="no_change_under_plan", reconciliation=reconciliation, as_of=as_of)
    if overage < 10:
        return _empty_preview(reason="no_change_below_threshold", reconciliation=reconciliation, as_of=as_of)

    resolved_plan = ensure_session_identities(goal_plan)
    daily_plan = list(resolved_plan.get("daily_plan") or [])
    templates = list(resolved_plan.get("session_templates") or [])
    window_end = as_of + timedelta(days=7)
    protected = {str(value)[:10] for value in protected_dates}
    protected.update(str(value)[:10] for value in resolved_plan.get("protected_dates", []) or [])
    near_term = dict((resolved_plan.get("constraint_summary") or {}).get("near_term_edit") or {})
    protected.update(str(value)[:10] for value in near_term.get("edited_dates", []) or [])

    future_total = 0.0
    eligible: list[dict[str, Any]] = []
    for index, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        current_date = _date_value(item[0])
        if current_date is None or not (as_of < current_date <= window_end):
            continue
        total = max(0.0, _float(item[1]))
        future_total += total
        template = templates[index] if index < len(templates) else {}
        role = str(template.get("session_role") or "").strip().lower()
        if current_date.isoformat() in protected or role != "easy" or total <= 5:
            continue
        eligible.append(
            {
                "index": index,
                "date": current_date.isoformat(),
                "session_role": role,
                "session_id": template.get("session_id"),
                "before_tss": round(total, 1),
                "capacity": max(0.0, min(total * 0.25, total - 5.0)),
            }
        )

    budget = _round_to_5(min(0.50 * overage, 0.15 * future_total, 40.0))
    if budget <= 0 or not eligible:
        return _empty_preview(reason="no_eligible_future_sessions", reconciliation=reconciliation, as_of=as_of)
    total_capacity = sum(item["capacity"] for item in eligible)
    applied_target = min(float(budget), total_capacity)
    changes: list[dict[str, Any]] = []
    remaining = applied_target
    for position, item in enumerate(eligible):
        if remaining <= 0:
            break
        remaining_capacity = sum(candidate["capacity"] for candidate in eligible[position:])
        proportional = remaining * (item["capacity"] / remaining_capacity) if remaining_capacity > 0 else 0.0
        reduction = min(item["capacity"], proportional)
        if position == len(eligible) - 1:
            reduction = min(item["capacity"], remaining)
        reduction = math.floor((reduction + 1e-9) * 10.0) / 10.0
        if reduction <= 0:
            continue
        after = round(item["before_tss"] - reduction, 1)
        remaining = round(max(0.0, remaining - reduction), 1)
        changes.append({**item, "after_tss": after, "delta_tss": round(after - item["before_tss"], 1)})

    actual_reduction = round(sum(-float(item["delta_tss"]) for item in changes), 1)
    payload = {
        "rule_version": REBALANCE_RULE_VERSION,
        "base_checkpoint_id": reconciliation.get("base_checkpoint_id"),
        "as_of": as_of.isoformat(),
        "status": "proposal" if changes else "no_change",
        "reason": "over_plan_future_reduction" if changes else "no_eligible_future_sessions",
        "overage_tss": round(overage, 1),
        "future_window_tss": round(future_total, 1),
        "reduction_budget_tss": budget,
        "future_tss_delta": round(-actual_reduction, 1),
        "unused_reduction_tss": round(max(0.0, budget - actual_reduction), 1),
        "changes": changes,
        "reconciliation_snapshot": deepcopy(dict(reconciliation)),
    }
    payload["preview_fingerprint"] = _canonical_fingerprint(payload)
    return payload


def _updated_description(
    description: str,
    total_tss: float,
    duration_minutes: int,
    parts: Mapping[str, float],
) -> str:
    canonical = {
        "total": f"Total TSS: {round(total_tss, 1)}",
        "duration": f"Оценка длительности: {duration_minutes} мин",
        "run": f"Run: {round(float(parts.get('run', 0.0) or 0.0), 1)}",
        "bike": f"Bike: {round(float(parts.get('bike', 0.0) or 0.0), 1)}",
        "swim": f"Swim: {round(float(parts.get('swim', 0.0) or 0.0), 1)}",
    }
    found: set[str] = set()
    lines = []
    for line in str(description or "").splitlines():
        if line.startswith("Total TSS:"):
            lines.append(canonical["total"])
            found.add("total")
        elif line.startswith("Оценка длительности:"):
            lines.append(canonical["duration"])
            found.add("duration")
        elif line.startswith("Run:"):
            lines.append(canonical["run"])
            found.add("run")
        elif line.startswith("Bike:"):
            lines.append(canonical["bike"])
            found.add("bike")
        elif line.startswith("Swim:"):
            lines.append(canonical["swim"])
            found.add("swim")
        else:
            lines.append(re.sub(r"\b\d+(?:\.\d+)?\s+TSS\b", f"{round(total_tss, 1)} TSS", line))
    for key in ("total", "duration", "run", "bike", "swim"):
        if key not in found:
            lines.append(canonical[key])
    return "\n".join(lines)


def apply_weekly_rebalance_preview(
    goal_plan: Mapping[str, Any],
    preview: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply a previously built pure preview to a copy of the goal plan."""
    if preview.get("status") != "proposal":
        return ensure_session_identities(goal_plan)
    original = ensure_session_identities(goal_plan)
    updated = deepcopy(original)
    daily_plan = list(updated.get("daily_plan") or [])
    templates = [dict(item or {}) for item in list(updated.get("session_templates") or [])]
    for change in preview.get("changes", []) or []:
        index = int(change["index"])
        before_dt, before_total, before_parts = daily_plan[index]
        after_total = float(change["after_tss"])
        scale = after_total / float(before_total) if float(before_total or 0.0) > 0 else 0.0
        after_parts = {key: round(float(value or 0.0) * scale, 1) for key, value in dict(before_parts or {}).items()}
        daily_plan[index] = (before_dt, after_total, after_parts)
        template = templates[index]
        before_duration = int(template.get("duration_minutes") or 0)
        after_duration = max(1, int(round(before_duration * scale))) if before_duration else 0
        template["duration_minutes"] = after_duration
        template["description"] = _updated_description(
            str(template.get("description") or ""),
            after_total,
            after_duration,
            after_parts,
        )
        if template.get("materialization_status") == "materialized":
            refreshed = rescale_materialized_session(
                template,
                target_tss=after_total,
                parts=after_parts,
            )
            refreshed["description"] = _updated_description(
                str(template.get("description") or ""),
                after_total,
                int(refreshed.get("duration_minutes") or after_duration),
                after_parts,
            )
            templates[index] = refreshed

    updated["daily_plan"] = daily_plan
    updated["session_templates"] = templates
    weekly_summary = [dict(row or {}) for row in list(updated.get("weekly_summary") or [])]
    for week_index, row in enumerate(weekly_summary):
        week_days = daily_plan[week_index * 7 : week_index * 7 + 7]
        row["weekly_tss"] = int(round(sum(float(item[1] or 0.0) for item in week_days)))
        for sport in ("bike", "run", "swim"):
            row[sport] = round(sum(float((item[2] or {}).get(sport, 0.0) or 0.0) for item in week_days), 1)
    updated["weekly_summary"] = weekly_summary
    updated["weekly_tss_plan"] = [int(row.get("weekly_tss") or 0) for row in weekly_summary]
    constraint_summary = dict(updated.get("constraint_summary") or {})
    constraint_summary["weekly_rebalance"] = {
        "rule_version": preview.get("rule_version"),
        "as_of": preview.get("as_of"),
        "base_checkpoint_id": preview.get("base_checkpoint_id"),
        "preview_fingerprint": preview.get("preview_fingerprint"),
        "future_tss_delta": preview.get("future_tss_delta"),
        "changes": deepcopy(list(preview.get("changes") or [])),
        "reconciliation_snapshot": deepcopy(preview.get("reconciliation_snapshot") or {}),
    }
    updated["constraint_summary"] = constraint_summary
    return ensure_session_identities(updated, previous_goal_plan=original)


__all__ = [
    "MATCH_RULE_VERSION",
    "REBALANCE_RULE_VERSION",
    "apply_weekly_rebalance_preview",
    "build_reconciliation",
    "build_weekly_rebalance_preview",
    "find_planned_session",
    "iter_parent_sessions",
]
