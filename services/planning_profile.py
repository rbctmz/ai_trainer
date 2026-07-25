"""Профиль планирования атлета — персистентные входы для `build_plan` (#271, M2).

До M2 режим/цель/дистанция/часы/дни жили только в React-стейте `/planning`, и каждый
вход начинался с констант. Профиль делает эти входы явными, валидируемыми и общими для
формы, онбординга и будущих потребителей (коуч, M3-handoff).

Хранение — один JSON-документ под ключом ``planning_profile`` в существующей таблице
``user_settings`` (ADR не требуется: схема БД не меняется, rollback = удалить ключ).

Два правила, которые здесь важнее краткости:

1. **Whitelist'ы не дублируются.** Режим/намерение/цель/дистанция/дни читаются из
   :mod:`services.planning_contracts`. Профиль не должен
   уметь сохранить то, что планировщик потом отвергнет.
2. **Чтение fail-closed.** Битый JSON, чужая форма или значение, ставшее невалидным
   после изменения whitelist'а, читаются как «профиля нет» (``completed=false``), а не
   роняют страницу и не предзаполняют форму мусором.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from services.planning_contracts import (
    DAY_MAP,
    DISTANCE_MAP,
    GOAL_TYPE_MAP,
    MAX_AVAILABLE_HOURS,
    MAX_HORIZON_WEEKS,
    MIN_AVAILABLE_HOURS,
    MIN_HORIZON_WEEKS,
    PLANNING_INTENTS,
    PLANNING_MODES,
)

PLANNING_PROFILE_SETTING_KEY = "planning_profile"

PROFILE_SOURCES = ("onboarding", "planning_form")
DEFAULT_PROFILE_SOURCE = "onboarding"

_DAY_ORDER = list(DAY_MAP.keys())

_REQUIRED_FIELDS = (
    "planning_mode",
    "intent",
    "goal_type",
    "distance",
    "available_hours",
    "available_days",
    "horizon_weeks",
)


def _choice(value: Any, allowed, field: str) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(allowed)}")
    return text


def _hours(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("available_hours must be a number")
    try:
        hours = float(value)
    except (TypeError, ValueError):
        raise ValueError("available_hours must be a number")
    if hours != hours or hours in (float("inf"), float("-inf")):  # NaN/inf
        raise ValueError("available_hours must be a finite number")
    if not (MIN_AVAILABLE_HOURS <= hours <= MAX_AVAILABLE_HOURS):
        raise ValueError(
            f"available_hours must be between {MIN_AVAILABLE_HOURS} and {MAX_AVAILABLE_HOURS}"
        )
    return round(hours, 2)


def _days(value: Any) -> List[str]:
    # Строка — частая ошибка клиента ("mon,wed"): молча принять её значило бы
    # разложить её на буквы, поэтому отвергаем явно.
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
        raise ValueError("available_days must be a list of weekday keys")
    days = {str(item or "").strip().lower() for item in value}
    unknown = sorted(day for day in days if day not in DAY_MAP)
    if unknown:
        raise ValueError(f"available_days contains unknown weekday(s): {', '.join(unknown)}")
    if not days:
        raise ValueError("available_days must not be empty")
    return [day for day in _DAY_ORDER if day in days]


def _horizon(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("horizon_weeks must be an integer")
    if isinstance(value, int):
        weeks = value
    elif isinstance(value, str) and value.isdigit():
        weeks = int(value)
    else:
        raise ValueError("horizon_weeks must be an integer")
    if not (MIN_HORIZON_WEEKS <= weeks <= MAX_HORIZON_WEEKS):
        raise ValueError(
            f"horizon_weeks must be between {MIN_HORIZON_WEEKS} and {MAX_HORIZON_WEEKS}"
        )
    return weeks


def normalize_profile(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Провалидировать и канонизировать профиль. Бросает ``ValueError`` (→ 422)."""
    if not isinstance(payload, Mapping):
        raise ValueError("planning profile must be an object")

    missing = [field for field in _REQUIRED_FIELDS if payload.get(field) is None]
    if missing:
        raise ValueError(f"planning profile is missing required field(s): {', '.join(missing)}")

    return {
        "planning_mode": _choice(payload.get("planning_mode"), PLANNING_MODES, "planning_mode"),
        "intent": _choice(payload.get("intent"), PLANNING_INTENTS, "intent"),
        "goal_type": _choice(payload.get("goal_type"), GOAL_TYPE_MAP, "goal_type"),
        "distance": _choice(payload.get("distance"), DISTANCE_MAP, "distance"),
        "available_hours": _hours(payload.get("available_hours")),
        "available_days": _days(payload.get("available_days")),
        "horizon_weeks": _horizon(payload.get("horizon_weeks")),
        "source": _choice(
            payload.get("source") or DEFAULT_PROFILE_SOURCE, PROFILE_SOURCES, "source"
        ),
    }


def load_profile(db: Any) -> Optional[Dict[str, Any]]:
    """Сохранённый профиль или ``None``, если его нет / он больше не валиден."""
    try:
        raw = db.get_user_setting(PLANNING_PROFILE_SETTING_KEY)
    except Exception:
        return None
    if not raw:
        return None
    try:
        stored = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(stored, Mapping):
        return None
    try:
        profile = normalize_profile(stored)
    except ValueError:
        # Профиль записан старой версией и не проходит текущий whitelist: честнее
        # показать «онбординг не пройден», чем предзаполнить форму мусором.
        return None
    profile["updated_at"] = str(stored.get("updated_at") or "")
    return profile


def save_profile(db: Any, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Провалидировать и записать профиль. Невалидный вход не трогает сохранённое."""
    profile = normalize_profile(payload)
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
    db.set_user_setting(PLANNING_PROFILE_SETTING_KEY, json.dumps(profile, ensure_ascii=False))
    return profile


def profile_status(db: Any) -> Dict[str, Any]:
    """``{"completed": bool, "profile": dict|None}`` — форма ответа онбординга."""
    profile = load_profile(db)
    return {"completed": profile is not None, "profile": profile}


__all__ = [
    "DEFAULT_PROFILE_SOURCE",
    "MAX_AVAILABLE_HOURS",
    "MAX_HORIZON_WEEKS",
    "MIN_AVAILABLE_HOURS",
    "MIN_HORIZON_WEEKS",
    "PLANNING_PROFILE_SETTING_KEY",
    "PROFILE_SOURCES",
    "load_profile",
    "normalize_profile",
    "profile_status",
    "save_profile",
]
