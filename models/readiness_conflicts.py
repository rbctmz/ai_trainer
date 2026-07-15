"""Salience-gate: детектор конфликта «готовность × плановая сессия» (issue #141).

Второй слой агентного контура (после models/readiness.py, issue #139).
Детерминированные правила без LLM: конфликт объявляется только когда роль
плановой сессии и статус готовности пересекаются в матрице SEVERITY_MATRIX;
во всех остальных случаях выход — «молчание» (silence=True), и это полноценный,
логируемый результат. ExecPlan: docs/readiness_conflict_gate_execplan.md.
"""
from __future__ import annotations

from datetime import date
from typing import Any


# Ниже этого порога уверенности готовности детектор молчит с data_gap=True:
# вмешательство на 2 факторах из 5 ложно-положительно по построению.
MIN_CONFIDENCE = 0.5

DEFAULT_HORIZON_DAYS = 3
# Policy from issue #152: always inspect the base horizon, then extend through
# the nearest quality session only when it is still inside this bounded window.
MAX_QUALITY_LOOKAHEAD_DAYS = 7

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
        role = str((tpl or {}).get("session_role") or "").strip().lower()
        if role not in KNOWN_ROLES:
            role = "easy"

        sessions.append(
            {
                "date": session_date.isoformat(),
                "days_until": days_until,
                "role": role,
                "tss": tss,
                "name": str(
                    (tpl or {}).get("session_focus")
                    or (tpl or {}).get("export_name")
                    or "Сессия"
                ),
                "sport_label": str((tpl or {}).get("sport_label") or ""),
                "phase": str((tpl or {}).get("phase") or ""),
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
    """Extend the base horizon through the nearest bounded quality session."""
    base = max(1, int(base_horizon_days))
    cap = max(base, int(max_horizon_days))
    candidates = upcoming_plan_sessions(
        goal_plan,
        today=today,
        horizon_days=cap,
    )
    quality_session = next(
        (
            session
            for session in candidates
            if session["role"] == "quality" and session["days_until"] >= base
        ),
        None,
    )
    if quality_session is None:
        return {
            "base_horizon_days": base,
            "effective_horizon_days": base,
            "extended_for_quality": False,
            "quality_session": None,
            "lookahead_policy": "base_plus_nearest_quality",
        }

    return {
        "base_horizon_days": base,
        "effective_horizon_days": min(cap, int(quality_session["days_until"]) + 1),
        "extended_for_quality": True,
        "quality_session": dict(quality_session),
        "lookahead_policy": "base_plus_nearest_quality",
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
        severity = SEVERITY_MATRIX.get((session["role"], status))
        if severity is None:
            continue
        report["conflicts"].append(
            {
                "date": session["date"],
                "days_until": session["days_until"],
                "severity": severity,
                "kind": f"{status}_readiness_{session['role']}_session",
                "session": {
                    "name": session["name"],
                    "role": session["role"],
                    "tss": session["tss"],
                    "sport_label": session.get("sport_label", ""),
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
    return f"{when}: {session['name']} ({role_label}), TSS {session['tss']}"
