"""Shared briefing-frequency setting: daily vs conflicts-only /today rendering.

Issue #235: the athlete can silence the full morning briefing on days the
salience gate has nothing to say. The setting lives in the existing generic
``user_settings`` key/value table (see ``data/database.py::get_user_setting``/
``set_user_setting``) — no new table.
"""
from __future__ import annotations

from typing import Any, Mapping

BRIEFING_FREQUENCY_KEY = "briefing_frequency"
DAILY = "daily"
CONFLICTS_ONLY = "conflicts_only"
VALID_FREQUENCIES = (DAILY, CONFLICTS_ONLY)
DEFAULT_FREQUENCY = DAILY


def get_briefing_frequency(db: Any) -> str:
    """Read the persisted frequency, defaulting to ``daily`` for any unset
    or unrecognised stored value — a stale/corrupt setting must never hide
    a briefing."""
    value = db.get_user_setting(BRIEFING_FREQUENCY_KEY, DEFAULT_FREQUENCY)
    return value if value in VALID_FREQUENCIES else DEFAULT_FREQUENCY


def set_briefing_frequency(db: Any, frequency: str) -> str:
    if frequency not in VALID_FREQUENCIES:
        raise ValueError(f"invalid briefing frequency: {frequency!r}")
    db.set_user_setting(BRIEFING_FREQUENCY_KEY, frequency)
    return frequency


def is_quiet_day(gate: Mapping[str, Any], active_proposal: Any) -> bool:
    """Conservative "nothing to say" check off the already-built payload
    (``gate`` + the resolved active proposal) — no extra queries.

    A false negative (showing the full brief on a quiet day) is cheap; a
    hidden conflict is not — so any doubt keeps the full brief.
    """
    gate_is_quiet = bool(gate.get("silence")) or bool(gate.get("data_gap"))
    no_pending_proposal = active_proposal is None
    no_open_conflict = not gate.get("conflicts")
    return gate_is_quiet and no_pending_proposal and no_open_conflict


__all__ = [
    "BRIEFING_FREQUENCY_KEY",
    "DAILY",
    "CONFLICTS_ONLY",
    "VALID_FREQUENCIES",
    "DEFAULT_FREQUENCY",
    "get_briefing_frequency",
    "set_briefing_frequency",
    "is_quiet_day",
]
