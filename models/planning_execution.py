"""Reusable execution-feedback and local-replanning helpers."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Mapping

from models.planning_summary import (
    EXECUTION_ADAPTATION_FOLLOW_UP_MODE_LABELS_RU,
    summarize_execution_adaptation_pressure,
)
from models.training_planner import (
    SESSION_ROLE_LABELS_RU,
    apply_planning_constraints,
    build_daily_session_templates,
    expand_weekly_to_daily_triathlon,
)

EXECUTION_DAY_OUTCOME_LABELS = {
    "as_planned": "По плану",
    "reduced": "Сделано легче",
    "missed": "Пропущено",
    "unavailable": "Недоступно",
}
EXECUTION_RESPONSE_STRATEGY_LABELS = {
    "protect_recovery": "Беречь восстановление",
    "catch_up": "Наверстать аккуратно",
}
EXECUTION_CORRECTIVE_ACTION_LABELS = {
    "keep_recovery": "Сохранить восстановление",
    "keep_easy": "Оставить лёгкой",
    "return_small_load": "Вернуть только малую часть объёма",
    "controlled_quality": "Сделать контролируемо",
    "single_key_stimulus": "Оставить одной ключевой работой",
    "hold_long_ceiling": "Не превращать в компенсацию",
}


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return int(default)


def _round_int(value: float) -> int:
    return int(round(float(value or 0.0)))


def _plan_adjustment_label(status: str) -> str:
    mapping = {
        "completed": "Выполнено по плану",
        "skipped": "Пропущены сессии",
        "reduced": "Нагрузка урезана",
        "unavailable": "Неделя ограничена",
        "none": "Нет",
    }
    return mapping.get((status or "none").lower(), "Нет")


def _normalize_response_strategy(strategy: Any) -> str:
    normalized = str(strategy or "protect_recovery").strip().lower()
    if normalized not in EXECUTION_RESPONSE_STRATEGY_LABELS:
        return "protect_recovery"
    return normalized


def _response_strategy_label(strategy: Any) -> str:
    normalized = _normalize_response_strategy(strategy)
    return EXECUTION_RESPONSE_STRATEGY_LABELS[normalized]


def _session_role_label(session_role: Any) -> str:
    normalized = str(session_role or "").strip().lower()
    return SESSION_ROLE_LABELS_RU.get(normalized, normalized or "—")


def _actual_tss_for_row(row: Mapping[str, Any]) -> int:
    planned_tss = max(0, _round_int(_coerce_float(row.get("planned_total_tss"))))
    outcome = str(row.get("outcome") or "as_planned").strip().lower()
    if outcome == "reduced":
        return min(planned_tss, max(0, _round_int(_coerce_float(row.get("actual_total_tss"), planned_tss))))
    if outcome in {"missed", "unavailable"}:
        return 0
    return planned_tss


def build_execution_reconciliation_rows(
    goal_plan: Mapping[str, Any],
    *,
    weeks: int = 1,
) -> List[Dict[str, Any]]:
    """Build editable day-level execution rows for the near-term horizon."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    session_templates = list(goal_plan.get("session_templates", []) or [])
    horizon_days = min(len(daily_plan), max(1, int(weeks or 1)) * 7)
    rows: List[Dict[str, Any]] = []

    for index, daily_item in enumerate(daily_plan[:horizon_days]):
        if not isinstance(daily_item, (list, tuple)) or len(daily_item) < 3:
            continue
        dt, total_tss, parts = daily_item
        session_template = session_templates[index] if index < len(session_templates) else {}
        date_value = dt.date() if isinstance(dt, datetime) else dt
        sport = str((session_template or {}).get("sport") or "").strip() or "—"
        session_role = str((session_template or {}).get("session_role") or "").strip() or "—"
        session_name = str((session_template or {}).get("export_name") or "").strip() or "Сессия"
        rows.append(
            {
                "index": index,
                "week_index": index // 7,
                "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                "date_label": date_value.strftime("%a %d.%m") if hasattr(date_value, "strftime") else str(date_value),
                "phase": str((session_template or {}).get("phase") or "—"),
                "sport": sport,
                "session_role": session_role,
                "session_name": session_name,
                "planned_total_tss": _round_int(_coerce_float(total_tss)),
                "planned_parts": dict(parts or {}),
                "planned_duration_minutes": _coerce_int((session_template or {}).get("duration_minutes"), 0),
                "outcome": "as_planned",
                "actual_total_tss": _round_int(_coerce_float(total_tss)),
            }
        )
    return rows


