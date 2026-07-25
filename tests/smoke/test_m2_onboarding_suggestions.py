"""M2 гейты «предложение вместо выдумывания» (#271 §5, §6 M2-T4/T5/T6).

Ядро среза. До M2 форма планирования стартовала в режиме `event_goal` и подставляла
`defaultEventDate()` = сегодня+56: атлет без гонки молча получал план с тейпером под
несуществующее событие. M2 заменяет молчаливые константы на предложение, выведенное из
его собственной истории, с явным `basis` (`derived` / `fallback`), и на честный
резолвер A-гонки, который НИКОГДА не подставляет дату.

  - M2-T4 : `suggested` выводится из истории; пустая/короткая история → fallback.
  - M2-T5 : нет A-гонки → `training_goal`, `has_a_race=false`, ни одной даты события.
  - M2-T6 : Intervals недоступен → поток продолжается с `degraded_reason`, не падает.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services import planning_onboarding as onboarding_service
from data.database import Database
from services.intervals_icu import IntervalsICUConfigurationError, IntervalsICUError


pytestmark = pytest.mark.smoke


WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _db(tmp_path, name: str = "suggest.db") -> Database:
    return Database(str(tmp_path / name))


def _recent_dates(weekdays: list[str], *, weeks: int, today: date | None = None) -> list[date]:
    """Последние `weeks` вхождений каждого из `weekdays` строго до `today`.

    Даты выводятся из реального «сегодня», а не из фиксированного календаря, — тесты
    этого репозитория уже обжигались на date-fragile ожиданиях (#163).
    """
    today = today or date.today()
    wanted = {WEEKDAY_KEYS.index(day) for day in weekdays}
    out: list[date] = []
    cursor = today - timedelta(days=1)
    while len(out) < len(wanted) * weeks:
        if cursor.weekday() in wanted:
            out.append(cursor)
        cursor -= timedelta(days=1)
    return out


def _seed(db: Database, dates: list[date], *, sport: str = "cycling", minutes: int = 60) -> None:
    db.save_activities(
        [
            {
                "activity_id": f"seed_{index}",
                "date": day.isoformat(),
                "sport": sport,
                "duration_minutes": minutes,
                "distance_km": 25.0,
                "tss": 50.0,
            }
            for index, day in enumerate(dates)
        ]
    )


def _no_events(**_kwargs):
    return {"events": [], "count": 0, "oldest": "", "newest": "", "read_only": True}


# --- M2-T4: предложение из истории ------------------------------------------

def test_m2_t4_available_days_are_derived_from_history(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    _seed(db, _recent_dates(["mon", "wed", "sat"], weeks=4))

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["available_days"]["value"] == ["mon", "wed", "sat"]
    assert suggested["available_days"]["basis"] == "derived"


def test_m2_t4_available_hours_are_derived_from_history(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    # 3 тренировки по 60 минут в неделю на протяжении 4 недель → 3.0 ч/нед.
    _seed(db, _recent_dates(["mon", "wed", "sat"], weeks=4), minutes=60)

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["available_hours"]["value"] == pytest.approx(3.0, abs=0.5)
    assert suggested["available_hours"]["basis"] == "derived"


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (10, 3.0),   # 0.5 ч/нед по истории — ниже минимального значения формы.
        (600, 20.0), # 30 ч/нед по истории — выше максимального значения формы.
    ],
)
def test_m2_t4_available_hours_are_clamped_to_product_bounds(
    tmp_path, monkeypatch, minutes, expected
):
    """Предложение обязано быть и сохраняемым, и отображаемым range-контролом."""
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    _seed(db, _recent_dates(["mon", "wed", "sat"], weeks=4), minutes=minutes)

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["available_hours"] == {"value": expected, "basis": "derived"}


def test_m2_t4_dominant_sport_drives_goal_type(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    _seed(db, _recent_dates(["tue", "thu", "sun"], weeks=4), sport="running")

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["goal_type"]["value"] == "run"
    assert suggested["goal_type"]["basis"] == "derived"
    assert suggested["distance"]["value"] in {"5k", "10k", "half_marathon", "marathon", "ultra"}


def test_m2_t4_empty_history_falls_back_without_pretending(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["available_days"]["value"] == WEEKDAY_KEYS
    assert suggested["available_hours"]["value"] == 10.0
    assert suggested["goal_type"]["value"] == "triathlon"
    for field in ("available_days", "available_hours", "goal_type", "distance"):
        assert suggested[field]["basis"] == "fallback", f"{field} не имеет права называться derived"


def test_m2_t4_short_history_is_not_trusted(tmp_path, monkeypatch):
    """Меньше двух недель истории — выводить недельный объём не из чего (§9 риск)."""
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    _seed(db, [date.today() - timedelta(days=offset) for offset in (1, 2, 3)])

    suggested = onboarding_service.suggest_planning_defaults(db)

    assert suggested["available_hours"]["basis"] == "fallback"
    assert suggested["available_days"]["basis"] == "fallback"


def test_m2_t4_suggested_profile_is_valid_for_save(tmp_path, monkeypatch):
    """Предложение должно быть сразу пригодно к сохранению — иначе онбординг в один
    клик невозможен."""
    from services import planning_profile

    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)
    _seed(db, _recent_dates(["mon", "wed", "sat"], weeks=4))

    suggested = onboarding_service.suggest_planning_defaults(db)
    profile = planning_profile.save_profile(
        db, {field: item["value"] for field, item in suggested.items()}
    )

    assert profile["available_days"] == ["mon", "wed", "sat"]


# --- M2-T5: A-гонка не выдумывается -----------------------------------------

def test_m2_t5_no_a_race_suggests_training_goal(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)

    context = onboarding_service.resolve_event_context()
    suggested = onboarding_service.suggest_planning_defaults(db)

    assert context["has_a_race"] is False
    assert context["degraded_reason"] is None, "отсутствие гонки — не деградация"
    assert context["events"] == []
    assert suggested["planning_mode"]["value"] == "training_goal"
    assert suggested["intent"]["value"] == "develop"


def test_m2_t5_no_event_date_is_ever_invented(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _no_events)
    db = _db(tmp_path)

    context = onboarding_service.resolve_event_context()
    suggested = onboarding_service.suggest_planning_defaults(db)

    assert "event_date" not in suggested
    assert context.get("event_date") is None
    assert all("date" not in str(key) for key in suggested)


def test_m2_t5_confirmed_a_race_switches_to_event_goal(tmp_path, monkeypatch):
    race_day = (date.today() + timedelta(days=70)).isoformat()

    def _with_race(**_kwargs):
        return {
            "events": [
                {"date": race_day, "priority": "A", "confirmed": True, "label": "Ironstar"},
                {"date": race_day, "priority": "B", "confirmed": True, "label": "Прикидка"},
            ],
            "count": 2,
        }

    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _with_race)
    db = _db(tmp_path)

    context = onboarding_service.resolve_event_context()
    suggested = onboarding_service.suggest_planning_defaults(db)

    assert context["has_a_race"] is True
    assert [event["priority"] for event in context["a_races"]] == ["A"]
    assert suggested["planning_mode"]["value"] == "event_goal"
    assert suggested["planning_mode"]["basis"] == "derived"


def test_m2_t5_unconfirmed_a_race_does_not_count(tmp_path, monkeypatch):
    """`confirmed=False` — это событие, у которого мы не опознали дисциплину. Строить
    вокруг него макроцикл молча нельзя (та же семантика, что уже в UI toggleEvent)."""

    def _unconfirmed(**_kwargs):
        return {
            "events": [
                {
                    "date": (date.today() + timedelta(days=40)).isoformat(),
                    "priority": "A",
                    "confirmed": False,
                    "label": "Что-то в календаре",
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _unconfirmed)
    db = _db(tmp_path)

    context = onboarding_service.resolve_event_context()

    assert context["has_a_race"] is False
    assert onboarding_service.suggest_planning_defaults(db)["planning_mode"]["value"] == "training_goal"


# --- M2-T6: недоступный Intervals не роняет поток ----------------------------

@pytest.mark.parametrize(
    "error",
    [
        IntervalsICUConfigurationError("Intervals.icu не настроен."),
        IntervalsICUError("Intervals.icu вернул 503."),
    ],
)
def test_m2_t6_intervals_failure_degrades_instead_of_raising(tmp_path, monkeypatch, error):
    def _boom(**_kwargs):
        raise error

    monkeypatch.setattr(onboarding_service, "discover_intervals_events", _boom)
    db = _db(tmp_path)

    context = onboarding_service.resolve_event_context()
    suggested = onboarding_service.suggest_planning_defaults(db)

    assert context["has_a_race"] is False
    assert context["degraded_reason"] and str(error) in context["degraded_reason"]
    assert context["events"] == []
    assert suggested["planning_mode"]["value"] == "training_goal"
    assert suggested["planning_mode"]["basis"] == "fallback"
