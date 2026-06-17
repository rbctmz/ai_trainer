"""Shared summaries for planning-specific product signals."""
from __future__ import annotations

from typing import Any, Dict

NEAR_TERM_EDIT_POST_STRATEGIES = (
    "keep",
    "catch_up",
    "protect_recovery",
)
NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU = {
    "keep": "Оставить как есть",
    "catch_up": "Наверстать аккуратно",
    "protect_recovery": "Беречь восстановление",
}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_near_term_edit_post_strategy(value: Any) -> str:
    strategy = str(value or "").strip().lower()
    if strategy in NEAR_TERM_EDIT_POST_STRATEGIES:
        return strategy
    return "keep"


def _build_follow_up_summary(
    strategy: str,
    total_delta_tss: int,
    future_delta_tss: int,
    future_target_tss: int,
    future_weeks: int,
    future_week_count: int,
) -> Dict[str, str]:
    strategy_label = NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU[strategy]
    future_delta_label = f"{future_delta_tss:+d} TSS"
    if future_weeks <= 0:
        future_weeks = 2

    if strategy == "keep":
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": "без автокоррекции следующих недель",
            "follow_up_description": "следующие 1-2 недели не меняются автоматически",
        }

    if total_delta_tss < 0 and future_delta_tss > 0:
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": f"{strategy_label}: {future_delta_label}",
            "follow_up_description": (
                f"дальше «{strategy_label}»: +{future_delta_tss} TSS "
                f"в следующих {future_week_count or future_weeks} нед."
            ),
        }

    if total_delta_tss > 0 and future_delta_tss < 0:
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": f"{strategy_label}: {future_delta_label}",
            "follow_up_description": (
                f"дальше «{strategy_label}»: {future_delta_label} "
                f"в следующих {future_week_count or future_weeks} нед."
            ),
        }

    if total_delta_tss < 0 and strategy == "protect_recovery":
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": strategy_label,
            "follow_up_description": "дальше «Беречь восстановление»: снятый объём не догоняется автоматически",
        }

    if total_delta_tss > 0 and strategy == "catch_up":
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": strategy_label,
            "follow_up_description": "дальше «Наверстать аккуратно»: добавленный объём пока не перераспределяется автоматически",
        }

    if abs(future_target_tss) > 0:
        return {
            "strategy_label": strategy_label,
            "future_delta_label": future_delta_label,
            "follow_up_compact_label": strategy_label,
            "follow_up_description": f"дальше «{strategy_label}»: безопасного окна для автокоррекции не нашлось",
        }

    return {
        "strategy_label": strategy_label,
        "future_delta_label": future_delta_label,
        "follow_up_compact_label": strategy_label,
        "follow_up_description": f"дальше «{strategy_label}»: автокоррекция не потребовалась",
    }


def summarize_near_term_edit(constraint_summary: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Normalize the persisted/manual near-term edit signal for UI and explainability."""
    if not isinstance(constraint_summary, dict):
        return None

    raw = constraint_summary.get("near_term_edit")
    if not isinstance(raw, dict):
        return None

    is_active = bool(raw.get("is_active"))
    edited_day_count = _int_or_zero(raw.get("edited_day_count"))
    horizon_days = _int_or_zero(raw.get("horizon_days"))
    total_delta_tss = _int_or_zero(raw.get("total_delta_tss"))
    label = str(raw.get("label") or "Ручная правка ближнего горизонта").strip()
    post_edit_strategy = normalize_near_term_edit_post_strategy(raw.get("post_edit_strategy"))
    future_delta_tss = _int_or_zero(raw.get("future_delta_tss"))
    future_target_tss = _int_or_zero(raw.get("future_target_tss"))
    future_weeks = _int_or_zero(raw.get("future_weeks"))
    future_week_count = _int_or_zero(raw.get("future_week_count"))

    if not is_active or edited_day_count <= 0 or horizon_days <= 0:
        return None

    follow_up = _build_follow_up_summary(
        post_edit_strategy,
        total_delta_tss,
        future_delta_tss,
        future_target_tss,
        future_weeks,
        future_week_count,
    )
    compact_label = f"{edited_day_count} дн. / {horizon_days} дн. · Δ {total_delta_tss:+d} TSS"
    if post_edit_strategy != "keep":
        compact_label += f" · {follow_up['follow_up_compact_label']}"

    return {
        "is_active": True,
        "label": label,
        "edited_day_count": edited_day_count,
        "horizon_days": horizon_days,
        "total_delta_tss": total_delta_tss,
        "post_edit_strategy": post_edit_strategy,
        "strategy_label": follow_up["strategy_label"],
        "future_delta_tss": future_delta_tss,
        "future_target_tss": future_target_tss,
        "future_weeks": future_weeks,
        "future_week_count": future_week_count,
        "delta_label": f"Δ {total_delta_tss:+d} TSS",
        "future_delta_label": follow_up["future_delta_label"],
        "follow_up_compact_label": follow_up["follow_up_compact_label"],
        "follow_up_description": follow_up["follow_up_description"],
        "compact_label": compact_label,
        "description": (
            f"{edited_day_count} дн. в ближайших {horizon_days} дн., "
            f"Δ {total_delta_tss:+d} TSS; {follow_up['follow_up_description']}"
        ),
    }


__all__ = [
    "NEAR_TERM_EDIT_POST_STRATEGIES",
    "NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU",
    "normalize_near_term_edit_post_strategy",
    "summarize_near_term_edit",
]
