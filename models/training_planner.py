from __future__ import annotations

from datetime import datetime, timedelta, date
from math import ceil
from typing import List, Dict, Tuple


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

        # Сумма по видам на неделю
        run_week = w_tss * mix['run']
        bike_week = w_tss * mix['bike']
        swim_week = w_tss * mix['swim']

        # Запись в сводку по неделе
        weekly_summary.append({
            'week_start': current.date(),
            'phase': phase,
            'weekly_tss': int(round(w_tss)),
            'bike': round(bike_week, 1),
            'run': round(run_week, 1),
            'swim': round(swim_week, 1),
        })

        for i in range(7):
            run_d = round(run_week * weights['run'][i], 1)
            bike_d = round(bike_week * weights['bike'][i], 1)
            swim_d = round(swim_week * weights['swim'][i], 1)
            total = round(run_d + bike_d + swim_d, 1)
            daily.append((current, total, {'run': run_d, 'bike': bike_d, 'swim': swim_d}))
            current += timedelta(days=1)

    return daily, weekly_summary


def flatten_daily_total(daily: List[Tuple[datetime, float, Dict[str, float]]]) -> List[Tuple[datetime, float]]:
    """Преобразует расширенный daily список в (date, total) для симуляции."""
    return [(dt, total) for dt, total, _ in daily]


def create_ics_from_daily(
    daily: List[Tuple[datetime, float, Dict[str, float]]],
    title_prefix: str = "Planned Training",
    duration_minutes: int = 60,
) -> str:
    """Генерирует ICS календарь из дневного плана.
    Создаёт по одному событию в день с суммарным TSS и разбивкой в описании.
    """
    from datetime import timezone
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
    for dt, total, parts in daily:
        start = fmt_dt(dt)
        end_dt = dt.replace(hour=8, minute=0, second=0, microsecond=0)
        end = end_dt.strftime('%Y%m%dT%H%M%S')
        uid = uuid.uuid4().hex
        desc = f"Total TSS: {total}\nRun: {parts.get('run',0)}\nBike: {parts.get('bike',0)}\nSwim: {parts.get('swim',0)}"
        title = f"{title_prefix} (TSS {int(round(total))})"
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
