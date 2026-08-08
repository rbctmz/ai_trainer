"""Матчинг плановых шагов с фактическими интервалами «по репетициям» (#383).

Сопоставляет work-шаги плана (``project_planned_intervals``) с детектированными
интервалами факта из Intervals.icu (#390) по порядку и длительности. Главная
цель — показать «план 3×(12' @90% / 4' @55%) → факт 3×(11'40\"/4'10\")»: какие
рабочие репетиции выполнены, насколько точно по длительности и зоне.

Чистая функция (нет I/O/БД), тестируется изолированно. Матчинг — по work-шагам;
разминка/заминка/rest в плане учитываются как контекст порядка, но фокус и
сводка — по work. tolerance по длительности — 30% (нечёткое сопоставление).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


_DURATION_TOLERANCE = 0.30  # ±30% по длительности — нечёткое сопоставление.


def _work_steps(planned: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [step for step in planned if str(step.get("type") or "") == "work"]


def _actual_seconds(iv: Mapping[str, Any]) -> int | None:
    value = iv.get("moving_time")
    if value is None:
        value = iv.get("elapsed_time")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _duration_delta(planned_seconds: int, actual_seconds: int) -> float:
    """Relative delta: 0.0 = exact; negative = actual shorter."""
    if planned_seconds <= 0:
        return 0.0
    return (actual_seconds - planned_seconds) / planned_seconds


def _within_tolerance(planned_seconds: int, actual_seconds: int) -> bool:
    if planned_seconds <= 0:
        return True
    return abs(_duration_delta(planned_seconds, actual_seconds)) <= _DURATION_TOLERANCE


def _match_step_to_actual(
    step: Mapping[str, Any], actuals: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any] | None, int | None]:
    """First actual interval matching the step's planned duration within tolerance.

    Returns (matched_actual | None, its index | None). ``actuals`` are scanned in
    order; the first within tolerance wins (greedy by order — work reps are
    typically similar but executed in sequence).
    """
    planned_seconds = int(step.get("duration_seconds") or 0)
    for index, iv in enumerate(actuals):
        actual_seconds = _actual_seconds(iv)
        if actual_seconds is None:
            continue
        if _within_tolerance(planned_seconds, actual_seconds):
            return iv, index
    return None, None


def match_plan_vs_fact(
    planned: Any,
    actual: Any,
) -> dict[str, Any]:
    """Match planned work steps to actual detected intervals (#383).

    Returns ``{matches: [...], summary}``. Each match is::

        {
          "planned": {duration_seconds, target_zone, ...},   # from plan
          "actual": {moving_time, distance_km, ...} | None,  # from fact or None
          "duration_delta": float | None,                    # relative; None if unmatched
          "zone": {"planned": int|None, "actual": int|None},
          "matched": bool,
        }

    ``summary`` counts planned/actual/matched and is empty-friendly. Inputs that
    are not lists return an empty match (fail-open — the card hides the section).
    """
    if not isinstance(planned, list) or not isinstance(actual, list):
        return {"matches": [], "summary": _empty_summary()}

    work_steps = _work_steps(planned)
    if not work_steps:
        return {
            "matches": [],
            "summary": {
                "planned_work_steps": 0,
                "actual_intervals": len(actual),
                "matched": 0,
            },
        }

    # Match against a copy so consumed indices aren't reused across identical reps.
    remaining = list(actual)
    matches: list[dict[str, Any]] = []
    matched_count = 0
    for step in work_steps:
        matched, index = _match_step_to_actual(step, remaining)
        if matched is None or index is None:
            matches.append(_unmatched(step))
            continue
        remaining.pop(index)
        matched_count += 1
        matches.append(_matched(step, matched))

    return {
        "matches": matches,
        "summary": {
            "planned_work_steps": len(work_steps),
            "actual_intervals": len(actual),
            "matched": matched_count,
        },
    }


def _matched(step: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    planned_seconds = int(step.get("duration_seconds") or 0)
    actual_seconds = _actual_seconds(actual) or 0
    return {
        "planned": dict(step),
        "actual": dict(actual),
        "duration_delta": (
            round(_duration_delta(planned_seconds, actual_seconds), 2)
            if planned_seconds > 0
            else None
        ),
        "zone": {
            "planned": _planned_zone(step),
            "actual": _compact(actual.get("zone")),
        },
        "matched": True,
    }


def _unmatched(step: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "planned": dict(step),
        "actual": None,
        "duration_delta": None,
        "zone": {"planned": _planned_zone(step), "actual": None},
        "matched": False,
    }


def _planned_zone(step: Mapping[str, Any]) -> int | None:
    target = step.get("target_zone")
    if not isinstance(target, Mapping):
        return None
    return _compact(target.get("relative_high"))


def _compact(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, 1)


def _empty_summary() -> dict[str, Any]:
    return {"planned_work_steps": 0, "actual_intervals": 0, "matched": 0}


def plan_replanned_after_delivery(
    match: Any,
    checkpoint: Any,
    deliveries: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Флаг рассинхрона с устройством (#398).

    Когда план на дату был доставлен в Intervals.icu (старая версия), а затем
    переплан (recovery_replan) — атлет мог тренироваться по предыдущей версии
    (кейс 2026-08-08: доставка 06:41, тренировка в 09:06 по старому плану).
    Возвращает описание риска или ``None``, если план не перепланирован либо
    доставки более ранней версии для этой даты не было.
    """
    if not isinstance(match, Mapping):
        return None
    checkpoint_id = match.get("base_checkpoint_id")
    session_date = str(match.get("session_date") or "")
    if checkpoint_id is None or not session_date:
        return None
    if not isinstance(checkpoint, Mapping):
        return None
    source = str(checkpoint.get("checkpoint_source") or "").strip().lower()
    if source != "recovery_replan":
        return None

    earlier = [
        item
        for item in deliveries
        if session_date in [str(value) for value in (item.get("dates") or [])]
        and item.get("checkpoint_id") is not None
        and int(item["checkpoint_id"]) < int(checkpoint_id)
    ]
    if not earlier:
        return None
    latest = max(earlier, key=lambda item: str(item.get("created_at") or ""))
    return {
        "reason": "replanned_after_delivery",
        "delivered_at": latest.get("created_at"),
        "delivery_checkpoint_id": latest.get("checkpoint_id"),
        "replanned_checkpoint_id": checkpoint_id,
    }


__all__ = ["match_plan_vs_fact", "plan_replanned_after_delivery"]
