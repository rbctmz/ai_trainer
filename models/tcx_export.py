from __future__ import annotations

from datetime import datetime
from typing import List, Dict


def _intensity_to_tcx(val: str, name_hint: str = "") -> str:
    v = (val or "").lower()
    name_l = (name_hint or "").lower()
    if 'cool' in name_l or v == 'cooldown':
        return 'Cooldown'
    if 'warm' in name_l or v in ('warmup', 'easy'):
        return 'Warmup'
    if v == 'rest':
        return 'Rest'
    return 'Active'


def _sport_to_tcx(sport: str) -> str:
    s = (sport or 'run').lower()
    if 'bike' in s or 'вел' in s:
        return 'Biking'
    if 'swim' in s or 'плав' in s:
        return 'Other'
    return 'Running'


def generate_tcx_workout(workout_name: str, sport: str, steps: List[Dict], created: datetime | None = None) -> str:
    """Генерирует TCX Workout (TrainingCenterDatabase v2) с базовыми полями,
    совместимый с импортом тренировок в Garmin Connect (Workout).

    Поля шага:
      - Name
      - Duration (Time_t / Seconds)
      - Intensity (Active/Warmup/Cooldown/Rest)
      - Target (None)
    """
    created = created or datetime.utcnow()
    sport_attr = _sport_to_tcx(sport)

    # Простейшая оценка длительности из TSS (секунды)
    def step_seconds(st: Dict) -> int:
        tss = float(st.get('tss', 0) or 0)
        return int(max(300, round(tss * 60)))

    lines: List[str] = []
    a = lines.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a('<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 '
      'http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">')
    a('  <Workouts>')
    a(f'    <Workout Sport="{sport_attr}">')
    a(f'      <Name>{workout_name}</Name>')

    for i, st in enumerate(steps):
        name = st.get('name', f'Step {i+1}')
        secs = step_seconds(st)
        intensity = _intensity_to_tcx(st.get('intensity', ''), name)
        a('      <Step xsi:type="Step_t">')
        a(f'        <Name>{name}</Name>')
        a('        <Duration xsi:type="Time_t">')
        a(f'          <Seconds>{secs}</Seconds>')
        a('        </Duration>')
        a(f'        <Intensity>{intensity}</Intensity>')
        # Для совместимости с Garmin Connect используем HR-зону как таргет
        a('        <Target xsi:type="HeartRateZone_t">')
        a('          <ZoneNumber>2</ZoneNumber>')
        a('        </Target>')
        a('      </Step>')

    a('    </Workout>')
    a('  </Workouts>')
    a('</TrainingCenterDatabase>')
    return "\n".join(lines) + "\n"
