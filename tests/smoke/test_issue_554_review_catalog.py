"""Регрессии независимого ревью PR #554: селектор каталога и derived-границы.

Четыре находки ревью закрываются одним слайсом:

* P1 — ``materialize_session_template`` обязан идти по ранжированным кандидатам
  и персистить первый материализуемый, а не ``candidates[0]`` (иначе
  доставляемая taper-сессия становится неисполни́мой и delivery падает
  fail-closed);
* P2 — ``failed_bounds`` derived-прескрипции обязан доезжать до персистируемой
  сессии и ног brick-обёртки, чтобы fail-closed прескрипция сохраняла
  аудит-след;
* P2 — на неисполни́мой ветке ``rescale_materialized_session`` ``target_tss``
  остаётся derived-нагрузкой, а запрошенный бюджет живёт только в
  ``requested_tss``;
* P1 — недельный rebalance масштабирует длительность от эффективной нагрузки
  плана, а не от исторического ``requested_tss`` (иначе одобренное сокращение
  сжимается в fail-closed прескрипцию и не доставляет свою нагрузку).

Ожидания выводятся из самой прескрипции (``_single_candidates``,
``materialize_workout``, ``planned_bike_tss_from_steps``); литералы помечены
комментарием, откуда они взяты.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.plan_actual_reconciliation import (
    MATCH_RULE_VERSION,
    apply_weekly_rebalance_preview,
    build_weekly_rebalance_preview,
)
from models.session_identity import ensure_session_identities
from models.training_planner import (
    build_daily_session_templates,
    project_daily_plan_from_session_templates,
)
from models.workout_catalog import (
    _single_candidates,
    catalog_definitions,
    materialize_brick_session,
    materialize_session_template,
    materialize_workout,
    planned_bike_tss_from_steps,
    planned_session_is_executable,
    rescale_materialized_session,
)


pytestmark = pytest.mark.smoke


# Репро супервайзера: taper long bike, бюджет 60 TSS при оценке 120 минут.
# FTP 200 делает деривированную NP/TSS сравнимой между кандидатами.
_TAPER_SELECTION = {
    "phase": "Taper",
    "session_role": "long",
    "sport": "bike",
    "goal_type": "Триатлон",
    "target_tss": 60.0,
    "estimated_duration_minutes": 120,
    "load_state": "balanced",
    "recent_template_keys": (),
}
_TAPER_ZONE = {"ftp": 200.0}

# Репро супервайзера: короткая quality-сессия, где derived-прескрипция не
# проходит объявленные границы дефиниции.
_SHORT_QUALITY_SELECTION = {
    "phase": "Build",
    "session_role": "quality",
    "sport": "bike",
    "goal_type": "Триатлон",
    "target_tss": 20.0,
    "estimated_duration_minutes": 30,
    "load_state": "balanced",
    "recent_template_keys": (),
}
_SHORT_QUALITY_ZONE = {"ftp": 160.0}


def _definition(key: str):
    return next(item for item in catalog_definitions() if item.template_key == key)


def _candidate_attempts(selection: dict, zone_snapshot: dict) -> list[dict]:
    """Материализует ранжированных кандидатов тем же входом, что и селектор."""
    attempts = []
    for definition, duration in _single_candidates(**selection):
        materialized = materialize_workout(
            definition,
            {"duration_minutes": duration, "target_tss": selection["target_tss"]},
            zone_snapshot,
        )
        attempts.append(
            {
                "template_key": definition.template_key,
                "duration_minutes": duration,
                "status": materialized["materialization_status"],
                "failed_bounds": list(materialized.get("failed_bounds") or []),
                "steps": materialized["steps"],
                "target_provenance": materialized["target_provenance"],
                "parameter_snapshot": materialized["parameter_snapshot"],
            }
        )
    return attempts


_TAPER_SHARPENING_KEYS = {"bike_vo2max_intervals", "bike_neuromuscular_sprints"}
# Тот же taper-день, но с бюджетом, который sharpening-кандидат может выдать:
# VO2max всё ещё не проходит свои полосы, neuromuscular — проходит.
_TAPER_LONG_RETRY_SELECTION = {**_TAPER_SELECTION, "target_tss": 50.0}


def test_taper_long_bike_retimes_the_sharpening_pair_instead_of_leaving_the_set():
    """P1: taper long ищет длительность внутри sharpening-набора, а не замену."""
    attempts = _candidate_attempts(_TAPER_SELECTION, _TAPER_ZONE)

    # Ранжирование: VO2max, race pace, aerobic endurance, neuromuscular.
    assert [item["template_key"] for item in attempts] == [
        "bike_vo2max_intervals",
        "bike_race_pace",
        "bike_aerobic_endurance",
        "bike_neuromuscular_sprints",
    ]
    # Материализуемые кандидаты вне sharpening-набора существуют, но заменой не
    # являются: длинная endurance-поездка переписала бы стимул дня.
    assert [
        item["status"] for item in attempts if item["template_key"] not in _TAPER_SHARPENING_KEYS
    ] == ["materialized", "materialized"]

    session = materialize_session_template(**_TAPER_SELECTION, zone_snapshot=_TAPER_ZONE)

    # Корень дефекта — пара (кандидат × длительность): при 40 минутах
    # bike_vo2max_intervals выдаёт 59.7 TSS/ч против своей полосы [70, 120], а
    # при 50 минутах — 72.6 TSS/ч внутри неё.
    assert session["template_key"] == "bike_vo2max_intervals"
    assert session["template_key"] in _TAPER_SHARPENING_KEYS
    assert session["duration_minutes"] == 50
    assert session["duration_minutes"] <= 60
    assert session["materialization_status"] == "materialized"
    assert not session.get("failed_bounds")
    assert planned_session_is_executable(session) is True

    selected_pair = materialize_workout(
        _definition(session["template_key"]),
        {"duration_minutes": session["duration_minutes"], "target_tss": 60.0},
        _TAPER_ZONE,
    )
    assert selected_pair["materialization_status"] == "materialized"
    derived = planned_bike_tss_from_steps(
        session["materialized_steps"], session["target_provenance"]
    )
    assert session["parameter_snapshot"]["target_tss"] == pytest.approx(
        derived["planned_tss"], abs=0.01
    )
    # 50 минут bike_vo2max_intervals при FTP 200 доставляют 60.5 TSS.
    assert derived["planned_tss"] == pytest.approx(60.5, abs=0.1)

    evidence = session["selection_evidence"]
    assert evidence["role_override"] == "long_to_sharpening"
    assert evidence["intent_constraint"] == "taper_long_sharpening"
    assert evidence["selected_template_key"] == "bike_vo2max_intervals"
    assert evidence["selected_duration_minutes"] == 50
    # Перебор шёл от выбранной селектором длительности наружу, пара 50 минут —
    # первая исполнимая.
    assert evidence["skipped_candidates"] == [
        {
            "template_key": "bike_vo2max_intervals",
            "duration_minutes": 40,
            "failed_bounds": ["density_below_minimum"],
        },
        {
            "template_key": "bike_vo2max_intervals",
            "duration_minutes": 35,
            "failed_bounds": ["density_below_minimum"],
        },
        {
            "template_key": "bike_vo2max_intervals",
            "duration_minutes": 45,
            "failed_bounds": ["density_below_minimum"],
        },
    ]
    assert evidence["intent_excluded_keys"] == [
        "bike_race_pace",
        "bike_aerobic_endurance",
    ]
    assert "reason" not in evidence


def test_taper_long_bike_uses_the_next_sharpening_candidate_when_needed():
    """P1: если первая sharpening-пара неисполнима целиком, берётся следующая."""
    attempts = _candidate_attempts(_TAPER_LONG_RETRY_SELECTION, _TAPER_ZONE)

    assert attempts[0]["template_key"] == "bike_vo2max_intervals"
    assert attempts[0]["status"] == "infeasible"
    # race pace материализуется, но ранжирован вне intent-набора.
    assert attempts[1]["template_key"] == "bike_race_pace"
    assert attempts[1]["status"] == "materialized"
    expected = next(
        item
        for item in attempts
        if item["status"] == "materialized" and item["template_key"] in _TAPER_SHARPENING_KEYS
    )
    assert expected["template_key"] == "bike_neuromuscular_sprints"

    session = materialize_session_template(
        **_TAPER_LONG_RETRY_SELECTION, zone_snapshot=_TAPER_ZONE
    )

    assert session["template_key"] == expected["template_key"]
    assert session["duration_minutes"] == expected["duration_minutes"] == 45
    assert session["duration_minutes"] <= 60
    assert session["materialization_status"] == "materialized"
    assert not session.get("failed_bounds")
    assert planned_session_is_executable(session) is True

    derived = planned_bike_tss_from_steps(
        session["materialized_steps"], session["target_provenance"]
    )
    assert derived["status"] == "derived"
    snapshot = session["parameter_snapshot"]
    assert snapshot["target_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    # 45 минут bike_neuromuscular_sprints при FTP 200 доставляют 31.0 TSS.
    assert snapshot["target_tss"] == pytest.approx(31.0, abs=0.1)
    assert snapshot["requested_tss"] == pytest.approx(50.0, abs=0.01)

    evidence = session["selection_evidence"]
    assert evidence["selected_template_key"] == "bike_neuromuscular_sprints"
    # Обе длительности VO2max внутри капа не проходят его полосу [70, 120].
    assert evidence["skipped_candidates"] == [
        {
            "template_key": "bike_vo2max_intervals",
            "duration_minutes": 35,
            "failed_bounds": ["density_below_minimum"],
        },
        {
            "template_key": "bike_vo2max_intervals",
            "duration_minutes": 40,
            "failed_bounds": ["density_below_minimum"],
        },
    ]
    assert evidence["intent_constraint"] == "taper_long_sharpening"
    assert evidence["intent_excluded_keys"] == [
        "bike_race_pace",
        "bike_aerobic_endurance",
    ]
    assert evidence["role_override"] == "long_to_sharpening"
    assert "reason" not in evidence


def test_fail_closed_selection_keeps_the_candidate_and_records_the_reason():
    """P1: без исполнимой пары (кандидат × длительность) сессия остаётся fail-closed."""
    attempts = _candidate_attempts(_SHORT_QUALITY_SELECTION, _SHORT_QUALITY_ZONE)

    # Единственный кандидат дня уже неисполним.
    assert [item["template_key"] for item in attempts] == ["bike_neuromuscular_sprints"]
    assert attempts[0]["status"] == "infeasible"

    session = materialize_session_template(
        **_SHORT_QUALITY_SELECTION, zone_snapshot=_SHORT_QUALITY_ZONE
    )

    assert session["template_key"] == attempts[0]["template_key"]
    assert session["materialization_status"] == "infeasible"
    assert session["materialized_steps"] == attempts[0]["steps"]
    assert planned_session_is_executable(session) is False
    assert session["selection_evidence"]["skipped_candidates"] == []
    assert session["selection_evidence"]["reason"] == "no_executable_candidate"
    # Вне Taper/Race Week long intent-ограничения нет.
    assert session["selection_evidence"]["intent_constraint"] is None
    assert session["selection_evidence"]["intent_excluded_keys"] == []


def test_fail_closed_session_carries_derived_failed_bounds():
    """P2: fail-closed прескрипция сохраняет derived-границы в сессии."""
    raw = materialize_workout(
        _definition("bike_neuromuscular_sprints"),
        {"duration_minutes": 30, "target_tss": 20.0},
        _SHORT_QUALITY_ZONE,
    )
    assert raw["materialization_status"] == "infeasible"
    # Границы дефиниции: TSS ниже min_tss и плотность ниже min_tss_per_hour.
    assert set(raw["failed_bounds"]) == {"tss_below_minimum", "density_below_minimum"}

    session = materialize_session_template(
        **_SHORT_QUALITY_SELECTION, zone_snapshot=_SHORT_QUALITY_ZONE
    )

    assert session["failed_bounds"] == list(raw["failed_bounds"])
    derived = planned_bike_tss_from_steps(raw["steps"], raw["target_provenance"])
    snapshot = session["parameter_snapshot"]
    # 30 минут bike_neuromuscular_sprints при FTP 160 дают 16.3 TSS.
    assert snapshot["target_tss"] == raw["parameter_snapshot"]["target_tss"] == pytest.approx(
        derived["planned_tss"], abs=0.01
    )
    assert snapshot["target_tss"] == pytest.approx(16.3, abs=0.1)
    assert snapshot["requested_tss"] == pytest.approx(20.0, abs=0.01)


def test_materialized_session_and_brick_legs_expose_failed_bounds_field():
    """P2: ноги brick-обёртки несут то же поле (пустое, если границы целы)."""
    brick = materialize_brick_session(
        phase="Base",
        target_tss=90.0,
        parts={"bike": 60.0, "run": 30.0},
        estimated_duration_minutes=120,
        goal_type="Триатлон",
        zone_snapshot=_TAPER_ZONE,
    )
    assert brick["kind"] == "composite"
    assert brick["materialization_status"] == "materialized"
    assert [leg["failed_bounds"] for leg in brick["legs"]] == [[], []]

    session = materialize_session_template(
        phase="Build",
        session_role="easy",
        sport="bike",
        goal_type="Триатлон",
        target_tss=45.0,
        estimated_duration_minutes=90,
        zone_snapshot=_TAPER_ZONE,
    )
    assert session["materialization_status"] == "materialized"
    # Исполнимая сессия не объявляет провал границ (ключ не появляется, чтобы
    # не расходиться с allow-list проекции дня).
    assert not session.get("failed_bounds")


def test_rescale_infeasible_single_keeps_derived_target_tss():
    """P2: неисполнимый rescale не подменяет derived-нагрузку бюджетом."""
    base = materialize_session_template(
        phase="Build",
        session_role="quality",
        sport="bike",
        goal_type="Триатлон",
        target_tss=60.0,
        estimated_duration_minutes=60,
        zone_snapshot=_TAPER_ZONE,
    )
    # ``sport`` штампует вызывающая сторона (materialize_day_sessions), а
    # power-ветка rescale читает его из сессии.
    base["sport"] = "bike"
    assert base["materialization_status"] == "materialized"
    assert base["parameter_snapshot"]["target_tss"] == pytest.approx(65.2, abs=0.1)

    scaled = rescale_materialized_session(base, target_tss=30.0, parts={"bike": 30.0})

    # Длительность считается от эффективной нагрузки прескрипции (65.2).
    assert scaled["duration_minutes"] == max(
        1,
        round(
            base["duration_minutes"]
            * 30.0
            / base["parameter_snapshot"]["target_tss"]
        ),
    )
    assert scaled["materialization_status"] == "infeasible"
    snapshot = scaled["parameter_snapshot"]
    derived = planned_bike_tss_from_steps(
        scaled["materialized_steps"], scaled["target_provenance"]
    )
    assert derived["status"] == "derived"
    assert snapshot["requested_tss"] == pytest.approx(30.0, abs=0.01)
    # До фикса в target_tss стоял запрошенный бюджет (30.0), а derived-нагрузка
    # пряталась только в planned_tss; для этой конфигурации derived = 30.2.
    assert snapshot["target_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    assert snapshot["planned_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    assert scaled["total_tss"] == pytest.approx(snapshot["target_tss"], abs=0.01)
    assert scaled["failed_bounds"] == ["duration_below_minimum", "tss_below_minimum"]


def test_rescale_infeasible_composite_leg_keeps_derived_target_tss():
    """P2: та же коррекция для ноги composite-сессии."""
    brick = materialize_brick_session(
        phase="Base",
        target_tss=90.0,
        parts={"bike": 60.0, "run": 30.0},
        estimated_duration_minutes=120,
        goal_type="Триатлон",
        zone_snapshot=_TAPER_ZONE,
    )
    assert brick["kind"] == "composite"
    request = 40.0
    parts = {
        "bike": round(request * 60.0 / 90.0, 1),  # 26.7 — доля вело в запросе
        "run": round(request * 30.0 / 90.0, 1),  # 13.3
    }

    scaled = rescale_materialized_session(brick, target_tss=request, parts=parts)

    bike_leg = next(leg for leg in scaled["legs"] if leg["sport"] == "bike")
    assert bike_leg["materialization_status"] == "infeasible"
    assert bike_leg["failed_bounds"] == ["duration_below_minimum"]
    snap = bike_leg["parameter_snapshot"]
    derived = planned_bike_tss_from_steps(
        bike_leg["materialized_steps"], bike_leg["target_provenance"]
    )
    assert derived["status"] == "derived"
    assert snap["requested_tss"] == pytest.approx(parts["bike"], abs=0.01)
    # До фикса в target_tss лежало 26.7 (запрос), а derived 26.8 был скрыт.
    assert snap["target_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    assert snap["target_tss"] != pytest.approx(snap["requested_tss"], abs=0.01)
    assert bike_leg["target_tss"] == pytest.approx(snap["target_tss"], abs=0.01)

    parent = scaled["parameter_snapshot"]
    assert parent["requested_tss"] == pytest.approx(request, abs=0.01)
    assert parent["target_tss"] == pytest.approx(
        sum(float(leg["target_tss"]) for leg in scaled["legs"]), abs=0.01
    )
    # 26.8 (вело) + 13.3 (бег) вместо запрошенных 40.0.
    assert parent["target_tss"] == pytest.approx(40.1, abs=0.1)
    assert scaled["total_tss"] == pytest.approx(parent["target_tss"], abs=0.01)


# --- finding 4: недельный rebalance масштабируется от эффективной нагрузки ---

_REBALANCE_START = date(2026, 7, 6)
_REBALANCE_AS_OF = date(2026, 7, 13)
# Индекс 2 (2026-07-08) делает bike_aerobic_endurance «свежим» для билдера.
# Индексы 9 и 11 — easy-дни внутри окна (as_of; as_of+7], которые rebalance
# имеет право сокращать: качественный стимул с бюджетом 70 TSS (derived-нагрузка
# заметно ниже) и восстановительный стимул с бюджетом 40 TSS.
_REBALANCE_EASY_BIKE_DAYS = {2: 45.0, 9: 70.0, 11: 40.0}
_REBALANCE_QUALITY_INDEX = 9
_REBALANCE_RECOVERY_INDEX = 11


def _weekly_rebalance_plan() -> dict:
    """Реальная цепочка билдера: build_daily_session_templates → проекция дня."""
    daily = []
    for index in range(21):
        current = _REBALANCE_START + timedelta(days=index)
        tss = _REBALANCE_EASY_BIKE_DAYS.get(index, 0.0)
        daily.append(
            (
                datetime.combine(current, datetime.min.time()),
                tss,
                {"bike": tss, "run": 0.0, "swim": 0.0},
            )
        )
    weekly = []
    for week_index in range(3):
        day_roles = ["off"] * 7
        for index in _REBALANCE_EASY_BIKE_DAYS:
            if index // 7 == week_index:
                day_roles[index % 7] = "easy"
        weekly.append(
            {
                "phase": "Build",
                "day_roles": day_roles,
                "day_focuses": ["—"] * 7,
            }
        )
    templates = build_daily_session_templates(
        daily,
        weekly,
        "triathlon",
        "olympic",
        zone_snapshot=_TAPER_ZONE,
    )
    plan = {
        "goal_type": "triathlon",
        "distance": "olympic",
        "start_week": _REBALANCE_START,
        "daily_plan": daily,
        "session_templates": templates,
        "weekly_summary": weekly,
        "weekly_tss_plan": [],
        "protected_dates": [],
        "constraint_summary": {},
        "near_term_edit_version": 0,
    }
    plan["daily_plan"] = project_daily_plan_from_session_templates(daily, templates)
    return ensure_session_identities(plan)


def _over_plan_reconciliation() -> dict:
    """Over-plan неделя: 180 факт против 100 плана даёт бюджет сокращения."""
    return {
        "rule_version": MATCH_RULE_VERSION,
        "base_checkpoint_id": 63,
        "data_quality": {
            "planned_session_count": 5,
            "matched_count": 4,
            "ambiguous_count": 0,
            "coverage": 0.8,
            "status": "sufficient",
            "reasons": [],
        },
        "metrics": {
            "planned_tss": 100.0,
            "matched_actual_tss": 180.0,
            "unplanned_tss": 0.0,
            "total_actual_tss": 180.0,
        },
        "rows": [],
        "unplanned_activities": [],
    }


def _approved_rebalance(plan: dict) -> tuple[dict, dict]:
    """Возвращает (preview, применённый план) для одного и того же fixture."""
    preview = build_weekly_rebalance_preview(
        plan,
        _over_plan_reconciliation(),
        as_of=_REBALANCE_AS_OF,
        protected_dates=set(),
    )
    assert preview["status"] == "proposal"
    return preview, apply_weekly_rebalance_preview(plan, preview)


def _change_for(preview: dict, index: int) -> dict:
    change = next((item for item in preview["changes"] if item["index"] == index), None)
    assert change is not None, preview
    return change


def test_weekly_rebalance_scales_the_quality_day_from_the_effective_load():
    """P1: правка недели делит на эффективную нагрузку, а не на старый бюджет."""
    plan = _weekly_rebalance_plan()
    index = _REBALANCE_QUALITY_INDEX
    before = plan["session_templates"][index]["sessions"][0]
    before_snapshot = before["parameter_snapshot"]

    # Гарантии репро: качественный стимул, бюджет заметно выше нагрузки.
    assert before["template_key"] == "bike_neuromuscular_sprints"
    assert before["materialization_status"] == "materialized"
    assert before_snapshot["requested_tss"] == pytest.approx(70.0, abs=0.01)
    # 60 минут bike_neuromuscular_sprints при FTP 200 доставляют 40.2 TSS.
    assert before_snapshot["target_tss"] == pytest.approx(40.2, abs=0.1)
    assert before_snapshot["requested_tss"] > 1.5 * before_snapshot["target_tss"]
    # Строка дня несёт эффективную нагрузку, а не исторический бюджет.
    assert plan["daily_plan"][index][1] == pytest.approx(
        before_snapshot["target_tss"], abs=0.1
    )

    preview, updated = _approved_rebalance(plan)
    change = _change_for(preview, index)
    assert change["before_tss"] == pytest.approx(before_snapshot["target_tss"], abs=0.1)

    after = updated["session_templates"][index]["sessions"][0]
    after_snapshot = after["parameter_snapshot"]

    # Длительность масштабируется от текущей эффективной нагрузки: 40.2 → 34.4
    # TSS даёт 51 минуту. От бюджета 70 TSS выходило 29 минут.
    expected_duration = max(
        1,
        round(
            before["duration_minutes"]
            * change["after_tss"]
            / before_snapshot["target_tss"]
        ),
    )
    assert after["duration_minutes"] == expected_duration == 51

    derived = planned_bike_tss_from_steps(
        after["materialized_steps"], after["target_provenance"]
    )
    assert derived["status"] == "derived"
    assert after_snapshot["target_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    # Утверждённое сокращение доставлено: 31.7 TSS против 14.5 TSS, которые
    # получались при делении на бюджет 70 (29 минут, без единого графика).
    # Остаточный density_below_minimum — граница самой дефиниции:
    # bike_neuromuscular_sprints держит плотность 40 TSS/ч, поэтому сокращение
    # ниже неё остаётся fail-closed, а не маскируется.
    assert derived["planned_tss"] >= 0.9 * change["after_tss"]
    assert after_snapshot["requested_tss"] == pytest.approx(change["after_tss"], abs=0.1)
    assert after["total_tss"] == pytest.approx(after_snapshot["target_tss"], abs=0.01)


def test_weekly_rebalance_keeps_an_approved_reduction_deliverable():
    """P1: сокращённый день остаётся доставляемым и отдаёт запрошенную нагрузку."""
    plan = _weekly_rebalance_plan()
    index = _REBALANCE_RECOVERY_INDEX
    before = plan["session_templates"][index]["sessions"][0]
    before_snapshot = before["parameter_snapshot"]

    assert before["template_key"] == "bike_recovery_spin"
    assert before["materialization_status"] == "materialized"
    assert before_snapshot["requested_tss"] == pytest.approx(40.0, abs=0.01)
    # 75 минут bike_recovery_spin при FTP 200 доставляют 28.6 TSS.
    assert before_snapshot["target_tss"] == pytest.approx(28.6, abs=0.1)
    assert before_snapshot["requested_tss"] > 1.3 * before_snapshot["target_tss"]

    preview, updated = _approved_rebalance(plan)
    change = _change_for(preview, index)

    after = updated["session_templates"][index]["sessions"][0]
    after_snapshot = after["parameter_snapshot"]

    # 28.6 → 24.4 TSS даёт 64 минуты и materialized-прескрипцию. От бюджета
    # 40 TSS получалось 46 минут и 17.5 TSS — 72% от утверждённой правки.
    expected_duration = max(
        1,
        round(
            before["duration_minutes"]
            * change["after_tss"]
            / before_snapshot["target_tss"]
        ),
    )
    budget_reference_duration = max(
        1,
        round(
            before["duration_minutes"]
            * change["after_tss"]
            / before_snapshot["requested_tss"]
        ),
    )
    assert after["duration_minutes"] == expected_duration
    assert after["duration_minutes"] > budget_reference_duration
    assert after["materialization_status"] == "materialized"
    assert not after.get("failed_bounds")

    derived = planned_bike_tss_from_steps(
        after["materialized_steps"], after["target_provenance"]
    )
    assert derived["status"] == "derived"
    assert derived["planned_tss"] == pytest.approx(change["after_tss"], abs=0.1)
    assert after_snapshot["target_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)
    assert after_snapshot["requested_tss"] == pytest.approx(change["after_tss"], abs=0.1)
    assert after["total_tss"] == pytest.approx(derived["planned_tss"], abs=0.01)


def test_rescale_keeps_the_budget_reference_for_records_without_a_derived_load():
    """Legacy-записи без derived NP-нагрузки сохраняют бюджетный знаменатель."""
    # До #554 ``parameter_snapshot`` нёс только бюджет (= target_tss), поэтому
    # масштаб считается от него — 60 → 40 минут при запросе 45 → 30 TSS.
    run_definition = _definition("run_aerobic_endurance")
    materialized = materialize_workout(
        run_definition,
        {"duration_minutes": 60, "target_tss": 45.0},
        {},
    )
    legacy = {
        "sport": "run",
        "materialization_status": materialized["materialization_status"],
        "duration_minutes": 60,
        "total_tss": materialized["parameter_snapshot"]["target_tss"],
        "parameter_snapshot": materialized["parameter_snapshot"],
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized["target_provenance"],
        "definition_snapshot": materialized["definition_snapshot"],
    }
    assert "requested_tss" not in legacy["parameter_snapshot"]
    assert "planned_tss_method" not in legacy["parameter_snapshot"]

    scaled = rescale_materialized_session(legacy, target_tss=30.0, parts={"run": 30.0})

    assert scaled["duration_minutes"] == 40
    assert scaled["materialization_status"] == "materialized"
    assert scaled["parameter_snapshot"]["target_tss"] == pytest.approx(30.0, abs=0.1)
