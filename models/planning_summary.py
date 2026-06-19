"""Shared summaries for planning-specific product signals."""
from __future__ import annotations

from typing import Any, Dict

NEAR_TERM_EDIT_POST_STRATEGIES = (
    "keep",
    "catch_up",
    "protect_recovery",
)
NEAR_TERM_EDIT_RISK_LEVELS = (
    "low",
    "medium",
    "high",
)
NEAR_TERM_EDIT_RISK_FOCUSES = (
    "balanced",
    "overload",
    "underload",
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


def normalize_near_term_edit_risk_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level in NEAR_TERM_EDIT_RISK_LEVELS:
        return level
    return "low"


def normalize_near_term_edit_risk_focus(value: Any) -> str:
    focus = str(value or "").strip().lower()
    if focus in NEAR_TERM_EDIT_RISK_FOCUSES:
        return focus
    return "balanced"


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


def _normalize_reason_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


def _build_risk_summary(
    raw: Dict[str, Any],
    total_delta_tss: int,
) -> Dict[str, Any]:
    level = normalize_near_term_edit_risk_level(raw.get("risk_level"))
    focus = normalize_near_term_edit_risk_focus(raw.get("risk_focus"))
    reasons = _normalize_reason_list(raw.get("risk_reasons"))
    guardrail = str(raw.get("risk_guardrail") or "").strip()

    if not reasons:
        if total_delta_tss < 0:
            reasons = ["правка разгружает ближайшее окно без агрессивной компенсации"]
        elif total_delta_tss > 0:
            reasons = ["объём в ближайшем окне изменён умеренно и остаётся контролируемым"]
        else:
            reasons = ["структура ближайшего окна меняется без заметного сдвига по объёму"]

    if level == "low":
        badge = "Риск низкий"
    elif focus == "underload":
        badge = "Высокий риск просадки ритма" if level == "high" else "Риск просадки ритма"
    else:
        badge = "Высокий риск перегруза" if level == "high" else "Повышенный риск перегруза"

    if not guardrail:
        if level == "low":
            guardrail = "После применения просто сверяйте самочувствие и не компенсируйте следующий день автоматически."
        elif focus == "underload":
            guardrail = "Если это не вынужденная разгрузка, верните один качественный стимул позже вместо резкого отката к пику."
        else:
            guardrail = "Сохраните явный лёгкий день и не компенсируйте усталость дополнительной интенсивностью."

    description = f"{badge}: {'; '.join(reasons[:3])}."
    return {
        "level": level,
        "focus": focus,
        "badge": badge,
        "reasons": reasons,
        "guardrail": guardrail,
        "description": description,
    }


def _build_near_term_edit_origin(raw: Dict[str, Any]) -> Dict[str, Any]:
    origin_kind = str(raw.get("origin_kind") or "").strip().lower()
    origin_checkpoint_id = _int_or_zero(raw.get("origin_checkpoint_id"))
    origin_checkpoint_source = str(raw.get("origin_checkpoint_source") or "").strip()
    origin_plan_adjustment_label = str(raw.get("origin_plan_adjustment_label") or "").strip()
    origin_weekly_review_headline = str(raw.get("origin_weekly_review_headline") or "").strip()
    origin_microcycle_headline = str(raw.get("origin_microcycle_headline") or "").strip()

    if origin_kind != "execution_microcycle_override":
        return {
            "kind": origin_kind,
            "checkpoint_id": origin_checkpoint_id,
            "checkpoint_source": origin_checkpoint_source,
            "plan_adjustment_label": origin_plan_adjustment_label,
            "weekly_review_headline": origin_weekly_review_headline,
            "microcycle_headline": origin_microcycle_headline,
            "label": "",
            "description": "",
            "is_execution_microcycle_override": False,
        }

    label = "Override после execution microcycle"
    if origin_checkpoint_id > 0:
        label += f" из checkpoint #{origin_checkpoint_id}"

    details = [
        item
        for item in [
            origin_plan_adjustment_label,
            origin_weekly_review_headline,
            origin_microcycle_headline,
        ]
        if item
    ]
    description = f"{label}: {' · '.join(details)}" if details else label

    return {
        "kind": origin_kind,
        "checkpoint_id": origin_checkpoint_id,
        "checkpoint_source": origin_checkpoint_source,
        "plan_adjustment_label": origin_plan_adjustment_label,
        "weekly_review_headline": origin_weekly_review_headline,
        "microcycle_headline": origin_microcycle_headline,
        "label": label,
        "description": description,
        "is_execution_microcycle_override": True,
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
    risk = _build_risk_summary(raw, total_delta_tss)
    origin = _build_near_term_edit_origin(raw)
    compact_label = f"{edited_day_count} дн. / {horizon_days} дн. · Δ {total_delta_tss:+d} TSS"
    if post_edit_strategy != "keep":
        compact_label += f" · {follow_up['follow_up_compact_label']}"
    if risk["level"] != "low":
        compact_label += f" · {risk['badge']}"

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
        "risk_level": risk["level"],
        "risk_focus": risk["focus"],
        "risk_badge": risk["badge"],
        "risk_reasons": risk["reasons"],
        "risk_guardrail": risk["guardrail"],
        "risk_description": risk["description"],
        "origin_kind": origin["kind"],
        "origin_checkpoint_id": origin["checkpoint_id"],
        "origin_checkpoint_source": origin["checkpoint_source"],
        "origin_plan_adjustment_label": origin["plan_adjustment_label"],
        "origin_weekly_review_headline": origin["weekly_review_headline"],
        "origin_microcycle_headline": origin["microcycle_headline"],
        "origin_label": origin["label"],
        "origin_description": origin["description"],
        "is_execution_microcycle_override": origin["is_execution_microcycle_override"],
        "compact_label": compact_label,
        "description": (
            f"{edited_day_count} дн. в ближайших {horizon_days} дн., "
            f"Δ {total_delta_tss:+d} TSS; {follow_up['follow_up_description']}; "
            f"{risk['description']}"
        ),
    }


__all__ = [
    "NEAR_TERM_EDIT_POST_STRATEGIES",
    "NEAR_TERM_EDIT_POST_STRATEGY_LABELS_RU",
    "NEAR_TERM_EDIT_RISK_FOCUSES",
    "NEAR_TERM_EDIT_RISK_LEVELS",
    "normalize_near_term_edit_risk_focus",
    "normalize_near_term_edit_risk_level",
    "normalize_near_term_edit_post_strategy",
    "summarize_near_term_edit",
]
