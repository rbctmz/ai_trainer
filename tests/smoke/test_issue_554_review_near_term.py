"""Issue #554 review gate (P1): правка дня исполняется по эффективной нагрузке.

Ревьюер воспроизвёл цепочку `build_daily_session_templates →
project_daily_plan_from_session_templates → apply_near_term_day_edits` на FTP 200:
день «качество • вело» показывал 65.2 TSS, правка «поднять до 70» отдавала день
на 47.7 TSS, а недельная заметка продолжала говорить «Δ +5 TSS»; правка «до 60»
давала 45 TSS вместо запрошенного значения. Причина: строка правки отдаёт
эффективную нагрузку дня (то, что план показывает после материализации), а
применённая правка передавала это число материализатору как бюджет сплита и
затем безусловно заменяла день нагрузкой из получившейся прескрипции — то есть
запрос на увеличение мог уменьшить план, а дельта и заметка считались из
запрошенного бюджета, а не из фактической нагрузки.

Инвариант: правка, выраженная эффективной целью, либо материализует прескрипцию,
согласованную с этой целью, либо называется явно неисполни́мой; дневной скаляр,
дельта правки и заметка считаются по фактической нагрузке, а дневной план,
недельная сводка и скаляры сессий остаются взаимно согласованными. Запрос на
увеличение не имеет права уменьшить план.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, Mapping

import pytest

from models.planning_near_term import (
    NEAR_TERM_EFFECTIVE_TARGET_TOLERANCE_TSS,
    apply_near_term_day_edits,
    build_near_term_edit_rows,
)
from models.training_planner import (
    build_daily_session_templates,
    project_daily_plan_from_session_templates,
)
from models.workout_catalog import extract_zone_snapshot

pytestmark = pytest.mark.smoke

# Санитизированное воспроизведение из ревью: FTP 200 и день качества, у которого
# бюджет сплита (77 TSS) больше того, что каталог выдаёт своей power-прескрипцией
# на эти минуты (65.2 TSS). Обе величины проверяются тестом, а не принимаются на
# веру: расхождение бюджета и прескрипции — источник находки.
FTP = 200.0
START = date(2026, 6, 8)
REVIEW_EFFECTIVE_TSS = 65.2
QUALITY_BIKE_BUDGET_TSS = 77.0
# Запросы ревьюера: поднять показанные 65.2 до 70 и снизить до 60.
REQUESTED_INCREASE_TSS = 70.0
REQUESTED_DECREASE_TSS = 60.0
# Нагрузка, которую выдаёт прескрипция, если запрос уходит материализатору как
# бюджет сплита: так работал путь правки до фикса.
BUDGET_DRIVEN_INCREASE_TSS = 47.7
BUDGET_DRIVEN_DECREASE_TSS = 45.0
# Ниже минимальной ступени каталога качественной вело-прескрипции не существует:
# такой запрос обязан вернуться как явно неисполни́мый, а не подмениться другой
# нагрузкой.
UNREACHABLE_TARGET_TSS = 5.0

WEEK_LAYOUT = (
    ("quality", "bike", QUALITY_BIKE_BUDGET_TSS, "Качество • вело"),
    ("easy", "run", 30.0, "Лёгкая • бег"),
    ("off", "off", 0.0, "Отдых"),
    ("easy", "run", 30.0, "Лёгкая • бег"),
    ("easy", "run", 30.0, "Лёгкая • бег"),
    ("long", "bike", 60.0, "Длительная • вело"),
    ("easy", "run", 33.0, "Лёгкая • бег"),
)
WEEK_COUNT = 2
DELTA_PATTERN = re.compile(r"Δ ([+-]\d+) TSS")


def _day_dt(day_index: int) -> datetime:
    return datetime.combine(START + timedelta(days=day_index), datetime.min.time())


def _parts(sport: str, total_tss: float) -> Dict[str, float]:
    return {
        candidate: round(total_tss, 1) if candidate == sport else 0.0
        for candidate in ("run", "bike", "swim")
    }


def _week_meta(week_index: int) -> Dict[str, Any]:
    return {
        "week_start": START + timedelta(days=7 * week_index),
        "phase": "Build",
        "weekly_tss": 260,
        "bike": 0.0,
        "run": 0.0,
        "swim": 0.0,
        "day_roles": [role for role, _sport, _tss, _focus in WEEK_LAYOUT],
        "day_focuses": [focus for _role, _sport, _tss, focus in WEEK_LAYOUT],
    }


def _split_daily() -> list[tuple[datetime, float, Dict[str, float]]]:
    """Дневной план сплита: бюджет по видам спорта, ещё не прескрипция."""
    daily: list[tuple[datetime, float, Dict[str, float]]] = []
    for day_index in range(7 * WEEK_COUNT):
        _role, sport, total_tss, _focus = WEEK_LAYOUT[day_index % 7]
        daily.append((_day_dt(day_index), total_tss, _parts(sport, total_tss)))
    return daily


def _build_plan() -> Dict[str, Any]:
    """Текущий план в том виде, в каком его читает поверхность правки."""
    daily = _split_daily()
    weekly_summary = [_week_meta(week_index) for week_index in range(WEEK_COUNT)]
    templates = build_daily_session_templates(
        daily,
        weekly_summary,
        goal_type="Триатлон",
        distance="Олимпийка",
        zone_snapshot={"ftp": FTP},
    )
    daily = project_daily_plan_from_session_templates(daily, templates)
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "weeks_to_race": WEEK_COUNT,
        "start_week": START,
        "weekly_tss_plan": [260] * WEEK_COUNT,
        "base_weekly_tss_plan": [260] * WEEK_COUNT,
        "phases": ["Build"] * WEEK_COUNT,
        "daily_plan": daily,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "constraint_summary": {
            "catch_up_strategy": "catch_up",
            "current_tsb": -4.0,
            "load_state": "balanced",
            "notes": ["Базовый план под текущую доступность."],
        },
    }


def _budget_driven_day_total(
    requested_tss: float,
    *,
    session_role: str = "quality",
    sport: str = "bike",
) -> float:
    """Нагрузка дня, если запрос уходит материализатору как бюджет сплита.

    Так работал путь правки до фикса: материализатор получал запрошенное число
    как бюджет и отдавал нагрузку своей прескрипции."""
    daily = [(_day_dt(0), requested_tss, _parts(sport, requested_tss))]
    templates = build_daily_session_templates(
        daily,
        [{"phase": "Build", "day_roles": [session_role], "day_focuses": ["—"]}],
        goal_type="Триатлон",
        distance="Олимпийка",
        zone_snapshot={"ftp": FTP},
    )
    projected = project_daily_plan_from_session_templates(daily, templates)
    return round(float(projected[0][1] or 0.0), 1)


def _session_loads(session: Mapping[str, Any]) -> Dict[str, float]:
    """Нагрузка одной сессии по видам спорта (композит — по своим ногам)."""
    if str(session.get("kind") or "") == "composite":
        loads: Dict[str, float] = {}
        for leg in list(session.get("legs") or []):
            sport = str(leg.get("sport") or "")
            loads[sport] = round(loads.get(sport, 0.0) + float(leg.get("target_tss") or 0.0), 1)
        return loads
    sport = str(session.get("sport") or "")
    if sport in {"", "off", "race"}:
        return {}
    return {sport: round(float(session.get("total_tss") or 0.0), 1)}


def _template_day_total(template: Mapping[str, Any]) -> float:
    """Сумма нагрузок сессий дня — то, что план обязан показывать как день."""
    return round(
        sum(
            load
            for session in list(template.get("sessions") or [])
            for load in _session_loads(session).values()
        ),
        1,
    )


def _prescription_tss(template: Mapping[str, Any]) -> float:
    """TSS из прескрипции первичной сессии дня, а не из бюджета сплита."""
    sessions = list(template.get("sessions") or [])
    assert sessions, f"day template has no sessions: {template}"
    snapshot = dict(sessions[0].get("parameter_snapshot") or {})
    return round(float(snapshot.get("target_tss") or sessions[0].get("total_tss") or 0.0), 1)


def _day_signature(template: Mapping[str, Any]) -> tuple:
    """Сравнимая подпись дня: нагрузка и сама прескрипция, без identity-полей."""
    return (
        str(template.get("date") or ""),
        str(template.get("session_role") or ""),
        str(template.get("sport") or ""),
        int(template.get("duration_minutes") or 0),
        _template_day_total(template),
        tuple(
            (
                str(session.get("sport") or ""),
                str(session.get("session_role") or ""),
                round(float(session.get("total_tss") or 0.0), 1),
                int(session.get("duration_minutes") or 0),
                str(session.get("template_key") or ""),
                str(session.get("prescription_fingerprint") or ""),
                len(list(session.get("materialized_steps") or [])),
            )
            for session in list(template.get("sessions") or [])
        ),
    )


def _edit_row(plan: Mapping[str, Any], *, total_tss: float) -> Dict[str, Any]:
    rows = build_near_term_edit_rows(plan, horizon_days=7)
    row = rows[0]
    return {
        **row,
        "session_role": row["current_role"],
        "sport": row["current_sport"],
        "total_tss": total_tss,
    }


def _apply(plan: Mapping[str, Any], *, total_tss: float) -> Dict[str, Any]:
    return apply_near_term_day_edits(plan, [_edit_row(plan, total_tss=total_tss)], horizon_days=7)


def _note_delta(note: Any) -> int:
    match = DELTA_PATTERN.search(str(note or ""))
    assert match, f"недельная заметка не несёт дельту TSS: {note!r}"
    return int(match.group(1))


def _assert_plan_is_consistent(plan: Mapping[str, Any]) -> None:
    """Дневной план, недельная сводка и скаляры сессий говорят одно и то же."""
    daily = list(plan["daily_plan"])
    templates = list(plan["session_templates"])
    weekly_summary = list(plan["weekly_summary"])
    assert len(daily) == len(templates)

    for day_index, ((_dt, total, parts), template) in enumerate(zip(daily, templates)):
        sessions = list(template.get("sessions") or [])
        if not sessions:
            continue
        session_total = _template_day_total(template)
        assert round(float(total or 0.0), 1) == pytest.approx(session_total, abs=0.1), day_index
        assert round(sum(float(value or 0.0) for value in parts.values()), 1) == pytest.approx(
            session_total,
            abs=0.1,
        ), day_index
        assert int(template.get("duration_minutes") or 0) == int(
            sessions[0].get("duration_minutes") or 0
        ), day_index

    for week_index, week_row in enumerate(weekly_summary):
        week_days = daily[week_index * 7 : week_index * 7 + 7]
        assert int(week_row.get("weekly_tss") or 0) == int(
            round(sum(float(day[1] or 0.0) for day in week_days))
        ), week_index
        assert int(plan["weekly_tss_plan"][week_index] or 0) == int(
            week_row.get("weekly_tss") or 0
        ), week_index


def test_quality_bike_day_increase_is_delivered_by_its_own_prescription():
    plan = _build_plan()
    row = build_near_term_edit_rows(plan, horizon_days=7)[0]
    current_total = float(row["current_total_tss"])
    current_template = dict(plan["session_templates"][0])

    # Строка правки показывает эффективную нагрузку дня — то, что несёт
    # прескрипция, а не бюджет сплита, из которого она собрана.
    assert current_total == pytest.approx(REVIEW_EFFECTIVE_TSS, abs=0.05)
    assert current_total == pytest.approx(_prescription_tss(current_template), abs=0.05)
    assert current_total < QUALITY_BIKE_BUDGET_TSS
    assert extract_zone_snapshot(plan["session_templates"]).get("ftp") == FTP

    # RED: если запрос уходит материализатору как бюджет, день не растёт, а
    # падает до 47.7 — именно это воспроизведение закрывает находка ревью.
    budget_driven = _budget_driven_day_total(REQUESTED_INCREASE_TSS)
    assert budget_driven == pytest.approx(BUDGET_DRIVEN_INCREASE_TSS, abs=0.05)
    assert budget_driven < current_total

    updated = _apply(plan, total_tss=REQUESTED_INCREASE_TSS)
    updated_total = round(float(updated["daily_plan"][0][1] or 0.0), 1)
    updated_template = dict(updated["session_templates"][0])

    # Запрос на увеличение не имеет права уменьшить план и обязан быть исполнен
    # прескрипцией в пределах задокументированного допуска.
    assert updated_total > current_total
    assert updated_total != pytest.approx(budget_driven, abs=0.05)
    assert abs(updated_total - REQUESTED_INCREASE_TSS) <= NEAR_TERM_EFFECTIVE_TARGET_TOLERANCE_TSS
    # Дневной скаляр — это прескрипция дня, а не запрошенное число.
    assert updated_total == pytest.approx(_prescription_tss(updated_template), abs=0.05)
    assert _prescription_tss(updated_template) == pytest.approx(71.0, abs=0.05)

    # Дельта недели и заметка считаются из фактической нагрузки.
    expected_delta = int(round(updated_total - current_total))
    assert expected_delta == 6
    near_term_edit = dict(updated["constraint_summary"]["near_term_edit"])
    assert near_term_edit["total_delta_tss"] == expected_delta
    assert near_term_edit["edited_day_count"] == 1
    assert near_term_edit["edited_dates"] == [START.isoformat()]
    assert near_term_edit["unmet_target_days"] == []
    assert near_term_edit["infeasible_days"] == []
    assert _note_delta(updated["weekly_summary"][0]["adjustment_note"]) == expected_delta

    _assert_plan_is_consistent(updated)


def test_quality_bike_day_decrease_is_delivered_by_its_own_prescription():
    plan = _build_plan()
    current_total = float(build_near_term_edit_rows(plan, horizon_days=7)[0]["current_total_tss"])

    # RED: как бюджет запрос 60 отдавал 45 TSS — снижение вдвое больше запрошенного.
    budget_driven = _budget_driven_day_total(REQUESTED_DECREASE_TSS)
    assert budget_driven == pytest.approx(BUDGET_DRIVEN_DECREASE_TSS, abs=0.05)

    updated = _apply(plan, total_tss=REQUESTED_DECREASE_TSS)
    updated_total = round(float(updated["daily_plan"][0][1] or 0.0), 1)
    updated_template = dict(updated["session_templates"][0])

    assert updated_total < current_total
    assert abs(updated_total - REQUESTED_DECREASE_TSS) <= NEAR_TERM_EFFECTIVE_TARGET_TOLERANCE_TSS
    assert updated_total == pytest.approx(_prescription_tss(updated_template), abs=0.05)
    assert updated_total == pytest.approx(60.5, abs=0.05)
    assert updated_total > budget_driven

    expected_delta = int(round(updated_total - current_total))
    assert expected_delta == -5
    near_term_edit = dict(updated["constraint_summary"]["near_term_edit"])
    assert near_term_edit["total_delta_tss"] == expected_delta
    assert _note_delta(updated["weekly_summary"][0]["adjustment_note"]) == expected_delta

    _assert_plan_is_consistent(updated)


def test_unreachable_effective_target_is_reported_and_never_substituted():
    plan = _build_plan()
    before_daily = list(plan["daily_plan"])
    before_signature = _day_signature(plan["session_templates"][0])
    current_total = float(build_near_term_edit_rows(plan, horizon_days=7)[0]["current_total_tss"])

    updated = _apply(plan, total_tss=UNREACHABLE_TARGET_TSS)

    near_term_edit = dict(updated["constraint_summary"]["near_term_edit"])
    # День не подменён другой нагрузкой и не сдвинут: правка названа неисполни́мой.
    assert round(float(updated["daily_plan"][0][1] or 0.0), 1) == pytest.approx(current_total, abs=0.05)
    assert updated["daily_plan"][0] == before_daily[0]
    assert _day_signature(updated["session_templates"][0]) == before_signature
    assert near_term_edit["is_active"] is False
    assert near_term_edit["edited_day_count"] == 0
    assert near_term_edit["unmet_target_days"] == []

    infeasible_days = list(near_term_edit["infeasible_days"])
    assert len(infeasible_days) == 1
    infeasible = dict(infeasible_days[0])
    assert infeasible["requested_tss"] == UNREACHABLE_TARGET_TSS
    assert infeasible["achieved_tss"] is None
    assert infeasible["reason"] == "no_feasible_prescription"
    assert infeasible["index"] == 0

    # Отказ виден и в недельной заметке, и в примечаниях плана.
    note = str(updated["weekly_summary"][0]["adjustment_note"])
    assert "не изменена" in note
    assert f"на {UNREACHABLE_TARGET_TSS:g} TSS" in note
    notes = [str(item) for item in updated["constraint_summary"]["notes"]]
    assert any("Эффективная нагрузка" in item for item in notes), notes

    _assert_plan_is_consistent(updated)


def test_multi_day_edit_reports_the_load_that_actually_landed_in_the_plan():
    """Недельная дельта и заметка равны тому, что стоит в дневном плане."""
    plan = _build_plan()
    rows = build_near_term_edit_rows(plan, horizon_days=7)
    horizon = 7
    before_horizon_total = round(sum(day[1] for day in plan["daily_plan"][:horizon]), 1)

    updated = apply_near_term_day_edits(
        plan,
        [
            {
                **rows[0],
                "session_role": rows[0]["current_role"],
                "sport": rows[0]["current_sport"],
                "total_tss": REQUESTED_INCREASE_TSS,
            },
            {**rows[1], "session_role": "off", "sport": "off", "total_tss": 0.0},
        ],
        horizon_days=horizon,
    )
    after_horizon_total = round(sum(day[1] for day in updated["daily_plan"][:horizon]), 1)
    expected_delta = int(round(after_horizon_total - before_horizon_total))

    near_term_edit = dict(updated["constraint_summary"]["near_term_edit"])
    assert near_term_edit["edited_day_count"] == 2
    assert near_term_edit["edited_dates"] == [
        START.isoformat(),
        (START + timedelta(days=1)).isoformat(),
    ]
    assert near_term_edit["total_delta_tss"] == expected_delta
    assert _note_delta(updated["weekly_summary"][0]["adjustment_note"]) == expected_delta

    # День, снятый правкой, действительно пуст, а его шаблон не несёт сессий.
    assert round(float(updated["daily_plan"][1][1] or 0.0), 1) == 0.0
    assert not list(updated["session_templates"][1].get("sessions") or [])
    assert str(updated["session_templates"][1].get("session_role") or "") == "off"
    # Увеличенный день остаётся своей прескрипцией, а не запрошенным числом,
    # и не сдвигается вниз из-за того, что рядом снят другой день.
    assert round(float(updated["daily_plan"][0][1] or 0.0), 1) > round(
        float(plan["daily_plan"][0][1] or 0.0),
        1,
    )
    assert round(float(updated["daily_plan"][0][1] or 0.0), 1) == pytest.approx(
        _prescription_tss(updated["session_templates"][0]),
        abs=0.05,
    )

    _assert_plan_is_consistent(updated)


@pytest.mark.parametrize(
    "requested_tss",
    (REQUESTED_INCREASE_TSS, REQUESTED_DECREASE_TSS, UNREACHABLE_TARGET_TSS),
)
def test_edit_never_moves_the_day_away_from_the_requested_target(requested_tss: float):
    """Правка либо приближает день к запросу, либо не трогает его вовсе."""
    plan = _build_plan()
    current_total = round(
        float(build_near_term_edit_rows(plan, horizon_days=7)[0]["current_total_tss"]),
        1,
    )

    updated = _apply(plan, total_tss=requested_tss)
    updated_total = round(float(updated["daily_plan"][0][1] or 0.0), 1)

    before_deviation = abs(current_total - requested_tss)
    after_deviation = abs(updated_total - requested_tss)
    assert after_deviation <= before_deviation + 1e-9
    assert updated_total == pytest.approx(_template_day_total(updated["session_templates"][0]), abs=0.1)
    if after_deviation > NEAR_TERM_EFFECTIVE_TARGET_TOLERANCE_TSS:
        reported: Iterable[Mapping[str, Any]] = (
            list(updated["constraint_summary"]["near_term_edit"]["unmet_target_days"])
            + list(updated["constraint_summary"]["near_term_edit"]["infeasible_days"])
        )
        assert any(
            dict(item)["requested_tss"] == round(float(requested_tss), 1) for item in reported
        ), "расхождение с запросом обязано быть названо явно"
    _assert_plan_is_consistent(updated)
