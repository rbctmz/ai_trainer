"""Issue #554 falsifier: delivered quality-bike load must equal its own power prescription.

Цепочка `build_plan → materialization → delivery` проверяется целиком, а не по частям:
определение каталога материализуется в упорядоченную power-прескрипцию, из неё
собирается сессия плана (как это делает планировщик), дневной скаляр проецируется в
`daily_plan`, и нативный delivery-путь публикует провайдерское событие. Инвариант:
объявленная в событии нагрузка (`icu_training_load`) равна TSS, выведенному из той же
power-прескрипции, которую это событие и доставляет.

До правки качественные шаблоны сохраняли generic density fallback, поэтому событие
несло бюджет недели (например 63 TSS на 50 минут), который сама прескрипция выдать не
может (~39 TSS). Тест падает на таком состоянии и проходит после выравнивания.

Порог сравнения — документированный tolerance округления провайдерской нагрузки
(±0.5 TSS после `round`), а не произвольный допуск.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from models.intervals_workout_delivery import build_delivery_events
from models.session_identity import ensure_session_identities
from models.workout_catalog import (
    catalog_definitions,
    materialize_workout,
    planned_bike_tss_from_steps,
)

pytestmark = pytest.mark.smoke

FTP = 160.0
DELIVERY_DAY = "2026-08-21"
QUALITY_TEMPLATES = (
    "bike_tempo_sweet_spot",
    "bike_threshold_intervals",
    "bike_vo2max_intervals",
    "bike_neuromuscular_sprints",
    "bike_race_pace",
)
# Санитизированное воспроизведение из issue #554: 50 минут tempo при запросе 63 TSS.
REPRODUCTION = ("bike_tempo_sweet_spot", 50, 63.0)


def _definition(template_key: str):
    match = next((item for item in catalog_definitions() if item.template_key == template_key), None)
    assert match is not None, f"no catalog definition {template_key}"
    return match


def _materialize(template_key: str, *, duration_minutes: int, requested_tss: float) -> dict:
    return materialize_workout(
        _definition(template_key),
        {"duration_minutes": duration_minutes, "target_tss": requested_tss},
        {"ftp": FTP},
    )


# Длительности перебираются, потому что плотность выведенной прескрипции зависит от
# длительности: один и тот же шаблон на 60 минутах может не попасть в свою полосу, а на
# 45–50 — попасть. Тест ищет исполнимую конфигурацию, а не зашивает её числом.
CANDIDATE_DURATIONS = (40, 45, 50, 60, 75, 90, 120)


def _request_candidates(template_key: str, duration_minutes: int) -> list[float]:
    definition = _definition(template_key)
    return [
        round(definition.max_tss_per_hour * duration_minutes / 60.0, 1),
        round(
            (definition.min_tss_per_hour + definition.max_tss_per_hour)
            / 2.0
            * duration_minutes
            / 60.0,
            1,
        ),
        round(definition.min_tss_per_hour * duration_minutes / 60.0, 1),
    ]


def _feasible_config(template_key: str) -> tuple[int, float]:
    """Первая конфигурация (минуты, запрос), которую прескрипция честно выдаёт."""
    for duration_minutes in CANDIDATE_DURATIONS:
        for requested in _request_candidates(template_key, duration_minutes):
            materialized = _materialize(
                template_key, duration_minutes=duration_minutes, requested_tss=requested
            )
            if materialized["materialization_status"] == "materialized":
                return duration_minutes, requested
    raise AssertionError(f"{template_key}: no feasible configuration in the candidate grid")


def _session(template_key: str, *, duration_minutes: int, requested_tss: float) -> dict:
    materialized = _materialize(
        template_key, duration_minutes=duration_minutes, requested_tss=requested_tss
    )
    if materialized["materialization_status"] != "materialized":
        return materialized
    definition = _definition(template_key)
    snapshot = dict(materialized["parameter_snapshot"])
    return {
        "sport": "bike",
        "sport_label": "вело",
        "session_role": "quality",
        "session_focus": definition.display_name,
        "duration_minutes": duration_minutes,
        "total_tss": snapshot.get("target_tss"),
        "template_key": definition.template_key,
        "export_name": definition.display_name,
        "description": f"Total TSS: {snapshot.get('target_tss')}\nОценка длительности: {duration_minutes} мин",
        "materialization_status": materialized["materialization_status"],
        "catalog_version": materialized["catalog_version"],
        "materializer_rule_version": materialized["rule_version"],
        "definition_snapshot": materialized["definition_snapshot"],
        "parameter_snapshot": snapshot,
        "materialized_steps": materialized["steps"],
        "target_provenance": materialized["target_provenance"],
        "structure_status": materialized["structure_status"],
        "structure_evidence": materialized["structure_evidence"],
    }


def _plan(session: dict) -> dict:
    """Минимальный план в той же форме, что строит `build_plan` для одного дня."""
    total = float(session.get("total_tss") or 0.0)
    return ensure_session_identities(
        {
            "daily_plan": [(datetime.fromisoformat(DELIVERY_DAY), total, {"bike": total})],
            "session_templates": [
                {
                    "date": DELIVERY_DAY,
                    "phase": "Build",
                    "sport": "bike",
                    "session_role": "quality",
                    "sessions": [session],
                }
            ],
            "weekly_summary": [
                {"weekly_tss": int(round(total)), "bike": total, "run": 0.0, "swim": 0.0}
            ],
            "weekly_tss_plan": [int(round(total))],
        }
    )


def _prescription_tss(session: dict) -> float:
    evidence = planned_bike_tss_from_steps(session["materialized_steps"], session["target_provenance"])
    assert isinstance(evidence, dict), evidence
    assert evidence.get("status") == "derived", evidence
    return float(evidence["planned_tss"])


def _deliver(session: dict) -> dict:
    events = build_delivery_events(_plan(session), [DELIVERY_DAY])
    assert len(events) == 1, events
    return events[0]


@pytest.mark.parametrize("template_key", QUALITY_TEMPLATES)
def test_delivered_quality_bike_load_equals_its_own_power_prescription(template_key: str) -> None:
    """Пять качественных шаблонов: доставленная нагрузка = TSS их power-прескрипции."""
    duration_minutes, requested = _feasible_config(template_key)
    session = _session(template_key, duration_minutes=duration_minutes, requested_tss=requested)
    assert session["materialization_status"] == "materialized", session["materialization_status"]

    derived = _prescription_tss(session)
    event = _deliver(session)

    assert event["icu_training_load"] == int(round(derived)), (
        f"{template_key}: доставлено {event['icu_training_load']} TSS, "
        f"прескрипция даёт {derived} TSS (запрошено {requested})"
    )
    # Событие доставляет ту же прескрипцию, из которой выведена нагрузка.
    assert event["moving_time"] == sum(
        int(step["duration_seconds"]) for step in session["materialized_steps"]
    )
    # Версия метода аудируема: качественные структуры выводятся NP-правилом, а не
    # старым суммированием середин зон.
    assert session["parameter_snapshot"]["planned_tss_method"] == "prescription_np_tss_v1"


def test_sanitized_reproduction_no_longer_publishes_the_inflated_budget() -> None:
    """50 минут tempo при запросе 63 TSS: доставка несёт честные ~39, а не 63."""
    template_key, duration_minutes, requested = REPRODUCTION
    session = _session(template_key, duration_minutes=duration_minutes, requested_tss=requested)
    assert session["materialization_status"] == "materialized", session["materialization_status"]

    derived = _prescription_tss(session)
    event = _deliver(session)

    assert event["icu_training_load"] == int(round(derived)), event["icu_training_load"]
    assert derived < requested - 5, f"прескрипция всё ещё выдаёт запрошенный бюджет: {derived}"
    # Расхождение бюджета и исполнимой сессии не скрыто: запрос сохранён как evidence.
    snapshot = session["parameter_snapshot"]
    assert float(snapshot["requested_tss"]) == pytest.approx(requested, abs=0.05)
    assert float(snapshot["target_tss"]) == pytest.approx(derived, abs=0.05)


def _infeasible_with_prescription(template_key: str) -> tuple[int, float]:
    """Конфигурация, где прескрипция выведена, но не проходит объявленные границы."""
    for duration_minutes in CANDIDATE_DURATIONS:
        for requested in _request_candidates(template_key, duration_minutes):
            materialized = _materialize(
                template_key, duration_minutes=duration_minutes, requested_tss=requested
            )
            if (
                materialized["materialization_status"] != "materialized"
                and materialized["parameter_snapshot"].get("planned_tss_method")
                == "prescription_np_tss_v1"
            ):
                return duration_minutes, requested
    raise AssertionError(f"{template_key}: no infeasible-with-prescription configuration found")


def test_infeasible_quality_budget_fails_closed_instead_of_publishing_a_fiction() -> None:
    """Запрос, который прескрипция выдать не может, не превращается в доставленную нагрузку."""
    template_key = REPRODUCTION[0]
    duration_minutes, requested = _infeasible_with_prescription(template_key)
    infeasible = _materialize(
        template_key, duration_minutes=duration_minutes, requested_tss=requested
    )

    assert infeasible["materialization_status"] != "materialized", infeasible["materialization_status"]
    snapshot = dict(infeasible["parameter_snapshot"])
    assert snapshot["planned_tss_method"] == "prescription_np_tss_v1"
    assert infeasible["failed_bounds"], infeasible
    # Расхождение объявлено явно, а не спрятано в сессии.
    assert float(snapshot["target_tss"]) < float(snapshot["requested_tss"])

    session = _session(template_key, duration_minutes=duration_minutes, requested_tss=requested)
    session.update(
        {
            "materialization_status": infeasible["materialization_status"],
            "parameter_snapshot": snapshot,
            "materialized_steps": infeasible["steps"],
            "target_provenance": infeasible["target_provenance"],
            "total_tss": float(requested),
            "failed_bounds": list(infeasible["failed_bounds"]),
        }
    )
    with pytest.raises(ValueError):
        _deliver(session)
