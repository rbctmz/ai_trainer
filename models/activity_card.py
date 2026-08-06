"""Чистая модель карточки завершённой тренировки (шаг 1 из #379).

Не ходит в БД: берёт активность, список последних фидбеков и readiness
словарём и возвращает данные карточки и детерминированный Markdown-разбор.
ExecPlan: docs/activity_card_execplan.md.
"""
from __future__ import annotations

from typing import Any, Mapping


# Качество исполнения у нас хранится шкалой 1–5 (1–2 провал, 3 неоднозначно,
# 4–5 успех); бейдж A–E — это отображение той же шкалы для карточки.
GRADE_BY_QUALITY: dict[int, str] = {
    5: "A",
    4: "B",
    3: "C",
    2: "D",
    1: "E",
}

TSS_SOURCE_LABELS_RU: dict[str, str] = {
    "power": "мощность",
    "pace": "темп",
    "heart_rate": "пульс",
    "heuristic": "оценка",
    "none": "нет данных",
}


def grade_from_quality(quality: int | None) -> str | None:
    if quality is None:
        return None
    return GRADE_BY_QUALITY.get(int(quality))


def foster_load_au(rpe: int | None, duration_minutes: int | float | None) -> int | None:
    """Нагрузка по Фостеру: AU = sRPE × длительность (мин)."""
    if rpe is None or duration_minutes is None:
        return None
    return int(round(float(rpe) * float(duration_minutes)))


def feedback_for_activity(
    activity_id: str,
    latest_feedbacks: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Найти фидбек для активности по `actual_activity_ids` фидбека."""
    for row in latest_feedbacks or []:
        if str(row.get("status") or "") == "tombstone":
            continue
        actual_ids = row.get("actual_activity_ids") or []
        if str(activity_id) in {str(value) for value in actual_ids}:
            quality = row.get("quality_rating_1_5")
            return {
                "session_rpe_1_10": row.get("session_rpe_1_10"),
                "quality_rating_1_5": quality,
                "grade": grade_from_quality(quality),
                "note": row.get("note"),
                "submitted_at": row.get("submitted_at"),
            }
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_activity_analysis(
    activity: Mapping[str, Any],
    feedback: Mapping[str, Any] | None,
    readiness: Mapping[str, Any] | None,
) -> str:
    """Детерминированный Markdown-разбор из реальных чисел (без LLM)."""
    lines: list[str] = [
        "## Разбор тренировки",
        "",
    ]
    sport = _text(activity.get("sport_label")) or _text(activity.get("sport")) or "—"
    duration = activity.get("duration_minutes")
    distance = activity.get("distance_km")
    tss = activity.get("tss")
    tss_source = _text(activity.get("tss_source")) or "неизвестен"
    tss_method = _text(activity.get("tss_method")) or ""
    if tss_method.startswith("pace_tss_swim"):
        tss_source_label = "CSS-темп"
    else:
        tss_source_label = TSS_SOURCE_LABELS_RU.get(tss_source, tss_source)
    avg_hr = activity.get("avg_hr")
    max_hr = activity.get("max_hr")

    duration_text = (
        f"{int(round(float(duration)))} мин" if duration is not None else "—"
    )
    distance_text = f"{float(distance):.1f} км" if distance is not None else None
    lines.append(
        f"- Вид: {sport}; длительность: {duration_text}"
        + (f"; дистанция: {distance_text}" if distance_text else "")
    )
    if tss is not None:
        lines.append(f"- Нагрузка: {float(tss):.0f} TSS (источник: {tss_source_label})")
    else:
        lines.append(f"- Нагрузка: не рассчитана (источник: {tss_source_label})")
    hr_parts = []
    if avg_hr is not None:
        hr_parts.append(f"средний {float(avg_hr):.0f}")
    if max_hr is not None:
        hr_parts.append(f"макс {float(max_hr):.0f}")
    if hr_parts:
        lines.append(f"- Пульс: {', '.join(hr_parts)}")
    if feedback:
        rpe = feedback.get("session_rpe_1_10")
        quality = feedback.get("quality_rating_1_5")
        grade = feedback.get("grade") or grade_from_quality(quality)
        parts = []
        if rpe is not None:
            parts.append(f"RPE {int(rpe)}/10")
            au = foster_load_au(rpe, duration)
            if au is not None:
                lines.append(
                    f"- Нагрузка по Фостеру: {au} AU (RPE {int(rpe)} × {duration_text})"
                )
        if grade is not None:
            parts.append(f"grade {grade} (качество {int(quality)}/5)")
        if parts:
            lines.append(f"- Субъективная оценка: {'; '.join(parts)}")
        note = _text(feedback.get("note"))
        if note:
            lines.append(f"- Заметка атлета: {note}")
    if readiness and readiness.get("score") is not None:
        lines.append(
            f"- Готовность на дату: {int(round(float(readiness['score'])))}/100"
            f" ({readiness.get('status') or '—'})"
        )
    lines.append("")
    lines.append("_Авто-разбор по данным; за развёрнутый анализ можно спросить Coach+._")
    return "\n".join(lines)


__all__ = [
    "GRADE_BY_QUALITY",
    "build_activity_analysis",
    "feedback_for_activity",
    "foster_load_au",
    "grade_from_quality",
]
