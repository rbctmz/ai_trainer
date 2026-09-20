"""Якорь метрик нагрузки на дашборде — контракт issue #598.

`calculate_current_status` — headless-билдер, общий для API и легаси-страницы —
вызывал `assemble_signals` без `as_of` и получал 30-дневный кадр отображения.
Оба фактора искажают CTL/ATL/TSB:

1. без якоря дни отдыха после последней тренировки не гасятся: метрики
   замерзают на дате последней активности (второй случай дефекта #139/#231);
2. 30-дневный кадр обрезает разогрев EWMA (`tau_CTL` = 42), поэтому CTL занижен
   даже без разрыва в данных: ровные 60 дней по 50 TSS дают CTL 25.5 вместо
   канонических 38.0.

Каноническое окно CTL/ATL/TSB — `LOAD_METRICS_WINDOW_DAYS` (issue #134),
канонический якорь — `athlete_local_date()`. Дашборд обязан воспроизводить
значения канонического readiness snapshot (`models.readiness._tsb_metrics`).

Почему это не косметика. `/api/dashboard/summary` перекрывает
`signals.load.ctl/atl/tsb` проекцией из snapshot, но `signals.load.form`,
`signals.critical` и `signals.recommendations` считаются внутри
`assemble_signals` от замороженного значения и проекцией не перекрываются.
В одном payload атлет получал TSB +16.4 «Готов к работе» и одновременно
«Критическое переутомление — Полный отдых 2-3 дня без тренировок».
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from data.database import Database
from models.banister import tsb_zone
from models.dashboard_summary import calculate_current_status
from models.readiness import (
    LOAD_METRICS_WINDOW_DAYS,
    _tsb_metrics,
    load_metrics_window_bounds,
)
from state import StateManager
from utils.athlete_time import athlete_local_date


pytestmark = pytest.mark.smoke


#: 3 недели нарастающей нагрузки — сценарий «нагрузочный блок + пропуск
#: тренировок» из acceptance criteria #598.
_HARD_BLOCK = [100.0] * 7 + [110.0] * 7 + [120.0] * 7
#: Ровная нагрузка без разрыва — регрессия витринной метрики (AC2).
_STEADY_LOAD = [50.0] * 60


def _seed(db: Database, days: list[float], end_offset_days: int) -> Database:
    """Записать дневную нагрузку, закончившуюся `end_offset_days` назад.

    Даты считаются от того же athlete-local дня, которым якорятся метрики
    (`utils.athlete_time.athlete_local_date`). Host-часы здесь не годятся:
    там, где локальная дата уже перешла на следующие сутки, последний день
    блока оказывался «вчера», в окно попадал лишний день отдыха и результат
    начинал зависеть от времени прогона (находка ревью PR #599).
    """
    today = athlete_local_date()
    block_end = today - timedelta(days=end_offset_days)
    block_start = block_end - timedelta(days=len(days) - 1)
    db.save_activities(
        [
            {
                "activity_id": f"anchor598-{end_offset_days}-{index}",
                "date": (block_start + timedelta(days=index)).strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 90,
                "distance_km": 40.0,
                "tss": float(tss),
            }
            for index, tss in enumerate(days)
        ]
    )
    return db


def _db(tmp_path, name: str) -> Database:
    return Database(str(tmp_path / name))


def _dashboard_status(db: Database, *, anchor=None):
    """Повторить форму вызова потребителей дашборда.

    30-дневный кадр остаётся кадром отображения; каноническое окно метрик и
    якорь передаются отдельно.
    """
    anchor = anchor or athlete_local_date()
    return calculate_current_status(
        db.get_activities(30),
        db.get_hrv_data(90),
        db.get_sleep_data(7),
        metrics_activities_df=pd.DataFrame(
            db.get_activities_between(*load_metrics_window_bounds(anchor))
        ),
        as_of=anchor,
    )


def test_rest_days_decay_dashboard_metrics(tmp_path) -> None:
    """AC1: метрики перестают замерзать на дате последней тренировки.

    До фикса на этом же наборе данных ATL оставался на уровне блока (106.2), а
    TSB был глубоко отрицательным (−68.5) у атлета, отдохнувшего 14 дней.
    """
    db = _seed(_db(tmp_path, "rest.db"), _HARD_BLOCK, end_offset_days=14)

    status = _dashboard_status(db)

    assert status["atl"] < 60.0, (
        f"ATL={status['atl']} не погас за 14 дней отдыха — метрики посчитаны "
        "на дату последней тренировки, а не на сегодня"
    )
    assert status["tsb"] > 0.0, (
        f"TSB={status['tsb']} должен быть положительным у отдохнувшего атлета"
    )


def test_dashboard_load_path_matches_canonical_readiness_tsb(tmp_path) -> None:
    """AC1/AC2: дашборд обязан совпадать с каноническим readiness snapshot.

    `project_readiness_snapshot` подставляет в payload значения snapshot, поэтому
    расхождение здесь означает, что часть payload посчитана от одной серии, а
    часть — от другой.
    """
    db = _seed(_db(tmp_path, "canonical.db"), _HARD_BLOCK, end_offset_days=14)
    anchor = athlete_local_date()
    history = db.get_activities(LOAD_METRICS_WINDOW_DAYS)

    canonical = _tsb_metrics(history, anchor)
    assert canonical is not None

    status = _dashboard_status(db, anchor=anchor)

    assert status["ctl"] == pytest.approx(canonical["ctl"], abs=0.1), (
        f"CTL дашборда {status['ctl']} != канонического {canonical['ctl']}"
    )
    assert status["atl"] == pytest.approx(canonical["atl"], abs=0.1), (
        f"ATL дашборда {status['atl']} != канонического {canonical['atl']}"
    )
    assert status["tsb"] == pytest.approx(canonical["tsb"], abs=0.1), (
        f"TSB дашборда {status['tsb']} != канонического {canonical['tsb']}"
    )


def test_steady_load_is_not_understated_by_display_window(tmp_path) -> None:
    """AC2: регрессия витринной метрики.

    Без разрыва в данных 60 дней по 50 TSS дают канонический CTL 38.0. На
    30-дневном кадре обрезанный разогрев EWMA давал 25.5 — занижение на треть
    ровно у того атлета, который тренируется стабильно.
    """
    db = _seed(_db(tmp_path, "steady.db"), _STEADY_LOAD, end_offset_days=0)

    status = _dashboard_status(db)

    assert status["ctl"] == pytest.approx(38.0, abs=0.5), (
        f"CTL={status['ctl']}: кадр отображения занижает витринную метрику "
        "(ожидалось каноническое значение 38.0)"
    )
    assert status["tsb"] == pytest.approx(-12.0, abs=1.0), f"TSB={status['tsb']}"


def test_canonical_snapshot_values_unchanged(tmp_path) -> None:
    """Регрессия: канонический контур расчёта этим слайсом не меняется."""
    db = _seed(_db(tmp_path, "guard.db"), _HARD_BLOCK, end_offset_days=14)
    anchor = athlete_local_date()

    canonical = _tsb_metrics(db.get_activities(LOAD_METRICS_WINDOW_DAYS), anchor)

    assert canonical is not None
    assert canonical["ctl"] == pytest.approx(31.3, abs=0.5)
    assert canonical["atl"] == pytest.approx(14.9, abs=0.5)
    assert canonical["tsb"] == pytest.approx(16.4, abs=0.5)
    assert canonical["window_days"] == LOAD_METRICS_WINDOW_DAYS


def test_api_summary_payload_agrees_with_itself(tmp_path) -> None:
    """AC1/AC2 на API-потребителе: payload не противоречит сам себе.

    Проекция перекрывает `signals.load.ctl/atl/tsb`, но не
    `signals.load.form`, `signals.critical` и `signals.recommendations`.
    До фикса ответ содержал TSB +16.4 («Свежесть») рядом с
    «Критическое переутомление — Полный отдых 2-3 дня без тренировок».
    """
    from api.routers.dashboard import dashboard_summary

    db = _seed(_db(tmp_path, "api.db"), _HARD_BLOCK, end_offset_days=14)

    payload = dashboard_summary(db=db, state=StateManager({}))

    signals = payload["signals"]
    load = signals["load"]
    assert load["tsb"] > 0.0, f"load.tsb={load['tsb']} заморожен на дате блока"

    expected_zone = tsb_zone(float(load["tsb"]))["label"]
    assert load["form"] == expected_zone, (
        f"load.form={load['form']!r} противоречит load.tsb={load['tsb']} "
        f"(ожидалась зона {expected_zone!r}): form посчитан от замороженной серии"
    )
    assert load["label"] == expected_zone, (
        f"load.label={load['label']!r} противоречит load.tsb={load['tsb']}"
    )

    assert signals["critical"]["status"] != "Критическое переутомление", (
        f"payload предписывает отдых при TSB={load['tsb']}: "
        f"{signals['critical']}"
    )
    for item in signals["recommendations"]:
        assert "TSB критически низкий" not in item.get("description", ""), (
            f"рекомендация построена на замороженном TSB: {item}"
        )


def test_legacy_dashboard_status_is_anchored(monkeypatch, tmp_path) -> None:
    """AC3: второй потребитель — легаси-страница Streamlit.

    Страница не применяет `project_readiness_snapshot`, поэтому замороженные
    значения доходили до атлета напрямую. Кэш-загрузчики подменяются на реальную
    временную БД, чтобы проверить именно проводку страницы.
    """
    import ui.pages.dashboard as page

    db = _seed(_db(tmp_path, "legacy.db"), _HARD_BLOCK, end_offset_days=14)
    monkeypatch.setattr(page, "load_activities", lambda days=30: db.get_activities(days))
    monkeypatch.setattr(
        page,
        "load_activities_between",
        lambda start, end: pd.DataFrame(db.get_activities_between(start, end)),
    )
    monkeypatch.setattr(page, "load_hrv", lambda days=90: db.get_hrv_data(days))
    monkeypatch.setattr(page, "load_sleep", lambda days=7: db.get_sleep_data(days))

    status = page._calculate_current_status(training_status={})

    assert status["atl"] < 60.0, (
        f"легаси-страница показывает ATL={status['atl']}: метрики заморожены"
    )
    assert status["tsb"] > 0.0, (
        f"легаси-страница показывает TSB={status['tsb']} у отдохнувшего атлета"
    )


def test_metrics_frame_matches_the_canonical_window(tmp_path) -> None:
    """Граница окна: `get_activities(N)` отдаёт N + 1 дату (находка ревью #614).

    Нагрузка ровно за 90 дней до якоря попадала в `get_activities(90)` по
    включительной границе `today - 90`, но не попадала в канонический
    snapshot, который читает ровно 90 дат. Из-за этого `load.form` считался
    от одного ряда, а спроецированный `load.label` — от другого, и один
    payload снова противоречил себе.
    """
    from api.routers.dashboard import dashboard_summary

    anchor = athlete_local_date()
    edge = anchor - timedelta(days=LOAD_METRICS_WINDOW_DAYS)
    db = _db(tmp_path, "edge.db")
    db.save_activities(
        [
            {
                "activity_id": "edge-old",
                "date": edge.strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 180,
                "distance_km": 80.0,
                "tss": 300.0,
            },
            {
                "activity_id": "edge-today",
                "date": anchor.strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": 95.0,
            },
        ]
    )

    payload = dashboard_summary(db=db, state=StateManager({}))
    load = payload["signals"]["load"]

    expected = tsb_zone(float(load["tsb"]))["label"]
    assert load["form"] == expected, (
        f"load.form={load['form']!r} противоречит load.tsb={load['tsb']} "
        f"(ожидалась зона {expected!r}): метрики считаются не по каноническому окну"
    )
    assert load["label"] == expected


def test_empty_account_keeps_zero_metrics(tmp_path) -> None:
    """AC4: ветка «Fresh/empty account» сохраняет текущее поведение."""
    status = calculate_current_status(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        metrics_activities_df=pd.DataFrame(),
        as_of=athlete_local_date(),
    )

    assert (status["ctl"], status["atl"], status["tsb"]) == (0.0, 0.0, 0.0)


def test_missing_metrics_frame_falls_back_to_display_frame(tmp_path) -> None:
    """Обратная совместимость: без нового параметра поведение прежнее.

    Существующие вызывающие `calculate_current_status` (и все 13 вызывающих
    `assemble_signals`) не должны изменить результат от добавления параметра.
    """
    db = _seed(_db(tmp_path, "compat.db"), _STEADY_LOAD, end_offset_days=0)
    display = db.get_activities(30)
    hrv = db.get_hrv_data(90)
    sleep = db.get_sleep_data(7)

    without = calculate_current_status(display, hrv, sleep, training_status={})
    explicit_none = calculate_current_status(
        display, hrv, sleep, training_status={}, metrics_activities_df=None, as_of=None
    )

    assert without["ctl"] == explicit_none["ctl"]
    assert without["atl"] == explicit_none["atl"]
    assert without["tsb"] == explicit_none["tsb"]
