from __future__ import annotations

from datetime import datetime, timedelta, date
from math import ceil
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from models.planning_summary import summarize_execution_adaptation_pressure

WEEKDAY_LABELS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
SESSION_ROLE_LABELS_RU = {
    "off": "Отдых",
    "race": "Старт",
    "activation": "Активация",
    "recovery": "Восстановление",
    "easy": "Легкая",
    "quality": "Качество",
    "long": "Длительная",
}
SPORT_LABELS_RU = {
    "run": "бег",
    "bike": "вело",
    "swim": "плавание",
    "brick": "вело → бег",
    "off": "отдых",
}


def _round_to_5(value: float) -> int:
    return int(round(float(value) / 5.0) * 5)


def recommended_training_days(goal_type: str) -> int:
    g = (goal_type or '').lower()
    if 'триатлон' in g or 'tri' in g:
        return 6
    if 'бег' in g or 'run' in g:
        return 5
    if 'вело' in g or 'bike' in g or 'cycle' in g:
        return 5
    return 5


def estimated_tss_per_hour(goal_type: str) -> int:
    g = (goal_type or '').lower()
    if 'триатлон' in g or 'tri' in g:
        return 42
    if 'бег' in g or 'run' in g:
        return 50
    if 'вело' in g or 'bike' in g or 'cycle' in g:
        return 45
    return 45


def normalize_available_day_indices(available_day_indices: List[int] | None) -> List[int]:
    if not available_day_indices:
        return list(range(7))
    valid = sorted({int(idx) for idx in available_day_indices if 0 <= int(idx) <= 6})
    return valid or list(range(7))


def available_day_density_factor(available_day_count: int, goal_type: str) -> float:
    recommended = max(1, recommended_training_days(goal_type))
    raw_ratio = available_day_count / recommended
    # Смягчаем штраф за меньшее число тренировочных дней, чтобы план не становился чрезмерно консервативным.
    return max(0.45, min(1.0, raw_ratio * 0.7 + 0.3))


def summarize_availability(
    goal_type: str,
    available_hours: float,
    available_day_indices: List[int] | None = None,
) -> Dict[str, object]:
    day_indices = normalize_available_day_indices(available_day_indices)
    tss_per_hour = estimated_tss_per_hour(goal_type)
    density_factor = available_day_density_factor(len(day_indices), goal_type)
    weekly_capacity_tss = max(50, _round_to_5(max(0.0, float(available_hours or 0.0)) * tss_per_hour * density_factor))
    return {
        'available_hours': round(float(available_hours or 0.0), 1),
        'available_day_indices': day_indices,
        'available_day_labels': [WEEKDAY_LABELS_RU[idx] for idx in day_indices],
        'available_day_count': len(day_indices),
        'recommended_days': recommended_training_days(goal_type),
        'density_factor': round(density_factor, 2),
        'tss_per_hour': tss_per_hour,
        'weekly_capacity_tss': weekly_capacity_tss,
    }


def constrain_weights_to_available_days(
    weights: Dict[str, List[float]],
    available_day_indices: List[int] | None = None,
) -> Dict[str, List[float]]:
    allowed_days = set(normalize_available_day_indices(available_day_indices))
    constrained: Dict[str, List[float]] = {}
    for sport, values in weights.items():
        masked = [
            float(values[idx] if idx < len(values) else 0.0) if idx in allowed_days else 0.0
            for idx in range(7)
        ]
        constrained[sport] = _normalize_weights(masked)
    return constrained


def _interruption_label(interruption_type: str) -> str:
    mapping = {
        'limited': 'Ограниченная доступность',
        'holiday': 'Отпуск',
        'illness': 'Болезнь',
        'injury': 'Травма',
        'none': 'Нет',
    }
    return mapping.get((interruption_type or 'none').lower(), 'Нет')


def _interruption_week_factor(interruption_type: str, week_index: int) -> float:
    schedules = {
        'limited': [0.75, 0.85, 0.95, 1.0],
        'holiday': [0.60, 0.70, 0.85, 0.95],
        'illness': [0.35, 0.50, 0.70, 0.85],
        'injury': [0.20, 0.35, 0.55, 0.75],
        'none': [1.0],
    }
    factors = schedules.get((interruption_type or 'none').lower(), [1.0])
    return factors[min(max(0, week_index), len(factors) - 1)]


def _plan_adjustment_label(status: str) -> str:
    mapping = {
        'completed': 'Выполнено по плану',
        'skipped': 'Пропущены сессии',
        'reduced': 'Нагрузка урезана',
        'unavailable': 'Неделя ограничена',
        'none': 'Нет',
    }
    return mapping.get((status or 'none').lower(), 'Нет')


def normalize_plan_adjustment(
    plan_adjustment: Mapping[str, Any] | None,
    available_day_count: int,
) -> Dict[str, Any]:
    raw = dict(plan_adjustment or {})
    status = str(raw.get('status', 'none') or 'none').strip().lower()
    if status not in {'none', 'completed', 'skipped', 'reduced', 'unavailable'}:
        status = 'none'

    weeks_default = 1 if status != 'none' else 0
    try:
        weeks = int(raw.get('weeks', weeks_default))
    except (TypeError, ValueError):
        weeks = weeks_default
    weeks = min(max(0, weeks), 2)

    day_count = max(1, int(available_day_count or 0))
    try:
        missed_sessions = int(raw.get('missed_sessions', 0))
    except (TypeError, ValueError):
        missed_sessions = 0
    missed_sessions = min(max(0, missed_sessions), day_count)

    try:
        reduced_load_share = float(raw.get('reduced_load_share', 0.70))
    except (TypeError, ValueError):
        reduced_load_share = 0.70
    reduced_load_share = max(0.35, min(0.95, reduced_load_share))

    execution_reconciliation = raw.get('execution_reconciliation')
    if not isinstance(execution_reconciliation, Mapping):
        execution_reconciliation = None
    execution_weekly_review = raw.get('execution_weekly_review')
    if not isinstance(execution_weekly_review, Mapping):
        execution_weekly_review = None
    execution_corrective_microcycle = raw.get('execution_corrective_microcycle')
    if not isinstance(execution_corrective_microcycle, Mapping):
        execution_corrective_microcycle = None
    execution_adaptation_pressure = summarize_execution_adaptation_pressure(
        raw.get('execution_adaptation_pressure')
    )

    catch_up_strategy_override = str(raw.get('catch_up_strategy_override') or '').strip().lower()
    if catch_up_strategy_override not in {'catch_up', 'protect_recovery'}:
        catch_up_strategy_override = ''

    try:
        completion_share_default = None
        if execution_reconciliation:
            completion_share_default = execution_reconciliation.get('completion_share')
        elif 'completion_share' in raw:
            completion_share_default = raw.get('completion_share')
        elif status == 'reduced':
            completion_share_default = reduced_load_share
        completion_share = (
            float(completion_share_default)
            if completion_share_default is not None
            else None
        )
    except (TypeError, ValueError):
        completion_share = None
    if completion_share is not None:
        completion_share = max(0.0, min(1.0, completion_share))

    changed_day_count = 0
    reduced_day_count = 0
    unavailable_day_count = 0
    planned_total_tss = 0
    actual_total_tss = 0
    delta_tss = 0
    compact_label = ''
    description = ''
    changed_rows = []
    if execution_reconciliation:
        try:
            changed_day_count = int(execution_reconciliation.get('changed_day_count', 0) or 0)
        except (TypeError, ValueError):
            changed_day_count = 0
        try:
            reduced_day_count = int(execution_reconciliation.get('reduced_day_count', 0) or 0)
        except (TypeError, ValueError):
            reduced_day_count = 0
        try:
            unavailable_day_count = int(execution_reconciliation.get('unavailable_day_count', 0) or 0)
        except (TypeError, ValueError):
            unavailable_day_count = 0
        try:
            planned_total_tss = int(execution_reconciliation.get('planned_total_tss', 0) or 0)
        except (TypeError, ValueError):
            planned_total_tss = 0
        try:
            actual_total_tss = int(execution_reconciliation.get('actual_total_tss', 0) or 0)
        except (TypeError, ValueError):
            actual_total_tss = 0
        try:
            delta_tss = int(execution_reconciliation.get('delta_tss', actual_total_tss - planned_total_tss) or 0)
        except (TypeError, ValueError):
            delta_tss = actual_total_tss - planned_total_tss
        compact_label = str(execution_reconciliation.get('compact_label', '') or '')
        description = str(execution_reconciliation.get('description', '') or '')
        changed_rows = [
            dict(item)
            for item in execution_reconciliation.get('changed_rows', [])
            if isinstance(item, Mapping)
        ][:10]

    return {
        'status': status,
        'label': _plan_adjustment_label(status),
        'weeks': weeks,
        'missed_sessions': missed_sessions,
        'reduced_load_share': reduced_load_share,
        'completion_share': completion_share,
        'available_day_count': day_count,
        'changed_day_count': changed_day_count,
        'reduced_day_count': reduced_day_count,
        'unavailable_day_count': unavailable_day_count,
        'planned_total_tss': planned_total_tss,
        'actual_total_tss': actual_total_tss,
        'delta_tss': delta_tss,
        'compact_label': compact_label,
        'description': description,
        'changed_rows': changed_rows,
        'execution_reconciliation': {
            'status': status,
            'planned_total_tss': planned_total_tss,
            'actual_total_tss': actual_total_tss,
            'delta_tss': delta_tss,
            'changed_day_count': changed_day_count,
            'missed_day_count': missed_sessions,
            'reduced_day_count': reduced_day_count,
            'unavailable_day_count': unavailable_day_count,
            'completion_share': completion_share if completion_share is not None else reduced_load_share,
            'compact_label': compact_label,
            'description': description,
            'changed_rows': changed_rows,
        } if execution_reconciliation else None,
        'execution_weekly_review': dict(execution_weekly_review) if execution_weekly_review else None,
        'execution_corrective_microcycle': dict(execution_corrective_microcycle) if execution_corrective_microcycle else None,
        'execution_adaptation_pressure': dict(execution_adaptation_pressure) if execution_adaptation_pressure else None,
        'catch_up_strategy_override': catch_up_strategy_override or None,
        'is_active': status in {'skipped', 'reduced', 'unavailable'} and weeks > 0,
    }


def _plan_adjustment_week_factor(plan_adjustment: Mapping[str, Any], week_index: int) -> float:
    status = str(plan_adjustment.get('status', 'none') or 'none').lower()
    completion_share = plan_adjustment.get('completion_share')
    try:
        completion_share = float(completion_share) if completion_share is not None else None
    except (TypeError, ValueError):
        completion_share = None
    if completion_share is not None and status in {'skipped', 'reduced', 'unavailable'}:
        return min(1.0, max(0.0, completion_share + 0.10 * max(0, week_index)))
    if status == 'skipped':
        day_count = max(1, int(plan_adjustment.get('available_day_count', 1) or 1))
        missed_sessions = max(1, int(plan_adjustment.get('missed_sessions', 1) or 1))
        completion_share = max(0.45, 1.0 - (missed_sessions / day_count) * 0.85)
        return min(1.0, completion_share + 0.10 * max(0, week_index))
    if status == 'reduced':
        reduced_load_share = float(plan_adjustment.get('reduced_load_share', 0.70) or 0.70)
        return min(0.95, max(0.35, reduced_load_share + 0.10 * max(0, week_index)))
    if status == 'unavailable':
        factors = [0.45, 0.70]
        return factors[min(max(0, week_index), len(factors) - 1)]
    return 1.0


