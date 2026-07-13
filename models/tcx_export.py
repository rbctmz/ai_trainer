from __future__ import annotations

from datetime import datetime
from html import escape
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

    def step_seconds(st: Dict) -> int:
        explicit = st.get('duration_seconds')
        if explicit is not None:
            return max(1, int(explicit))
        tss = float(st.get('tss', 0) or 0)
        return int(max(300, round(tss * 60)))

    def target_lines(st: Dict) -> List[str]:
        target = st.get('target')
        if not isinstance(target, dict):
            return [
                '        <Target xsi:type="HeartRateZone_t">',
                '          <ZoneNumber>2</ZoneNumber>',
                '        </Target>',
            ]
        target_type = str(target.get('type') or 'open')
        evidence = " ".join(
            f"{key}={value}"
            for key, value in target.items()
            if value is not None
        ).replace('--', '-')
        return [
            '        <Target xsi:type="None_t" />',
            f'        <!-- AI Trainer target evidence: {escape(target_type)} {escape(evidence)} -->',
        ]

    lines: List[str] = []
    a = lines.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a('<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
      'xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 '
      'http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">')
    a('  <Workouts>')
    a(f'    <Workout Sport="{sport_attr}">')
    a(f'      <Name>{escape(workout_name)}</Name>')

    for i, st in enumerate(steps):
        name = st.get('name', f'Step {i+1}')
        secs = step_seconds(st)
        intensity = _intensity_to_tcx(st.get('intensity', ''), name)
        a('      <Step xsi:type="Step_t">')
        a(f'        <Name>{escape(str(name))}</Name>')
        a('        <Duration xsi:type="Time_t">')
        a(f'          <Seconds>{secs}</Seconds>')
        a('        </Duration>')
        a(f'        <Intensity>{intensity}</Intensity>')
        for target_line in target_lines(st):
            a(target_line)
        a('      </Step>')

    a('    </Workout>')
    a('  </Workouts>')
    a('</TrainingCenterDatabase>')
    return "\n".join(lines) + "\n"
