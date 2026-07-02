"""Deterministic coach decision audit helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DecisionType = Literal["Push", "Moderate", "Recovery", "Monitor"]


@dataclass(frozen=True)
class CoachDecision:
    decision_type: DecisionType
    reason: str
    workout_id: str | None = None


def build_coach_decision(final_response: str, db: Any | None = None) -> CoachDecision:
    """Classify the final coach synthesis into a small auditable decision."""
    metrics = _performance_metrics(db)
    tsb = _num(metrics.get("tsb")) if metrics else None
    readiness = _latest_readiness(db)

    if tsb is not None:
        if tsb <= -20:
            return CoachDecision(
                "Recovery",
                _one_line(f"TSB {tsb:+.1f}: восстановление сегодня приоритетнее интенсивности."),
            )
        if tsb <= -8:
            return CoachDecision(
                "Moderate",
                _one_line(f"TSB {tsb:+.1f}: держите нагрузку контролируемой без агрессивной интенсивности."),
            )
        if tsb >= 5 and (readiness is None or readiness >= 55):
            return CoachDecision(
                "Push",
                _one_line(f"TSB {tsb:+.1f}: можно выполнить качественную работу по плану."),
            )

    text = (final_response or "").lower()
    if _has_any(text, ("восстанов", "отдых", "разгруз", "сниз", "уменьш", "устал", "перетрен")):
        return CoachDecision(
            "Recovery",
            "Ответ коуча ставит восстановление и снижение нагрузки выше интенсивности.",
        )
    if _has_any(text, ("умерен", "контрол", "осторож", "лёгк", "легк", "без интенсив")):
        return CoachDecision(
            "Moderate",
            "Ответ коуча рекомендует контролируемую умеренную нагрузку.",
        )
    if _has_any(text, ("интервал", "темпов", "качествен", "увелич", "повыс", "готов")):
        return CoachDecision(
            "Push",
            "Ответ коуча разрешает качественную работу или прогресс нагрузки.",
        )

    return CoachDecision(
        "Monitor",
        "Недостаточно сильного сигнала для изменения нагрузки.",
    )


def _performance_metrics(db: Any | None) -> dict[str, Any]:
    if db is None:
        return {}
    try:
        from models.ai_tools import AITools

        metrics = AITools(db).get_performance_metrics(days=90)
    except Exception:
        return {}
    return metrics if isinstance(metrics, dict) and "tsb" in metrics else {}


def _latest_readiness(db: Any | None) -> float | None:
    if db is None or not hasattr(db, "get_training_status"):
        return None
    try:
        frame = db.get_training_status(days=14)
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True) or "training_readiness" not in frame:
        return None
    for value in frame["training_readiness"]:
        parsed = _num(value)
        if parsed is not None:
            return parsed
    return None


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _one_line(text: str, max_len: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"
