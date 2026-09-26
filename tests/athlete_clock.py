"""Общий якорь времени для тестов: часы атлета, а не раннера (#663).

Продукт anchored на локальную дату атлета (`Settings.ATHLETE_TIMEZONE`,
по умолчанию `Europe/Moscow`), а тесты исторически строили фикстуры от
`date.today()`/`datetime.now()` — то есть от часов машины. На CI-раннере в UTC
это расходилось на сутки каждую ночь после 21:00 UTC, и обязательная проверка
падала на 24 тестах.

Правило: фикстура, которая изображает «сегодня» продукта, обязана брать дату из
этого модуля. Если тесту нужна именно машинная дата (проверка таймзонного
поведения), он обязан сказать это явно и не через `date.today()`.
"""
from __future__ import annotations

from datetime import date, datetime

from utils.athlete_time import athlete_local_date, athlete_zone


def athlete_today() -> date:
    """Сегодняшняя дата в зоне атлета — то же, что видит продукт."""
    return athlete_local_date()


def athlete_now() -> datetime:
    """Наивный datetime в зоне атлета: замена `datetime.now()` в фикстурах."""
    return datetime.now(athlete_zone()).replace(tzinfo=None)


__all__ = ["athlete_now", "athlete_today"]
