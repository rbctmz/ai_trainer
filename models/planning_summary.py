"""Shared summaries for planning-specific product signals."""
from __future__ import annotations

from typing import Any, Dict


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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

    if not is_active or edited_day_count <= 0 or horizon_days <= 0:
        return None

    return {
        "is_active": True,
        "label": label,
        "edited_day_count": edited_day_count,
        "horizon_days": horizon_days,
        "total_delta_tss": total_delta_tss,
        "delta_label": f"Δ {total_delta_tss:+d} TSS",
        "compact_label": f"{edited_day_count} дн. / {horizon_days} дн. · Δ {total_delta_tss:+d} TSS",
        "description": (
            f"{edited_day_count} дн. в ближайших {horizon_days} дн., "
            f"Δ {total_delta_tss:+d} TSS"
        ),
    }


__all__ = ["summarize_near_term_edit"]
