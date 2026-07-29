"""Salience-gate: детектор конфликта «готовность × плановая сессия» (#141, #315).

Второй слой агентного контура (после models/readiness.py, issue #139).
Детерминированные правила без LLM: конфликт объявляется только когда роль
плановой сессии либо структурированная цена нагрузки и статус готовности
пересекаются с правилами; во всех остальных случаях выход — «молчание»
(silence=True), и это полноценный, логируемый результат.
ExecPlan: docs/readiness_conflict_gate_execplan.md.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from numbers import Real
from typing import Any, Mapping


# Ниже этого порога уверенности готовности детектор молчит с data_gap=True:
# вмешательство на 2 факторах из 5 ложно-положительно по построению.
MIN_CONFIDENCE = 0.5

DEFAULT_HORIZON_DAYS = 3
# Policy from issues #152/#315: always inspect the base horizon, then extend
# through the nearest quality or structured high-load session inside this cap.
MAX_QUALITY_LOOKAHEAD_DAYS = 7
HIGH_FATIGUE_COMPONENT = 3
HIGH_RECOVERY_HOURS = 30

KNOWN_ROLES = ("recovery", "easy", "activation", "long", "quality")

# (роль сессии, статус готовности) → severity. Отсутствие ключа = нет конфликта.
# recovery/отдых не конфликтуют никогда: план и состояние согласны.
SEVERITY_MATRIX: dict[tuple[str, str], str] = {
    ("quality", "low"): "high",
    ("quality", "limited"): "medium",
    ("long", "low"): "high",
    ("long", "limited"): "medium",
    ("easy", "low"): "medium",
    ("activation", "low"): "medium",
}

ROLE_LABELS_RU = {
    "recovery": "восстановление",
    "easy": "лёгкая",
    "activation": "активация",
    "long": "длительная",
    "quality": "качественная",
}


def _compact_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _fatigue_cost(value: Any) -> list[int | float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return []
    numbers: list[int | float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, Real):
            return []
        numeric = float(component)
        if not isfinite(numeric) or numeric < 0:
            return []
        numbers.append(_compact_number(numeric))
    return numbers


def _recovery_hours(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        return None
    return _compact_number(numeric)


def _candidate_name(candidate: Mapping[str, Any]) -> str:
    return str(
        candidate.get("session_focus")
        or candidate.get("template_name")
        or candidate.get("export_name")
        or "Сессия"
    )


def _structured_load_metadata(template: Mapping[str, Any]) -> dict[str, Any]:
    """Aggregate structured load across every executable session of a plan day."""
    child_sessions = [
        session
        for session in list(template.get("sessions") or [])
        if isinstance(session, Mapping)
    ]
    candidates = child_sessions or [template]
    aggregate_fatigue: list[int | float] = []
    aggregate_recovery: int | float | None = None
    sources: list[dict[str, Any]] = []

    for position, candidate in enumerate(candidates):
        fatigue = _fatigue_cost(candidate.get("fatigue_cost"))
        recovery = _recovery_hours(candidate.get("expected_recovery_hours"))
        if fatigue:
            if not aggregate_fatigue:
                aggregate_fatigue = list(fatigue)
            else:
                aggregate_fatigue = [
                    max(current, incoming)
                    for current, incoming in zip(aggregate_fatigue, fatigue)
                ]
        if recovery is not None:
            aggregate_recovery = (
                recovery
                if aggregate_recovery is None
                else max(aggregate_recovery, recovery)
            )
        if fatigue or recovery is not None:
            max_fatigue = max(fatigue, default=0)
            sources.append(
                {
                    "position": position,
                    "name": _candidate_name(candidate),
                    "role": str(candidate.get("session_role") or ""),
                    "sport_label": str(candidate.get("sport_label") or ""),
                    "fatigue_cost": fatigue,
                    "expected_recovery_hours": recovery,
                    "load_salient": (
                        max_fatigue >= HIGH_FATIGUE_COMPONENT
                        or (
                            recovery is not None
                            and recovery >= HIGH_RECOVERY_HOURS
                        )
                    ),
                }
            )

    load_salient = (
        max(aggregate_fatigue, default=0) >= HIGH_FATIGUE_COMPONENT
        or (
            aggregate_recovery is not None
            and aggregate_recovery >= HIGH_RECOVERY_HOURS
        )
    )
    salient_sources = [source for source in sources if source["load_salient"]]
    ranked_sources = salient_sources or sources
    source = (
        max(
            ranked_sources,
            key=lambda item: (
                max(item["fatigue_cost"], default=0),
                item["expected_recovery_hours"] or 0,
                -item["position"],
            ),
        )
        if ranked_sources
        else None
    )
    if source is not None:
        source = {
            key: value
            for key, value in source.items()
            if key not in {"position", "load_salient"}
        }

    return {
        "fatigue_cost": aggregate_fatigue,
        "expected_recovery_hours": aggregate_recovery,
        "load_salient": load_salient,
        "salience_source": source if load_salient else None,
    }


def upcoming_plan_sessions(
    goal_plan: dict[str, Any] | None,
    *,
    today: date,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> list[dict[str, Any]]:
    """Сессии активного плана в горизонте [today, today+horizon_days).

    Дни отдыха (TSS <= 0) пропускаются. Неизвестная роль трактуется как easy —
    консервативно: слабее quality/long, но не выпадает из оценки.
    """
    if not goal_plan:
        return []

    daily_plan = list(goal_plan.get("daily_plan") or [])
    templates = list(goal_plan.get("session_templates") or [])

    sessions: list[dict[str, Any]] = []
    for i, item in enumerate(daily_plan):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        raw_date = item[0]
        session_date = raw_date.date() if hasattr(raw_date, "date") else raw_date
        if not isinstance(session_date, date):
            continue
        days_until = (session_date - today).days
        if days_until < 0 or days_until >= horizon_days:
            continue
        tss = int(round(float(item[1] or 0)))
        if tss <= 0:
            continue

        tpl = templates[i] if i < len(templates) else {}
        template = tpl if isinstance(tpl, Mapping) else {}
        role = str(template.get("session_role") or "").strip().lower()
        if role not in KNOWN_ROLES:
            role = "easy"

        sessions.append(
            {
                "date": session_date.isoformat(),
                "days_until": days_until,
                "role": role,
                "tss": tss,
                "name": _candidate_name(template),
                "sport_label": str(template.get("sport_label") or ""),
                "phase": str(template.get("phase") or ""),
                **_structured_load_metadata(template),
            }
        )

    sessions.sort(key=lambda s: s["days_until"])
    return sessions


def resolve_effective_horizon(
    goal_plan: dict[str, Any] | None,
    *,
    today: date,
    base_horizon_days: int = DEFAULT_HORIZON_DAYS,
    max_horizon_days: int = MAX_QUALITY_LOOKAHEAD_DAYS,
) -> dict[str, Any]:
    """Extend through the nearest bounded quality or structured high-load day."""
    base = max(1, int(base_horizon_days))
    cap = max(base, int(max_horizon_days))
    candidates = upcoming_plan_sessions(
        goal_plan,
        today=today,
        horizon_days=cap,
    )
    salience_session = next(
        (
            session
            for session in candidates
            if (
                session["role"] == "quality"
                or (
                    session["role"] == "easy"
                    and bool(session.get("load_salient"))
                )
            )
            and session["days_until"] >= base
        ),
        None,
    )
    if salience_session is None:
        return {
            "base_horizon_days": base,
            "effective_horizon_days": base,
            "extended_for_quality": False,
            "quality_session": None,
            "extended_for_salience": False,
            "salience_session": None,
            "lookahead_policy": "base_plus_nearest_significant",
        }

    is_quality = salience_session["role"] == "quality"
    return {
        "base_horizon_days": base,
        "effective_horizon_days": min(
            cap,
            int(salience_session["days_until"]) + 1,
        ),
        "extended_for_quality": is_quality,
        "quality_session": dict(salience_session) if is_quality else None,
        "extended_for_salience": True,
        "salience_session": dict(salience_session),
        "lookahead_policy": "base_plus_nearest_significant",
    }


def detect_readiness_conflicts(
    readiness: dict[str, Any],
    sessions: list[dict[str, Any]],
    *,
    today: date,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> dict[str, Any]:
    """Собрать отчёт конфликтов готовности и плановых сессий.

    readiness — результат models/readiness.py::compute_readiness_today.
    sessions — список из upcoming_plan_sessions (или совместимый).
    """
    score = readiness.get("score")
    status = str(readiness.get("status") or "unknown")
    confidence = float(readiness.get("confidence") or 0.0)

    report: dict[str, Any] = {
        "as_of": readiness.get("as_of_date") or today.isoformat(),
        "horizon_days": horizon_days,
        "readiness": {"score": score, "status": status, "confidence": confidence},
        "sessions_evaluated": [],
        "conflicts": [],
        "silence": True,
        "data_gap": False,
        "reason": "",
    }

    if score is None or confidence < MIN_CONFIDENCE:
        report["data_gap"] = True
        report["reason"] = (
            "Недостаточно свежих данных о восстановлении "
            f"(confidence {confidence:.2f} < {MIN_CONFIDENCE}) — детектор молчит."
        )
        return report

    evaluated = [s for s in sessions if 0 <= int(s.get("days_until", -1)) < horizon_days]
    report["sessions_evaluated"] = evaluated

    readiness_evidence = _readiness_evidence(readiness)

    for session in evaluated:
        high_load_easy = (
            session["role"] == "easy"
            and bool(session.get("load_salient"))
        )
        matrix_role = "quality" if high_load_easy else session["role"]
        severity = SEVERITY_MATRIX.get((matrix_role, status))
        if severity is None:
            continue
        kind_role = f"high_load_{session['role']}" if high_load_easy else session["role"]
        report["conflicts"].append(
            {
                "date": session["date"],
                "days_until": session["days_until"],
                "severity": severity,
                "kind": f"{status}_readiness_{kind_role}_session",
                "session": {
                    "name": session["name"],
                    "role": session["role"],
                    "tss": session["tss"],
                    "sport_label": session.get("sport_label", ""),
                    "fatigue_cost": list(session.get("fatigue_cost") or []),
                    "expected_recovery_hours": session.get(
                        "expected_recovery_hours"
                    ),
                    "load_salient": bool(session.get("load_salient")),
                    "salience_source": session.get("salience_source"),
                },
                "evidence": [
                    readiness_evidence,
                    _session_evidence(session),
                ],
            }
        )

    if report["conflicts"]:
        report["silence"] = False
        worst = max(report["conflicts"], key=lambda c: 0 if c["severity"] == "medium" else 1)
        report["reason"] = (
            f"Готовность {status} ({score}/100) расходится с планом: "
            f"{worst['session']['name']} через {worst['days_until']} дн."
        )
    else:
        report["reason"] = (
            f"Готовность {status} ({score}/100) не противоречит сессиям "
            f"ближайших {horizon_days} дн. — вмешательство не требуется."
        )
    return report


def _readiness_evidence(readiness: dict[str, Any]) -> str:
    score = readiness.get("score")
    status = readiness.get("status")
    driver_bits = [
        str(d.get("evidence"))
        for d in (readiness.get("drivers") or [])
        if d.get("evidence")
    ]
    drivers = "; ".join(driver_bits[:3]) or "драйверы недоступны"
    return f"Готовность {score}/100 ({status}): {drivers}"


def _session_evidence(session: dict[str, Any]) -> str:
    days_until = int(session.get("days_until", 0))
    if days_until == 0:
        when = "Сегодня"
    elif days_until == 1:
        when = "Завтра"
    else:
        when = f"Через {days_until} дн."
    role_label = ROLE_LABELS_RU.get(session["role"], session["role"])
    evidence = f"{when}: {session['name']} ({role_label}), TSS {session['tss']}"
    if session.get("load_salient"):
        fatigue = list(session.get("fatigue_cost") or [])
        recovery = session.get("expected_recovery_hours")
        load_bits = []
        if fatigue:
            load_bits.append(f"fatigue {'/'.join(str(value) for value in fatigue)}")
        if recovery is not None:
            load_bits.append(f"восстановление ~{recovery} ч")
        source = session.get("salience_source")
        if isinstance(source, Mapping) and source.get("name") != session.get("name"):
            load_bits.append(f"источник нагрузки: {source.get('name')}")
        if load_bits:
            evidence = f"{evidence}; {', '.join(load_bits)}"
    return evidence