def _plan_adjustment_note(plan_adjustment: Mapping[str, Any], factor: float) -> str:
    status = str(plan_adjustment.get('status', 'none') or 'none').lower()
    percent = int(round(float(factor) * 100))
    execution_reconciliation = plan_adjustment.get('execution_reconciliation')
    if isinstance(execution_reconciliation, Mapping):
        planned_total_tss = int(execution_reconciliation.get('planned_total_tss', 0) or 0)
        actual_total_tss = int(execution_reconciliation.get('actual_total_tss', 0) or 0)
        changed_day_count = int(execution_reconciliation.get('changed_day_count', 0) or 0)
        unavailable_day_count = int(execution_reconciliation.get('unavailable_day_count', 0) or 0)
        missed_day_count = int(execution_reconciliation.get('missed_day_count', 0) or 0)
        reduced_day_count = int(execution_reconciliation.get('reduced_day_count', 0) or 0)
        note = f"checkpoint: факт {actual_total_tss}/{planned_total_tss} TSS"
        if unavailable_day_count > 0:
            note += f" · недоступно {unavailable_day_count} дн."
        elif missed_day_count > 0:
            note += f" · пропуск {missed_day_count} дн."
        elif reduced_day_count > 0:
            note += f" · облегчено {reduced_day_count} дн."
        elif changed_day_count > 0:
            note += f" · изменено {changed_day_count} дн."
        return f"{note} → {percent}%"
    if status == 'skipped':
        missed_sessions = max(1, int(plan_adjustment.get('missed_sessions', 1) or 1))
        return f"checkpoint: пропущено {missed_sessions} сесс. → {percent}%"
    if status == 'reduced':
        return f"checkpoint: урезанная неделя → {percent}%"
    if status == 'unavailable':
        return f"checkpoint: ограниченная неделя → {percent}%"
    return f"checkpoint: {percent}%"


def _metric_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def assess_start_load_state(
    current_ctl: float | None = None,
    current_atl: float | None = None,
    current_tsb: float | None = None,
) -> Dict[str, object]:
    """Оценивает стартовое состояние спортсмена перед построением плана."""
    ctl = _metric_or_none(current_ctl)
    atl = _metric_or_none(current_atl)
    tsb = _metric_or_none(current_tsb)
    atl_ratio = None
    if ctl is not None and ctl > 0 and atl is not None:
        atl_ratio = atl / ctl

    state = "balanced"
    label = "Нейтральный старт"
    guard_factors: List[float] = []
    catch_up_share_cap: float | None = None
    catch_up_share_floor: float | None = None
    catch_up_ramp_rate = 0.08

    if (tsb is not None and tsb <= -25) or (atl_ratio is not None and atl_ratio >= 1.6):
        state = "deep_fatigue"
        label = "Глубокая усталость"
        guard_factors = [0.75, 0.85, 0.95]
        catch_up_share_cap = 0.25
        catch_up_ramp_rate = 0.05
    elif (tsb is not None and tsb <= -10) or (atl_ratio is not None and atl_ratio >= 1.25):
        state = "fatigued"
        label = "Накопленная усталость"
        guard_factors = [0.90, 0.95]
        catch_up_share_cap = 0.45
        catch_up_ramp_rate = 0.07
    elif (tsb is not None and tsb >= 10) and (atl_ratio is None or atl_ratio <= 0.9):
        state = "fresh"
        label = "Свежий старт"
        catch_up_share_floor = 0.70
        catch_up_ramp_rate = 0.10

    return {
        "state": state,
        "label": label,
        "guard_factors": guard_factors,
        "catch_up_share_cap": catch_up_share_cap,
        "catch_up_share_floor": catch_up_share_floor,
        "catch_up_ramp_rate": catch_up_ramp_rate,
        "atl_ratio": round(atl_ratio, 2) if atl_ratio is not None else None,
        "ctl": ctl,
        "atl": atl,
        "tsb": tsb,
    }


def apply_planning_constraints(
    weekly_tss: List[int],
    phases: List[str],
    goal_type: str,
    available_hours: float,
    available_day_indices: List[int] | None = None,
    interruption_type: str = 'none',
    interruption_weeks: int = 0,
    catch_up_strategy: str = 'protect_recovery',
    current_tsb: float | None = None,
    current_ctl: float | None = None,
    current_atl: float | None = None,
    plan_adjustment: Mapping[str, Any] | None = None,
) -> Tuple[List[int], List[Dict[str, object]], Dict[str, object]]:
    """Ограничивает недельный план доступностью и локально перепланирует ближайшие недели при сбое."""
    availability = summarize_availability(goal_type, available_hours, available_day_indices)
    weekly_capacity_tss = int(availability['weekly_capacity_tss'])
    load_state = assess_start_load_state(
        current_ctl=current_ctl,
        current_atl=current_atl,
        current_tsb=current_tsb,
    )
    normalized_adjustment = normalize_plan_adjustment(
        plan_adjustment,
        int(availability['available_day_count']),
    )

    adjusted_plan = [max(0, int(round(value))) for value in weekly_tss]
    details: List[Dict[str, object]] = []
    capacity_loss = 0

    for week_index, value in enumerate(adjusted_plan):
        note_parts: List[str] = []
        if value > weekly_capacity_tss:
            capacity_loss += value - weekly_capacity_tss
            value = weekly_capacity_tss
            note_parts.append(f"потолок {weekly_capacity_tss} TSS")
        adjusted_plan[week_index] = value
        details.append({
            'week_index': week_index,
            'phase': phases[week_index] if week_index < len(phases) else 'Base',
            'capacity_tss': weekly_capacity_tss,
            'adjustment_note': '',
            'notes': note_parts,
        })

    interruption_type = (interruption_type or 'none').lower()
    interruption_weeks = min(max(0, int(interruption_weeks)), len(adjusted_plan))
    apply_load_guard = not (interruption_type in {'illness', 'injury'} and interruption_weeks > 0)
    load_guard_loss = 0
    if apply_load_guard:
        for week_index, factor in enumerate(load_state['guard_factors']):
            if week_index >= len(adjusted_plan):
                break
            phase = (phases[week_index] if week_index < len(phases) else '').lower()
            if phase == 'taper':
                continue
            before = adjusted_plan[week_index]
            after = min(before, max(0, _round_to_5(before * factor)))
            if after != before:
                load_guard_loss += before - after
                adjusted_plan[week_index] = after
                details[week_index]['notes'].append(
                    f"{load_state['label']} {int(round((1.0 - factor) * 100))}%"
                )

    interruption_loss = 0

    for week_index in range(interruption_weeks):
        factor = _interruption_week_factor(interruption_type, week_index)
        before = adjusted_plan[week_index]
        after = min(before, max(0, _round_to_5(before * factor)))
        if after != before:
            interruption_loss += before - after
            adjusted_plan[week_index] = after
            details[week_index]['notes'].append(
                f"{_interruption_label(interruption_type)} {int(round((1.0 - factor) * 100))}%"
            )

    catch_up_strategy = (catch_up_strategy or 'protect_recovery').lower()
    recoverable_loss = 0
    recovered_tss = 0

    if catch_up_strategy == 'catch_up' and interruption_loss > 0:
        recovery_share = 0.60
        if interruption_type in {'illness', 'injury'}:
            recovery_share = min(recovery_share, 0.40)
        if current_tsb is not None and current_tsb <= -15:
            recovery_share = min(recovery_share, 0.35)
        if load_state['catch_up_share_cap'] is not None:
            recovery_share = min(recovery_share, float(load_state['catch_up_share_cap']))
        if load_state['catch_up_share_floor'] is not None and interruption_type in {'limited', 'holiday'}:
            recovery_share = max(recovery_share, float(load_state['catch_up_share_floor']))
        recoverable_loss = _round_to_5(interruption_loss * recovery_share)
        remaining = recoverable_loss

        for week_index in range(interruption_weeks, len(adjusted_plan)):
            phase = (phases[week_index] if week_index < len(phases) else '').lower()
            if phase == 'taper':
                continue
            current_value = adjusted_plan[week_index]
            extra_capacity = max(0, weekly_capacity_tss - current_value)
            ramp_room = max(10, _round_to_5(current_value * float(load_state['catch_up_ramp_rate'])))
            add = _round_to_5(min(extra_capacity, ramp_room, remaining))
            if add <= 0:
                continue
            adjusted_plan[week_index] += add
            remaining -= add
            recovered_tss += add
            details[week_index]['notes'].append(f"возврат +{add} TSS")
            if remaining <= 0:
                break

    if catch_up_strategy != 'catch_up' and interruption_loss > 0 and interruption_weeks > 0:
        details[interruption_weeks - 1]['notes'].append("без компенсации нагрузки")

    plan_adjustment_loss = 0
    plan_adjustment_recoverable = 0
    plan_adjustment_recovered = 0
    if normalized_adjustment['is_active']:
        affected_weeks = min(int(normalized_adjustment['weeks']), len(adjusted_plan))
        adaptation_pressure = normalized_adjustment.get('execution_adaptation_pressure')
        follow_up_mode = ''
        follow_up_label = ''
        growth_cap_tss_per_week = 0
        rebuild_horizon_weeks = 0
        recovery_share_cap = 0.0
        if isinstance(adaptation_pressure, Mapping):
            follow_up_mode = str(adaptation_pressure.get('follow_up_mode') or '').strip().lower()
            follow_up_label = str(adaptation_pressure.get('follow_up_label') or '').strip()
            growth_cap_tss_per_week = int(adaptation_pressure.get('growth_cap_tss_per_week', 0) or 0)
            rebuild_horizon_weeks = int(adaptation_pressure.get('rebuild_horizon_weeks', 0) or 0)
            try:
                recovery_share_cap = float(adaptation_pressure.get('recovery_share_cap', 0.0) or 0.0)
            except (TypeError, ValueError):
                recovery_share_cap = 0.0
        for week_index in range(affected_weeks):
            factor = _plan_adjustment_week_factor(normalized_adjustment, week_index)
            before = adjusted_plan[week_index]
            after = min(before, max(0, _round_to_5(before * factor)))
            if after == before:
                continue
            plan_adjustment_loss += before - after
            adjusted_plan[week_index] = after
            details[week_index]['notes'].append(_plan_adjustment_note(normalized_adjustment, factor))

        if (
            catch_up_strategy == 'catch_up'
            and plan_adjustment_loss > 0
            and follow_up_mode in {'', 'catch_up'}
        ):
            recovery_share_by_status = {
                'skipped': 0.50,
                'reduced': 0.40,
                'unavailable': 0.35,
            }
            recovery_share = recovery_share_by_status.get(normalized_adjustment['status'], 0.0)
            if current_tsb is not None and current_tsb <= -15:
                recovery_share = min(recovery_share, 0.30)
            if load_state['catch_up_share_cap'] is not None:
                recovery_share = min(recovery_share, float(load_state['catch_up_share_cap']))
            if recovery_share_cap > 0:
                recovery_share = min(recovery_share, recovery_share_cap)
            plan_adjustment_recoverable = _round_to_5(plan_adjustment_loss * recovery_share)
            remaining = plan_adjustment_recoverable
            recovery_window_end = min(len(adjusted_plan), affected_weeks + 2)

            for week_index in range(affected_weeks, recovery_window_end):
                phase = (phases[week_index] if week_index < len(phases) else '').lower()
                if phase == 'taper':
                    continue
                current_value = adjusted_plan[week_index]
                extra_capacity = max(0, weekly_capacity_tss - current_value)
                ramp_room = max(10, _round_to_5(current_value * min(float(load_state['catch_up_ramp_rate']), 0.08)))
                add = _round_to_5(min(extra_capacity, ramp_room, remaining))
                if add <= 0:
                    continue
                adjusted_plan[week_index] += add
                remaining -= add
                plan_adjustment_recovered += add
                details[week_index]['notes'].append(f"локальный возврат +{add} TSS")
                if remaining <= 0:
                    break

        if plan_adjustment_loss > 0 and affected_weeks > 0:
            if follow_up_mode == 'hold':
                details[affected_weeks - 1]['notes'].append("режим hold: удержать текущий потолок")
            elif follow_up_mode == 'protect_recovery':
                details[affected_weeks - 1]['notes'].append("режим protect_recovery: объём не догоняется автоматически")
            elif catch_up_strategy != 'catch_up':
                details[affected_weeks - 1]['notes'].append("локальный объём не догоняется автоматически")

        if growth_cap_tss_per_week > 0 and rebuild_horizon_weeks > 0 and affected_weeks > 0:
            rebound_window_end = min(len(adjusted_plan), affected_weeks + rebuild_horizon_weeks)
            for week_index in range(affected_weeks, rebound_window_end):
                previous_value = adjusted_plan[week_index - 1]
                allowed_value = max(previous_value, previous_value + growth_cap_tss_per_week)
                if adjusted_plan[week_index] <= allowed_value:
                    continue
                adjusted_plan[week_index] = allowed_value
                mode_note = follow_up_label or "режим после execution drift"
                details[week_index]['notes'].append(
                    f"{mode_note.lower()} · ceiling +{growth_cap_tss_per_week} TSS/нед."
                )

    for week_index, value in enumerate(adjusted_plan):
        details[week_index]['adjusted_tss'] = value
        details[week_index]['adjustment_note'] = ' · '.join(details[week_index]['notes']) or '—'

    summary_notes = [
        f"Доступно {availability['available_hours']} ч/нед ≈ потолок {weekly_capacity_tss} TSS",
        f"Дни: {', '.join(availability['available_day_labels'])}",
    ]
    if load_state['state'] == 'deep_fatigue':
        summary_notes.append("Стартовое состояние: глубокая усталость — первые недели дополнительно смягчены")
    elif load_state['state'] == 'fatigued':
        summary_notes.append("Стартовое состояние: накопленная усталость — старт плана сделан мягче")
    elif load_state['state'] == 'fresh':
        summary_notes.append("Стартовое состояние: свежесть — план не ограничен дополнительно и может вернуть больше нагрузки после отпуска")
    if load_guard_loss > 0:
        summary_notes.append(f"Стартовая усталость дополнительно сняла ~{load_guard_loss} TSS в первые недели")
    if capacity_loss > 0:
        summary_notes.append(f"Ограничение по доступности сняло ~{capacity_loss} TSS относительно базового плана")
    if interruption_type != 'none' and interruption_weeks > 0:
        summary_notes.append(f"{_interruption_label(interruption_type)} на {interruption_weeks} нед.")
    if interruption_loss > 0 and catch_up_strategy == 'catch_up':
        summary_notes.append(
            f"Стратегия «Наверстать аккуратно» вернула {recovered_tss} из {recoverable_loss} TSS"
        )
    elif interruption_loss > 0:
        summary_notes.append("Стратегия «Беречь восстановление» не догоняет пропущенный объём автоматически")
    if normalized_adjustment['status'] == 'completed':
        summary_notes.append("Checkpoint: неделя выполнена по плану — локальная перепланировка не потребовалась")
    elif normalized_adjustment['is_active']:
        summary_notes.append(
            f"Checkpoint: {normalized_adjustment['label']} на {normalized_adjustment['weeks']} нед."
        )
        if normalized_adjustment.get('execution_reconciliation'):
            summary_notes.append(
                "Факт ближнего окна: "
                f"{normalized_adjustment['actual_total_tss']} из {normalized_adjustment['planned_total_tss']} TSS, "
                f"изменено {normalized_adjustment['changed_day_count']} дн."
            )
        execution_weekly_review = normalized_adjustment.get('execution_weekly_review')
        if isinstance(execution_weekly_review, Mapping):
            weekly_headline = str(execution_weekly_review.get('headline') or '').strip()
            selected_response_label = str(execution_weekly_review.get('selected_response_label') or '').strip()
            if weekly_headline:
                note = f"Weekly review: {weekly_headline}."
                if selected_response_label:
                    note += f" Ответ: {selected_response_label}."
                summary_notes.append(note)
        execution_corrective_microcycle = normalized_adjustment.get('execution_corrective_microcycle')
        if isinstance(execution_corrective_microcycle, Mapping):
            microcycle_headline = str(execution_corrective_microcycle.get('headline') or '').strip()
            if microcycle_headline:
                summary_notes.append(f"Execution microcycle: {microcycle_headline}.")
        execution_adaptation_pressure = normalized_adjustment.get('execution_adaptation_pressure')
        if isinstance(execution_adaptation_pressure, Mapping):
            compact_label = str(execution_adaptation_pressure.get('compact_label') or '').strip()
            follow_up_window_description = str(
                execution_adaptation_pressure.get('follow_up_window_description') or ''
            ).strip()
            reason = str(execution_adaptation_pressure.get('reason') or '').strip()
            if compact_label:
                note = f"Execution drift pressure: {compact_label}."
                if follow_up_window_description:
                    note += f" {follow_up_window_description}"
                if reason:
                    note += f" {reason}"
                summary_notes.append(note)
        if plan_adjustment_loss > 0 and catch_up_strategy == 'catch_up' and plan_adjustment_recoverable > 0:
            summary_notes.append(
                f"Локальная перепланировка вернула {plan_adjustment_recovered} из {plan_adjustment_recoverable} TSS в ближайшем окне"
            )
        elif plan_adjustment_loss > 0:
            summary_notes.append("Локальная перепланировка не размазывает пропущенный объём по всему циклу")
    if current_tsb is not None and current_tsb <= -15 and catch_up_strategy == 'catch_up':
        summary_notes.append("Текущий TSB низкий — возврат объёма дополнительно ограничен, чтобы не усиливать усталость")

    summary = {
        **availability,
        'interruption_type': interruption_type,
        'interruption_label': _interruption_label(interruption_type),
        'interruption_weeks': interruption_weeks,
        'catch_up_strategy': catch_up_strategy,
        'capacity_loss_tss': capacity_loss,
        'interruption_loss_tss': interruption_loss,
        'recoverable_loss_tss': recoverable_loss,
        'recovered_tss': recovered_tss,
        'plan_adjustment': normalized_adjustment,
        'plan_adjustment_loss_tss': plan_adjustment_loss,
        'plan_adjustment_recoverable_tss': plan_adjustment_recoverable,
        'plan_adjustment_recovered_tss': plan_adjustment_recovered,
        'execution_adaptation_pressure': normalized_adjustment.get('execution_adaptation_pressure'),
        'current_tsb': current_tsb,
        'current_ctl': current_ctl,
        'current_atl': current_atl,
        'load_state': load_state['state'],
        'load_state_label': load_state['label'],
        'load_guard_loss_tss': load_guard_loss,
        'notes': summary_notes,
    }
    return adjusted_plan, details, summary


