"""Сопоставление плановых этапов с фактической структурой тренировки (#383).

Сопоставляет work-шаги плана (``project_planned_intervals``) с детектированными
интервалами факта из Intervals.icu (#390) по порядку и длительности. Главная
цель — показать «план 3×(12' @90% / 4' @55%) → факт 3×(11'40\"/4'10\")»: какие
рабочие репетиции выполнены, насколько точно по длительности и зоне.

Если фактические участки образуют непрерывную временную шкалу, несколько
соседних кругов могут составлять один этап плана (например Auto Lap внутри
длинной работы). Для разреженного факта без надёжных смещений сохраняется
осторожный режим один-к-одному только для work-шагов. Допуск длительности — 30%.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


_DURATION_TOLERANCE = 0.30  # ±30% по длительности — нечёткое сопоставление.
_TIMELINE_GAP_TOLERANCE_SECONDS = 2


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


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
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
    *,
    sport: str | None = None,
    athlete_profile: Mapping[str, Any] | None = None,
    actual_source: str | None = None,
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
        return _empty_result()

    if _is_contiguous_timeline(actual):
        return _match_contiguous_timeline(
            planned,
            actual,
            sport=sport,
            athlete_profile=athlete_profile,
        )

    # Garmin laps are raw device boundaries, not detected work intervals. If
    # their elapsed timeline cannot be trusted, greedy duration matching could
    # label a warm-up/auto-lap as completed work. Fail closed instead.
    if str(actual_source or "").strip().lower() == "garmin":
        work_steps = _work_steps(planned)
        return {
            "alignment_mode": "work_intervals",
            "step_matches": [],
            "matches": [_unmatched(step) for step in work_steps],
            "summary": {
                "planned_steps": len(planned),
                "planned_work_steps": len(work_steps),
                "actual_intervals": len(actual),
                "matched_steps": 0,
                "matched": 0,
            },
        }

    work_steps = _work_steps(planned)
    if not work_steps:
        return {
            "alignment_mode": "work_intervals",
            "step_matches": [],
            "matches": [],
            "summary": {
                "planned_steps": len(planned),
                "planned_work_steps": 0,
                "actual_intervals": len(actual),
                "matched_steps": 0,
                "matched": 0,
            },
        }

    # Advance beyond every match so later planned steps cannot consume an actual
    # interval that occurred before the previous match.
    remaining = list(actual)
    matches: list[dict[str, Any]] = []
    matched_count = 0
    for step in work_steps:
        matched, index = _match_step_to_actual(step, remaining)
        if matched is None or index is None:
            matches.append(_unmatched(step))
            continue
        remaining = remaining[index + 1 :]
        matched_count += 1
        matches.append(_matched(step, matched))

    return {
        "alignment_mode": "work_intervals",
        "step_matches": [],
        "matches": matches,
        "summary": {
            "planned_steps": len(planned),
            "planned_work_steps": len(work_steps),
            "actual_intervals": len(actual),
            "matched_steps": matched_count,
            "matched": matched_count,
        },
    }


def _is_contiguous_timeline(actual: Sequence[Mapping[str, Any]]) -> bool:
    """True when intervals cover one timeline from zero without material gaps."""
    if not actual:
        return False
    cursor = 0
    for interval in actual:
        if not isinstance(interval, Mapping):
            return False
        start = _number(interval.get("start_index"))
        duration = _timeline_seconds(interval)
        if start is None or duration is None or duration <= 0:
            return False
        if abs(start - cursor) > _TIMELINE_GAP_TOLERANCE_SECONDS:
            return False
        cursor = int(round(start)) + duration
    return True


def _timeline_seconds(interval: Mapping[str, Any]) -> int | None:
    """Timeline span: Garmin start offsets accumulate elapsed, not moving time."""
    elapsed = _number(interval.get("elapsed_time"))
    if elapsed is not None:
        return int(round(elapsed))
    return _actual_seconds(interval)


def _match_contiguous_timeline(
    planned: Sequence[Mapping[str, Any]],
    actual: Sequence[Mapping[str, Any]],
    *,
    sport: str | None,
    athlete_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    groups = _partition_actual_by_planned_duration(planned, actual)
    step_matches: list[dict[str, Any]] = []
    for step, group in zip(planned, groups):
        aggregated = _aggregate_actual_group(group) if group else None
        planned_seconds = int(step.get("duration_seconds") or 0)
        actual_seconds = _actual_seconds(aggregated or {})
        matched = bool(
            aggregated is not None
            and actual_seconds is not None
            and _within_tolerance(planned_seconds, actual_seconds)
        )
        step_matches.append(
            _timeline_match(
                step,
                aggregated,
                matched,
                sport=sport,
                athlete_profile=athlete_profile,
            )
        )

    work_matches = [
        item
        for item in step_matches
        if str(item["planned"].get("type") or "") == "work"
    ]
    return {
        "alignment_mode": "timeline",
        "step_matches": step_matches,
        "matches": work_matches,
        "summary": {
            "planned_steps": len(planned),
            "planned_work_steps": len(work_matches),
            "actual_intervals": len(actual),
            "matched_steps": sum(1 for item in step_matches if item["matched"]),
            "matched": sum(1 for item in work_matches if item["matched"]),
            "intensity_assessed": sum(
                1
                for item in step_matches
                if item["intensity"]["status"] != "unavailable"
            ),
            "intensity_within": sum(
                1
                for item in step_matches
                if item["intensity"]["status"] == "within"
            ),
        },
    }


def _partition_actual_by_planned_duration(
    planned: Sequence[Mapping[str, Any]],
    actual: Sequence[Mapping[str, Any]],
) -> list[list[Mapping[str, Any]]]:
    """Globally best ordered partition of actual intervals across plan steps."""
    step_count = len(planned)
    actual_count = len(actual)
    if step_count == 0:
        return []

    durations = [_actual_seconds(interval) or 0 for interval in actual]
    prefix = [0]
    for duration in durations:
        prefix.append(prefix[-1] + duration)

    infinity = float("inf")
    costs = [[infinity] * (actual_count + 1) for _ in range(step_count + 1)]
    previous = [[-1] * (actual_count + 1) for _ in range(step_count + 1)]
    costs[0][0] = 0.0

    for step_index in range(1, step_count + 1):
        planned_seconds = int(planned[step_index - 1].get("duration_seconds") or 0)
        for consumed in range(actual_count + 1):
            for group_start in range(consumed + 1):
                prior = costs[step_index - 1][group_start]
                if prior == infinity:
                    continue
                group_seconds = prefix[consumed] - prefix[group_start]
                group_cost = _partition_cost(planned_seconds, group_seconds)
                candidate = prior + group_cost
                if candidate < costs[step_index][consumed]:
                    costs[step_index][consumed] = candidate
                    previous[step_index][consumed] = group_start

    groups: list[list[Mapping[str, Any]]] = []
    consumed = actual_count
    for step_index in range(step_count, 0, -1):
        group_start = previous[step_index][consumed]
        if group_start < 0:
            group_start = consumed
        groups.append(list(actual[group_start:consumed]))
        consumed = group_start
    groups.reverse()
    return groups


def _partition_cost(planned_seconds: int, actual_seconds: int) -> float:
    if actual_seconds <= 0:
        return 1.5
    if planned_seconds <= 0:
        return 0.0
    return abs(_duration_delta(planned_seconds, actual_seconds))


def _aggregate_actual_group(
    intervals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    durations = [_actual_seconds(interval) or 0 for interval in intervals]
    total_seconds = sum(durations)
    result: dict[str, Any] = {
        "start_index": intervals[0].get("start_index"),
        "moving_time": total_seconds,
        "elapsed_time": sum(
            int(round(_number(interval.get("elapsed_time")) or duration))
            for interval, duration in zip(intervals, durations)
        ),
        "source_interval_count": len(intervals),
        "source_interval_durations": durations,
    }

    for field in (
        "average_watts",
        "average_heartrate",
        "average_cadence",
        "average_speed",
    ):
        weighted = _weighted_average(intervals, durations, field)
        if weighted is not None:
            result[field] = weighted

    for field in ("distance_km", "training_load"):
        values = [_number(interval.get(field)) for interval in intervals]
        present = [value for value in values if value is not None]
        if present:
            result[field] = _compact(sum(present), digits=2)

    minimums = [_number(interval.get("min_heartrate")) for interval in intervals]
    maximums = [_number(interval.get("max_heartrate")) for interval in intervals]
    if any(value is not None for value in minimums):
        result["min_heartrate"] = _compact(
            min(value for value in minimums if value is not None)
        )
    if any(value is not None for value in maximums):
        result["max_heartrate"] = _compact(
            max(value for value in maximums if value is not None)
        )

    zone_seconds: dict[int | float, int] = {}
    for interval, duration in zip(intervals, durations):
        zone = _compact(interval.get("zone"))
        if zone is not None:
            zone_seconds[zone] = zone_seconds.get(zone, 0) + duration
    if zone_seconds:
        result["zone"] = max(zone_seconds, key=zone_seconds.get)

    intensity_types = {
        str(interval.get("intensity_type") or "").strip().lower()
        for interval in intervals
        if str(interval.get("intensity_type") or "").strip()
    }
    if len(intensity_types) == 1:
        result["intensity_type"] = intensity_types.pop()
    return result


def _weighted_average(
    intervals: Sequence[Mapping[str, Any]],
    durations: Sequence[int],
    field: str,
) -> int | float | None:
    weighted_sum = 0.0
    weight = 0
    for interval, duration in zip(intervals, durations):
        value = _number(interval.get(field))
        if value is None or duration <= 0:
            continue
        weighted_sum += value * duration
        weight += duration
    if weight <= 0:
        return None
    return _compact(weighted_sum / weight)


def _timeline_match(
    step: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
    matched: bool,
    *,
    sport: str | None,
    athlete_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    planned_seconds = int(step.get("duration_seconds") or 0)
    actual_seconds = _actual_seconds(actual or {})
    return {
        "planned": dict(step),
        "actual": dict(actual) if actual is not None else None,
        "duration_delta": (
            round(_duration_delta(planned_seconds, actual_seconds), 2)
            if actual_seconds is not None and planned_seconds > 0
            else None
        ),
        "zone": {
            "planned": _planned_zone(step),
            "actual": _compact((actual or {}).get("zone")),
        },
        "intensity": _compare_intensity(
            step,
            actual,
            sport=sport,
            athlete_profile=athlete_profile,
        ),
        "matched": matched,
    }


def _compare_intensity(
    step: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
    *,
    sport: str | None,
    athlete_profile: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target = step.get("target_zone")
    profile = athlete_profile or {}
    heart_rate_value = _number((actual or {}).get("average_heartrate"))
    average_heartrate = (
        int(round(heart_rate_value)) if heart_rate_value is not None else None
    )
    unavailable = {
        "metric": None,
        "unit": None,
        "actual_value": None,
        "actual_relative": None,
        "target_low": None,
        "target_high": None,
        "status": "unavailable",
        "average_heartrate": average_heartrate,
    }
    if not isinstance(target, Mapping) or not isinstance(actual, Mapping):
        return unavailable

    metric = str(target.get("type") or "").strip().lower()
    target_low = _number(target.get("relative_low"))
    target_high = _number(target.get("relative_high"))
    if target_low is None or target_high is None:
        return {**unavailable, "metric": metric or None}

    actual_value: float | None = None
    actual_relative: float | None = None
    unit: str | None = None
    normalized_sport = str(sport or "").strip().lower()
    duration = _actual_seconds(actual)
    distance_km = _number(actual.get("distance_km"))

    if metric == "pace" and duration and distance_km and distance_km > 0:
        if normalized_sport in {"swim", "swimming"}:
            threshold = _number(
                profile.get("swim_threshold_pace_seconds_per_100m")
            )
            actual_value = duration / (distance_km * 10)
            unit = "seconds_per_100m"
        else:
            threshold = _number(profile.get("threshold_pace_seconds_per_km"))
            actual_value = duration / distance_km
            unit = "seconds_per_km"
        if threshold and threshold > 0 and actual_value > 0:
            actual_relative = threshold / actual_value
    elif metric == "power":
        actual_value = _number(actual.get("average_watts"))
        threshold = _number(profile.get("ftp"))
        unit = "watts"
        if actual_value is not None and threshold and threshold > 0:
            actual_relative = actual_value / threshold
    elif metric == "heart_rate":
        actual_value = _number(actual.get("average_heartrate"))
        threshold = _number(profile.get("lthr"))
        unit = "bpm"
        if actual_value is not None and threshold and threshold > 0:
            actual_relative = actual_value / threshold

    if actual_relative is None or actual_value is None:
        return {
            **unavailable,
            "metric": metric or None,
            "unit": unit,
            "target_low": _compact(target_low, digits=2),
            "target_high": _compact(target_high, digits=2),
        }

    if actual_relative < target_low:
        status = "below"
    elif actual_relative > target_high:
        status = "above"
    else:
        status = "within"
    return {
        "metric": metric,
        "unit": unit,
        "actual_value": round(actual_value, 1),
        "actual_relative": _compact(actual_relative, digits=2),
        "target_low": _compact(target_low, digits=2),
        "target_high": _compact(target_high, digits=2),
        "status": status,
        "average_heartrate": average_heartrate,
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


def _planned_zone(step: Mapping[str, Any]) -> int | float | None:
    target = step.get("target_zone")
    if not isinstance(target, Mapping):
        return None
    return _compact(target.get("relative_high"), digits=2)


def _compact(value: Any, *, digits: int = 1) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return round(number, digits)


def _empty_summary() -> dict[str, Any]:
    return {
        "planned_steps": 0,
        "planned_work_steps": 0,
        "actual_intervals": 0,
        "matched_steps": 0,
        "matched": 0,
    }


def _empty_result() -> dict[str, Any]:
    return {
        "alignment_mode": "work_intervals",
        "step_matches": [],
        "matches": [],
        "summary": _empty_summary(),
    }


def plan_replanned_after_delivery(
    match: Any,
    checkpoint: Any,
    deliveries: Sequence[Mapping[str, Any]],
    *,
    activity_started_at: str | None = None,
) -> dict[str, Any] | None:
    """Флаг рассинхрона с устройством (#398).

    Когда план на дату был доставлен в Intervals.icu (старая версия), а затем
    переплан (recovery_replan) — атлет мог тренироваться по предыдущей версии
    (кейс 2026-08-08: доставка 06:41, тренировка в 09:06 по старому плану).
    Возвращает описание риска или ``None``, если план не перепланирован либо
    доставки более ранней версии для этой даты не было.

    #461: если известен старт активности и текущий чекпоинт был успешно
    доставлен повторно ДО старта — устройство получило новую версию, и флаг
    гасится (кейс 2026-08-17: редоставка в 05:48, тренировка в 16:54).
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

    if _redelivered_before_start(
        deliveries, checkpoint_id, session_date, activity_started_at
    ):
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


def _redelivered_before_start(
    deliveries: Sequence[Mapping[str, Any]],
    checkpoint_id: Any,
    session_date: str,
    activity_started_at: str | None,
) -> bool:
    """True, когда текущий чекпоинт доставлен успешно до старта активности."""
    if not activity_started_at:
        return False
    started = _parse_utc(activity_started_at)
    if started is None:
        return False
    for item in deliveries:
        try:
            same_checkpoint = int(item.get("checkpoint_id")) == int(checkpoint_id)
        except (TypeError, ValueError):
            continue
        if not same_checkpoint:
            continue
        if session_date not in [str(value) for value in (item.get("dates") or [])]:
            continue
        if str(item.get("status") or "").strip().lower() != "success":
            continue
        delivered = _parse_utc(str(item.get("created_at") or ""))
        if delivered is not None and delivered <= started:
            return True
    return False


def _parse_utc(raw: str) -> datetime | None:
    """Parse ``2026-08-17T16:54:23Z`` / ``2026-08-17 05:48:02`` as UTC."""
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def structure_from_streams(
    planned: Sequence[Mapping[str, Any]],
    streams: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Синтетическая фактическая структура из 1 Гц-стримов по плановым шагам (#462).

    Нарезка стартует с первого активного сэмпла (запись часто начинается раньше
    педалирования — лидирующие нули watts реальны). Каждый плановый шаг получает
    окно своей длительности; закончившийся стрим не эмитит поздние шаги, и матчер
    честно покажет «Факт: нет». Требуется мощность или пульс: без обоих сигналов
    структура не выдумывается (fail-open к прежнему пути).
    """
    channels = {
        str(stream.get("type")): stream.get("data")
        for stream in streams
        if isinstance(stream, Mapping) and isinstance(stream.get("data"), list)
    }
    watts = channels.get("watts")
    heartrate = channels.get("heartrate")
    if not watts and not heartrate:
        return []
    length = max(len(watts or []), len(heartrate or []))
    if length <= 0:
        return []

    def _value_at(series: Any, index: int) -> float | None:
        if not series or index >= len(series):
            return None
        value = series[index]
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _active(index: int) -> bool:
        watt_value = _value_at(watts, index) if watts else None
        if watt_value is not None:
            return watt_value > 0
        return _value_at(heartrate, index) is not None

    start = 0
    while start < length and not _active(start):
        start += 1
    if start >= length:
        return []

    distance = channels.get("distance")
    structure: list[dict[str, Any]] = []
    cursor = start
    for step in planned:
        duration = int(step.get("duration_seconds") or 0)
        if duration <= 0:
            continue
        end = min(cursor + duration, length)
        if end <= cursor:
            break
        watt_values = [
            value
            for value in (_value_at(watts, i) for i in range(cursor, end))
            if value is not None
        ]
        hr_values = [
            value
            for value in (_value_at(heartrate, i) for i in range(cursor, end))
            if value is not None
        ]
        interval: dict[str, Any] = {
            # Шкала синтетической структуры начинается с нуля: холостой префикс
            # записи (лидирующие нули) вырезан, матчер требует непрерывность с 0.
            "start_index": cursor - start,
            "moving_time": sum(1 for i in range(cursor, end) if _active(i)),
            "elapsed_time": end - cursor,
        }
        if watt_values:
            interval["average_watts"] = round(sum(watt_values) / len(watt_values), 1)
        if hr_values:
            interval["average_heartrate"] = round(sum(hr_values) / len(hr_values))
        if distance:
            distance_start = _value_at(distance, cursor)
            distance_end = _value_at(distance, end - 1)
            if distance_start is not None and distance_end is not None:
                interval["distance_km"] = round(
                    (distance_end - distance_start) / 1000.0, 2
                )
        structure.append(interval)
        cursor = end
    return structure


def select_actual_structure(payload: Any) -> tuple[list, str | None]:
    """Выбрать фактическую структуру для матчинга с приоритетом кругов Garmin (#460).

    Автодетект Intervals.icu строит интервалы по смене зоны мощности и сливает
    мягкие тренировки (шаги внутри одной зоны) в один блок на всю сессию.
    Круги Garmin — границы, записанные устройством, — лежат рядом в той же
    записи и отражают выполненную структуру. Когда они есть, матчинг идёт по
    ним; иначе — прежнее поведение по интервалам провайдера.
    """
    if not isinstance(payload, Mapping):
        return [], None
    intervals = payload.get("intervals")
    if not isinstance(intervals, list):
        intervals = []
    source = payload.get("source")
    source = source if isinstance(source, str) else None
    if source == "intervals":
        laps = payload.get("garmin_laps")
        if isinstance(laps, list) and laps:
            return laps, "garmin"
    return intervals, source


__all__ = [
    "match_plan_vs_fact",
    "plan_replanned_after_delivery",
    "select_actual_structure",
    "structure_from_streams",
]
