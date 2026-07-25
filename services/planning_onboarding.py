"""Онбординг планирования: предложение вместо выдумывания (#271, M2 §5).

Раньше первый вход на `/planning` стартовал с констант: 10 часов, все семь дней,
режим `event_goal` и дата события «сегодня + 56 дней». Последнее — не дефолт, а
молчаливая выдумка: атлет без гонки получал план с тейпером под несуществующее
событие и никакого сигнала об этом.

Здесь собраны две функции, которые это заменяют:

* :func:`suggest_planning_defaults` — предложение, выведенное из истории самого
  атлета. Каждое поле несёт ``basis``: ``derived`` (посчитано по данным) или
  ``fallback`` (данных не хватило). UI обязан показывать basis — атлет должен
  видеть, что система знает, а что домыслила.
* :func:`resolve_event_context` — честный резолвер A-гонки. Нет подтверждённой
  A-гонки — предлагается `training_goal`; недоступный Intervals — поток
  продолжается с видимой причиной. Дата события не подставляется НИКОГДА.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Mapping, Optional

import pandas as pd

from services.intervals_icu import IntervalsICUError
from services.planning_contracts import MAX_AVAILABLE_HOURS, MIN_AVAILABLE_HOURS
from services.planning_events import discover_intervals_events

# Окно, по которому считаем недельный объём и рабочие дни.
HISTORY_WINDOW_DAYS = 28
# Меньше двух недель истории — выводить недельный ритм не из чего: два-три заезда
# после установки приложения не описывают неделю атлета (§9 риск).
MIN_TRUSTED_HISTORY_DAYS = 14
EVENT_DISCOVERY_DAYS = 365

BASIS_DERIVED = "derived"
BASIS_FALLBACK = "fallback"

FALLBACK_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FALLBACK_HOURS = 10.0
FALLBACK_GOAL_TYPE = "triathlon"
FALLBACK_DISTANCE = "olympic"
FALLBACK_HORIZON_WEEKS = 8

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Канонический спорт активности → цель планирования (+ дистанция по умолчанию для неё).
_SPORT_TO_GOAL = {
    "cycling": "bike",
    "bike": "bike",
    "ride": "bike",
    "вело": "bike",
    "running": "run",
    "run": "run",
    "бег": "run",
    "swimming": "swim",
    "swim": "swim",
    "плавание": "swim",
}
_GOAL_DEFAULT_DISTANCE = {
    "bike": "100k",
    "run": "half_marathon",
    "triathlon": "olympic",
}


def _suggestion(value: Any, basis: str) -> Dict[str, Any]:
    return {"value": value, "basis": basis}


def _history(db: Any) -> pd.DataFrame:
    try:
        frame = db.get_activities(HISTORY_WINDOW_DAYS)
    except Exception:
        return pd.DataFrame()
    if frame is None or getattr(frame, "empty", True):
        return pd.DataFrame()
    if "date" not in frame:
        return pd.DataFrame()
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.dropna(subset=["date"])


def _history_is_trusted(frame: pd.DataFrame) -> bool:
    """История считается описывающей ритм, если она покрывает ≥2 недель."""
    if frame.empty:
        return False
    span_days = (frame["date"].max() - frame["date"].min()).days + 1
    return span_days >= MIN_TRUSTED_HISTORY_DAYS


def _suggest_days(frame: pd.DataFrame, trusted: bool) -> Dict[str, Any]:
    if not trusted:
        return _suggestion(list(FALLBACK_DAYS), BASIS_FALLBACK)
    used = {_WEEKDAY_KEYS[int(weekday)] for weekday in frame["date"].dt.weekday.tolist()}
    days = [day for day in _WEEKDAY_KEYS if day in used]
    return _suggestion(days, BASIS_DERIVED) if days else _suggestion(list(FALLBACK_DAYS), BASIS_FALLBACK)


def _suggest_hours(frame: pd.DataFrame, trusted: bool) -> Dict[str, Any]:
    if not trusted or "duration_minutes" not in frame:
        return _suggestion(FALLBACK_HOURS, BASIS_FALLBACK)
    minutes = pd.to_numeric(frame["duration_minutes"], errors="coerce").fillna(0.0)
    if minutes.sum() <= 0:
        return _suggestion(FALLBACK_HOURS, BASIS_FALLBACK)
    # Медиана недельной суммы, а не среднее: одна гонка или один пропуск не должны
    # задавать доступное время на весь план.
    weekly = minutes.groupby(frame["date"].dt.to_period("W")).sum() / 60.0
    hours = float(weekly.median())
    if hours <= 0:
        return _suggestion(FALLBACK_HOURS, BASIS_FALLBACK)
    rounded = round(hours * 2) / 2
    clamped = max(MIN_AVAILABLE_HOURS, min(MAX_AVAILABLE_HOURS, rounded))
    return _suggestion(clamped, BASIS_DERIVED)


def _suggest_goal(frame: pd.DataFrame, trusted: bool) -> tuple[Dict[str, Any], Dict[str, Any]]:
    if not trusted or "sport" not in frame:
        return (
            _suggestion(FALLBACK_GOAL_TYPE, BASIS_FALLBACK),
            _suggestion(FALLBACK_DISTANCE, BASIS_FALLBACK),
        )

    disciplines = {
        _SPORT_TO_GOAL.get(str(sport or "").strip().lower())
        for sport in frame["sport"].tolist()
    }
    disciplines.discard(None)
    if not disciplines:
        return (
            _suggestion(FALLBACK_GOAL_TYPE, BASIS_FALLBACK),
            _suggestion(FALLBACK_DISTANCE, BASIS_FALLBACK),
        )

    # Три дисциплины (или две с плаванием) — это триатлет; одна — моноспорт.
    if len(disciplines) >= 3 or ("swim" in disciplines and len(disciplines) >= 2):
        goal_type = "triathlon"
    elif disciplines == {"swim"}:
        # Чистое плавание целью планирования у нас не является — честнее fallback.
        return (
            _suggestion(FALLBACK_GOAL_TYPE, BASIS_FALLBACK),
            _suggestion(FALLBACK_DISTANCE, BASIS_FALLBACK),
        )
    else:
        counts = {
            discipline: sum(
                1
                for sport in frame["sport"].tolist()
                if _SPORT_TO_GOAL.get(str(sport or "").strip().lower()) == discipline
            )
            for discipline in disciplines
        }
        goal_type = max(counts, key=lambda key: counts[key])
        if goal_type == "swim":
            return (
                _suggestion(FALLBACK_GOAL_TYPE, BASIS_FALLBACK),
                _suggestion(FALLBACK_DISTANCE, BASIS_FALLBACK),
            )

    distance = _GOAL_DEFAULT_DISTANCE.get(goal_type, FALLBACK_DISTANCE)
    # Дистанция — это выбор цели, а не факт истории: спорт выведен, дистанция нет.
    return _suggestion(goal_type, BASIS_DERIVED), _suggestion(distance, BASIS_FALLBACK)


def resolve_event_context(
    *, days: int = EVENT_DISCOVERY_DAYS, today: Optional[date] = None
) -> Dict[str, Any]:
    """Что известно о гонках атлета — без единой подставленной даты.

    ``has_a_race`` — есть ли ПОДТВЕРЖДЁННАЯ A-гонка (`confirmed is not False`: та же
    семантика, что уже применяет UI). Отсутствие гонок — нормальный сценарий, а не
    деградация: ``degraded_reason`` остаётся ``None``. Недоступный или ненастроенный
    Intervals — деградация: причина видна, но поток онбординга продолжается.
    """
    try:
        discovered = discover_intervals_events(days=days, today=today) or {}
        events = list(discovered.get("events") or [])
        degraded_reason = None
    except IntervalsICUError as exc:
        events = []
        degraded_reason = str(exc)

    a_races = [
        event
        for event in events
        if isinstance(event, Mapping)
        and str(event.get("priority") or "").strip().upper() == "A"
        and event.get("confirmed") is not False
    ]

    return {
        "has_a_race": bool(a_races),
        "events": events,
        "a_races": a_races,
        "source": "intervals_icu",
        "degraded_reason": degraded_reason,
    }


def suggest_planning_defaults(
    db: Any, *, today: Optional[date] = None, event_context: Optional[Mapping[str, Any]] = None
) -> Dict[str, Dict[str, Any]]:
    """Предложение параметров планирования с честным ``basis`` на каждом поле."""
    frame = _history(db)
    trusted = _history_is_trusted(frame)
    context = (
        dict(event_context)
        if event_context is not None
        else resolve_event_context(today=today)
    )

    goal_type, distance = _suggest_goal(frame, trusted)
    has_a_race = bool(context.get("has_a_race"))

    return {
        "planning_mode": _suggestion(
            "event_goal" if has_a_race else "training_goal",
            # `training_goal` без данных о гонках (Intervals молчит) — это выбор по
            # умолчанию, а не вывод: помечаем fallback, чтобы UI не выдавал догадку
            # за знание.
            BASIS_DERIVED if (has_a_race or context.get("degraded_reason") is None) else BASIS_FALLBACK,
        ),
        "intent": _suggestion("develop", BASIS_FALLBACK),
        "goal_type": goal_type,
        "distance": distance,
        "available_hours": _suggest_hours(frame, trusted),
        "available_days": _suggest_days(frame, trusted),
        "horizon_weeks": _suggestion(FALLBACK_HORIZON_WEEKS, BASIS_FALLBACK),
    }


__all__ = [
    "BASIS_DERIVED",
    "BASIS_FALLBACK",
    "EVENT_DISCOVERY_DAYS",
    "HISTORY_WINDOW_DAYS",
    "MIN_TRUSTED_HISTORY_DAYS",
    "resolve_event_context",
    "suggest_planning_defaults",
]