def triathlon_target_weekly_tss(distance: str) -> Tuple[int, int]:
    """Грубые целевые диапазоны недельного TSS по типу дистанции.
    Возвращает (min_tss, max_tss).
    """
    d = (distance or '').lower()
    if any(k in d for k in ['sprint', 'спринт']):
        return (300, 500)
    if any(k in d for k in ['olympic', 'олимп']):
        return (500, 700)
    if any(k in d for k in ['70.3', 'half', 'полу', 'half-iron']):
        return (700, 1000)
    if any(k in d for k in ['iron', 'full', 'полный']):
        return (1000, 1400)
    return (500, 700)


def running_target_weekly_tss(distance: str) -> Tuple[int, int]:
    d = (distance or '').lower()
    if any(k in d for k in ['5k', '5 км', '5к', '5 к']):
        return (250, 350)
    if any(k in d for k in ['10k', '10 км', '10к']):
        return (300, 450)
    if any(k in d for k in ['half', 'полумарафон', '21', '21k', '21 км']):
        return (500, 700)
    if any(k in d for k in ['marathon', 'марафон', '42', '42k', '42 км']):
        return (700, 1000)
    if any(k in d for k in ['ultra', 'ультра']):
        return (800, 1200)
    return (500, 700)


def cycling_target_weekly_tss(distance: str) -> Tuple[int, int]:
    d = (distance or '').lower()
    if any(k in d for k in ['40k', 'tt', 'разделка']):
        return (400, 600)
    if any(k in d for k in ['100km', '100 км', 'фондо', 'gran fondo']):
        return (600, 900)
    if any(k in d for k in ['century', '100mi', '160 км']):
        return (800, 1100)
    if any(k in d for k in ['200k', '200 км', 'бревет']):
        return (1000, 1400)
    if any(k in d for k in ['stage', 'этапная', 'многодневка']):
        return (1200, 1600)
    return (600, 900)


def goal_target_weekly_tss(goal_type: str, distance: str) -> Tuple[int, int]:
    g = (goal_type or '').lower()
    if 'триатлон' in g or 'tri' in g:
        return triathlon_target_weekly_tss(distance)
    if 'бег' in g or 'run' in g:
        return running_target_weekly_tss(distance)
    if 'вело' in g or 'bike' in g or 'cycle' in g:
        return cycling_target_weekly_tss(distance)
    return (500, 700)


def suggest_target_weekly_tss(goal_type: str, distance: str, activities_df) -> Dict[str, object]:
    """Оценивает разумный целевой Weekly TSS на основе истории.
    Основано на недельной агрегации TSS за последние 8–12 недель,
    ограничивает рост относительно последних недель и диапазона для дистанции.
    Возвращает словарь: {'suggested': int, 'last_week': float, 'avg_4': float, 'best_8': float}
    """
    try:
        import pandas as pd
    except Exception:
        # Защита на случай отсутствия pandas в окружении
        return {'suggested': goal_target_weekly_tss(goal_type, distance)[0], 'last_week': 0, 'avg_4': 0, 'best_8': 0}

    if activities_df is None or activities_df.empty or 'date' not in activities_df.columns:
        t_min, _ = goal_target_weekly_tss(goal_type, distance)
        return {'suggested': t_min, 'last_week': 0, 'avg_4': 0, 'best_8': 0}

    df = activities_df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    if 'tss' not in df.columns:
        df['tss'] = 0.0
    df['tss'] = pd.to_numeric(df['tss'], errors='coerce').fillna(0.0)

    # Недельная агрегация (Пн..Вс) — формируем явную колонку week_start
    week_start = (df['date'] - pd.to_timedelta(df['date'].dt.weekday, unit='D')).dt.date
    weekly = (
        pd.DataFrame({'week_start': week_start, 'tss': df['tss']})
        .groupby('week_start', as_index=False)['tss']
        .sum()
        .rename(columns={'tss': 'weekly_tss'})
        .sort_values('week_start')
    )

    # Берём последние 12 недель для анализа
    recent = weekly.tail(12)
    if recent.empty:
        t_min, _ = goal_target_weekly_tss(goal_type, distance)
        return {'suggested': t_min, 'last_week': 0, 'avg_4': 0, 'best_8': 0}

    last_week = float(recent['weekly_tss'].iloc[-1]) if len(recent) >= 1 else 0.0
    avg_4 = float(recent['weekly_tss'].tail(4).mean()) if len(recent) >= 1 else 0.0
    best_8 = float(recent['weekly_tss'].tail(8).max()) if len(recent) >= 1 else 0.0

    base_min, base_max = goal_target_weekly_tss(goal_type, distance)

    # Базовая цель — между avg_4*1.15 и base диапазоном
    candidate = max(avg_4 * 1.15, last_week * 1.10, base_min)
    # Ограничим потолок
    candidate = min(candidate, base_max, best_8 * 1.10, last_week * 1.25)
    suggested = int(round(candidate / 5.0) * 5)  # округление к кратному 5

    return {
        'suggested': max(base_min, min(suggested, base_max)),
        'last_week': round(last_week, 1),
        'avg_4': round(avg_4, 1),
        'best_8': round(best_8, 1),
    }


