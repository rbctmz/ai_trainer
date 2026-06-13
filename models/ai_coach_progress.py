"""Progress-report helpers for the AI coaching flow."""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


PROGRESS_KEYWORDS = (
    "прогресс за месяц",
    "прогресс за последний месяц",
    "покажи прогресс за месяц",
    "итоги месяца",
    "итоги за месяц",
    "month progress",
    "monthly progress",
)


def is_progress_request(text: Optional[str]) -> bool:
    """Определяет, просит ли пользователь отчёт по прогрессу за месяц."""
    if not text:
        return False
    lowered = text.lower()
    if "прогресс" in lowered and "меся" in lowered:
        return True
    return any(keyword in lowered for keyword in PROGRESS_KEYWORDS)


def maybe_append_progress_report(
    state: Any,
    user_input: Optional[str],
    final_response: str,
    tool_result_formatter: Callable[[str, Any], str],
) -> str:
    """Добавляет отчёт о прогрессе, если пользователь его запрашивал."""
    if not is_progress_request(user_input):
        return final_response

    filtered_existing = _filter_progress_sections(final_response)
    if filtered_existing and "## 📈 Прогресс" in filtered_existing:
        return filtered_existing

    progress_report = build_progress_report(
        state,
        tool_result_formatter,
    )
    if not progress_report:
        return filtered_existing or final_response

    base_text = filtered_existing.strip()
    if base_text and progress_report.strip() == base_text:
        return base_text

    if base_text:
        return f"{base_text}\n\n{progress_report}".strip()

    return progress_report.strip()


def build_progress_report(
    state: Any,
    tool_result_formatter: Callable[[str, Any], str],
    period_days: int = 30,
    previous_days: Optional[int] = None,
) -> Optional[str]:
    """Собирает структурированный отчёт о прогрессе, восстановлении и сне."""
    if state is None:
        return None

    ai_tools = getattr(state, "ai_tools", None)
    if ai_tools is None:
        return None

    previous_days = previous_days or period_days

    sections: List[str] = []
    compare_data: Optional[Dict[str, Any]] = None

    compare_result = _execute_tool(ai_tools, "compare_periods", period1_days=period_days, period2_days=previous_days)
    if compare_result.get("success"):
        compare_data = compare_result.get("result")
        if compare_data:
            compare_block = tool_result_formatter("compare_periods", compare_data)
            if compare_block:
                sections.append(compare_block.strip())
    else:
        error_msg = compare_result.get("error")
        if error_msg:
            sections.append(f"ℹ️ **Не удалось сформировать сравнение:** {error_msg}")

    load_data: Optional[Dict[str, Any]] = None
    load_result = _execute_tool(ai_tools, "analyze_training_load", days=period_days)
    if load_result.get("success"):
        potential_load = load_result.get("result")
        if isinstance(potential_load, dict) and potential_load:
            load_data = potential_load

    hrv_data: Optional[Dict[str, Any]] = None
    hrv_result = _execute_tool(ai_tools, "analyze_hrv_trends", days=period_days)
    if hrv_result.get("success"):
        potential_hrv = hrv_result.get("result")
        if isinstance(potential_hrv, dict) and potential_hrv:
            hrv_data = potential_hrv

    recovery_section = _format_recovery_section(load_data, hrv_data, period_days)
    if recovery_section:
        sections.append(recovery_section)

    sleep_data: Optional[Dict[str, Any]] = None
    sleep_result = _execute_tool(ai_tools, "get_sleep_stats", days=period_days)
    if sleep_result.get("success"):
        sleep_data = sleep_result.get("result")
        if isinstance(sleep_data, dict) and sleep_data.get("has_data"):
            sections.append(_format_sleep_section(sleep_data))

    recommendations = _generate_progress_recommendations(compare_data, load_data, hrv_data, sleep_data)
    if recommendations:
        bullet_lines = [f"{idx}. {rec}" for idx, rec in enumerate(recommendations, 1)]
        sections.append("### Что сделать дальше\n" + "\n".join(bullet_lines))

    sections.append("_Хочешь, составлю план на следующую неделю или разберу конкретный вид спорта?_")

    return "\n\n".join(section for section in sections if section and section.strip())


