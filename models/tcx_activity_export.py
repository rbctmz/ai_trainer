from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Dict


def _sport_to_tcx_activity(sport: str) -> str:
    s = (sport or 'run').lower()
    if 'bike' in s or 'вел' in s:
        return 'Biking'
    if 'swim' in s or 'плав' in s:
        return 'Other'
    return 'Running'


def _default_speed_m_s(sport: str) -> float:
    s = (sport or 'run').lower()
    if 'bike' in s or 'вел' in s:
        return 7.5  # ~27 км/ч
    if 'swim' in s or 'плав' in s:
        return 1.1  # ~1.1 м/с
    return 3.0      # ~10.8 км/ч бег


def _estimate_step_seconds(step: Dict) -> int:
    explicit = step.get('duration_seconds')
    if explicit is not None:
        return max(1, int(explicit))
    tss = float(step.get('tss', 0) or 0)
    return int(max(300, round(tss * 60)))


def generate_tcx_activity(workout_name: str, sport: str, steps: List[Dict], start_time: datetime | None = None, point_dt: int = 5) -> str:
    """Генерирует TCX Activity (для импорта как активности в Garmin Connect).

    - Формирует один Lap с треком из синтетических точек каждые `point_dt` секунд.
    - DistanceMeters накапливается из постоянной скорости по виду спорта.
    - Без GPS координат (подходит для indoor/без трека), но с временем/дистанцией.
    """
    start_time = (start_time or datetime.utcnow()).replace(tzinfo=timezone.utc)
    sport_attr = _sport_to_tcx_activity(sport)
    speed = _default_speed_m_s(sport)

    # Собираем длительности шагов и суммарное время
    step_secs = [_estimate_step_seconds(s) for s in steps]
    total_secs = int(sum(step_secs))

    # Трекинг точек
    lines: List[str] = []
    a = lines.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a('<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 '
      'http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">')
    a('  <Activities>')
    a(f'    <Activity Sport="{sport_attr}">')
    a(f'      <Id>{start_time.isoformat().replace("+00:00","Z")}</Id>')
    a(f'      <Lap StartTime="{start_time.isoformat().replace("+00:00","Z")}">')
    a(f'        <TotalTimeSeconds>{total_secs}</TotalTimeSeconds>')
    a(f'        <DistanceMeters>{int(total_secs * speed)}</DistanceMeters>')
    a('        <Intensity>Active</Intensity>')
    a('        <TriggerMethod>Manual</TriggerMethod>')
    a('        <Track>')

    dist = 0.0
    cur = start_time
    remaining = total_secs
    step_idx = 0
    step_remaining = step_secs[0] if step_secs else 0

    # Первая точка в момент старта
    a('          <Trackpoint>')
    a(f'            <Time>{cur.isoformat().replace("+00:00","Z")}</Time>')
    a(f'            <DistanceMeters>{int(dist)}</DistanceMeters>')
    a('          </Trackpoint>')

    while remaining > 0:
        dt_step = min(point_dt, remaining)
        cur += timedelta(seconds=dt_step)
        remaining -= dt_step
        step_remaining -= dt_step
        dist += speed * dt_step

        a('          <Trackpoint>')
        a(f'            <Time>{cur.isoformat().replace("+00:00","Z")}</Time>')
        a(f'            <DistanceMeters>{int(dist)}</DistanceMeters>')
        a('          </Trackpoint>')

        if step_remaining <= 0 and step_idx + 1 < len(step_secs):
            step_idx += 1
            step_remaining = step_secs[step_idx]

    a('        </Track>')
    a('      </Lap>')
    a('    </Activity>')
    a('  </Activities>')
    a('</TrainingCenterDatabase>')
    return "\n".join(lines) + "\n"
