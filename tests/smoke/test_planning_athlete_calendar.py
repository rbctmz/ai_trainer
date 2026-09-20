"""Календарный день атлета в планировщике — контракт issue #601.

`api/planning_service.py` решал календарный день атлета по host clock в шести
местах: начало недели, окно активных ограничений, `active_plan_overview`,
`as_of` для гоночных оверлеев в `build_plan`, `week_by_week_plan` и окно
восстановления в `_refresh_match_recovery`. Канонический хелпер
`utils.athlete_time.athlete_local_date()` (issue #577) в модуле уже импортирован,
но применён только к якорю метрик (#599).

При дефолтной конфигурации (`ATHLETE_TIMEZONE = Europe/Moscow` и хост в той же
зоне) дефект латентен, поэтому проверять его сравнением значений бесполезно:
тесты подменяют сам источник даты и смотрят, следует ли за ним поведение.

Отдельно: `datetime.now().isoformat()` на строках ревизии плана — это метки
времени, а не атлетские границы, и они обязаны остаться host-clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from api import planning_service as ps
from data.database import Database


pytestmark = pytest.mark.smoke


#: Решения об атлетском календарном дне, которых в модуле быть не должно.
_HOST_CLOCK_BOUNDARIES = ("datetime.now().date()", "date.today()")


def _monday(day):
    return day - timedelta(days=day.weekday())


def _athlete_day_is(monkeypatch, days: int):
    """Сдвинуть атлетский день относительно host clock на `days` суток."""
    shifted = datetime.now().date() + timedelta(days=days)
    monkeypatch.setattr(ps, "athlete_local_date", lambda *args, **kwargs: shifted)
    return shifted


def test_start_week_follows_athlete_calendar(monkeypatch) -> None:
    """AC1: начало недели — атлетский понедельник, а не хостовый.

    Сдвиг на сутки всегда меняет понедельник: для любого дня недели
    начало недели следующего дня отличается от начала текущей недели.
    """
    shifted = _athlete_day_is(monkeypatch, 1)
    host_monday = _monday(datetime.now().date())

    assert ps._start_week() == _monday(shifted), (
        "_start_week не взял атлетский день: "
        f"{ps._start_week()} вместо {_monday(shifted)}"
    )
    assert ps._start_week() != host_monday


def test_current_status_constraint_window_follows_athlete_calendar(
    monkeypatch, tmp_path
) -> None:
    """AC1: окно активных ограничений отсчитывается от атлетского дня."""
    shifted = _athlete_day_is(monkeypatch, 1)
    db = Database(str(tmp_path / "calendar.db"))

    with mock.patch.object(
        db, "get_coach_constraints", wraps=db.get_coach_constraints
    ) as spy:
        ps.current_status(db)

    assert spy.called, "current_status перестал запрашивать активные ограничения"
    window_start = spy.call_args.kwargs.get("start_date")
    assert window_start == shifted.isoformat(), (
        f"окно ограничений начинается с {window_start}, "
        f"а атлетский день — {shifted.isoformat()}"
    )


def test_no_host_clock_athlete_boundaries_remain() -> None:
    """AC2: в модуле не остаётся решений об атлетском дне по host clock.

    Это прямая формулировка acceptance criteria #601: смешение двух источников
    «сегодня» в одном файле — гарантированная будущая ошибка при правке рядом.
    """
    source = Path(ps.__file__).read_text(encoding="utf-8")
    offenders = [
        f"  {number}: {line.strip()}"
        for number, line in enumerate(source.splitlines(), start=1)
        if any(pattern in line for pattern in _HOST_CLOCK_BOUNDARIES)
    ]

    assert offenders == [], (
        "атлетский календарный день решается по host clock:\n"
        + "\n".join(offenders)
    )


def test_matching_timezones_keep_behavior(monkeypatch) -> None:
    """AC4: при совпадении зон хоста и атлета поведение не меняется."""
    host_today = datetime.now().date()
    monkeypatch.setattr(ps, "athlete_local_date", lambda *args, **kwargs: host_today)

    assert ps._start_week() == _monday(host_today)
    assert ps._start_week(host_today) == _monday(host_today)