def summarize_execution_reconciliation(
    execution_reconciliation: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    """Normalize a persisted day-level execution reconciliation summary."""
    if not isinstance(execution_reconciliation, Mapping):
        return None

    planned_total_tss = _round_int(_coerce_float(execution_reconciliation.get("planned_total_tss")))
    actual_total_tss = _round_int(_coerce_float(execution_reconciliation.get("actual_total_tss")))
    delta_tss = _round_int(_coerce_float(execution_reconciliation.get("delta_tss"), actual_total_tss - planned_total_tss))
    changed_day_count = _coerce_int(execution_reconciliation.get("changed_day_count"))
    missed_day_count = _coerce_int(execution_reconciliation.get("missed_day_count"))
    reduced_day_count = _coerce_int(execution_reconciliation.get("reduced_day_count"))
    unavailable_day_count = _coerce_int(execution_reconciliation.get("unavailable_day_count"))
    completion_share = execution_reconciliation.get("completion_share")
    if completion_share is None:
        completion_share = (actual_total_tss / planned_total_tss) if planned_total_tss > 0 else 1.0
    completion_share = max(0.0, min(1.0, _coerce_float(completion_share, 1.0)))
    changed_rows = [
        dict(row)
        for row in execution_reconciliation.get("changed_rows", [])
        if isinstance(row, dict)
    ][:10]

    status = str(execution_reconciliation.get("status") or "").strip().lower()
    if not status:
        if changed_day_count <= 0:
            status = "completed"
        elif unavailable_day_count > 0 and unavailable_day_count >= max(1, (changed_day_count + 1) // 2):
            status = "unavailable"
        elif missed_day_count > 0 and reduced_day_count == 0:
            status = "skipped"
        else:
            status = "reduced"

    compact_label = str(execution_reconciliation.get("compact_label") or "").strip()
    if not compact_label:
        compact_label = (
            f"{actual_total_tss}/{planned_total_tss} TSS · {changed_day_count} дн. изменено"
            if changed_day_count > 0
            else f"{actual_total_tss}/{planned_total_tss} TSS"
        )

    description = str(execution_reconciliation.get("description") or "").strip()
    if not description:
        if changed_day_count <= 0:
            description = "Ближнее окно выполнено по плану без отклонений."
        else:
            description = (
                f"По факту выполнено {actual_total_tss} из {planned_total_tss} TSS; "
                f"изменено {changed_day_count} дн."
            )

    return {
        "status": status,
        "status_label": _plan_adjustment_label(status),
        "planned_total_tss": planned_total_tss,
        "actual_total_tss": actual_total_tss,
        "delta_tss": delta_tss,
        "changed_day_count": changed_day_count,
        "missed_day_count": missed_day_count,
        "reduced_day_count": reduced_day_count,
        "unavailable_day_count": unavailable_day_count,
        "completion_share": completion_share,
        "compact_label": compact_label,
        "description": description,
        "changed_rows": changed_rows,
    }


def summarize_execution_weekly_review(
    execution_weekly_review: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    """Normalize a compact weekly review derived from execution facts."""
    if not isinstance(execution_weekly_review, Mapping):
        return None

    recommended_strategy = _normalize_response_strategy(
        execution_weekly_review.get("recommended_response_strategy")
    )
    selected_strategy = _normalize_response_strategy(
        execution_weekly_review.get(
            "selected_response_strategy",
            recommended_strategy,
        )
    )
    deviations = [
        {
            "code": str(item.get("code") or "").strip(),
            "label": str(item.get("label") or "").strip(),
            "detail": str(item.get("detail") or "").strip(),
        }
        for item in execution_weekly_review.get("deviations", [])
        if isinstance(item, Mapping)
    ][:5]
    return {
        "headline": str(execution_weekly_review.get("headline") or "").strip(),
        "review_badge": str(execution_weekly_review.get("review_badge") or "").strip(),
        "deviations": [item for item in deviations if item["label"]],
        "recommended_response_strategy": recommended_strategy,
        "recommended_response_label": _response_strategy_label(recommended_strategy),
        "recommended_response_reason": str(execution_weekly_review.get("recommended_response_reason") or "").strip(),
        "selected_response_strategy": selected_strategy,
        "selected_response_label": _response_strategy_label(selected_strategy),
        "planned_active_day_count": _coerce_int(execution_weekly_review.get("planned_active_day_count")),
        "actual_active_day_count": _coerce_int(execution_weekly_review.get("actual_active_day_count")),
        "key_session_loss_count": _coerce_int(execution_weekly_review.get("key_session_loss_count")),
        "long_session_loss_count": _coerce_int(execution_weekly_review.get("long_session_loss_count")),
        "compression_risk": bool(execution_weekly_review.get("compression_risk", False)),
    }


def build_execution_adaptation_pressure(
    execution_reconciliation: Mapping[str, Any] | None,
    execution_weekly_review: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    """Turn execution drift into a compact next-1-2-week follow-up mode."""
    summary = summarize_execution_reconciliation(execution_reconciliation)
    review = summarize_execution_weekly_review(execution_weekly_review)
    if not isinstance(summary, dict):
        return None

    changed_day_count = _coerce_int(summary.get("changed_day_count"))
    reduced_day_count = _coerce_int(summary.get("reduced_day_count"))
    unavailable_day_count = _coerce_int(summary.get("unavailable_day_count"))
    completion_share = float(summary.get("completion_share", 1.0) or 1.0)
    delta_tss = _coerce_int(summary.get("delta_tss"))
    key_session_loss_count = _coerce_int((review or {}).get("key_session_loss_count"))
    long_session_loss_count = _coerce_int((review or {}).get("long_session_loss_count"))
    compression_risk = bool((review or {}).get("compression_risk"))
    selected_response_strategy = _normalize_response_strategy(
        (review or {}).get("selected_response_strategy")
    )

    score = 0
    signals: List[str] = []

    if changed_day_count >= 2:
        score += 10
        signals.append(f"изменено {changed_day_count} дн.")
    if delta_tss <= -20:
        score += 10
        signals.append(f"Δ {delta_tss:+d} TSS")
    if delta_tss <= -40:
        score += 15
    if completion_share < 0.90:
        score += 10
        signals.append(f"выполнено {int(round(completion_share * 100))}% окна")
    if completion_share < 0.80:
        score += 15
    if reduced_day_count > 0:
        score += 5
    if unavailable_day_count > 0:
        score += 15
        signals.append(f"недоступно {unavailable_day_count} дн.")
    if key_session_loss_count > 0:
        score += 20
        signals.append("потерян ключевой стимул")
    if long_session_loss_count > 0:
        score += 20
        signals.append("сорвана длинная сессия")
    if compression_risk:
        score += 20
        signals.append("есть риск компрессии недели")
    score = max(0, min(100, score))

    high_pressure = (
        compression_risk
        or (key_session_loss_count > 0 and long_session_loss_count > 0)
        or completion_share < 0.75
        or unavailable_day_count > 0
        or score >= 60
    )
    low_pressure = (
        not high_pressure
        and selected_response_strategy == "catch_up"
        and score <= 20
        and key_session_loss_count <= 0
        and long_session_loss_count <= 0
        and not compression_risk
    )
    level = "high" if high_pressure else "low" if low_pressure else "medium"

    if level == "high":
        follow_up_mode = "protect_recovery"
        growth_cap_tss_per_week = 15
        recovery_share_cap = 0.0
    elif level == "low":
        follow_up_mode = "catch_up"
        growth_cap_tss_per_week = 40
        recovery_share_cap = 0.35
    else:
        follow_up_mode = "hold"
        growth_cap_tss_per_week = 25
        recovery_share_cap = 0.0

    rebuild_horizon_weeks = 2 if changed_day_count > 0 else 1
    follow_up_label = EXECUTION_ADAPTATION_FOLLOW_UP_MODE_LABELS_RU[follow_up_mode]

    if follow_up_mode == "protect_recovery":
        reason = (
            "Дрейф недели уже слишком велик: ближайшие 1-2 недели лучше держать мягче и не ускорять rebound."
        )
    elif follow_up_mode == "catch_up":
        reason = (
            "Отклонение умеренное: можно вернуть только малую часть объёма, но под явным weekly ceiling."
        )
    else:
        reason = (
            "Окно уже сдвинулось заметно: следующие 1-2 недели лучше удержать текущий потолок, а не сразу разгонять план."
        )

    return {
        "level": level,
        "score": score,
        "follow_up_mode": follow_up_mode,
        "follow_up_label": follow_up_label,
        "rebuild_horizon_weeks": rebuild_horizon_weeks,
        "growth_cap_tss_per_week": growth_cap_tss_per_week,
        "recovery_share_cap": recovery_share_cap,
        "signals": signals,
        "reason": reason,
    }


def summarize_execution_weekly_review_rows(
    rows: List[Mapping[str, Any]] | None,
    *,
    current_response_strategy: str = "protect_recovery",
) -> Dict[str, Any]:
    """Derive a compact weekly review from day-level execution facts."""
    normalized_current_strategy = _normalize_response_strategy(current_response_strategy)
    planned_total_tss = 0
    actual_total_tss = 0
    planned_active_day_count = 0
    actual_active_day_count = 0
    changed_day_count = 0
    key_session_losses: List[str] = []
    long_session_losses: List[str] = []
    reduced_quality_sessions: List[str] = []
    unavailable_days = 0
    missed_days = 0

    for row in rows or []:
        planned_tss = max(0, _round_int(_coerce_float(row.get("planned_total_tss"))))
        actual_tss = _actual_tss_for_row(row)
        outcome = str(row.get("outcome") or "as_planned").strip().lower()
        session_name = str(row.get("session_name") or "Сессия").strip()
        session_role = str(row.get("session_role") or "").strip().lower()

        planned_total_tss += planned_tss
        actual_total_tss += actual_tss
        if planned_tss > 0:
            planned_active_day_count += 1
        if actual_tss > 0:
            actual_active_day_count += 1

        if outcome != "as_planned" or actual_tss != planned_tss:
            changed_day_count += 1
        if outcome == "missed":
            missed_days += 1
        elif outcome == "unavailable":
            unavailable_days += 1

        if session_role == "quality":
            if outcome in {"missed", "unavailable"}:
                key_session_losses.append(session_name)
            elif actual_tss < planned_tss:
                reduced_quality_sessions.append(session_name)
        if session_role == "long" and (outcome in {"missed", "unavailable"} or actual_tss * 2 < max(1, planned_tss)):
            long_session_losses.append(session_name)

    completion_share = (actual_total_tss / planned_total_tss) if planned_total_tss > 0 else 1.0
    delta_tss = actual_total_tss - planned_total_tss
    compression_risk = (
        planned_active_day_count > 0
        and actual_active_day_count > 0
        and actual_active_day_count < planned_active_day_count
        and completion_share >= 0.75
        and changed_day_count > 0
    )

    deviations: List[Dict[str, str]] = []
    if key_session_losses:
        deviations.append(
            {
                "code": "missed_key_session",
                "label": "Пропущена ключевая сессия",
                "detail": ", ".join(key_session_losses[:2]),
            }
        )
    if long_session_losses:
        deviations.append(
            {
                "code": "lost_long_session",
                "label": "Сорвана длинная сессия",
                "detail": ", ".join(long_session_losses[:2]),
            }
        )
    if reduced_quality_sessions:
        deviations.append(
            {
                "code": "reduced_quality_session",
                "label": "Ключевая работа сделана мягче",
                "detail": ", ".join(reduced_quality_sessions[:2]),
            }
        )
    if compression_risk:
        deviations.append(
            {
                "code": "overload_compression",
                "label": "Нагрузка сжалась в меньшее число дней",
                "detail": (
                    f"{actual_total_tss}/{planned_total_tss} TSS осталось в "
                    f"{actual_active_day_count} из {planned_active_day_count} активных дней"
                ),
            }
        )
    if delta_tss <= -40 and not any(item["code"] == "overload_compression" for item in deviations):
        deviations.append(
            {
                "code": "reduced_volume",
                "label": "Объём недели заметно снижен",
                "detail": f"Δ {delta_tss:+d} TSS",
            }
        )

    recommended_strategy = normalized_current_strategy
    recommended_reason = "Текущее окно близко к плану, поэтому можно сохранить исходную стратегию реакции."
    review_badge = "Неделя близка к плану"
    headline = "Окно выполнено близко к плану"

    if long_session_losses and key_session_losses:
        headline = "Потеряны длинная и ключевая сессии"
        review_badge = "Сильное отклонение"
        recommended_strategy = "protect_recovery"
        recommended_reason = "Когда выпали и длинная, и ключевая работа, безопаснее не пытаться вернуть этот объём одним коротким блоком."
    elif long_session_losses:
        headline = "Сорвана длинная сессия недели"
        review_badge = "Потеря длинной сессии"
        recommended_strategy = "protect_recovery"
        recommended_reason = "Длинную сессию лучше не догонять автоматически в ближайшие 1-2 дня, иначе неделя сожмётся."
    elif key_session_losses:
        headline = "Пропущена ключевая сессия"
        review_badge = "Потеря качества"
        recommended_strategy = "protect_recovery"
        recommended_reason = "После пропуска ключевой работы важнее вернуть структуру недели, чем срочно добивать интенсивность."
    elif compression_risk:
        headline = "Нагрузка сжалась в меньшее число дней"
        review_badge = "Риск компрессии"
        recommended_strategy = "protect_recovery"
        recommended_reason = "Похожий объём в меньшем числе дней повышает риск компрессии, поэтому лучше сохранить восстановление."
    elif completion_share < 0.80 or unavailable_days > 0:
        headline = "Неделя выполнена мягче запланированного"
        review_badge = "Сниженный объём"
        recommended_strategy = "protect_recovery"
        recommended_reason = "Факт недели уже заметно легче плана; безопаснее принять это окно как новый baseline, а не догонять объём."
    elif changed_day_count > 0 and completion_share >= 0.90:
        headline = "Неделя почти сохранена несмотря на сдвиги"
        review_badge = "Лёгкое отклонение"
        recommended_strategy = "catch_up"
        recommended_reason = "Ключевые сессии не потеряны, а отклонение умеренное, поэтому можно вернуть только небольшую часть объёма."

    return {
        "headline": headline,
        "review_badge": review_badge,
        "deviations": deviations,
        "recommended_response_strategy": recommended_strategy,
        "recommended_response_label": _response_strategy_label(recommended_strategy),
        "recommended_response_reason": recommended_reason,
        "selected_response_strategy": normalized_current_strategy,
        "selected_response_label": _response_strategy_label(normalized_current_strategy),
        "planned_active_day_count": planned_active_day_count,
        "actual_active_day_count": actual_active_day_count,
        "key_session_loss_count": len(key_session_losses) + len(reduced_quality_sessions),
        "long_session_loss_count": len(long_session_losses),
        "compression_risk": compression_risk,
    }


def _corrective_action_for_session(
    session_role: str,
    *,
    response_strategy: str,
    deviation_codes: set[str],
) -> Dict[str, str]:
    normalized_role = str(session_role or "").strip().lower()
    normalized_strategy = _normalize_response_strategy(response_strategy)

    if normalized_role in {"off", "recovery"}:
        if normalized_strategy == "catch_up":
            return {
                "action_code": "keep_recovery",
                "action_label": "Не забирать буфер восстановления",
                "reason": "Даже при аккуратном catch-up этот день остаётся защитой от компрессии недели.",
            }
        return {
            "action_code": "keep_recovery",
            "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["keep_recovery"],
            "reason": "Этот день нужен, чтобы вернуть ритм недели без догонки выпавшего объёма.",
        }
    if normalized_role == "quality":
        if normalized_strategy == "protect_recovery":
            return {
                "action_code": "controlled_quality",
                "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["controlled_quality"],
                "reason": "Верните структуру недели, но не пытайтесь добрать выпавшую интенсивность внутри этой сессии.",
            }
        if "missed_key_session" in deviation_codes:
            return {
                "action_code": "single_key_stimulus",
                "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["single_key_stimulus"],
                "reason": "После пропуска ключевой работы не вставляйте вторую компенсационную quality-сессию рядом.",
            }
        return {
            "action_code": "single_key_stimulus",
            "action_label": "Сохранить как главный стимул",
            "reason": "Можно вернуть только малую часть объёма вокруг этой сессии, не расширяя её сверх плана.",
        }
    if normalized_role == "long":
        if "lost_long_session" in deviation_codes or normalized_strategy == "protect_recovery":
            return {
                "action_code": "hold_long_ceiling",
                "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["hold_long_ceiling"],
                "reason": "Следующая длинная сессия остаётся потолком недели, а не компенсацией за сорванную работу.",
            }
        return {
            "action_code": "hold_long_ceiling",
            "action_label": "Оставить потолком недели",
            "reason": "Возврат нагрузки не должен превращать следующую длинную сессию в сверхобъём.",
        }
    if normalized_strategy == "catch_up":
        return {
            "action_code": "return_small_load",
            "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["return_small_load"],
            "reason": "Безопаснее вернуть немного объёма через лёгкий день, чем добавлять ещё одну тяжёлую работу.",
        }
    return {
        "action_code": "keep_easy",
        "action_label": EXECUTION_CORRECTIVE_ACTION_LABELS["keep_easy"],
        "reason": "Лёгкий день помогает разжать неделю и вернуть ритм без лишней догонки.",
    }


def summarize_execution_corrective_microcycle(
    execution_corrective_microcycle: Mapping[str, Any] | None,
) -> Dict[str, Any] | None:
    """Normalize a compact corrective 2-3 day microcycle derived from execution review."""
    if not isinstance(execution_corrective_microcycle, Mapping):
        return None

    selected_strategy = _normalize_response_strategy(
        execution_corrective_microcycle.get("selected_response_strategy")
    )
    sessions = []
    for item in execution_corrective_microcycle.get("sessions", []):
        if not isinstance(item, Mapping):
            continue
        sessions.append(
            {
                "date": str(item.get("date") or "").strip(),
                "date_label": str(item.get("date_label") or "").strip(),
                "session_name": str(item.get("session_name") or "Сессия").strip(),
                "session_role": str(item.get("session_role") or "").strip(),
                "session_role_label": str(item.get("session_role_label") or _session_role_label(item.get("session_role"))).strip(),
                "sport": str(item.get("sport") or "").strip(),
                "planned_total_tss": _coerce_int(item.get("planned_total_tss")),
                "planned_duration_minutes": _coerce_int(item.get("planned_duration_minutes")),
                "delta_tss": _coerce_int(item.get("delta_tss")),
                "delta_label": str(item.get("delta_label") or "").strip(),
                "action_code": str(item.get("action_code") or "").strip(),
                "action_label": str(item.get("action_label") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )

    return {
        "headline": str(execution_corrective_microcycle.get("headline") or "").strip(),
        "summary": str(execution_corrective_microcycle.get("summary") or "").strip(),
        "today_action": str(execution_corrective_microcycle.get("today_action") or "").strip(),
        "next_window": str(execution_corrective_microcycle.get("next_window") or "").strip(),
        "guardrail": str(execution_corrective_microcycle.get("guardrail") or "").strip(),
        "selected_response_strategy": selected_strategy,
        "selected_response_label": _response_strategy_label(selected_strategy),
        "window_total_tss": _coerce_int(execution_corrective_microcycle.get("window_total_tss")),
        "window_delta_tss": _coerce_int(execution_corrective_microcycle.get("window_delta_tss")),
        "window_day_count": _coerce_int(execution_corrective_microcycle.get("window_day_count")),
        "sessions": sessions[:3],
    }


def build_execution_corrective_microcycle(
    goal_plan: Mapping[str, Any],
    execution_weekly_review: Mapping[str, Any] | None,
    *,
    baseline_goal_plan: Mapping[str, Any] | None = None,
    horizon_days: int = 3,
) -> Dict[str, Any] | None:
    """Build a concrete corrective 2-3 day microcycle from the rebuilt near-term plan."""
    daily_plan = list(goal_plan.get("daily_plan", []) or [])
    session_templates = list(goal_plan.get("session_templates", []) or [])
    if not daily_plan:
        return None

    review = summarize_execution_weekly_review(execution_weekly_review)
    selected_strategy = _normalize_response_strategy(
        (
            (review or {}).get("selected_response_strategy")
            or ((goal_plan.get("constraint_summary", {}) or {}).get("catch_up_strategy"))
            or "protect_recovery"
        )
    )
    deviation_codes = {
        str(item.get("code") or "").strip()
        for item in ((review or {}).get("deviations") or [])
        if isinstance(item, Mapping)
    }

    baseline_daily_plan = list((baseline_goal_plan or {}).get("daily_plan", []) or [])
    session_rows: List[Dict[str, Any]] = []
    window_total_tss = 0
    window_delta_tss = 0

    for index, daily_item in enumerate(daily_plan[: max(1, int(horizon_days or 3))]):
        if not isinstance(daily_item, (list, tuple)) or len(daily_item) < 3:
            continue
        dt, total_tss, _parts = daily_item
        session_template = session_templates[index] if index < len(session_templates) else {}
        baseline_total_tss = 0
        if index < len(baseline_daily_plan):
            baseline_item = baseline_daily_plan[index]
            if isinstance(baseline_item, (list, tuple)) and len(baseline_item) >= 2:
                baseline_total_tss = _round_int(_coerce_float(baseline_item[1]))
        planned_total_tss = _round_int(_coerce_float(total_tss))
        if not baseline_daily_plan:
            baseline_total_tss = planned_total_tss
        delta_tss = planned_total_tss - baseline_total_tss
        action = _corrective_action_for_session(
            str((session_template or {}).get("session_role") or ""),
            response_strategy=selected_strategy,
            deviation_codes=deviation_codes,
        )
        date_value = dt.date() if isinstance(dt, datetime) else dt
        session_rows.append(
            {
                "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
                "date_label": date_value.strftime("%a %d.%m") if hasattr(date_value, "strftime") else str(date_value),
                "session_name": str((session_template or {}).get("export_name") or "Сессия").strip(),
                "session_role": str((session_template or {}).get("session_role") or "").strip().lower(),
                "session_role_label": _session_role_label((session_template or {}).get("session_role")),
                "sport": str((session_template or {}).get("sport") or "").strip(),
                "planned_total_tss": planned_total_tss,
                "planned_duration_minutes": _coerce_int((session_template or {}).get("duration_minutes")),
                "delta_tss": delta_tss,
                "delta_label": f"{delta_tss:+d} TSS" if delta_tss else "0 TSS",
                "action_code": action["action_code"],
                "action_label": action["action_label"],
                "reason": action["reason"],
            }
        )
        window_total_tss += planned_total_tss
        window_delta_tss += delta_tss

    if not session_rows:
        return None

    if "lost_long_session" in deviation_codes and selected_strategy == "protect_recovery":
        headline = "Ближайшие 2-3 дня: не догонять сорванную длинную"
        summary = "Следующий микроцикл возвращает ритм недели, но не пытается вернуть сорванный длинный объём одним блоком."
        guardrail = "Не переносите потерянную длинную сессию в ближайшие 48 часов."
    elif "missed_key_session" in deviation_codes and selected_strategy == "protect_recovery":
        headline = "Ближайшие 2-3 дня: вернуть структуру без второй quality-сессии"
        summary = "Микроцикл сохраняет только один качественный стимул и не добирает пропущенную интенсивность сверху."
        guardrail = "Не добавляйте вторую интенсивную работу рядом с текущей ключевой сессией."
    elif "overload_compression" in deviation_codes:
        headline = "Ближайшие 2-3 дня: разжать нагрузку и вернуть буфер"
        summary = "Следующее окно сохраняет лёгкий или восстановительный буфер, чтобы неделя не сжималась в меньшее число дней."
        guardrail = "Не сжимайте похожий объём в меньшее число тренировочных дней."
    elif selected_strategy == "catch_up":
        headline = "Ближайшие 2-3 дня: вернуть только малую часть объёма"
        summary = "Следующее окно аккуратно возвращает часть нагрузки, но не строит компенсационный мини-блок."
        guardrail = "Не делайте две тяжёлые сессии подряд и не расширяйте следующую длинную работу."
    else:
        headline = "Ближайшие 2-3 дня: сохранить ритм без компенсации"
        summary = "Следующее окно держит структуру недели и принимает фактический объём как новый ориентир."
        guardrail = "Не превращайте ближайший микроцикл в попытку быстро закрыть выпавший долг."

    if review and review.get("recommended_response_reason"):
        guardrail = str(review["recommended_response_reason"]).strip()

    today_row = session_rows[0]
    today_action = (
        f"{today_row['date_label']}: {today_row['action_label']} — "
        f"{today_row['session_name']} ({today_row['planned_total_tss']} TSS)."
    )
    if len(session_rows) > 1:
        next_window = " ; ".join(
            f"{row['date_label']}: {row['action_label']} ({row['session_name']})"
            for row in session_rows[1:]
        )
    else:
        next_window = summary

    return {
        "headline": headline,
        "summary": summary,
        "today_action": today_action,
        "next_window": next_window,
        "guardrail": guardrail,
        "selected_response_strategy": selected_strategy,
        "selected_response_label": _response_strategy_label(selected_strategy),
        "window_total_tss": window_total_tss,
        "window_delta_tss": window_delta_tss,
        "window_day_count": len(session_rows),
        "sessions": session_rows,
    }


def summarize_execution_reconciliation_rows(
    rows: List[Mapping[str, Any]] | None,
) -> Dict[str, Any]:
    """Summarize day-level execution facts into a compact local-replan input."""
    planned_total_tss = 0
    actual_total_tss = 0
    changed_day_count = 0
    missed_day_count = 0
    reduced_day_count = 0
    unavailable_day_count = 0
    changed_rows: List[Dict[str, Any]] = []

    for row in rows or []:
        planned_tss = max(0, _round_int(_coerce_float(row.get("planned_total_tss"))))
        outcome = str(row.get("outcome") or "as_planned").strip().lower()
        planned_total_tss += planned_tss
        actual_tss = _actual_tss_for_row(row)

        actual_total_tss += actual_tss
        changed = outcome != "as_planned" or actual_tss != planned_tss
        if not changed:
            continue

        changed_day_count += 1
        if outcome == "missed":
            missed_day_count += 1
        elif outcome == "reduced":
            reduced_day_count += 1
        elif outcome == "unavailable":
            unavailable_day_count += 1

        changed_rows.append(
            {
                "Дата": str(row.get("date_label") or row.get("date") or ""),
                "Сессия": str(row.get("session_name") or "Сессия"),
                "Роль": str(row.get("session_role") or "—"),
                "План TSS": planned_tss,
                "Факт TSS": actual_tss,
                "Δ TSS": f"{actual_tss - planned_tss:+d}",
                "Статус": EXECUTION_DAY_OUTCOME_LABELS.get(outcome, EXECUTION_DAY_OUTCOME_LABELS["as_planned"]),
            }
        )

    completion_share = (actual_total_tss / planned_total_tss) if planned_total_tss > 0 else 1.0
    if changed_day_count <= 0:
        status = "completed"
    elif unavailable_day_count > 0 and unavailable_day_count >= max(1, (changed_day_count + 1) // 2):
        status = "unavailable"
    elif missed_day_count > 0 and reduced_day_count == 0:
        status = "skipped"
    else:
        status = "reduced"

    summary = summarize_execution_reconciliation(
        {
            "status": status,
            "planned_total_tss": planned_total_tss,
            "actual_total_tss": actual_total_tss,
            "delta_tss": actual_total_tss - planned_total_tss,
            "changed_day_count": changed_day_count,
            "missed_day_count": missed_day_count,
            "reduced_day_count": reduced_day_count,
            "unavailable_day_count": unavailable_day_count,
            "completion_share": completion_share,
            "changed_rows": changed_rows,
        }
    )
    assert summary is not None
    return summary


def build_execution_plan_adjustment(
    goal_plan: Mapping[str, Any],
    rows: List[Mapping[str, Any]] | None,
    *,
    weeks: int = 1,
    response_strategy_override: str | None = None,
) -> Dict[str, Any]:
    """Convert day-level execution facts into a plan-adjustment payload."""
    summary = summarize_execution_reconciliation_rows(rows)
    current_response_strategy = str(
        ((goal_plan.get("constraint_summary", {}) or {}).get("catch_up_strategy") or "protect_recovery")
    )
    weekly_review = summarize_execution_weekly_review_rows(
        rows,
        current_response_strategy=response_strategy_override or current_response_strategy,
    )
    selected_response_strategy = _normalize_response_strategy(
        response_strategy_override or weekly_review["recommended_response_strategy"]
    )
    weekly_review["selected_response_strategy"] = selected_response_strategy
    weekly_review["selected_response_label"] = _response_strategy_label(selected_response_strategy)
    adaptation_pressure = build_execution_adaptation_pressure(summary, weekly_review)
    status = str(summary["status"] or "completed")
    available_day_count = _coerce_int((goal_plan.get("constraint_summary", {}) or {}).get("available_day_count"), 0)
    missed_sessions = summary["missed_day_count"] + summary["unavailable_day_count"]

    return {
        "status": status,
        "label": _plan_adjustment_label(status),
        "weeks": max(1, int(weeks or 1)) if status != "none" else 0,
        "missed_sessions": missed_sessions,
        "reduced_load_share": max(0.35, min(0.95, float(summary["completion_share"]))),
        "completion_share": float(summary["completion_share"]),
        "available_day_count": max(1, available_day_count),
        "execution_reconciliation": summary,
        "execution_weekly_review": weekly_review,
        "execution_adaptation_pressure": adaptation_pressure,
        "catch_up_strategy_override": selected_response_strategy,
    }


def _coerce_start_week(goal_plan: Mapping[str, Any]) -> date:
    raw_start_week = goal_plan.get("start_week")
    if isinstance(raw_start_week, datetime):
        return raw_start_week.date()
    if isinstance(raw_start_week, date):
        return raw_start_week

    weekly_summary = list(goal_plan.get("weekly_summary", []) or [])
    if weekly_summary:
        week_start = weekly_summary[0].get("week_start")
        if isinstance(week_start, datetime):
            return week_start.date()
        if isinstance(week_start, date):
            return week_start

    return datetime.now().date()


def rebuild_goal_plan_with_adjustment(
    goal_plan: Mapping[str, Any],
    plan_adjustment: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    """Rebuild a goal plan from its persisted context plus a new execution checkpoint."""
    constraint_summary = dict(goal_plan.get("constraint_summary", {}) or {})
    base_weekly_tss_plan = [
        int(round(value))
        for value in (goal_plan.get("base_weekly_tss_plan") or goal_plan.get("weekly_tss_plan") or [])
    ]
    phases = list(goal_plan.get("phases", []) or [])
    goal_type = str(goal_plan.get("goal_type") or "Триатлон")
    distance = str(goal_plan.get("distance") or "")
    start_week = _coerce_start_week(goal_plan)
    planner_mix = goal_plan.get("planner_mix") or None
    planner_weights = goal_plan.get("planner_weights") or None
    effective_catch_up_strategy = str(
        (
            (plan_adjustment or {}).get("catch_up_strategy_override")
            or constraint_summary.get("catch_up_strategy", "protect_recovery")
            or "protect_recovery"
        )
    )

    weekly_tss_plan, constraint_details, rebuilt_constraint_summary = apply_planning_constraints(
        base_weekly_tss_plan,
        phases,
        goal_type,
        available_hours=float(constraint_summary.get("available_hours", 0.0) or 0.0),
        available_day_indices=list(constraint_summary.get("available_day_indices", []) or []),
        interruption_type=str(constraint_summary.get("interruption_type", "none") or "none"),
        interruption_weeks=int(constraint_summary.get("interruption_weeks", 0) or 0),
        catch_up_strategy=effective_catch_up_strategy,
        current_tsb=float(constraint_summary.get("current_tsb", 0.0)) if constraint_summary.get("current_tsb") is not None else None,
        current_ctl=float(constraint_summary.get("current_ctl", 0.0)) if constraint_summary.get("current_ctl") is not None else None,
        current_atl=float(constraint_summary.get("current_atl", 0.0)) if constraint_summary.get("current_atl") is not None else None,
        plan_adjustment=plan_adjustment,
    )

    daily_plan, weekly_summary = expand_weekly_to_daily_triathlon(
        weekly_tss_plan,
        phases,
        distance,
        start_week,
        mix_overrides=planner_mix,
        weights_overrides=planner_weights,
        available_day_indices=list(rebuilt_constraint_summary.get("available_day_indices", []) or []),
        goal_type=goal_type,
        load_state=str(rebuilt_constraint_summary.get("load_state", "balanced")),
    )

    for week_row, detail in zip(weekly_summary, constraint_details):
        week_row["capacity_tss"] = detail.get("capacity_tss")
        week_row["adjustment_note"] = detail.get("adjustment_note", "—")

    session_templates = build_daily_session_templates(
        daily_plan,
        weekly_summary,
        goal_type=goal_type,
        distance=distance,
    )
    corrective_microcycle = None
    rebuilt_plan_adjustment = rebuilt_constraint_summary.get("plan_adjustment")
    if isinstance(rebuilt_plan_adjustment, dict) and rebuilt_plan_adjustment.get("execution_weekly_review"):
        corrective_microcycle = build_execution_corrective_microcycle(
            {
                "daily_plan": daily_plan,
                "session_templates": session_templates,
                "constraint_summary": rebuilt_constraint_summary,
            },
            rebuilt_plan_adjustment.get("execution_weekly_review"),
            baseline_goal_plan=goal_plan,
        )
        if corrective_microcycle is not None:
            rebuilt_plan_adjustment["execution_corrective_microcycle"] = corrective_microcycle
            notes = [
                str(note)
                for note in rebuilt_constraint_summary.get("notes", [])
                if note
            ]
            notes.append(
                "Execution microcycle: "
                f"{corrective_microcycle['headline']} "
                f"({corrective_microcycle['window_delta_tss']:+d} TSS в первых {corrective_microcycle['window_day_count']} дн.)."
            )
            rebuilt_constraint_summary["notes"] = notes

    return {
        "goal_type": goal_type,
        "distance": distance,
        "weeks_to_race": int(goal_plan.get("weeks_to_race", len(weekly_tss_plan)) or len(weekly_tss_plan)),
        "start_week": start_week,
        "weekly_tss_plan": weekly_tss_plan,
        "base_weekly_tss_plan": base_weekly_tss_plan,
        "phases": phases,
        "daily_plan": daily_plan,
        "session_templates": session_templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": rebuilt_constraint_summary,
        "planner_mix": planner_mix,
        "planner_weights": planner_weights,
    }


__all__ = [
    "EXECUTION_DAY_OUTCOME_LABELS",
    "EXECUTION_RESPONSE_STRATEGY_LABELS",
    "build_execution_adaptation_pressure",
    "build_execution_plan_adjustment",
    "build_execution_corrective_microcycle",
    "build_execution_reconciliation_rows",
    "rebuild_goal_plan_with_adjustment",
    "summarize_execution_adaptation_pressure",
    "summarize_execution_corrective_microcycle",
    "summarize_execution_reconciliation",
    "summarize_execution_reconciliation_rows",
    "summarize_execution_weekly_review",
    "summarize_execution_weekly_review_rows",
]
