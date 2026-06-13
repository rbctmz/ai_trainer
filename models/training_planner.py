from __future__ import annotations

from datetime import datetime, timedelta, date
from math import ceil
from typing import Any, Dict, List, Mapping, Sequence, Tuple

WEEKDAY_LABELS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
SESSION_ROLE_LABELS_RU = {
    "off": "Отдых",
    "recovery": "Восстановление",
    "easy": "Легкая",
    "quality": "Качество",
    "long": "Длительная",
}
SPORT_LABELS_RU = {
    "run": "бег",
    "bike": "вело",
    "swim": "плавание",
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
) -> Tuple[List[int], List[Dict[str, object]], Dict[str, object]]:
    """Ограничивает недельный план доступностью и корректирует первые недели под сценарии ограничений."""
    availability = summarize_availability(goal_type, available_hours, available_day_indices)
    weekly_capacity_tss = int(availability['weekly_capacity_tss'])
    load_state = assess_start_load_state(
        current_ctl=current_ctl,
        current_atl=current_atl,
        current_tsb=current_tsb,
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
    else:  # taper
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
    elif p == "taper":
        count = 1 if active_day_count >= 4 else 0
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
    elif (phase or "").lower() == "taper" and active_day_count >= 5:
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
    recovery_days = [idx for idx, role in enumerate(roles) if role == "recovery"]

    key_labels = [f"{WEEKDAY_LABELS_RU[idx]} {focuses[idx].lower()}" for idx in quality_days + long_days]
    recovery_labels = [WEEKDAY_LABELS_RU[idx] for idx in recovery_days]
    structure_summary = (
        f"{len(quality_days)} качеств. дн., "
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
) -> Tuple[List[Tuple[datetime, float, Dict[str, float]]], List[Dict[str, object]]]:
    """Разворачивает недельный triathlon-план в поминутную ленту по дням с разбивкой по видам спорта.
    Возвращает:
      - daily: список (datetime, total_daily_tss, {'run':..., 'bike':..., 'swim':...})
      - weekly_summary: список словарей {'week_start': date, 'phase': str, 'weekly_tss': int, 'bike': float, 'run': float, 'swim': float}
    """
    daily: List[Tuple[datetime, float, Dict[str, float]]] = []
    weekly_summary: List[Dict[str, object]] = []

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
        # Дневные веса: кастом или дефолт
        if weights_overrides and phase in weights_overrides:
            custom = weights_overrides[phase]
            weights = {
                'run': _normalize_weights(custom.get('run', daily_weights_for_phase(phase)['run'])),
                'bike': _normalize_weights(custom.get('bike', daily_weights_for_phase(phase)['bike'])),
                'swim': _normalize_weights(custom.get('swim', daily_weights_for_phase(phase)['swim'])),
            }
        else:
            weights = daily_weights_for_phase(phase)
        weights = constrain_weights_to_available_days(weights, available_day_indices)

        # Сумма по видам на неделю
        run_week = w_tss * mix['run']
        bike_week = w_tss * mix['bike']
        swim_week = w_tss * mix['swim']
        week_parts: List[Dict[str, float]] = []
        for i in range(7):
            run_d = round(run_week * weights['run'][i], 1)
            bike_d = round(bike_week * weights['bike'][i], 1)
            swim_d = round(swim_week * weights['swim'][i], 1)
            week_parts.append({'run': run_d, 'bike': bike_d, 'swim': swim_d})

        adjusted_week_parts, day_roles, day_focuses = _apply_recovery_aware_day_structure(
            week_parts,
            int(round(w_tss)),
            phase,
            goal_type,
            load_state,
        )

        bike_total = round(sum(parts.get('bike', 0.0) for parts in adjusted_week_parts), 1)
        run_total = round(sum(parts.get('run', 0.0) for parts in adjusted_week_parts), 1)
        swim_total = round(sum(parts.get('swim', 0.0) for parts in adjusted_week_parts), 1)
        structure_meta = _build_week_structure_metadata(day_roles, day_focuses)

        weekly_summary.append({
            'week_start': current.date(),
            'phase': phase,
            'weekly_tss': int(round(w_tss)),
            'bike': bike_total,
            'run': run_total,
            'swim': swim_total,
            **structure_meta,
        })

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
    estimated = total * base_minutes_per_tss[sport_key] * role_multiplier[role_key]
    if total <= 0:
        estimated = 30 if role_key == "off" else 45
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


def build_daily_session_templates(
    daily: List[Tuple[datetime, float, Dict[str, float]]],
    weekly_summary: Sequence[Mapping[str, object]],
    goal_type: str,
    distance: str,
) -> List[Dict[str, Any]]:
    """Строит метаданные сессий, выровненные с daily plan без смены его контракта."""
    templates: List[Dict[str, Any]] = []

    for idx, (dt, total, parts) in enumerate(daily):
        week_idx = idx // 7
        day_idx = idx % 7
        week_meta = weekly_summary[week_idx] if week_idx < len(weekly_summary) else {}
        day_roles = list(week_meta.get("day_roles") or ["easy"] * 7)
        day_focuses = list(week_meta.get("day_focuses") or ["—"] * 7)
        session_role = str(day_roles[day_idx] if day_idx < len(day_roles) else "easy")
        session_focus = str(day_focuses[day_idx] if day_idx < len(day_focuses) else "—")
        sport = _dominant_sport(parts)
        phase = str(week_meta.get("phase", "Base") or "Base")
        duration_minutes = _estimate_session_duration_minutes(total, sport, session_role)
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
                "template_key": f"{phase.lower()}:{session_role}:{sport}",
                "export_name": export_name,
                "description": description,
            }
        )

    return templates


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