def create_weekly_tss_plan(
    start_weekly_tss: int,
    weeks_total: int,
    target_weekly_tss: int,
    deload_every: int = 4,
    taper_weeks: int = 2,
    max_ramp: float = 0.10,
) -> List[int]:
    """Формирует список недельных TSS до старта.
    - Рост не более `max_ramp` в неделю
    - Каждая `deload_every`-я неделя — разгрузка (-30%)
    - Последние `taper_weeks` — сужение (-40%, затем -60%)
    """
    if weeks_total <= 0:
        return []

    plan: List[int] = []
    current = max(0, int(start_weekly_tss))
    target = max(0, int(target_weekly_tss))

    for w in range(1, weeks_total + 1):
        # Тейпер на последние недели
        if weeks_total - w < taper_weeks:
            weeks_left = weeks_total - w
            if weeks_left == 1:
                val = int(round(target * 0.6))
            else:
                val = int(round(target * 0.8))
            plan.append(max(0, val))
            continue

        # Разгрузочная неделя
        if deload_every and (w % deload_every == 0):
            plan.append(int(round(current * 0.7)))
            continue

        # Плавный рост к цели
        if current < target:
            increment = max(20, int(round(current * max_ramp)))
            current = min(target, current + increment)
        else:
            # Если уже выше цели — подравниваемся
            current = target
        plan.append(current)

    return plan


def compute_phase_schedule(weeks_total: int) -> List[str]:
    """Возвращает список фаз 'Base'/'Build'/'Peak'/'Taper' длиной weeks_total.
    По умолчанию: Base 40%, Build 40%, Peak 15%, Taper 5% (не меньше 1 недели каждая при достаточном горизонте).
    """
    if weeks_total <= 0:
        return []
    base = max(1, int(round(weeks_total * 0.4)))
    build = max(1, int(round(weeks_total * 0.4)))
    peak = max(1, int(round(weeks_total * 0.15)))
    taper = max(1, weeks_total - (base + build + peak))
    # Подгонка до суммы
    phases = ['Base'] * base + ['Build'] * build + ['Peak'] * peak + ['Taper'] * taper
    # Обрезаем/дополняем
    phases = phases[:weeks_total]
    while len(phases) < weeks_total:
        phases.append('Taper')
    return phases


RACE_OVERLAY_RULE_VERSION = "race-microcycle-v2"
_RACE_PRE_CAPS = {
    "A": {-7: 0.65, -6: 0.60, -5: 0.55, -4: 0.50, -3: 0.40, -2: 0.30, -1: 0.20},
    "B": {-4: 0.75, -3: 0.60, -2: 0.45, -1: 0.25},
    "C": {-1: 0.70},
}

_RACE_MICROCYCLE_PRESCRIPTIONS = {
    "A": {
        -7: ("recovery", "swim", "Техника и восстановление • плавание"),
        -6: ("easy", "bike", "Легкая аэробная • вело"),
        -5: ("easy", "run", "Легкая аэробная • бег"),
        -4: ("recovery", "swim", "Техника • плавание"),
        -3: ("activation", "bike", "Короткое заострение • вело"),
        -2: ("off", "off", "Отдых перед стартом"),
        -1: ("activation", "run", "Короткая активация • бег"),
    },
    "B": {
        -4: ("easy", "swim", "Легкая техника • плавание"),
        -3: ("activation", "bike", "Короткое заострение • вело"),
        -2: ("off", "off", "Отдых перед стартом"),
        -1: ("activation", "run", "Короткая активация • бег"),
    },
    "C": {},
}
_RACE_PRIORITY_RANK = {"A": 0, "B": 1, "C": 2}
_PRESCRIPTION_SAFETY_RANK = {
    "race": 0,
    "off": 1,
    "recovery": 2,
    "activation": 3,
    "easy": 4,
}
_RACE_READINESS_HORIZON_DAYS = 7


def compute_event_aware_phase_schedule(
    weeks_total: int,
    *,
    planning_mode: str,
    intent: str = "develop",
    manual_phases: Sequence[str] | None = None,
) -> List[str]:
    """Return phases for race-anchored, rolling, or manual planning."""
    weeks = max(0, int(weeks_total or 0))
    if weeks == 0:
        return []
    mode = str(planning_mode or "event_goal").strip().lower()
    normalized_intent = str(intent or "develop").strip().lower()

    if mode == "manual":
        phases = [str(value).strip() for value in (manual_phases or []) if str(value).strip()]
        if len(phases) != weeks:
            raise ValueError("manual_phases must contain exactly horizon_weeks phases")
        return phases

    if mode == "training_goal":
        cycle = (
            ["Maintenance", "Maintenance", "Maintenance", "Recovery"]
            if normalized_intent == "maintain"
            else ["Base", "Base", "Build", "Recovery"]
        )
        return [cycle[index % len(cycle)] for index in range(weeks)]

    if mode != "event_goal":
        raise ValueError("planning_mode must be event_goal, training_goal, or manual")
    if weeks == 1:
        return ["Race Week"]
    if weeks == 2:
        return ["Taper", "Race Week"]
    return compute_phase_schedule(weeks - 2) + ["Taper", "Race Week"]


