"""Детерминированная научная проверка уже сформированного плана.

Blocks используется для курирования источников, но никогда не вызывается из
этого модуля. Политика и ссылки заморожены версией, поэтому один и тот же
checkpoint можно проверить офлайн и получить тот же результат.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping


SCIENCE_POLICY_VERSION = "plan-science-v1"

_HARD_ROLES = frozenset({"long", "quality"})
_TRIATHLON_SPORTS = ("swim", "bike", "run")
_SPORT_LABELS = {"swim": "плавание", "bike": "велосипед", "run": "бег"}

_EVIDENCE = {
    "hard_day_spacing": {
        "ref_id": "REF-302",
        "level": "B+",
        "doi": "10.1007/s40279-024-02067-4",
        "finding": "Чередование тяжёлых и лёгких дней — базовый принцип построения микроцикла.",
    },
    "triathlon_brick_specificity": {
        "ref_id": "REF-655",
        "level": "A",
        "doi": "10.1016/j.jsams.2022.07.006",
        "finding": "Переход с велосипеда на бег создаёт отдельную тренируемую нагрузку.",
    },
    "taper_volume_shape": {
        "ref_id": "REF-107",
        "level": "A",
        "doi": "10.1249/mss.0b013e31806010e0",
        "finding": "Перед стартом объём снижают, сохраняя частоту и короткую интенсивность.",
    },
    "triathlon_taper_frequency": {
        "ref_id": "REF-536",
        "level": "B+",
        "doi": "10.1007/s004210050087",
        "finding": "При снижении объёма плавательная частота и интенсивность сохраняются.",
    },
    "triathlon_swim_specificity": {
        "ref_id": "REF-538",
        "level": "A",
        "doi": "10.2165/00007256-200232060-00001",
        "finding": "Три дисциплины требуют специфичной практики: экономичность между ними не переносится.",
    },
    "triathlon_taper_activation": (
        {
            "ref_id": "REF-107",
            "level": "A",
            "doi": "10.1249/mss.0b013e31806010e0",
            "finding": "При снижении нагрузки объём уменьшают, а короткую интенсивность и частоту сохраняют.",
        },
        {
            "ref_id": "REF-538",
            "level": "A",
            "doi": "10.2165/00007256-200232060-00001",
            "finding": "Подготовка к триатлону остаётся специфичной для каждой дисциплины.",
        },
    ),
}


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _is_triathlon(goal_plan: Mapping[str, Any]) -> bool:
    goal = str(goal_plan.get("goal_type") or "").strip().lower()
    return "триатлон" in goal or "tri" in goal


def _confirmed_a_event_date(goal_plan: Mapping[str, Any]) -> date | None:
    for raw in list(goal_plan.get("events") or []):
        if not isinstance(raw, Mapping):
            continue
        if str(raw.get("priority") or "").upper() != "A":
            continue
        if raw.get("confirmed") is not True:
            continue
        parsed = _date(raw.get("date"))
        if parsed is not None:
            return parsed
    if str(goal_plan.get("planning_mode") or "").strip().lower() == "event_goal":
        return _date(goal_plan.get("macrocycle_event_date") or goal_plan.get("event_date"))
    return None


def _leaf_sessions(goal_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    leaves: list[dict[str, Any]] = []
    for raw_parent in list(goal_plan.get("session_templates") or []):
        if not isinstance(raw_parent, Mapping):
            continue
        parent = dict(raw_parent)
        children = [
            dict(item)
            for item in list(parent.get("sessions") or [])
            if isinstance(item, Mapping)
        ]
        candidates = children or [parent]
        for child in candidates:
            merged = {
                **child,
                "date": child.get("date") or parent.get("date"),
                "phase": child.get("phase") or parent.get("phase"),
                "session_role": child.get("session_role") or parent.get("session_role"),
                "duration_minutes": child.get("duration_minutes")
                if child.get("duration_minutes") is not None
                else parent.get("duration_minutes"),
            }
            parsed_date = _date(merged.get("date"))
            if parsed_date is None:
                continue
            try:
                duration = max(0, int(round(float(merged.get("duration_minutes") or 0))))
            except (TypeError, ValueError):
                duration = 0
            merged["parsed_date"] = parsed_date
            merged["duration_minutes"] = duration
            leaves.append(merged)
    return leaves


def _finding(
    rule_id: str,
    *,
    status: str,
    title: str,
    summary: str,
    recommendation: str,
    affected_dates: Iterable[date | str] = (),
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    dates = sorted(
        {
            value.isoformat() if isinstance(value, date) else str(value)
            for value in affected_dates
            if value
        }
    )
    raw_evidence = _EVIDENCE[rule_id]
    evidence_rows = raw_evidence if isinstance(raw_evidence, tuple) else (raw_evidence,)
    return {
        "rule_id": rule_id,
        "status": status,
        "severity": "warning" if status == "attention" else "info",
        "title": title,
        "summary": summary,
        "recommendation": recommendation,
        "affected_dates": dates,
        "metrics": dict(metrics or {}),
        "evidence": [dict(item) for item in evidence_rows],
    }


def _hard_day_spacing(leaves: list[dict[str, Any]]) -> dict[str, Any]:
    hard_dates = sorted(
        {
            item["parsed_date"]
            for item in leaves
            if str(item.get("session_role") or "").strip().lower() in _HARD_ROLES
        }
    )
    conflicts: list[date] = []
    for previous, current in zip(hard_dates, hard_dates[1:]):
        if (current - previous).days < 2:
            conflicts.extend((previous, current))
    if conflicts:
        return _finding(
            "hard_day_spacing",
            status="attention",
            title="Чередование тяжёлых и лёгких дней",
            summary="В плане есть тяжёлые тренировки в соседние дни.",
            recommendation="Разделить соседние тяжёлые дни лёгкой тренировкой или отдыхом.",
            affected_dates=conflicts,
            metrics={"minimum_gap_days": 2, "hard_day_count": len(hard_dates)},
        )
    return _finding(
        "hard_day_spacing",
        status="passed",
        title="Чередование тяжёлых и лёгких дней",
        summary="Соседних тяжёлых дней не найдено.",
        recommendation="Сохранить текущее чередование нагрузки и восстановления.",
        metrics={"minimum_gap_days": 2, "hard_day_count": len(hard_dates)},
    )


def _is_bike_run_brick(item: Mapping[str, Any]) -> bool:
    sport = str(item.get("sport") or "").strip().lower()
    kind = str(item.get("kind") or "").strip().lower()
    leg_sports = {
        str(leg.get("sport") or "").strip().lower()
        for leg in list(item.get("legs") or [])
        if isinstance(leg, Mapping)
    }
    return sport == "brick" and (kind == "composite" or {"bike", "run"} <= leg_sports)


def _brick_specificity(
    goal_plan: Mapping[str, Any], leaves: list[dict[str, Any]], event_date: date | None
) -> dict[str, Any]:
    if not _is_triathlon(goal_plan) or event_date is None:
        return _finding(
            "triathlon_brick_specificity",
            status="data_gap",
            title="Связка велосипед — бег",
            summary="Для проверки нужна подтверждённая триатлонная A-цель.",
            recommendation="Подтвердить основную триатлонную цель и дату старта.",
        )
    eligible = [
        item
        for item in leaves
        if str(item.get("phase") or "").strip().lower() in {"build", "peak"}
        and item["parsed_date"] < event_date
    ]
    if not eligible:
        return _finding(
            "triathlon_brick_specificity",
            status="data_gap",
            title="Связка велосипед — бег",
            summary="В сохранённом горизонте нет фаз «Развитие» или «Пик» для этой проверки.",
            recommendation="Проверить связки после появления соответствующих фаз в горизонте плана.",
        )
    bricks = [item for item in eligible if _is_bike_run_brick(item)]
    if not bricks:
        return _finding(
            "triathlon_brick_specificity",
            status="attention",
            title="Связка велосипед — бег",
            summary="В фазах «Развитие» и «Пик» не найдено ни одной связки велосипед — бег.",
            recommendation="Добавить хотя бы одну выполнимую связку: велосипед и сразу короткий бег.",
            metrics={"brick_count": 0},
        )
    return _finding(
        "triathlon_brick_specificity",
        status="passed",
        title="Связка велосипед — бег",
        summary=f"Найдено связок в специфических фазах: {len(bricks)}.",
        recommendation="Сохранить связки и не превращать их в две несвязанные тренировки.",
        affected_dates=[item["parsed_date"] for item in bricks],
        metrics={"brick_count": len(bricks)},
    )


def _window_minutes(
    leaves: list[dict[str, Any]], start: date, end: date
) -> int:
    return sum(
        int(item.get("duration_minutes") or 0)
        for item in leaves
        if start <= item["parsed_date"] < end
        and str(item.get("sport") or "").strip().lower() not in {"off", "race"}
    )


def _window_is_covered(leaves: list[dict[str, Any]], start: date, end: date) -> bool:
    return any(start <= item["parsed_date"] < end for item in leaves)


def _taper_volume(
    goal_plan: Mapping[str, Any], leaves: list[dict[str, Any]], event_date: date | None
) -> dict[str, Any]:
    if not _is_triathlon(goal_plan) or event_date is None:
        return _finding(
            "taper_volume_shape",
            status="data_gap",
            title="Снижение объёма перед стартом",
            summary="Для проверки нужна подтверждённая триатлонная A-цель.",
            recommendation="Подтвердить основную триатлонную цель и дату старта.",
        )
    windows = {
        "baseline": (event_date - timedelta(days=21), event_date - timedelta(days=14)),
        "first_taper": (event_date - timedelta(days=14), event_date - timedelta(days=7)),
        "final": (event_date - timedelta(days=7), event_date),
    }
    covered = {
        key: _window_is_covered(leaves, start, end)
        for key, (start, end) in windows.items()
    }
    baseline = _window_minutes(leaves, *windows["baseline"])
    first_taper = _window_minutes(leaves, *windows["first_taper"])
    final = _window_minutes(leaves, *windows["final"])
    base_metrics = {
        "baseline_week_minutes": baseline,
        "first_taper_week_minutes": first_taper,
        "final_week_minutes": final,
    }
    if not all(covered.values()):
        return _finding(
            "taper_volume_shape",
            status="data_gap",
            title="Снижение объёма перед стартом",
            summary="Недостаточно базовой недели и двух недель снижения объёма перед стартом.",
            recommendation="Проверить сохранённый горизонт и длительности тренировок.",
            metrics={**base_metrics, "covered_windows": covered},
        )
    reduction = int(round((1.0 - final / baseline) * 100)) if baseline > 0 else None
    progressive = baseline > first_taper > final
    metrics = {
        **base_metrics,
        "reduction_percent": reduction,
        "progressive_reduction": progressive,
    }
    if baseline <= 0 or first_taper <= 0 or final <= 0:
        return _finding(
            "taper_volume_shape",
            status="attention",
            title="Снижение объёма перед стартом",
            summary="Одна из покрытых недель перед стартом осталась без тренировочного объёма.",
            recommendation="Вернуть небольшой объём и выстроить последовательное снижение без полной пустой недели.",
            metrics=metrics,
        )
    if reduction is None or not 40 <= reduction <= 60 or not progressive:
        issue = (
            f"Итоговое снижение составляет {reduction}% вместо коридора 40–60%."
            if not 40 <= reduction <= 60
            else "Общий объём снижен правильно, но по неделям снижение идёт не последовательно."
        )
        return _finding(
            "taper_volume_shape",
            status="attention",
            title="Снижение объёма перед стартом",
            summary=issue,
            recommendation="Плавно снизить объём в течение двух недель, сохранив короткую интенсивность.",
            metrics=metrics,
        )
    return _finding(
        "taper_volume_shape",
        status="passed",
        title="Снижение объёма перед стартом",
        summary=f"За две недели объём последовательно снижен на {reduction}% от базовой недели.",
        recommendation="Сохранить снижение объёма и короткие качественные включения.",
        metrics=metrics,
    )


def _session_sports(item: Mapping[str, Any]) -> set[str]:
    sports = {str(item.get("sport") or "").strip().lower()}
    sports.update(
        str(leg.get("sport") or "").strip().lower()
        for leg in list(item.get("legs") or [])
        if isinstance(leg, Mapping)
    )
    return sports & set(_TRIATHLON_SPORTS)


def _taper_frequency(
    goal_plan: Mapping[str, Any], leaves: list[dict[str, Any]], event_date: date | None
) -> dict[str, Any]:
    if not _is_triathlon(goal_plan) or event_date is None:
        return _finding(
            "triathlon_taper_frequency",
            status="data_gap",
            title="Частота дисциплин перед стартом",
            summary="Для проверки нужна подтверждённая триатлонная A-цель.",
            recommendation="Подтвердить основную триатлонную цель и дату старта.",
        )
    final = [
        item
        for item in leaves
        if event_date - timedelta(days=7) <= item["parsed_date"] < event_date
    ]
    present: set[str] = set()
    for item in final:
        present.update(_session_sports(item))
    missing = [sport for sport in _TRIATHLON_SPORTS if sport not in present]
    metrics = {"present_sports": sorted(present), "missing_sports": missing}
    if missing:
        labels = ", ".join(_SPORT_LABELS[sport] for sport in missing)
        return _finding(
            "triathlon_taper_frequency",
            status="attention",
            title="Частота дисциплин перед стартом",
            summary=f"В последние семь дней отсутствуют: {labels}.",
            recommendation="Вернуть короткие лёгкие или активационные занятия пропущенных дисциплин.",
            metrics=metrics,
        )
    return _finding(
        "triathlon_taper_frequency",
        status="passed",
        title="Частота дисциплин перед стартом",
        summary="В последнюю неделю сохранены плавание, велосипед и бег.",
        recommendation="Сохранять частоту, сокращая прежде всего длительность занятий.",
        metrics=metrics,
    )


def _looks_specific_or_intense(item: Mapping[str, Any]) -> bool:
    role = str(item.get("session_role") or "").strip().lower()
    if role in {"quality", "activation", "race"}:
        return True
    marker = " ".join(
        str(item.get(key) or "").strip().lower()
        for key in ("template_key", "stimulus", "session_focus")
    )
    return any(
        token in marker
        for token in (
            "race_pace",
            "race-specific",
            "race specific",
            "open_water",
            "open water",
            "sighting",
            "threshold",
            "activation",
            "vo2",
            "neuromuscular",
        )
    )


def _swim_specificity(
    goal_plan: Mapping[str, Any], leaves: list[dict[str, Any]], event_date: date | None
) -> dict[str, Any]:
    if not _is_triathlon(goal_plan) or event_date is None:
        return _finding(
            "triathlon_swim_specificity",
            status="data_gap",
            title="Специфичность плавания",
            summary="Для проверки нужна подтверждённая триатлонная A-цель.",
            recommendation="Подтвердить основную триатлонную цель и дату старта.",
        )
    eligible = [
        item
        for item in leaves
        if item["parsed_date"] < event_date - timedelta(days=7)
        and str(item.get("phase") or "").strip().lower() in {"peak", "taper"}
    ]
    if not eligible:
        return _finding(
            "triathlon_swim_specificity",
            status="data_gap",
            title="Специфичность плавания",
            summary="В сохранённом горизонте нет фаз «Пик» или «Снижение нагрузки» для этой проверки.",
            recommendation="Проверить специфичность плавания после появления этих фаз в горизонте плана.",
        )
    rehearsals = [
        item
        for item in eligible
        if str(item.get("sport") or "").strip().lower() == "swim"
        and _looks_specific_or_intense(item)
    ]
    if not rehearsals:
        return _finding(
            "triathlon_swim_specificity",
            status="attention",
            title="Специфичность плавания",
            summary="Перед стартовой неделей нет специфичной плавательной тренировки в фазах «Пик» или «Снижение нагрузки».",
            recommendation=(
                "Добавить работу в соревновательном темпе в бассейне; при наличии безопасного доступа — "
                "отдельно отработать старт, ориентирование и экипировку на открытой воде."
            ),
            metrics={"specific_swim_count": 0},
        )
    return _finding(
        "triathlon_swim_specificity",
        status="passed",
        title="Специфичность плавания",
        summary=f"До стартовой недели найдено специфичных плавательных тренировок: {len(rehearsals)}.",
        recommendation="Сохранить специфичную работу, не увеличивая её объём в последнюю неделю.",
        affected_dates=[item["parsed_date"] for item in rehearsals],
        metrics={"specific_swim_count": len(rehearsals)},
    )


def _taper_activation(
    goal_plan: Mapping[str, Any], leaves: list[dict[str, Any]], event_date: date | None
) -> dict[str, Any]:
    if not _is_triathlon(goal_plan) or event_date is None:
        return _finding(
            "triathlon_taper_activation",
            status="data_gap",
            title="Короткая интенсивность перед стартом",
            summary="Для проверки нужна подтверждённая триатлонная A-цель.",
            recommendation="Подтвердить основную триатлонную цель и дату старта.",
        )
    final = [
        item
        for item in leaves
        if event_date - timedelta(days=7) <= item["parsed_date"] < event_date
    ]
    activated: set[str] = set()
    for item in final:
        if _looks_specific_or_intense(item):
            activated.update(_session_sports(item))
    missing = [sport for sport in _TRIATHLON_SPORTS if sport not in activated]
    metrics = {"activated_sports": sorted(activated), "missing_sports": missing}
    if missing:
        labels = ", ".join(_SPORT_LABELS[sport] for sport in missing)
        return _finding(
            "triathlon_taper_activation",
            status="attention",
            title="Короткая интенсивность перед стартом",
            summary=f"В последнюю неделю нет коротких интенсивных включений: {labels}.",
            recommendation=(
                "Добавить короткие контролируемые включения пропущенных дисциплин, "
                "не возвращая прежний тренировочный объём."
            ),
            metrics=metrics,
        )
    return _finding(
        "triathlon_taper_activation",
        status="passed",
        title="Короткая интенсивность перед стартом",
        summary="В последнюю неделю сохранены короткие интенсивные включения трёх дисциплин.",
        recommendation="Сохранить включения короткими и не превращать их в тяжёлые тренировки.",
        metrics=metrics,
    )


def audit_training_plan(
    goal_plan: Mapping[str, Any], *, source: str = "stored"
) -> dict[str, Any]:
    """Проверить конечный план без мутаций, I/O и текущего времени."""
    leaves = _leaf_sessions(goal_plan)
    event_date = _confirmed_a_event_date(goal_plan)
    findings = [
        _hard_day_spacing(leaves),
        _brick_specificity(goal_plan, leaves, event_date),
        _taper_volume(goal_plan, leaves, event_date),
        _taper_frequency(goal_plan, leaves, event_date),
        _swim_specificity(goal_plan, leaves, event_date),
        _taper_activation(goal_plan, leaves, event_date),
    ]
    counts = {
        status: sum(item["status"] == status for item in findings)
        for status in ("passed", "attention", "data_gap")
    }
    if counts["attention"] == 0 and counts["data_gap"] == 0:
        count = counts["passed"]
        suffix = "проверка" if count % 10 == 1 and count % 100 != 11 else (
            "проверки" if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14} else "проверок"
        )
        headline = f"Все {count} {suffix} пройдены"
    elif counts["attention"]:
        headline = f"Требуют внимания: {counts['attention']}"
        if counts["data_gap"]:
            headline += f" · недостаточно данных: {counts['data_gap']}"
    else:
        headline = f"Недостаточно данных: {counts['data_gap']}"
    return {
        "state": "available" if leaves else "data_gap",
        "policy_version": SCIENCE_POLICY_VERSION,
        "source": str(source or "stored"),
        "summary": {**counts, "headline": headline},
        "findings": findings,
    }


__all__ = ["SCIENCE_POLICY_VERSION", "audit_training_plan"]
