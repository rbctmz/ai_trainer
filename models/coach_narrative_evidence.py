"""Deterministic evidence boundary for athlete-facing coach narratives.

The policy is intentionally narrow. It is not a generic factuality checker:
only recovery/readiness, HRV suppression, bounded trends, causal claims from a
single-session comparison, missed sessions and calendar-relative claims are recognized.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


COACH_NARRATIVE_EVIDENCE_VERSION = "coach_narrative_evidence_v1"
COACH_NARRATIVE_GATE_RULE_VERSION = "coach_narrative_gate_v1"

READINESS_CLAIM_CONTRADICTED = "READINESS_CLAIM_CONTRADICTED"
HRV_CLAIM_CONTRADICTED = "HRV_CLAIM_CONTRADICTED"
TREND_COMPARATOR_MISSING = "TREND_COMPARATOR_MISSING"
TREND_CLAIM_CONTRADICTED = "TREND_CLAIM_CONTRADICTED"
CALENDAR_REFERENCE_MISMATCH = "CALENDAR_REFERENCE_MISMATCH"
SESSION_MISSED_UNSUPPORTED = "SESSION_MISSED_UNSUPPORTED"
READINESS_EVIDENCE_MISSING = "READINESS_EVIDENCE_MISSING"
READINESS_EVIDENCE_STALE = "READINESS_EVIDENCE_STALE"
HRV_EVIDENCE_MISSING = "HRV_EVIDENCE_MISSING"
INVALID_ATHLETE_TIMEZONE = "INVALID_ATHLETE_TIMEZONE"
CAUSAL_CLAIM_UNSUPPORTED = "CAUSAL_CLAIM_UNSUPPORTED"

_REASON_ORDER = (
    READINESS_CLAIM_CONTRADICTED,
    HRV_CLAIM_CONTRADICTED,
    TREND_COMPARATOR_MISSING,
    TREND_CLAIM_CONTRADICTED,
    CALENDAR_REFERENCE_MISMATCH,
    SESSION_MISSED_UNSUPPORTED,
    READINESS_EVIDENCE_MISSING,
    READINESS_EVIDENCE_STALE,
    HRV_EVIDENCE_MISSING,
    INVALID_ATHLETE_TIMEZONE,
    CAUSAL_CLAIM_UNSUPPORTED,
)
_DATA_GAP_CODES = {
    TREND_COMPARATOR_MISSING,
    SESSION_MISSED_UNSUPPORTED,
    READINESS_EVIDENCE_MISSING,
    READINESS_EVIDENCE_STALE,
    HRV_EVIDENCE_MISSING,
    INVALID_ATHLETE_TIMEZONE,
    CAUSAL_CLAIM_UNSUPPORTED,
}

_RU_WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)
_MATERIAL_RECOVERY = re.compile(
    r"(?:восстановлен\w*\s+(?:плох\w*|низк\w*|неудовлетвор\w*)|"
    r"(?:плох\w*|низк\w*|неудовлетвор\w*)\s+восстановлен\w*|"
    r"плох\w*\s+восстанови\w*|"
    r"(?:readiness|готовност\w*)\s+(?:плох\w*|низк\w*)|"
    r"не\s+восстановил\w*|восстановлен\w*\s+просел\w*)",
    re.IGNORECASE,
)
_MATERIAL_HRV = re.compile(
    r"(?:(?:hrv|вср)\s+(?:подавлен\w*|снижен\w*|низк\w*)|"
    r"(?:hrv|вср)\s+просел\w*|"
    r"(?:подавлен\w*|снижен\w*|низк\w*)\s+(?:hrv|вср)|"
    r"(?:hrv|вср)\s+ниже\s+(?:норм\w*|баз\w*))",
    re.IGNORECASE,
)
_MISSED_SESSION = re.compile(
    r"(?:трениров\w*|сесси\w*).{0,24}(?:пропущен\w*|не\s+выполнен\w*)|"
    r"(?:пропустил\w*|пропущен\w*|не\s+выполнен\w*).{0,24}(?:трениров\w*|сесси\w*)",
    re.IGNORECASE,
)
_NEGATED_MISS_PREFIX = re.compile(r"\bне\s*$", re.IGNORECASE)
_NEGATED_MISS_MATCH = re.compile(
    r"\bне\s+(?:был\w*\s+)?пропущен\w*",
    re.IGNORECASE,
)
_TREND_WORD = re.compile(
    r"(?:тренд\w*|улучш\w*|ухудш\w*|раст[её]т|вырос\w*|снижа\w*|"
    r"сниз(?:ил|ила|ило|или|ился|илась|илось|ились)\w*|стабил\w*|"
    r"лучше\s+прошл\w*|хуже\s+прошл\w*)",
    re.IGNORECASE,
)
_TREND_SUBJECT = re.compile(
    r"(?:hrv|вср|форма|нагрузк\w*|показател\w*|трениров\w*|сесси\w*|тренд\w*)",
    re.IGNORECASE,
)
_RELATIVE_DATE = re.compile(r"\b(?:сегодня|вчера|до\s+старта)\b", re.IGNORECASE)
_ISO_DATE = r"(\d{4}-\d{2}-\d{2})"
_NEGATED_ASSERTION = re.compile(
    r"(?:не\s+(?:подтвержда|доказыва)\w*|нельзя\s+сказать|нет\s+(?:данных|оснований)|"
    r"не\s+видно|не\s+похоже).{0,48}$",
    re.IGNORECASE,
)
_CONDITIONAL_PREFIX = re.compile(
    r"(?:^|[,:;]\s*)(?:если|когда|при\s+условии)\b.{0,64}$",
    re.IGNORECASE,
)
_BARE_PRI_PREFIX = re.compile(r"(?:^|[,:;]\s*)при\b.{0,64}$", re.IGNORECASE)
_ADVICE_VERB = re.compile(
    r"\b(?:держи|держите|сохраняй|сохраняйте|поддерживай|поддерживайте|"
    r"оставь|оставьте|выбери|выберите|отдохн\w*|отдыхай\w*|лучше|пусть)\b",
    re.IGNORECASE,
)
_INTENT_MARKER = re.compile(r"\b(?:хочу|планирую|цель\s*[-—:]?)\b", re.IGNORECASE)
_PLANNED_OR_FUTURE_TREND = re.compile(
    r"(?:\b(?:завтра|послезавтра)\b|"
    r"\b(?:на|в)\s+следующ\w+\s+"
    r"(?:недел\w*|д(?:ень|ня|ней)|месяц\w*|микроцикл\w*)\b|"
    r"\bпо\s+плану\b|"
    r"\bпланов\w*\s+(?:нагрузк\w*|объ[её]м\w*|трениров\w*|сесси\w*|разгрузк\w*)\b)",
    re.IGNORECASE,
)
_TREND_CLAIM_SEPARATOR = re.compile(r"[,;:—–]|\s+-\s+")
_CAUSAL_TAIL = re.compile(
    r"\b(?:потому\s+что|так\s+как|поскольку)\b\s*(.+)$",
    re.IGNORECASE,
)
_CAUSAL_ASSERTION = re.compile(
    r"(?:\b(?:вызван\w*|обусловлен\w*|из-за|благодаря|"
    r"причин\w*|следстви\w*)\b|"
    r"(?<!не\s)\b(?:доказыва\w*|подтвержда\w*|наблюда\w*|произошл\w*)"
    r".{0,32}\bадаптаци\w*\b|\b(?:это|значит)\s+адаптаци\w*\b|"
    r"\bадаптаци\w*(?:(?!\bне\b).){0,32}"
    r"\b(?:привел\w*|привод\w*|вызва\w*|обуслов\w*)\b|"
    r"\bсвязан\w*.{0,16}\bадаптаци\w*\b|"
    r"\bрезультат\w*\s+адаптаци\w*\b)",
    re.IGNORECASE,
)
_NEGATED_CAUSAL_PREFIX = re.compile(r"\bне\s*$", re.IGNORECASE)
_COMPARISON_CAUSAL_SCOPE = re.compile(
    r"(?:адаптаци\w*|сравнен\w*|сесси\w*|трениров\w*|tss|rpe|"
    r"мощност\w*|темп\w*|скорост\w*|пульс\w*|"
    r"интенсивност\w*|длительност\w*|нагрузк\w*|показател\w*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CoachNarrativeEvidence:
    """Allowlisted structured evidence supplied to the narrative gate."""

    payload: Mapping[str, Any]
    fingerprint: str


@dataclass(frozen=True)
class CoachNarrativeGateResult:
    """Final text plus stable, machine-readable validation outcome."""

    delivered_text: str
    outcome: str
    reason_codes: tuple[str, ...]
    evidence_version: str
    evidence_fingerprint: str

    @property
    def changed(self) -> bool:
        return self.outcome != "pass"

    def metadata(self) -> dict[str, Any]:
        return {
            "rule_version": COACH_NARRATIVE_GATE_RULE_VERSION,
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "evidence_version": self.evidence_version,
            "evidence_fingerprint": self.evidence_fingerprint,
        }


def resolve_calendar_evidence(
    *,
    athlete_timezone: str,
    observed_at_utc: datetime | None = None,
    event_date: Any = None,
) -> dict[str, Any]:
    """Resolve one timezone-aware calendar anchor, failing closed on bad TZ."""
    observed = observed_at_utc or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("observed_at_utc must be timezone-aware")
    timezone_name = str(athlete_timezone or "").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return {
            "status": "data_gap",
            "reason": "invalid_timezone",
            "athlete_timezone": timezone_name,
            "observed_at_utc": _utc_text(observed),
            "local_date": None,
            "yesterday_date": None,
            "yesterday_weekday_ru": None,
            "iso_weekday": None,
            "weekday_ru": None,
            "race_date": _date_text(event_date),
            "days_to_race": None,
        }

    local_date = observed.astimezone(zone).date()
    yesterday_date = local_date - timedelta(days=1)
    race_date = _as_date(event_date)
    return {
        "status": "available",
        "reason": None,
        "athlete_timezone": timezone_name,
        "observed_at_utc": _utc_text(observed),
        "local_date": local_date.isoformat(),
        "yesterday_date": yesterday_date.isoformat(),
        "yesterday_weekday_ru": _RU_WEEKDAYS[yesterday_date.weekday()],
        "iso_weekday": local_date.isoweekday(),
        "weekday_ru": _RU_WEEKDAYS[local_date.weekday()],
        "race_date": race_date.isoformat() if race_date else None,
        "days_to_race": (race_date - local_date).days if race_date else None,
    }


def build_coach_narrative_evidence(
    *,
    readiness_snapshot: Mapping[str, Any] | None,
    tool_results: Iterable[Mapping[str, Any]] = (),
    session_evidence: Mapping[str, Any] | None = None,
    goal_plan: Mapping[str, Any] | None = None,
    athlete_timezone: str,
    observed_at_utc: datetime | None = None,
) -> CoachNarrativeEvidence:
    """Build a deterministic, JSON-safe evidence bundle from raw facts."""
    tools = [dict(item) for item in tool_results if isinstance(item, Mapping)]
    payload = {
        "version": COACH_NARRATIVE_EVIDENCE_VERSION,
        "calendar": resolve_calendar_evidence(
            athlete_timezone=athlete_timezone,
            observed_at_utc=observed_at_utc,
            event_date=_event_date(goal_plan, tools),
        ),
        "readiness": _readiness_evidence(readiness_snapshot),
        "comparators": _comparator_evidence(tools),
        "sessions": _session_evidence(session_evidence),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return CoachNarrativeEvidence(
        payload=payload,
        fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


def validate_coach_narrative(
    narrative: str,
    evidence: CoachNarrativeEvidence,
) -> CoachNarrativeGateResult:
    """Validate bounded claims and return the only text safe for delivery."""
    text = str(narrative or "")
    claim_text = "\n".join(_claim_segments(text))
    payload = evidence.payload
    readiness = dict(payload.get("readiness") or {})
    calendar = dict(payload.get("calendar") or {})
    comparators = dict(payload.get("comparators") or {})
    comparator_domains = set(comparators.get("domains") or [])
    sessions = dict(payload.get("sessions") or {})
    found: set[str] = set()

    if _has_asserted_claim(claim_text, _MATERIAL_RECOVERY):
        if readiness.get("status") in {None, "unknown"} or readiness.get("score") is None:
            found.add(READINESS_EVIDENCE_MISSING)
        elif readiness.get("stale") or readiness.get("is_provisional"):
            found.add(READINESS_EVIDENCE_STALE)
        elif _number(readiness.get("score")) >= 60 and readiness.get("status") in {
            "strong",
            "ready",
        }:
            found.add(READINESS_CLAIM_CONTRADICTED)

    if _has_asserted_claim(claim_text, _MATERIAL_HRV):
        hrv = dict((readiness.get("factors_by_key") or {}).get("hrv") or {})
        if not hrv:
            found.add(HRV_EVIDENCE_MISSING)
        elif readiness.get("stale") or readiness.get("is_provisional") or hrv.get(
            "stale_input"
        ):
            found.add(READINESS_EVIDENCE_STALE)
        elif _hrv_is_not_suppressed(hrv):
            found.add(HRV_CLAIM_CONTRADICTED)

    trend_domains = _trend_claim_domains(claim_text)
    if trend_domains and not trend_domains.issubset(comparator_domains):
        found.add(TREND_COMPARATOR_MISSING)
    elif _trend_direction_mismatch(claim_text, comparators.get("directions") or {}):
        found.add(TREND_CLAIM_CONTRADICTED)

    if _RELATIVE_DATE.search(claim_text):
        if calendar.get("status") != "available":
            found.add(INVALID_ATHLETE_TIMEZONE)
        elif _calendar_mismatch(claim_text, calendar):
            found.add(CALENDAR_REFERENCE_MISMATCH)

    if _missed_session_claim_unsupported(claim_text, sessions, calendar):
        found.add(SESSION_MISSED_UNSUPPORTED)

    if (
        comparators.get("causal_claim_allowed") is False
        and _unsupported_comparison_causal_claim(claim_text)
    ):
        found.add(CAUSAL_CLAIM_UNSUPPORTED)

    reason_codes = tuple(code for code in _REASON_ORDER if code in found)
    if not reason_codes:
        return CoachNarrativeGateResult(
            delivered_text=text,
            outcome="pass",
            reason_codes=(),
            evidence_version=COACH_NARRATIVE_EVIDENCE_VERSION,
            evidence_fingerprint=evidence.fingerprint,
        )

    outcome = "data_gap" if any(code in _DATA_GAP_CODES for code in reason_codes) else "replaced"
    return CoachNarrativeGateResult(
        delivered_text=_replacement_text(reason_codes, payload),
        outcome=outcome,
        reason_codes=reason_codes,
        evidence_version=COACH_NARRATIVE_EVIDENCE_VERSION,
        evidence_fingerprint=evidence.fingerprint,
    )


def fail_closed_coach_narrative(
    evidence_fingerprint: str = "unavailable",
) -> CoachNarrativeGateResult:
    """Safe result for an unexpected validator failure."""
    return CoachNarrativeGateResult(
        delivered_text=(
            "Данных недостаточно, чтобы безопасно подтвердить вывод коуча. "
            "Сверьте синхронизацию и повторите запрос."
        ),
        outcome="data_gap",
        reason_codes=(READINESS_EVIDENCE_MISSING,),
        evidence_version=COACH_NARRATIVE_EVIDENCE_VERSION,
        evidence_fingerprint=evidence_fingerprint,
    )


def _readiness_evidence(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(snapshot or {})
    factors = {
        str(item.get("key")): {
            key: item.get(key)
            for key in (
                "score",
                "raw_value",
                "baseline",
                "deviation",
                "as_of",
                "source",
                "stale_input",
            )
        }
        for item in source.get("factors") or []
        if isinstance(item, Mapping) and item.get("key")
    }
    return {
        "rule_version": source.get("rule_version"),
        "status": source.get("status"),
        "score": source.get("score"),
        "confidence": source.get("confidence"),
        "stale": bool(source.get("stale")),
        "is_provisional": bool(source.get("is_provisional")),
        "missing_inputs": list(source.get("missing_inputs") or []),
        "factors_by_key": factors,
    }


def _session_evidence(source: Mapping[str, Any] | None) -> dict[str, Any]:
    value = dict(source or {})
    rows = [dict(row) for row in value.get("rows") or [] if isinstance(row, Mapping)]
    confirmed_rows = [
        row
        for row in rows
        if row.get("completion_status") == "did_not_start"
        or row.get("execution_state") == "missed_confirmed"
    ]
    confirmed_missed = [
        {
            "date": str(row.get("date") or value.get("date") or "")[:10] or None,
            "session_id": str(row.get("session_id") or "") or None,
            "sport": _canonical_sport(row.get("sport")),
            "name": str(
                row.get("name")
                or row.get("planned_name")
                or row.get("session_name")
                or ""
            )
            or None,
        }
        for row in confirmed_rows
    ]
    if value.get("missed_confirmed") and not confirmed_missed:
        confirmed_missed.append(
            {
                "date": str(value.get("date") or "")[:10] or None,
                "session_id": None,
                "sport": None,
                "name": None,
            }
        )
    return {
        "status": value.get("status") or "unavailable",
        "rule_version": value.get("rule_version"),
        "date": value.get("date"),
        "missed_supported": bool(confirmed_missed),
        "confirmed_missed": confirmed_missed,
    }


def _comparator_evidence(tool_results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    domains: set[str] = set()
    directions: dict[str, str] = {}
    causal_claim_allowed: bool | None = None
    for item in tool_results:
        if not item.get("success"):
            continue
        name = str(item.get("tool_name") or "")
        raw = item.get("raw_result")
        data = dict(raw) if isinstance(raw, Mapping) else {}
        if name == "analyze_hrv_trends" and _number(data.get("data_points")) >= 7:
            if data.get("baseline_median") is not None and data.get("trend_direction"):
                direction = _normalize_direction(data["trend_direction"])
                if direction is not None:
                    domains.add("hrv")
                    directions["hrv"] = direction
        elif name == "compare_periods":
            recent = data.get("recent_period")
            previous = data.get("previous_period")
            if isinstance(recent, Mapping) and isinstance(previous, Mapping):
                if not recent.get("no_data") and not previous.get("no_data"):
                    domains.update({"generic", "load"})
                    comparison = data.get("comparison")
                    comparison = dict(comparison) if isinstance(comparison, Mapping) else {}
                    delta = _number(comparison.get("tss_change"))
                    if delta != float("-inf"):
                        direction = _direction_from_delta(delta)
                        directions.update({"generic": direction, "load": direction})
        elif name == "analyze_training_load":
            if len(list(data.get("weekly_breakdown") or [])) >= 2:
                direction = _normalize_direction(data.get("load_trend"))
                if direction is not None:
                    domains.update({"generic", "load"})
                    directions.update({"generic": direction, "load": direction})
        elif name == "get_performance_metrics" and data.get("fitness_trend"):
            direction = _normalize_direction(data.get("fitness_trend"))
            if direction is not None:
                domains.update({"generic", "fitness", "load"})
                directions.update(
                    {"generic": direction, "fitness": direction, "load": direction}
                )
        elif name == "get_comparable_session":
            guardrails = data.get("guardrails")
            guardrails = dict(guardrails) if isinstance(guardrails, Mapping) else {}
            if guardrails.get("causal_claim_allowed") is False:
                causal_claim_allowed = False
            if data.get("status") == "available":
                comparison = data.get("comparison")
                comparison = (
                    dict(comparison) if isinstance(comparison, Mapping) else {}
                )
                tss_delta = _number(comparison.get("tss_delta"))
                if tss_delta != float("-inf"):
                    domains.add("session_tss")
                    directions["session_tss"] = _direction_from_delta(tss_delta)
                sport_metric = comparison.get("sport_metric")
                sport_metric = (
                    dict(sport_metric) if isinstance(sport_metric, Mapping) else {}
                )
                metric_delta = _number(sport_metric.get("delta"))
                metric_domain = _session_metric_domain(sport_metric.get("kind"))
                if metric_domain is not None and metric_delta != float("-inf"):
                    domains.add(metric_domain)
                    directions[metric_domain] = _session_metric_direction(
                        metric_domain,
                        metric_delta,
                    )
    return {
        "domains": sorted(domains),
        "directions": directions,
        "causal_claim_allowed": causal_claim_allowed,
    }


def _trend_claim_domains(text: str) -> set[str]:
    domains: set[str] = set()
    for segment, _trend_word in _asserted_historical_trend_claims(text):
        if not _TREND_SUBJECT.search(segment):
            continue
        domains.update(_trend_domains_for_claim(segment))
    return domains


def _trend_direction_mismatch(text: str, directions: Mapping[str, Any]) -> bool:
    for segment, trend_word in _asserted_historical_trend_claims(text):
        if not _TREND_SUBJECT.search(segment):
            continue
        claimed = _claimed_direction(trend_word.lower())
        if claimed is None:
            continue
        for domain in _trend_domains_for_claim(segment):
            observed = _normalize_direction(directions.get(domain))
            if observed is not None and observed != claimed:
                return True
    return False


def _trend_domains_for_claim(text: str) -> set[str]:
    lowered = text.lower()
    if "hrv" in lowered or "вср" in lowered:
        return {"hrv"}
    if "форма" in lowered or "показател" in lowered:
        return {"fitness"}
    session_scope = bool(
        re.search(r"трениров\w*|сесси\w*|прошл\w*", lowered, re.IGNORECASE)
    )
    if session_scope:
        if re.search(r"темп\w*|скорост\w*", lowered):
            return {"session_pace"}
        if "мощност" in lowered:
            return {"session_power"}
        if "tss" in lowered or "нагруз" in lowered:
            return {"session_tss"}
        return {"session"}
    if "нагруз" in lowered:
        return {"load"}
    return {"generic"}


def _session_metric_domain(kind: Any) -> str | None:
    normalized = str(kind or "").strip().lower()
    if normalized in {"pace_seconds_per_km", "pace_seconds_per_100m"}:
        return "session_pace"
    if normalized == "power_watts":
        return "session_power"
    return None


def _session_metric_direction(domain: str, delta: float) -> str:
    if domain == "session_pace":
        return _direction_from_delta(-delta)
    return _direction_from_delta(delta)


def _claimed_direction(text: str) -> str | None:
    if re.search(r"улучш\w*|раст[её]т|вырос\w*", text):
        return "improving"
    if re.search(
        r"ухудш\w*|снижа\w*|сниз(?:ил|ила|ило|или|ился|илась|илось|ились)\w*",
        text,
    ):
        return "declining"
    if re.search(r"стабил\w*", text):
        return "stable"
    return None


def _normalize_direction(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"improving", "increasing", "растущий", "улучшается"} or re.search(
        r"рост|увелич", text
    ):
        return "improving"
    if text in {"declining", "decreasing", "снижающийся", "ухудшается"} or re.search(
        r"снижен|снижение|ухудш", text
    ):
        return "declining"
    if text in {"stable", "стабильный", "стабильно"} or "стабил" in text:
        return "stable"
    return None


def _direction_from_delta(value: float) -> str:
    if value > 0:
        return "improving"
    if value < 0:
        return "declining"
    return "stable"


def _has_asserted_claim(
    text: str,
    pattern: re.Pattern[str],
    *,
    negated_prefix: re.Pattern[str] | None = None,
    negated_match: re.Pattern[str] | None = None,
) -> bool:
    for segment in _claim_segments(text):
        for match in pattern.finditer(segment):
            prefix = segment[: match.start()]
            suffix = segment[match.end() :]
            is_negated = _NEGATED_ASSERTION.search(prefix) or (
                negated_prefix is not None and negated_prefix.search(prefix)
            ) or (
                negated_match is not None and negated_match.search(match.group())
            )
            is_conditional = _CONDITIONAL_PREFIX.search(prefix) or (
                _BARE_PRI_PREFIX.search(prefix) and _ADVICE_VERB.search(suffix)
            )
            if not is_negated and not is_conditional:
                return True
    return False


def _unsupported_comparison_causal_claim(text: str) -> bool:
    """Reject causal claims derived from the comparison, not unrelated advice."""
    return any(
        _COMPARISON_CAUSAL_SCOPE.search(segment)
        and _has_asserted_claim(
            segment,
            _CAUSAL_ASSERTION,
            negated_prefix=_NEGATED_CAUSAL_PREFIX,
        )
        for segment in _claim_segments(text)
    )


def _missed_session_claim_unsupported(
    text: str,
    sessions: Mapping[str, Any],
    calendar: Mapping[str, Any],
) -> bool:
    confirmed = [
        dict(row)
        for row in sessions.get("confirmed_missed") or []
        if isinstance(row, Mapping)
    ]
    for segment in _claim_segments(text):
        if not _has_asserted_claim(
            segment,
            _MISSED_SESSION,
            negated_prefix=_NEGATED_MISS_PREFIX,
            negated_match=_NEGATED_MISS_MATCH,
        ):
            continue
        candidates = confirmed
        claimed_dates = _claimed_session_dates(segment, calendar)
        if len(claimed_dates) > 1:
            return True
        if claimed_dates:
            claimed_date = next(iter(claimed_dates))
            candidates = [row for row in candidates if row.get("date") == claimed_date]
        claimed_sport = _claim_sport(segment)
        if claimed_sport:
            candidates = [row for row in candidates if row.get("sport") == claimed_sport]
        lowered = segment.lower()
        mentioned_ids = {
            str(row.get("session_id"))
            for row in confirmed
            if row.get("session_id") and str(row.get("session_id")).lower() in lowered
        }
        if mentioned_ids:
            candidates = [
                row for row in candidates if str(row.get("session_id")) in mentioned_ids
            ]
        mentioned_names = {
            str(row.get("name"))
            for row in confirmed
            if row.get("name") and str(row.get("name")).lower() in lowered
        }
        if mentioned_names:
            candidates = [row for row in candidates if str(row.get("name")) in mentioned_names]
        if not candidates:
            return True
    return False


def _claimed_session_dates(text: str, calendar: Mapping[str, Any]) -> set[str]:
    dates = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    if re.search(r"\bсегодня\w*", text, re.IGNORECASE):
        dates.add(str(calendar.get("local_date") or ""))
    if re.search(r"\bвчера\w*", text, re.IGNORECASE):
        dates.add(str(calendar.get("yesterday_date") or ""))
    dates.discard("")
    return dates


def _claim_sport(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\b(?:swim\w*|плав\w*)", lowered):
        return "swim"
    if re.search(r"\b(?:bike\w*|cycling\w*|вело\w*)", lowered):
        return "bike"
    if re.search(r"\b(?:run\w*|running\w*|бег\w*)", lowered):
        return "run"
    return None


def _canonical_sport(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"swim", "swimming", "плавание"}:
        return "swim"
    if text in {"bike", "cycling", "велосипед", "вело"}:
        return "bike"
    if text in {"run", "running", "бег"}:
        return "run"
    return text or None


def _asserted_trend_matches(segment: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for match in _TREND_WORD.finditer(segment):
        prefix = segment[: match.start()]
        if _NEGATED_ASSERTION.search(prefix) or _CONDITIONAL_PREFIX.search(prefix):
            continue
        clause_prefix = re.split(r"[,;:—-]", prefix)[-1]
        if _ADVICE_VERB.search(clause_prefix):
            continue
        matches.append(match)
    return matches


def _asserted_historical_trend_claims(text: str) -> list[tuple[str, str]]:
    """Return match-scoped observed trends without losing punctuated subjects."""
    claims: list[tuple[str, str]] = []
    for segment in _claim_segments(text):
        matches = _asserted_trend_matches(segment)
        starts = [0] * len(matches)
        ends = [len(segment)] * len(matches)
        for index in range(len(matches) - 1):
            left = matches[index]
            right = matches[index + 1]
            gap = segment[left.end() : right.start()]
            separators = list(_TREND_CLAIM_SEPARATOR.finditer(gap))
            if not separators:
                continue
            separator = separators[-1]
            ends[index] = left.end() + separator.start()
            starts[index + 1] = left.end() + separator.end()
        for index, match in enumerate(matches):
            scope = segment[starts[index] : ends[index]].strip()
            if not scope or _PLANNED_OR_FUTURE_TREND.search(scope):
                continue
            claims.append((scope, match.group()))
    return claims


def _claim_segments(text: str) -> list[str]:
    segments: list[str] = []
    for line in str(text or "").splitlines() or [str(text or "")]:
        if line.lstrip().startswith(">"):
            continue
        for segment in re.split(r"(?<=[.!?])\s+", line):
            cleaned = re.sub(r"«[^»]*»|\"[^\"]*\"", "", segment).strip()
            if not cleaned:
                continue
            cleaned = _normalize_inline_markdown(cleaned)
            segments.extend(_intent_free_claim_parts(cleaned))
    return segments


def _normalize_inline_markdown(text: str) -> str:
    projected = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    projected = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", projected)
    return re.sub(r"(?<!\\)[*_~`]+", "", projected)


def _intent_free_claim_parts(text: str) -> list[str]:
    if not _INTENT_MARKER.search(text):
        return [text]
    parts: list[str] = []
    for part in re.split(r"\s*[,;]\s*", text):
        cleaned = part.strip()
        if not cleaned:
            continue
        if not _INTENT_MARKER.search(cleaned):
            parts.append(cleaned)
            continue
        tail = _CAUSAL_TAIL.search(cleaned)
        if tail and tail.group(1).strip():
            parts.append(tail.group(1).strip())
    return parts


def _calendar_mismatch(text: str, calendar: Mapping[str, Any]) -> bool:
    today = str(calendar.get("local_date") or "")
    yesterday = str(calendar.get("yesterday_date") or "")
    weekday = str(calendar.get("weekday_ru") or "")
    yesterday_weekday = str(calendar.get("yesterday_weekday_ru") or "")
    days_to_race = calendar.get("days_to_race")

    for match in re.finditer(rf"сегодня[^.\n]{{0,40}}?{_ISO_DATE}", text, re.IGNORECASE):
        if match.group(1) != today:
            return True
    for match in re.finditer(rf"вчера[^.\n]{{0,40}}?{_ISO_DATE}", text, re.IGNORECASE):
        if match.group(1) != yesterday:
            return True
    weekday_match = re.search(
        r"сегодня\s+(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)",
        text,
        re.IGNORECASE,
    )
    if weekday_match and weekday_match.group(1).lower() != weekday:
        return True
    yesterday_weekday_match = re.search(
        r"вчера\s+(?:(?:был|была|было)\s+)?"
        r"(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье)",
        text,
        re.IGNORECASE,
    )
    if (
        yesterday_weekday_match
        and yesterday_weekday_match.group(1).lower() != yesterday_weekday
    ):
        return True
    race_match = re.search(
        r"до\s+старта\D{0,20}(\d{1,4})\s*(?:дн(?:ей|я|ь)?|день|дня)",
        text,
        re.IGNORECASE,
    )
    if race_match:
        if days_to_race is None or int(race_match.group(1)) != int(days_to_race):
            return True
    return False


def _replacement_text(reason_codes: tuple[str, ...], payload: Mapping[str, Any]) -> str:
    lines = ["Не могу подтвердить исходный вывод по имеющимся данным."]
    readiness = dict(payload.get("readiness") or {})
    calendar = dict(payload.get("calendar") or {})
    if READINESS_CLAIM_CONTRADICTED in reason_codes:
        lines.append(
            f"- Канонический снимок: readiness {_format_number(readiness.get('score'))} "
            f"({readiness.get('status')}); исходный тезис о низком состоянии отклонён."
        )
    if HRV_CLAIM_CONTRADICTED in reason_codes:
        lines.append("- Фактор HRV не подтверждает утверждение о подавлении HRV.")
    if TREND_COMPARATOR_MISSING in reason_codes:
        lines.append("- Данных недостаточно для вывода о тренде: нет подходящего сравнения.")
    if TREND_CLAIM_CONTRADICTED in reason_codes:
        lines.append("- Направление заявленного тренда противоречит структурированному сравнению.")
    if CALENDAR_REFERENCE_MISMATCH in reason_codes:
        lines.append(
            f"- Каноническая дата: {calendar.get('local_date')} "
            f"({calendar.get('weekday_ru')}, {calendar.get('athlete_timezone')})."
        )
    if SESSION_MISSED_UNSUPPORTED in reason_codes:
        lines.append("- Данных недостаточно, чтобы считать тренировку пропущенной.")
    if CAUSAL_CLAIM_UNSUPPORTED in reason_codes:
        lines.append("- Одно сравнение не доказывает причину или адаптацию.")
    if any(
        code in reason_codes
        for code in (
            READINESS_EVIDENCE_MISSING,
            READINESS_EVIDENCE_STALE,
            HRV_EVIDENCE_MISSING,
            INVALID_ATHLETE_TIMEZONE,
        )
    ):
        lines.append("- Данных недостаточно для проверки утверждения; сначала обновите факты.")
    return "\n".join(lines)


def _event_date(
    goal_plan: Mapping[str, Any] | None,
    tool_results: Iterable[Mapping[str, Any]],
) -> Any:
    plan = dict(goal_plan or {})
    for key in ("event_date", "race_date"):
        if plan.get(key):
            return plan[key]
    for event in plan.get("events") or []:
        if isinstance(event, Mapping) and event.get("date"):
            return event["date"]
    for item in tool_results:
        if item.get("tool_name") != "get_active_plan" or not item.get("success"):
            continue
        raw = item.get("raw_result")
        if not isinstance(raw, Mapping):
            continue
        goal = raw.get("goal") if isinstance(raw.get("goal"), Mapping) else raw
        if goal.get("event_date"):
            return goal["event_date"]
    return None


def _hrv_is_not_suppressed(hrv: Mapping[str, Any]) -> bool:
    score = _number(hrv.get("score"))
    deviation = _number(hrv.get("deviation"))
    return score >= 60 or (hrv.get("deviation") is not None and deviation >= -5)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _format_number(value: Any) -> str:
    parsed = _number(value)
    return f"{parsed:g}" if parsed != float("-inf") else "н/д"


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _date_text(value: Any) -> str | None:
    parsed = _as_date(value)
    return parsed.isoformat() if parsed else None


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