def apply_race_event_overlays(
    daily_plan: Sequence[Tuple[datetime, float, Dict[str, float]]],
    weekly_summary: Sequence[Mapping[str, object]],
    events: Any,
    *,
    goal_type: str = "",
    load_state: str = "balanced",
    as_of: date | None = None,
) -> Tuple[
    List[Tuple[datetime, float, Dict[str, float]]],
    List[Dict[str, object]],
    Dict[str, Any],
]:
    """Apply versioned A/B/C caps and deterministic race-microcycle intent."""
    from models.plan_events import normalized_events

    copied_daily = [(dt, float(total or 0.0), dict(parts or {})) for dt, total, parts in daily_plan]
    copied_summary: List[Dict[str, object]] = []
    for row in weekly_summary:
        copied = dict(row)
        copied["day_roles"] = list(row.get("day_roles") or ["easy"] * 7)
        copied["day_focuses"] = list(row.get("day_focuses") or ["—"] * 7)
        copied_summary.append(copied)

    available_dates = {dt.date().isoformat() for dt, _total, _parts in copied_daily}
    caps: Dict[str, float] = {}
    prescriptions: Dict[str, Dict[str, Any]] = {}
    contexts: Dict[str, Dict[str, Any]] = {}
    protected_dates: set[str] = set()
    overlays: List[Dict[str, Any]] = []
    is_triathlon = "триатлон" in str(goal_type or "").lower() or "tri" in str(goal_type or "").lower()
    normalized_load_state = str(load_state or "balanced").strip().lower()

    def activation_is_readiness_bounded(target: date) -> bool:
        if normalized_load_state != "deep_fatigue":
            return False
        if as_of is None:
            return False
        days_until = (target - as_of).days
        return 0 <= days_until < _RACE_READINESS_HORIZON_DAYS

    before_rows: Dict[str, Dict[str, Any]] = {}
    for index, (dt, total, parts) in enumerate(copied_daily):
        week_meta = copied_summary[index // 7] if index // 7 < len(copied_summary) else {}
        day_index = index % 7
        roles = list(week_meta.get("day_roles") or ["easy"] * 7)
        focuses = list(week_meta.get("day_focuses") or ["—"] * 7)
        before_rows[dt.date().isoformat()] = {
            "phase": str(week_meta.get("phase") or ""),
            "role": str(roles[day_index] if day_index < len(roles) else "easy"),
            "sport": _dominant_sport(parts),
            "focus": str(focuses[day_index] if day_index < len(focuses) else "—"),
            "tss": round(float(total or 0.0), 1),
        }

    def context_score(context: Mapping[str, Any]) -> tuple[int, int, str]:
        return (
            _RACE_PRIORITY_RANK.get(str(context.get("priority") or "C"), 3),
            abs(int(context.get("offset") or 0)),
            str(context.get("event_date") or ""),
        )

    def register_context(iso: str, context: Dict[str, Any]) -> None:
        current = contexts.get(iso)
        if current is None or context_score(context) < context_score(current):
            contexts[iso] = dict(context)

    def prescription_score(prescription: Mapping[str, Any]) -> tuple[int, int, int, str]:
        context = prescription.get("context") or {}
        return (
            _PRESCRIPTION_SAFETY_RANK.get(str(prescription.get("role") or "easy"), 5),
            _RACE_PRIORITY_RANK.get(str(context.get("priority") or "C"), 3),
            abs(int(context.get("offset") or 0)),
            str(context.get("event_date") or ""),
        )

    def set_cap(day: date, cap: float, *, context: Dict[str, Any]) -> None:
        iso = day.isoformat()
        if iso not in available_dates:
            return
        caps[iso] = min(float(cap), caps.get(iso, 1.0))
        register_context(iso, context)

    def set_prescription(
        day: date,
        *,
        role: str,
        sport: str | None,
        focus: str,
        context: Dict[str, Any],
    ) -> None:
        iso = day.isoformat()
        if iso not in available_dates:
            return
        candidate = {
            "role": role,
            "sport": sport if is_triathlon else None,
            "focus": focus,
            "context": dict(context),
        }
        current = prescriptions.get(iso)
        if current is None or prescription_score(candidate) < prescription_score(current):
            prescriptions[iso] = candidate
            contexts[iso] = dict(context)

    ordered_events = sorted(
        normalized_events(events),
        key=lambda event: (
            str(event.get("date") or ""),
            _RACE_PRIORITY_RANK.get(str(event.get("priority") or "C"), 3),
            str(event.get("label") or ""),
        ),
    )
    for event in ordered_events:
        try:
            event_day = date.fromisoformat(str(event["date"])[:10])
        except (TypeError, ValueError):
            continue
        priority = str(event["priority"])
        affected: List[str] = []
        for offset, cap in _RACE_PRE_CAPS[priority].items():
            target = event_day + timedelta(days=offset)
            context = {
                "event_date": event_day.isoformat(),
                "priority": priority,
                "offset": offset,
                "label": str(event.get("label") or ""),
            }
            set_cap(target, cap, context=context)
            prescription = (
                _RACE_MICROCYCLE_PRESCRIPTIONS[priority].get(offset)
                if is_triathlon
                else None
            )
            if (
                not is_triathlon
                and priority in {"A", "B"}
                and offset == -1
                and str((before_rows.get(target.isoformat()) or {}).get("role") or "")
                in {"long", "quality"}
            ):
                prescription = ("easy", None, "Легкая подводка перед стартом")
            if prescription is not None:
                role, sport, focus = prescription
                readiness_removed_activation = (
                    role == "activation" and activation_is_readiness_bounded(target)
                )
                if readiness_removed_activation:
                    role, sport, focus = "off", "off", "Отдых вместо активации · глубокая усталость"
                if role == "off":
                    set_cap(target, 0.0, context=context)
                    if not readiness_removed_activation:
                        protected_dates.add(target.isoformat())
                set_prescription(
                    target,
                    role=role,
                    sport=sport,
                    focus=focus,
                    context=context,
                )
            if target.isoformat() in available_dates:
                affected.append(target.isoformat())

        race_focus = f"Старт {priority} · {str(event.get('label') or '').strip()}".rstrip(" ·")
        race_context = {
            "event_date": event_day.isoformat(),
            "priority": priority,
            "offset": 0,
            "label": str(event.get("label") or ""),
        }
        set_cap(event_day, 0.0, context=race_context)
        set_prescription(
            event_day,
            role="race",
            sport="off",
            focus=race_focus,
            context=race_context,
        )
        if event_day.isoformat() in available_dates:
            protected_dates.add(event_day.isoformat())
            affected.append(event_day.isoformat())

        if priority in {"A", "B"}:
            for offset in (1, 2):
                target = event_day + timedelta(days=offset)
                context = {
                    "event_date": event_day.isoformat(),
                    "priority": priority,
                    "offset": offset,
                    "label": str(event.get("label") or ""),
                }
                set_cap(target, 0.0, context=context)
                set_prescription(
                    target,
                    role="off",
                    sport="off",
                    focus="Восстановление после старта",
                    context=context,
                )
                if target.isoformat() in available_dates:
                    protected_dates.add(target.isoformat())
                    affected.append(target.isoformat())
        else:
            target = event_day + timedelta(days=1)
            context = {
                "event_date": event_day.isoformat(),
                "priority": priority,
                "offset": 1,
                "label": str(event.get("label") or ""),
            }
            set_cap(target, 0.50, context=context)
            set_prescription(
                target,
                role="recovery",
                sport=None,
                focus="Восстановление после старта C",
                context=context,
            )
            if target.isoformat() in available_dates:
                affected.append(target.isoformat())

        overlays.append(
            {
                "date": event_day.isoformat(),
                "priority": priority,
                "label": str(event.get("label") or ""),
                "affected_dates": sorted(set(affected)),
            }
        )

    adjusted: List[Tuple[datetime, float, Dict[str, float]]] = []
    for dt, total, parts in copied_daily:
        iso = dt.date().isoformat()
        cap = max(0.0, min(1.0, caps.get(iso, 1.0)))
        adjusted_parts = {sport: round(float(value or 0.0) * cap, 1) for sport, value in parts.items()}
        adjusted_total = round(sum(adjusted_parts.values()), 1)
        if total > 0 and not parts:
            adjusted_total = round(total * cap, 1)
        prescription = prescriptions.get(iso) or {}
        role = str(prescription.get("role") or "")
        prescribed_sport = str(prescription.get("sport") or "")
        if role in {"off", "race"}:
            adjusted_parts = {sport: 0.0 for sport in (parts or {"run": 0, "bike": 0, "swim": 0})}
            adjusted_total = 0.0
        elif prescribed_sport in {"run", "bike", "swim"} and adjusted_total > 0:
            adjusted_parts = {"run": 0.0, "bike": 0.0, "swim": 0.0}
            adjusted_parts[prescribed_sport] = round(min(float(total or 0.0), adjusted_total), 1)
            adjusted_total = round(sum(adjusted_parts.values()), 1)
        adjusted.append((dt, round(min(float(total or 0.0), adjusted_total), 1), adjusted_parts))

    for week_index, summary in enumerate(copied_summary):
        week_rows = adjusted[week_index * 7 : week_index * 7 + 7]
        roles = list(summary.get("day_roles") or ["easy"] * 7)
        focuses = list(summary.get("day_focuses") or ["—"] * 7)
        while len(roles) < 7:
            roles.append("easy")
        while len(focuses) < 7:
            focuses.append("—")
        for day_index, (dt, _total, _parts) in enumerate(week_rows):
            iso = dt.date().isoformat()
            prescription = prescriptions.get(iso)
            if prescription is not None:
                roles[day_index] = str(prescription["role"])
                focuses[day_index] = str(prescription["focus"])
        summary["day_roles"] = roles
        summary["day_focuses"] = focuses
        summary["weekly_tss"] = int(round(sum(row[1] for row in week_rows)))
        for sport in ("bike", "run", "swim"):
            summary[sport] = round(sum(float(row[2].get(sport, 0.0) or 0.0) for row in week_rows), 1)
        summary.update(_build_week_structure_metadata(roles, focuses))

    after_rows: Dict[str, Dict[str, Any]] = {}
    for index, (dt, total, parts) in enumerate(adjusted):
        week_meta = copied_summary[index // 7] if index // 7 < len(copied_summary) else {}
        day_index = index % 7
        roles = list(week_meta.get("day_roles") or ["easy"] * 7)
        focuses = list(week_meta.get("day_focuses") or ["—"] * 7)
        after_rows[dt.date().isoformat()] = {
            "role": str(roles[day_index] if day_index < len(roles) else "easy"),
            "sport": _dominant_sport(parts),
            "focus": str(focuses[day_index] if day_index < len(focuses) else "—"),
            "tss": round(float(total or 0.0), 1),
        }

    microcycle_changes: List[Dict[str, Any]] = []
    for iso in sorted(contexts):
        before = before_rows.get(iso)
        after = after_rows.get(iso)
        if before is None or after is None:
            continue
        context = contexts[iso]
        microcycle_changes.append(
            {
                "date": iso,
                "event_date": str(context.get("event_date") or ""),
                "priority": str(context.get("priority") or ""),
                "label": str(context.get("label") or ""),
                "offset": int(context.get("offset") or 0),
                "phase": str(before.get("phase") or ""),
                "before": {
                    "role": before["role"],
                    "sport": before["sport"],
                    "focus": before["focus"],
                    "tss": before["tss"],
                },
                "after": dict(after),
            }
        )

    return adjusted, copied_summary, {
        "rule_version": RACE_OVERLAY_RULE_VERSION,
        "protected_dates": sorted(protected_dates),
        "overlays": overlays,
        "microcycle_changes": microcycle_changes,
    }


def synchronize_microcycle_changes(
    changes: Sequence[Mapping[str, Any]],
    daily_plan: Sequence[Tuple[datetime, float, Dict[str, float]]],
    session_templates: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Refresh overlay explainability from the final persisted daily/template truth."""
    daily_by_date = {
        dt.date().isoformat(): (round(float(total or 0.0), 1), dict(parts or {}))
        for dt, total, parts in daily_plan
    }
    templates_by_date = {
        str(template.get("date") or "")[:10]: dict(template)
        for template in session_templates
        if str(template.get("date") or "")[:10]
    }
    synchronized: List[Dict[str, Any]] = []
    for raw_change in changes:
        change = dict(raw_change or {})
        day = str(change.get("date") or "")[:10]
        daily = daily_by_date.get(day)
        template = templates_by_date.get(day)
        if daily is not None and template is not None:
            total, parts = daily
            change["after"] = {
                "role": str(template.get("session_role") or "easy"),
                "sport": str(template.get("sport") or _dominant_sport(parts)),
                "focus": str(
                    template.get("adjustment_note")
                    or template.get("session_focus")
                    or template.get("export_name")
                    or "—"
                ),
                "tss": total,
            }
        synchronized.append(change)
    return synchronized


def current_periodization_phase(goal_plan: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Resolve today's periodization phase (Base/Build/Peak/Taper) from an active goal plan.

    Returns None when there is no active plan or event_date — callers should
    treat "no phase" as a valid state (e.g. no goal set yet), not fall back to
    a guessed phase like 'Base'.
    """
    if not goal_plan:
        return None
    persisted_phases = [str(value) for value in (goal_plan.get("phases") or []) if str(value)]
    start_value = goal_plan.get("start_week")
    try:
        if isinstance(start_value, datetime):
            start_date = start_value.date()
        elif isinstance(start_value, date):
            start_date = start_value
        else:
            start_date = date.fromisoformat(str(start_value)[:10])
    except (TypeError, ValueError):
        start_date = None

    event_date_str = goal_plan.get("macrocycle_event_date") or goal_plan.get("event_date")
    event_dt = None
    if event_date_str:
        try:
            event_dt = date.fromisoformat(str(event_date_str)[:10])
        except (TypeError, ValueError):
            event_dt = None
    if persisted_phases and start_date is not None:
        current_idx = max(0, min(len(persisted_phases) - 1, (date.today() - start_date).days // 7))
        return {
            "phase": persisted_phases[current_idx],
            "days_to_race": (event_dt - date.today()).days if event_dt is not None else None,
            "total_weeks": len(persisted_phases),
        }
    if not event_date_str:
        return None
    try:
        event_dt = date.fromisoformat(str(event_date_str)[:10])
    except (TypeError, ValueError):
        return None
    days_to_race = (event_dt - date.today()).days
    if days_to_race < 0:
        return None
    weeks_remaining = days_to_race // 7
    total_weeks = int(goal_plan.get('weeks_to_race') or (weeks_remaining + 1))
    phases = compute_phase_schedule(total_weeks)
    if not phases:
        return None
    current_idx = max(0, min(len(phases) - 1, total_weeks - weeks_remaining - 1))
    return {
        'phase': phases[current_idx],
        'days_to_race': days_to_race,
        'total_weeks': total_weeks,
    }


def triathlon_weekly_mix(distance: str, phase: str) -> Dict[str, float]:
    """Проценты распределения TSS по видам спорта (bike/run/swim) на неделю.
    Сумма = 1.0
    """
    d = (distance or '').lower()
    # Базовые соотношения по дистанции (чем длиннее — тем больше bike)
    if any(k in d for k in ['iron', 'full', 'полный']):
        base_mix = {'bike': 0.55, 'run': 0.30, 'swim': 0.15}
    elif any(k in d for k in ['70.3', 'half', 'полу']):
        base_mix = {'bike': 0.50, 'run': 0.33, 'swim': 0.17}
    elif any(k in d for k in ['olympic', 'олимп']):
        base_mix = {'bike': 0.47, 'run': 0.35, 'swim': 0.18}
    else:  # sprint
        base_mix = {'bike': 0.45, 'run': 0.37, 'swim': 0.18}

    # Корректировка по фазам
    phase = (phase or 'Base').lower()
    if phase == 'base':
        adj = {'bike': 0.00, 'run': 0.00, 'swim': 0.00}
    elif phase == 'build':
        adj = {'bike': -0.02, 'run': +0.02, 'swim': 0.00}
    elif phase == 'peak':
        adj = {'bike': -0.02, 'run': +0.02, 'swim': 0.00}
    elif phase in {'maintenance'}:
        adj = {'bike': 0.00, 'run': 0.00, 'swim': 0.00}
    else:  # taper
        adj = {'bike': -0.03, 'run': -0.02, 'swim': +0.05}

    mix = {k: max(0.05, min(0.85, base_mix[k] + adj[k])) for k in base_mix}
    s = sum(mix.values())
    return {k: v / s for k, v in mix.items()}


def daily_weights_for_phase(phase: str) -> Dict[str, List[float]]:
    """Весовые коэффициенты по дням недели для распределения внутри недели.
    На выходе словарь с ключами 'bike','run','swim', значения — список из 7 весов, сумма по каждому = 1.
    Пн..Вс.
    """
    p = (phase or 'Base').lower()
    if p == 'base':
        run =  [0.10, 0.18, 0.15, 0.07, 0.22, 0.18, 0.10]
        bike = [0.10, 0.15, 0.20, 0.05, 0.25, 0.15, 0.10]
        swim = [0.15, 0.15, 0.20, 0.10, 0.15, 0.15, 0.10]
    elif p == 'build':
        run =  [0.08, 0.20, 0.18, 0.06, 0.24, 0.16, 0.08]
        bike = [0.08, 0.18, 0.22, 0.04, 0.26, 0.14, 0.08]
        swim = [0.16, 0.16, 0.18, 0.10, 0.18, 0.14, 0.08]
    elif p == 'peak':
        run =  [0.08, 0.22, 0.20, 0.05, 0.25, 0.12, 0.08]
        bike = [0.08, 0.20, 0.24, 0.04, 0.26, 0.10, 0.08]
        swim = [0.18, 0.18, 0.16, 0.10, 0.16, 0.14, 0.08]
    elif p == 'maintenance':
        run =  [0.10, 0.18, 0.15, 0.07, 0.22, 0.18, 0.10]
        bike = [0.10, 0.15, 0.20, 0.05, 0.25, 0.15, 0.10]
        swim = [0.15, 0.15, 0.20, 0.10, 0.15, 0.15, 0.10]
    else:  # taper, race week, recovery
        run =  [0.12, 0.18, 0.16, 0.08, 0.18, 0.16, 0.12]
        bike = [0.12, 0.18, 0.18, 0.08, 0.18, 0.16, 0.10]
        swim = [0.18, 0.16, 0.18, 0.12, 0.16, 0.12, 0.08]

    # Нормировка на случай неточных сумм
    def norm(x: List[float]) -> List[float]:
        s = sum(x) or 1.0
        return [v / s for v in x]

    return {'run': norm(run), 'bike': norm(bike), 'swim': norm(swim)}


def _normalize_mix(mix: Dict[str, float]) -> Dict[str, float]:
    s = sum(max(0.0, v) for v in mix.values()) or 1.0
    return {k: max(0.0, v) / s for k, v in mix.items()}


def _normalize_weights(weights: List[float]) -> List[float]:
    s = sum(max(0.0, x) for x in weights) or 1.0
    return [max(0.0, x) / s for x in weights]


def _prefer_sunday_long_day(goal_type: str) -> bool:
    del goal_type
    return False


def _pick_preferred_day(preferred: List[int], allowed_days: List[int], excluded: set[int] | None = None) -> int | None:
    excluded = excluded or set()
    for day_idx in preferred:
        if day_idx in allowed_days and day_idx not in excluded:
            return day_idx
    for day_idx in allowed_days:
        if day_idx not in excluded:
            return day_idx
    return None


def _session_quality_count(phase: str, active_day_count: int, load_state: str) -> int:
    p = (phase or "Base").lower()
    if active_day_count < 3:
        return 0

    if p in {"build", "peak"}:
        count = 2 if active_day_count >= 5 else 1
    elif p in {"taper", "race week"}:
        count = 1 if active_day_count >= 4 else 0
    elif p == "recovery":
        count = 0
    else:
        count = 1 if active_day_count >= 4 else 0

    if load_state == "fatigued":
        count = max(0, count - 1)
    elif load_state == "deep_fatigue":
        count = max(0, count - 1)

    if load_state == "fresh" and p in {"build", "peak"} and active_day_count >= 6:
        count = max(count, 2)

    return min(count, max(0, active_day_count - 1))


def _session_recovery_count(active_day_count: int, quality_count: int, load_state: str, phase: str) -> int:
    if active_day_count < 4:
        return 0

    recovery_count = 1
    if load_state in {"fatigued", "deep_fatigue"} and active_day_count >= 5:
        recovery_count = 2
    elif (phase or "").lower() in {"taper", "race week", "recovery"} and active_day_count >= 5:
        recovery_count = 2

    max_recovery = max(0, active_day_count - quality_count - 1)
    return min(recovery_count, max_recovery)


def _build_recovery_aware_day_roles(
    active_days: List[int],
    phase: str,
    goal_type: str,
    load_state: str,
) -> List[str]:
    roles = ["off"] * 7
    if not active_days:
        return roles

    for day_idx in active_days:
        roles[day_idx] = "easy"

    preferred_long = [6, 5, 4, 3, 2, 1, 0] if _prefer_sunday_long_day(goal_type) else [5, 6, 4, 3, 2, 1, 0]
    long_day = _pick_preferred_day(preferred_long, active_days)
    if long_day is not None:
        roles[long_day] = "long"

    quality_count = _session_quality_count(phase, len(active_days), load_state)
    quality_preferred = [1, 3, 2, 4, 0, 6, 5]
    reserved = {long_day} if long_day is not None else set()
    quality_days: List[int] = []
    for _ in range(quality_count):
        quality_day = _pick_preferred_day(quality_preferred, active_days, reserved | set(quality_days))
        if quality_day is None:
            break
        quality_days.append(quality_day)
        roles[quality_day] = "quality"

    recovery_target = _session_recovery_count(len(active_days), len(quality_days), load_state, phase)
    recovery_days: List[int] = []
    key_days = sorted([day for day in quality_days if day is not None] + ([long_day] if long_day is not None else []))
    for key_day in key_days:
        next_active = next(
            (
                day_idx
                for day_idx in active_days
                if day_idx > key_day and roles[day_idx] == "easy" and day_idx not in recovery_days
            ),
            None,
        )
        if next_active is not None:
            recovery_days.append(next_active)
            if len(recovery_days) >= recovery_target:
                break
        prev_active = next(
            (
                day_idx
                for day_idx in reversed(active_days)
                if day_idx < key_day and roles[day_idx] == "easy" and day_idx not in recovery_days
            ),
            None,
        )
        if prev_active is not None:
            recovery_days.append(prev_active)
            if len(recovery_days) >= recovery_target:
                break

    if len(recovery_days) < recovery_target:
        for day_idx in [0, 2, 4, 6, 1, 3, 5]:
            if day_idx in active_days and roles[day_idx] == "easy" and day_idx not in recovery_days:
                recovery_days.append(day_idx)
                if len(recovery_days) >= recovery_target:
                    break

    for day_idx in recovery_days[:recovery_target]:
        roles[day_idx] = "recovery"

    return roles


def _role_multipliers_for_week(phase: str, load_state: str) -> Dict[str, float]:
    p = (phase or "Base").lower()
    if p == "build":
        multipliers = {"off": 0.0, "recovery": 0.55, "easy": 0.92, "quality": 1.18, "long": 1.30}
    elif p == "peak":
        multipliers = {"off": 0.0, "recovery": 0.55, "easy": 0.88, "quality": 1.22, "long": 1.25}
    elif p == "taper":
        multipliers = {"off": 0.0, "recovery": 0.65, "easy": 0.95, "quality": 1.05, "long": 1.05}
    else:
        multipliers = {"off": 0.0, "recovery": 0.58, "easy": 0.95, "quality": 1.10, "long": 1.25}

    if load_state == "fresh":
        multipliers["quality"] += 0.05
        multipliers["long"] += 0.05
    elif load_state == "fatigued":
        multipliers["recovery"] += 0.15
        multipliers["easy"] += 0.03
        multipliers["quality"] = max(0.75, multipliers["quality"] - 0.12)
        multipliers["long"] = max(0.85, multipliers["long"] - 0.10)
    elif load_state == "deep_fatigue":
        multipliers["recovery"] += 0.20
        multipliers["easy"] += 0.08
        multipliers["quality"] = max(0.70, multipliers["quality"] - 0.20)
        multipliers["long"] = max(0.80, multipliers["long"] - 0.15)

    return multipliers


def _dominant_sport(parts: Dict[str, float]) -> str:
    active = {sport: float(value or 0.0) for sport, value in parts.items() if float(value or 0.0) > 0.0}
    if not active:
        return "off"
    return max(active.items(), key=lambda item: item[1])[0]


def _build_day_focus_label(role: str, sport: str) -> str:
    if role == "off":
        return "Отдых"
    role_label = SESSION_ROLE_LABELS_RU.get(role, role.title())
    sport_label = SPORT_LABELS_RU.get(sport, sport)
    return f"{role_label} • {sport_label}"


def _apply_recovery_aware_day_structure(
    week_parts: List[Dict[str, float]],
    week_total_tss: int,
    phase: str,
    goal_type: str,
    load_state: str,
) -> Tuple[List[Dict[str, float]], List[str], List[str]]:
    active_days = [idx for idx, parts in enumerate(week_parts) if sum(float(value or 0.0) for value in parts.values()) > 0.0]
    roles = _build_recovery_aware_day_roles(active_days, phase, goal_type, load_state)
    multipliers = _role_multipliers_for_week(phase, load_state)

    base_totals = [sum(float(value or 0.0) for value in parts.values()) for parts in week_parts]
    weighted_totals = [base_totals[idx] * multipliers.get(roles[idx], 1.0) for idx in range(7)]
    weighted_sum = sum(weighted_totals)

    if weighted_sum <= 0:
        focuses = [_build_day_focus_label(roles[idx], _dominant_sport(week_parts[idx])) for idx in range(7)]
        return week_parts, roles, focuses

    scale = float(week_total_tss) / weighted_sum
    adjusted_parts: List[Dict[str, float]] = []
    for idx, parts in enumerate(week_parts):
        day_total = base_totals[idx]
        if day_total <= 0:
            adjusted_parts.append({"run": 0.0, "bike": 0.0, "swim": 0.0})
            continue

        scaled_total = weighted_totals[idx] * scale
        ratio = scaled_total / day_total if day_total > 0 else 0.0
        adjusted_parts.append(
            {
                "run": round(float(parts.get("run", 0.0)) * ratio, 1),
                "bike": round(float(parts.get("bike", 0.0)) * ratio, 1),
                "swim": round(float(parts.get("swim", 0.0)) * ratio, 1),
            }
        )

    total_after = round(sum(sum(parts.values()) for parts in adjusted_parts), 1)
    diff = round(float(week_total_tss) - total_after, 1)
    if abs(diff) >= 0.1 and active_days:
        target_day = _pick_preferred_day(
            [idx for idx, role in enumerate(roles) if role == "long"] + list(reversed(active_days)),
            active_days,
        )
        if target_day is not None:
            sport = _dominant_sport(adjusted_parts[target_day])
            if sport == "off":
                sport = "run"
            adjusted_parts[target_day][sport] = round(max(0.0, adjusted_parts[target_day].get(sport, 0.0) + diff), 1)

    focuses = [_build_day_focus_label(roles[idx], _dominant_sport(adjusted_parts[idx])) for idx in range(7)]
    return adjusted_parts, roles, focuses


def _build_week_structure_metadata(
    roles: List[str],
    focuses: List[str],
) -> Dict[str, object]:
    long_days = [idx for idx, role in enumerate(roles) if role == "long"]
    quality_days = [idx for idx, role in enumerate(roles) if role == "quality"]
    activation_days = [idx for idx, role in enumerate(roles) if role == "activation"]
    recovery_days = [idx for idx, role in enumerate(roles) if role == "recovery"]

    key_labels = [
        f"{WEEKDAY_LABELS_RU[idx]} {focuses[idx].lower()}"
        for idx in quality_days + long_days + activation_days
    ]
    recovery_labels = [WEEKDAY_LABELS_RU[idx] for idx in recovery_days]
    structure_summary = (
        f"{len(quality_days)} качеств. дн., "
        f"{len(activation_days)} активац., "
        f"{len(recovery_days)} восстановит. дн., "
        f"длительная: {WEEKDAY_LABELS_RU[long_days[0]] if long_days else '—'}"
    )

    return {
        "day_roles": roles,
        "day_focuses": focuses,
        "key_sessions": "; ".join(key_labels) if key_labels else "—",
        "recovery_days": ", ".join(recovery_labels) if recovery_labels else "—",
        "structure_summary": structure_summary,
    }


def goal_weekly_mix(goal_type: str, distance: str, phase: str) -> Dict[str, float]:
    g = (goal_type or '').lower()
    if 'триатлон' in g or 'tri' in g:
        return triathlon_weekly_mix(distance, phase)
    if 'бег' in g or 'run' in g:
        return {'run': 1.0, 'bike': 0.0, 'swim': 0.0}
    if 'вело' in g or 'bike' in g or 'cycle' in g:
        return {'run': 0.0, 'bike': 1.0, 'swim': 0.0}
    return {'run': 1.0, 'bike': 0.0, 'swim': 0.0}


def expand_weekly_to_daily_triathlon(
    weekly_tss: List[int],
    phases: List[str],
    distance: str,
    start_date: date,
    mix_overrides: Dict[str, Dict[str, float]] | None = None,
    weights_overrides: Dict[str, Dict[str, List[float]]] | None = None,
    available_day_indices: List[int] | None = None,
    goal_type: str = "Триатлон",
    load_state: str = "balanced",
    available_weekly_hours: float | None = None,
) -> Tuple[List[Tuple[datetime, float, Dict[str, float]]], List[Dict[str, object]]]:
    """Разворачивает недельный triathlon-план в поминутную ленту по дням с разбивкой по видам спорта.
    Возвращает:
      - daily: список (datetime, total_daily_tss, {'run':..., 'bike':..., 'swim':...})
      - weekly_summary: список словарей {'week_start': date, 'phase': str, 'weekly_tss': int, 'bike': float, 'run': float, 'swim': float}
    """
    daily: List[Tuple[datetime, float, Dict[str, float]]] = []
    weekly_summary: List[Dict[str, object]] = []
    # Issue #205 M3b.1 r4: rotation state — плановый, не недельный. Scheduler и
    # builder стартуют с одинаково пустой истории шаблонов и проходят недели в
    # одном порядке; projected rotation прошлой недели — вход следующей.
    projected_template_rotation: List[str] = []

    current = datetime.combine(start_date, datetime.min.time())
    for w_idx, w_tss in enumerate(weekly_tss):
        phase = phases[w_idx] if w_idx < len(phases) else phases[-1] if phases else 'Base'
        # Микс дисциплин: кастом или дефолт
        if mix_overrides and phase in mix_overrides:
            mix = _normalize_mix(mix_overrides[phase])
        else:
            # Используем общий микс (триатлон/бег/вело)
            # Для обратной совместимости тут не знаем goal_type — ожидаем, что
            # вызывающая сторона подаст mix_overrides для не‑триатлона.
            # По умолчанию берём триатлонский базовый микс.
            mix = triathlon_weekly_mix(distance, phase)
        # Сумма по видам на неделю — недельный sport budget.
        run_week = round(w_tss * mix['run'], 1)
        bike_week = round(w_tss * mix['bike'], 1)
        swim_week = round(w_tss * mix['swim'], 1)

        # Issue #205 M3b: недельный бюджет размещается детерминированным slot
        # scheduler'ом в ограниченное число дневных слотов (роли, two-a-day
        # пары, день отдыха), а не размазывается весами по всем семи дням.
        # Цепочка: weekly sport budget → слоты → allocated_parts → sessions[]
        # → weekly_summary. Текущая готовность (load_state) ограничена
        # семидневным окном от начала плана: будущие недели планируются как
        # "balanced", чтобы сегодняшняя усталость не стирала будущие brick'и и
        # активации (прецедент Issue #201/#202).
        from models.session_scheduler import schedule_week_slots

        # Issue #205 M3b.1: пользовательские weights_overrides не игнорируются
        # молча — они становятся слот-преференциями (длинная едет в самый
        # тяжёлый предпочтённый день спортсмена).
        day_preferences = None
        if weights_overrides and phase in weights_overrides:
            converted = {
                sport: [float(v or 0.0) for v in vector]
                for sport, vector in weights_overrides[phase].items()
                if sport in ("run", "bike", "swim")
                and vector
                and any(float(v or 0.0) > 0 for v in vector)
            }
            day_preferences = converted or None

        week_within_readiness_window = current.date() < start_date + timedelta(days=7)
        slot_plan = schedule_week_slots(
            week_budget={"run": run_week, "bike": bike_week, "swim": swim_week},
            phase=phase,
            goal_type=goal_type,
            load_state=load_state if week_within_readiness_window else "balanced",
            available_day_indices=available_day_indices,
            available_weekly_hours=available_weekly_hours,
            day_preferences=day_preferences,
            template_rotation=projected_template_rotation,
        )
        projected_template_rotation = list(slot_plan.get("template_rotation") or projected_template_rotation)
        adjusted_week_parts = slot_plan["allocated_parts"]
        day_roles = slot_plan["day_roles"]
        day_focuses = slot_plan["day_focuses"]

        bike_total = round(sum(parts.get('bike', 0.0) for parts in adjusted_week_parts), 1)
        run_total = round(sum(parts.get('run', 0.0) for parts in adjusted_week_parts), 1)
        swim_total = round(sum(parts.get('swim', 0.0) for parts in adjusted_week_parts), 1)
        structure_meta = _build_week_structure_metadata(day_roles, day_focuses)

        weekly_summary.append({
            'week_start': current.date(),
            'phase': phase,
            # Issue #205 M3b: недельный TSS — сумма размещённого бюджета; при
            # явном hours-трим scheduler'а она честно меньше исходного w_tss.
            'weekly_tss': int(round(bike_total + run_total + swim_total)),
            'bike': bike_total,
            'run': run_total,
            'swim': swim_total,
            **structure_meta,
        })
        if slot_plan["notes"]:
            weekly_summary[-1]["scheduler_notes"] = list(slot_plan["notes"])
            weekly_summary[-1]["scheduler_status"] = slot_plan["status"]

        for parts in adjusted_week_parts:
            total = round(parts.get('run', 0.0) + parts.get('bike', 0.0) + parts.get('swim', 0.0), 1)
            daily.append((current, total, parts))
            current += timedelta(days=1)

    return daily, weekly_summary


def flatten_daily_total(daily: List[Tuple[datetime, float, Dict[str, float]]]) -> List[Tuple[datetime, float]]:
    """Преобразует расширенный daily список в (date, total) для симуляции."""
    return [(dt, total) for dt, total, _ in daily]


def _estimate_session_duration_minutes(total_tss: float, sport: str, session_role: str) -> int:
    base_minutes_per_tss = {
        "run": 1.0,
        "bike": 1.8,
        "swim": 1.4,
        "off": 0.8,
    }
    role_multiplier = {
        "off": 0.75,
        "recovery": 1.25,
        "easy": 1.10,
        "quality": 0.95,
        "long": 1.35,
    }
    sport_key = sport if sport in base_minutes_per_tss else "run"
    role_key = session_role if session_role in role_multiplier else "easy"
    total = max(0.0, float(total_tss or 0.0))
    if total <= 0:
        return 0
    estimated = total * base_minutes_per_tss[sport_key] * role_multiplier[role_key]
    return max(30, min(240, int(round(estimated / 5.0) * 5)))


def _build_session_export_name(goal_type: str, distance: str, session_focus: str) -> str:
    goal_label = " ".join(part for part in [str(goal_type or "").strip(), str(distance or "").strip()] if part)
    focus_label = str(session_focus or "").strip()
    if focus_label and focus_label != "—":
        return f"{goal_label} — {focus_label}" if goal_label else focus_label
    return goal_label or "План тренировки"


def _build_session_description(
    goal_type: str,
    distance: str,
    phase: str,
    session_role: str,
    session_focus: str,
    sport: str,
    total_tss: float,
    parts: Mapping[str, float],
    duration_minutes: int,
) -> str:
    lines = [
        "План из AI Trainer",
        f"Цель: {goal_type} / {distance}",
        f"Фаза: {phase or 'Base'}",
    ]
    if session_focus and session_focus != "—":
        lines.append(f"Фокус: {session_focus}")
    lines.append(f"Роль дня: {SESSION_ROLE_LABELS_RU.get(session_role, session_role)}")
    lines.append(f"Основной спорт: {SPORT_LABELS_RU.get(sport, sport)}")
    lines.append(f"Оценка длительности: {duration_minutes} мин")
    lines.append(f"Total TSS: {round(float(total_tss or 0.0), 1)}")
    lines.append(f"Run: {round(float(parts.get('run', 0.0) or 0.0), 1)}")
    lines.append(f"Bike: {round(float(parts.get('bike', 0.0) or 0.0), 1)}")
    lines.append(f"Swim: {round(float(parts.get('swim', 0.0) or 0.0), 1)}")
    return "\n".join(lines)


_SPLIT_SPORT_ORDER = ("bike", "run", "swim")


def _split_day_sessions(
    *,
    parts: Mapping[str, float],
    total: float,
    is_brick: bool,
    phase: str,
    session_role: str,
    day_focus: str,
    goal_type: str,
    distance: str,
    zone_snapshot: Mapping[str, Any],
    load_state: str,
    recent_template_keys: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, float], Dict[str, str]]:
    """Issue #205 M3: materialize one executable session per discipline.

    The blended day budget in ``parts`` is preserved exactly: each discipline
    with a non-zero share becomes its own session carrying that share's TSS
    (short if small — same-discipline preservation, never re-glued onto the
    dominant sport). A feasible brick day is one composite session whose legs
    carry the bike/run budget (``brick_status="grouped"``); an infeasible brick
    day falls back to independent same-discipline sessions with
    ``brick_status="not_grouped"`` and the refusal reason. Returns
    ``(sessions, allocated_parts, day_meta)`` where ``allocated_parts`` is the
    immutable distributor decision.
    """
    from models.workout_catalog import materialize_brick_session, materialize_session_template

    def _finalize(sport: str, role: str, tss: float, catalog: Dict[str, Any]) -> Dict[str, Any]:
        duration = int(catalog.get("duration_minutes") or _estimate_session_duration_minutes(tss, sport, role))
        name = str(catalog.get("template_name") or "").strip() or day_focus
        export_name = _build_session_export_name(goal_type, distance, name)
        description = _build_session_description(
            goal_type=goal_type,
            distance=distance,
            phase=phase,
            session_role=role,
            session_focus=name,
            sport=sport,
            total_tss=tss,
            parts={sport: tss},
            duration_minutes=duration,
        )
        return {
            "sport": sport,
            "sport_label": SPORT_LABELS_RU.get(sport, sport),
            "session_role": role,
            "session_focus": name,
            "duration_minutes": duration,
            "total_tss": round(float(tss or 0.0), 1),
            "template_key": f"{phase.lower()}:{role}:{sport}",
            "export_name": export_name,
            "description": description,
            **catalog,
        }

    if is_brick:
        duration = _estimate_session_duration_minutes(total, _dominant_sport(parts), session_role)
        catalog = materialize_brick_session(
            phase=phase,
            target_tss=total,
            parts=dict(parts),
            estimated_duration_minutes=duration,
            goal_type=goal_type,
            zone_snapshot=zone_snapshot,
            load_state=load_state,
        )
        if catalog.get("materialization_status") == "materialized" and catalog.get("kind") == "composite":
            allocated: Dict[str, float] = {}
            for leg in catalog.get("legs") or []:
                leg_sport = str(leg.get("sport") or "")
                allocated[leg_sport] = round(allocated.get(leg_sport, 0.0) + float(leg.get("target_tss") or 0.0), 1)
            recent_template_keys.append(str(catalog.get("template_key") or ""))
            return (
                [_finalize("brick", session_role, total, catalog)],
                allocated,
                {"brick_status": "grouped"},
            )
        # Brick infeasible on this day: fall through to independent same-day
        # sessions of the same disciplines with their original TSS. The refusal
        # is recorded, never silently re-glued onto the dominant sport; the
        # sport budget is not the brick allocator's to change.
        brick_meta = {
            "brick_status": "not_grouped",
            "brick_status_reason": str(catalog.get("materialization_status") or "infeasible"),
        }
    else:
        brick_meta = {}

    disciplines = [d for d in _SPLIT_SPORT_ORDER if round(float(parts.get(d, 0.0) or 0.0), 1) > 0]
    disciplines.sort(key=lambda d: (-round(float(parts.get(d, 0.0) or 0.0), 1), _SPLIT_SPORT_ORDER.index(d)))
    sessions: List[Dict[str, Any]] = []
    allocated = {}
    for position, discipline in enumerate(disciplines):
        discipline_tss = round(float(parts.get(discipline, 0.0) or 0.0), 1)
        allocated[discipline] = discipline_tss
        role = session_role if position == 0 else "easy"
        duration = _estimate_session_duration_minutes(discipline_tss, discipline, role)
        catalog = materialize_session_template(
            phase=phase,
            session_role=role,
            sport=discipline,
            target_tss=discipline_tss,
            estimated_duration_minutes=duration,
            goal_type=goal_type,
            zone_snapshot=zone_snapshot,
            load_state=load_state,
            recent_template_keys=recent_template_keys,
        )
        if catalog.get("materialization_status") == "materialized":
            recent_template_keys.append(str(catalog.get("template_key") or ""))
        sessions.append(_finalize(discipline, role, discipline_tss, catalog))
    return sessions, allocated, brick_meta


def build_daily_session_templates(
    daily: List[Tuple[datetime, float, Dict[str, float]]],
    weekly_summary: Sequence[Mapping[str, object]],
    goal_type: str,
    distance: str,
    *,
    load_state: str = "balanced",
    zone_snapshot: Mapping[str, Any] | None = None,
    brick_day_indices: set[int] | Sequence[int] = (),
) -> List[Dict[str, Any]]:
    """Строит метаданные сессий, выровненные с daily plan без смены его контракта."""
    from models.workout_catalog import (
        materialize_brick_session,
        materialize_session_template,
    )

    templates: List[Dict[str, Any]] = []
    brick_indices = {int(value) for value in brick_day_indices}
    resolved_zones = dict(zone_snapshot or {})
    recent_template_keys: List[str] = []

    for idx, (dt, total, parts) in enumerate(daily):
        week_idx = idx // 7
        day_idx = idx % 7
        week_meta = weekly_summary[week_idx] if week_idx < len(weekly_summary) else {}
        day_roles = list(week_meta.get("day_roles") or ["easy"] * 7)
        day_focuses = list(week_meta.get("day_focuses") or ["—"] * 7)
        session_role = str(day_roles[day_idx] if day_idx < len(day_roles) else "easy")
        session_focus = str(day_focuses[day_idx] if day_idx < len(day_focuses) else "—")
        phase = str(week_meta.get("phase", "Base") or "Base")
        dominant = _dominant_sport(parts)
        is_training = (
            float(total or 0.0) > 0 and dominant not in {"off", "race"} and session_role != "off"
        )
        if is_training:
            day_sessions, allocated_parts, day_meta = _split_day_sessions(
                parts=parts,
                total=float(total or 0.0),
                is_brick=idx in brick_indices,
                phase=phase,
                session_role=session_role,
                day_focus=session_focus,
                goal_type=goal_type,
                distance=distance,
                zone_snapshot=resolved_zones,
                load_state=load_state,
                recent_template_keys=recent_template_keys,
            )
        else:
            day_sessions, allocated_parts, day_meta = [], {}, {}

        # Issue #205 M3: day-level scalar fields are a projection of sessions[0];
        # a rest/race day (no sessions) keeps its off scalars. daily_plan parts
        # are never overwritten — they remain the immutable budget.
        if day_sessions:
            primary = dict(day_sessions[0])
            sport = str(primary.get("sport") or dominant)
            session_focus = str(primary.get("session_focus") or session_focus)
            duration_minutes = int(primary.get("duration_minutes") or 0)
            export_name = str(
                primary.get("export_name") or _build_session_export_name(goal_type, distance, session_focus)
            )
            description = str(primary.get("description") or "")
            template_key = str(primary.get("template_key") or f"{phase.lower()}:{session_role}:{sport}")
            projected = {
                key: value
                for key, value in primary.items()
                if key
                not in {
                    "sport",
                    "sport_label",
                    "session_role",
                    "session_focus",
                    "duration_minutes",
                    "total_tss",
                    "template_key",
                    "export_name",
                    "description",
                }
            }
        else:
            sport = dominant if is_training else "off"
            duration_minutes = 0
            export_name = _build_session_export_name(goal_type, distance, session_focus)
            description = _build_session_description(
                goal_type=goal_type,
                distance=distance,
                phase=phase,
                session_role=session_role,
                session_focus=session_focus,
                sport=sport,
                total_tss=total,
                parts=parts,
                duration_minutes=duration_minutes,
            )
            template_key = f"{phase.lower()}:{session_role}:{sport}"
            projected = {}

        templates.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "week_index": week_idx,
                "day_index": day_idx,
                "phase": phase,
                "session_role": session_role,
                "session_focus": session_focus,
                "sport": sport,
                "sport_label": SPORT_LABELS_RU.get(sport, sport),
                "duration_minutes": duration_minutes,
                "template_key": template_key,
                "export_name": export_name,
                "description": description,
                "allocated_parts": allocated_parts,
                **day_meta,
                **projected,
                "sessions": day_sessions,
            }
        )

    return templates


def iter_leaf_sessions(template: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Ordered executable leaf sessions of one day template.

    Issue #205 read model shared by delivery, Today, and dashboards. A single
    session yields one leaf; a composite brick yields one leaf per leg in leg
    order (kept separate); a rest or race day (``sessions == []``) yields none,
    so race/rest is never counted as a training session.
    """
    leaves: List[Dict[str, Any]] = []
    for session in list(template.get("sessions") or []):
        if not isinstance(session, Mapping):
            continue
        if str(session.get("kind") or "single") == "composite":
            for position, leg in enumerate(list(session.get("legs") or []), start=1):
                leaves.append(
                    {
                        "kind": "brick_leg",
                        "session_id": leg.get("leg_id") or session.get("session_id"),
                        "group_id": session.get("session_id"),
                        "leg_index": int(leg.get("leg_index") or position),
                        "sport": str(leg.get("sport") or ""),
                        "sport_label": SPORT_LABELS_RU.get(str(leg.get("sport") or ""), str(leg.get("sport") or "")),
                        "session_role": str(session.get("session_role") or ""),
                        "total_tss": round(float(leg.get("target_tss") or 0.0), 1),
                        "name": str(leg.get("template_name") or session.get("export_name") or "Brick leg"),
                        "materialized_steps": list(leg.get("materialized_steps") or []),
                    }
                )
        else:
            leaves.append(
                {
                    "kind": "single",
                    "session_id": session.get("session_id"),
                    "sport": str(session.get("sport") or ""),
                    "sport_label": str(session.get("sport_label") or SPORT_LABELS_RU.get(str(session.get("sport") or ""), str(session.get("sport") or ""))),
                    "session_role": str(session.get("session_role") or ""),
                    "total_tss": round(float(session.get("total_tss") or 0.0), 1),
                    "name": str(session.get("export_name") or session.get("template_name") or "Сессия"),
                    "materialized_steps": list(session.get("materialized_steps") or []),
                }
            )
    return leaves


def derive_weekly_sport_buckets_from_sessions(
    weekly_summary: Sequence[Mapping[str, object]],
    session_templates: Sequence[Mapping[str, Any]],
) -> List[Dict[str, object]]:
    """Issue #205: the weekly per-sport buckets are a derived projection of the
    materialized leaf sessions — the product table must be computed from what
    the athlete would actually execute, never from the pre-split accounting
    parts. Layering: parts/allocated_parts → sessions[] → weekly_summary."""
    derived = [dict(row or {}) for row in weekly_summary]
    for week_index, row in enumerate(derived):
        buckets = {"bike": 0.0, "run": 0.0, "swim": 0.0}
        for template in list(session_templates)[week_index * 7 : week_index * 7 + 7]:
            if not isinstance(template, Mapping):
                continue
            for leaf in iter_leaf_sessions(template):
                sport = str(leaf.get("sport") or "")
                if sport in buckets:
                    buckets[sport] = round(
                        buckets[sport] + float(leaf.get("total_tss") or 0.0), 1
                    )
        row.update(buckets)
    return derived


def create_ics_from_daily(
    daily: List[Tuple[datetime, float, Dict[str, float]]],
    title_prefix: str = "Planned Training",
    duration_minutes: int = 60,
    session_templates: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Генерирует ICS календарь из дневного плана.
    Создаёт по одному событию в день с суммарным TSS и разбивкой в описании.
    """
    import uuid

    def fmt_dt(dt: datetime) -> str:
        # Используем локальное время без TZ в формате UTC 'Z'
        naive = dt.replace(hour=7, minute=0, second=0, microsecond=0)
        return naive.strftime('%Y%m%dT%H%M%S')

    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//AI Trainer//Goal Planner//EN'
    ]
    for idx, (dt, total, parts) in enumerate(daily):
        session_template = session_templates[idx] if session_templates and idx < len(session_templates) else {}
        resolved_duration = int(session_template.get("duration_minutes", duration_minutes) or duration_minutes)
        resolved_duration = max(30, resolved_duration)
        start = fmt_dt(dt)
        end_dt = dt.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(minutes=resolved_duration)
        end = end_dt.strftime('%Y%m%dT%H%M%S')
        uid = uuid.uuid4().hex
        desc = str(
            session_template.get("description")
            or f"Total TSS: {total}\nRun: {parts.get('run',0)}\nBike: {parts.get('bike',0)}\nSwim: {parts.get('swim',0)}"
        )
        base_title = str(session_template.get("export_name") or title_prefix)
        title = f"{base_title} (TSS {int(round(total))})"
        lines += [
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTART:{start}',
            f'DTEND:{end}',
            f'SUMMARY:{title}',
            f'DESCRIPTION:{desc}',
            'END:VEVENT'
        ]
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines)



def weeks_until(target_date: date, from_date: date | None = None) -> int:
    base = from_date or datetime.now().date()
    days = max(0, (target_date - base).days)
    return max(1, ceil(days / 7))