def _execute_tool(ai_tools: Any, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
    response = ai_tools.execute_tool(tool_name, **kwargs)
    return response if isinstance(response, dict) else {}


def _format_recovery_section(
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    period_days: int,
) -> str:
    """Формирует блок про нагрузку и восстановление в рамках периода."""
    if not load_data and not hrv_data:
        return ""

    lines: List[str] = [f"### Нагрузка и восстановление ({period_days} дней)"]

    if load_data:
        trend = load_data.get("load_trend", "н/д")
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        total_week_tss = sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown)
        avg_week_tss = total_week_tss / len(weekly_breakdown) if weekly_breakdown else 0.0
        avg_sessions = (
            sum(float(week.get("session_count", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown
            else 0.0
        )
        intensity = load_data.get("intensity_distribution", {})

        lines.append(f"- Тренд нагрузки: {trend}")
        if avg_week_tss > 0:
            lines.append(f"- Средний недельный TSS: {avg_week_tss:.0f} при {avg_sessions:.1f} тренировок/нед")
        if intensity:
            lines.append(
                "- Распределение интенсивности: "
                f"{intensity.get('low_intensity_percent', 0):.0f}% низк · "
                f"{intensity.get('moderate_intensity_percent', 0):.0f}% умер · "
                f"{intensity.get('high_intensity_percent', 0):.0f}% высок"
            )

    if hrv_data:
        current = hrv_data.get("current_rmssd")
        recent_avg = hrv_data.get("recent_avg_7days")
        baseline = hrv_data.get("baseline_median")
        trend = hrv_data.get("trend_direction")
        recovery_state = hrv_data.get("recovery_state")

        trend_text = _describe_hrv_trend(trend)
        recovery_label = _describe_recovery_state(recovery_state)

        lines.append(
            "- HRV (RMSSD): "
            f"{float(current or 0):.1f} мс (7д {float(recent_avg or 0):.1f} мс, "
            f"база {float(baseline or 0):.1f} мс) — {trend_text}, {recovery_label}"
        )

    return "\n".join(lines)


def _describe_hrv_trend(direction: Optional[str]) -> str:
    mapping = {
        "improving": "тренд растёт",
        "declining": "тренд снижается",
        "stable": "тренд стабильный",
    }
    return mapping.get(direction, "тренд не определён")


def _describe_recovery_state(state: Optional[str]) -> str:
    mapping = {
        "excellent": "восстановление отличное",
        "good": "восстановление хорошее",
        "fair": "восстановление умеренное",
        "poor": "восстановление требует внимания",
    }
    return mapping.get(state, "восстановление под контролем")


def _format_sleep_section(sleep_data: Dict[str, Any]) -> str:
    """Формирует блок про сон."""
    stats = sleep_data.get("statistics", {})
    if not stats:
        return ""

    lines = ["### Сон"]

    avg_hours = stats.get("avg_sleep_hours")
    if avg_hours is not None:
        lines.append(f"- Средняя продолжительность: {avg_hours:.1f} ч")

    avg_score = stats.get("avg_sleep_score")
    if avg_score is not None:
        lines.append(f"- Средняя оценка: {avg_score:.0f}/100")

    avg_efficiency = stats.get("avg_sleep_efficiency")
    if avg_efficiency is not None:
        lines.append(f"- Эффективность: {avg_efficiency:.1f}%")

    lines.append(f"- Текущее качество: {stats.get('current_sleep_quality', 'н/д')}")

    return "\n".join(lines)


def _generate_progress_recommendations(
    compare_data: Optional[Dict[str, Any]],
    load_data: Optional[Dict[str, Any]],
    hrv_data: Optional[Dict[str, Any]],
    sleep_data: Optional[Dict[str, Any]],
) -> List[str]:
    """Создаёт список рекомендуемых действий на основе данных."""
    recs: List[str] = []

    if compare_data:
        comparison = compare_data.get("comparison", {}) or {}
        tss_change = comparison.get("tss_change")
        duration_change = comparison.get("volume_change")
        activity_change = comparison.get("activity_count_change")

        if isinstance(tss_change, (int, float)):
            if tss_change < -40:
                recs.append("Верни одну интервальную сессию средней интенсивности, чтобы остановить спад нагрузки.")
            elif tss_change > 60:
                recs.append("Сохраняй объём, но закладывай лёгкий день после тяжёлых тренировок — нагрузка растёт.")

        if isinstance(duration_change, (int, float)) and duration_change < -120:
            recs.append("Добавь длительную тренировку на выносливость (60–75 мин), чтобы подтянуть объём.")

        if isinstance(activity_change, (int, float)) and activity_change < 0:
            recs.append("Планируй минимум 5 качественных сессий в неделю, чтобы удержать частоту тренировок.")

    if load_data:
        weekly_breakdown = load_data.get("weekly_breakdown") or []
        avg_week_tss = (
            sum(float(week.get("total_tss", 0) or 0) for week in weekly_breakdown) / len(weekly_breakdown)
            if weekly_breakdown
            else 0.0
        )
        trend = (load_data.get("load_trend") or "").lower()
        intensity = load_data.get("intensity_distribution", {})

        if avg_week_tss > 380:
            recs.append("Нагрузка за месяц высокая — планируй день восстановления после каждой тяжёлой сессии.")
        elif avg_week_tss < 220 and (trend in ("снижение", "низкий") or "decreasing" in trend):
            recs.append("Добавь интервальную работу средней интенсивности, чтобы вернуть растущий тренд нагрузки.")

        high_intensity = intensity.get("high_intensity_percent")
        if isinstance(high_intensity, (int, float)) and high_intensity < 10 and avg_week_tss >= 250:
            recs.append("Увеличь долю высокоинтенсивных блоков до 12–15%, чтобы ускорить прогресс.")

    if hrv_data:
        current = hrv_data.get("current_rmssd")
        baseline = hrv_data.get("baseline_median")
        if isinstance(current, (int, float)) and isinstance(baseline, (int, float)) and baseline > 0:
            deviation = (current - baseline) / baseline * 100
            if deviation < -5:
                recs.append("HRV ниже базы — включи активное восстановление и удлини сон на 30–45 минут.")
            elif deviation > 8:
                recs.append("HRV стабильно высокий — можно добавить качественную интервальную работу.")

    if sleep_data and sleep_data.get("has_data"):
        stats = sleep_data.get("statistics", {})
        avg_hours = stats.get("avg_sleep_hours")
        if isinstance(avg_hours, (int, float)) and avg_hours < 7:
            recs.append("Повысь среднюю продолжительность сна до 7–7.5 ч, это ускорит восстановление.")

    unique_recs: List[str] = []
    seen = set()
    for rec in recs:
        if rec not in seen:
            unique_recs.append(rec)
            seen.add(rec)
        if len(unique_recs) >= 3:
            break

    if not unique_recs:
        unique_recs.append("Готов помочь составить персональный план — просто напомни, какие цели приоритетны.")

    return unique_recs


def _filter_progress_sections(text: str) -> str:
    """Удаляет инструментальные блоки, оставляя только прогресс и свободный текст."""
    if not text or not text.strip():
        return ""

    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    kept: List[str] = []

    for section in sections:
        stripped = section.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            if "прогресс" in stripped.lower():
                kept.append(stripped)
        else:
            kept.append(stripped)

    return "\n\n".join(kept).strip()
