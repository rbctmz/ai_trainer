from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Tuple

from models.training_planner import iter_leaf_sessions


def _estimate_step_durations(total_tss: float) -> Dict[str, float]:
    """Грубое распределение TSS по шагам: разминка / работа / заминка."""
    total = max(0.0, float(total_tss))
    return {
        'warmup': round(total * 0.15, 1),
        'main': round(total * 0.70, 1),
        'cooldown': round(total * 0.15, 1),
    }


def _sport_targets(sport: str) -> Dict[str, str]:
    sport_l = (sport or 'run').lower()
    if 'bike' in sport_l or 'вел' in sport_l:
        return {
            'easy': 'power_zone_1_2',
            'steady': 'power_zone_2_3',
            'hard': 'power_zone_4',
            'cooldown': 'power_zone_1',
        }
    if 'swim' in sport_l or 'плав' in sport_l:
        return {
            'easy': 'pace_easy',
            'steady': 'pace_mod',
            'hard': 'pace_threshold',
            'cooldown': 'pace_easy',
        }
    return {
        'easy': 'hr_zone_1_2',
        'steady': 'hr_zone_2_3',
        'hard': 'hr_zone_4',
        'cooldown': 'hr_zone_1',
    }


def _build_role_blueprint(session_role: str) -> List[Dict[str, object]]:
    role = (session_role or 'easy').lower()
    if role == 'off':
        return [
            {'name': 'Rest / Mobility', 'intensity': 'rest', 'target_level': 'easy', 'share': 1.0},
        ]
    if role == 'recovery':
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target_level': 'easy', 'share': 0.20},
            {'name': 'Recovery Endurance', 'intensity': 'easy', 'target_level': 'easy', 'share': 0.60},
            {'name': 'Cooldown', 'intensity': 'easy', 'target_level': 'cooldown', 'share': 0.20},
        ]
    if role == 'quality':
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target_level': 'easy', 'share': 0.20},
            {'name': 'Main Intervals', 'intensity': 'moderate', 'target_level': 'hard', 'share': 0.45},
            {'name': 'Reset', 'intensity': 'easy', 'target_level': 'steady', 'share': 0.15},
            {'name': 'Cooldown', 'intensity': 'easy', 'target_level': 'cooldown', 'share': 0.20},
        ]
    if role == 'long':
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target_level': 'easy', 'share': 0.10},
            {'name': 'Endurance Block', 'intensity': 'moderate', 'target_level': 'steady', 'share': 0.55},
            {'name': 'Steady Finish', 'intensity': 'moderate', 'target_level': 'hard', 'share': 0.20},
            {'name': 'Cooldown', 'intensity': 'easy', 'target_level': 'cooldown', 'share': 0.15},
        ]
    return [
        {'name': 'Warmup', 'intensity': 'easy', 'target_level': 'easy', 'share': 0.15},
        {'name': 'Aerobic Endurance', 'intensity': 'moderate', 'target_level': 'steady', 'share': 0.70},
        {'name': 'Cooldown', 'intensity': 'easy', 'target_level': 'cooldown', 'share': 0.15},
    ]


def build_steps_for_sport(total_tss: float, sport: str, session_role: str = 'easy', phase: str | None = None) -> List[Dict]:
    """Формирует список шагов тренировки для workout_step сообщений.
    Каждый шаг описывает таргет в терминах вида спорта.
    Возвращает список словарей: {'name','intensity','target','tss'}
    """
    del phase  # пока фаза не меняет структуру шага, но сигнатура готова для будущих шаблонов.

    total = max(0.0, float(total_tss or 0.0))
    targets = _sport_targets(sport)
    blueprint = _build_role_blueprint(session_role)
    shares = [float(step.get('share', 0.0) or 0.0) for step in blueprint]
    distributed = [round(total * share, 1) for share in shares]
    diff = round(total - sum(distributed), 1)
    if distributed:
        distributed[-1] = round(distributed[-1] + diff, 1)

    steps: List[Dict] = []
    for idx, step in enumerate(blueprint):
        target_level = str(step.get('target_level', 'steady'))
        steps.append(
            {
                'name': str(step.get('name', f'Step {idx + 1}')),
                'intensity': str(step.get('intensity', 'moderate')),
                'target': targets.get(target_level, targets['steady']),
                'tss': max(0.0, distributed[idx] if idx < len(distributed) else 0.0),
            }
        )
    return steps


def resolve_export_steps(
    session_template: Mapping[str, Any] | None,
    *,
    total_tss: float,
    sport: str,
    session_role: str = "easy",
    phase: str | None = None,
) -> Tuple[str, List[Dict]]:
    """Resolve executable export steps for a day-template.

    Зеркалирует api.planning_service.export_workout: материализованные шаги
    (single leaf или конкатенация ног composite) используются, когда они есть;
    легаси-fallback build_steps_for_sport включается только при их отсутствии
    (договор #299 — modern executable vs legacy fallback). Возвращает (sport, steps).

    Issue #317: устраняет расхождение параллельных путей экспорта — UI honour'ит
    темп/мощность так же, как API и доставка в Intervals.
    """
    template = dict(session_template or {})
    steps: List[Dict] = []
    resolved_sport = str(sport or "")
    for leaf in iter_leaf_sessions(template):
        leaf_steps = list(leaf.get("materialized_steps") or [])
        if leaf_steps:
            steps.extend(leaf_steps)
            if not resolved_sport:
                resolved_sport = str(leaf.get("sport") or resolved_sport)
    if not steps:  # pre-identity-wrapping / legacy single template
        top_steps = list(template.get("materialized_steps") or [])
        if top_steps:
            steps = top_steps
    if steps:
        return resolved_sport, steps
    return resolved_sport, build_steps_for_sport(total_tss, sport, session_role, phase)


def generate_fit_csv(workout_name: str, sport: str, steps: List[Dict], created: datetime | None = None) -> str:
    """Генерирует FIT-CSV совместимый с официальными примерами FitCSVTool (WorkoutIndividualSteps.csv).
    Структура:
      - file_id (type=workout, manufacturer=garmin, garmin_product, serial_number, time_created в FIT epoch)
      - workout (wkt_name, num_valid_steps)
      - workout_step (message_index, wkt_step_name, intensity, duration_type, duration_time, target_type, target_hr_zone)

    Примечания:
      - Используем числовые enum для sport, intensity и duration_type.
      - materialized prescription задаёт точные секунды; старые роли используют TSS fallback.
      - target_type следует сохранённому target (power/heart-rate/speed/open).
    """
    created = created or datetime.utcnow()
    # Карта вида спорта в численный enum FIT (sport): 0=generic, 1=running, 2=cycling, 5=swimming
    sport_map = {'run': 1, 'bike': 2, 'swim': 5}
    s_key = sport_map['run']
    sl = sport.lower()
    if 'bike' in sl or 'вел' in sl:
        s_key = sport_map['bike']
    elif 'swim' in sl or 'плав' in sl:
        s_key = sport_map['swim']

    lines = []
    append = lines.append
    # Заголовок как в примере (включая Units)
    append('Type,Local Number,Message,Field 1,Value 1,Units 1,Field 2,Value 2,Units 2,Field 3,Value 3,Units 3,Field 4,Value 4,Units 4,Field 5,Value 5,Units 5,Field 6,Value 6,Units 6,Field 7,Value 7,Units 7,')

    # Вспомогательная функция для времени FIT (секунды от 1989-12-31 00:00:00 UTC)
    def to_fit_timestamp(dt: datetime) -> int:
        try:
            from datetime import timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            fit_epoch = datetime(1989, 12, 31, tzinfo=timezone.utc)
            return int((dt - fit_epoch).total_seconds())
        except Exception:
            return 621463080

    created = created or datetime.utcnow()
    ts = to_fit_timestamp(created)

    # Definition: file_id (как в примере из SDK)
    append('Definition,0,file_id,type,1,,manufacturer,1,,garmin_product,1,,serial_number,1,,time_created,1,,')
    # Data: file_id
    # type=5 (workout), manufacturer=15 (garmin), garmin_product=22 (пример), serial_number=1234, time_created=<FIT ts>
    append(f'Data,0,file_id,type,5,,manufacturer,15,,garmin_product,22,,serial_number,1234,,time_created,{ts},,')

    # Definition: workout (минимальный набор полей)
    append('Definition,1,workout,wkt_name,10,,num_valid_steps,1,,')
    append(f'Data,1,workout,wkt_name,{workout_name},,num_valid_steps,{len(steps)},,')

    # Definition: workout_step (как в примере)
    append('Definition,2,workout_step,message_index,1,,wkt_step_name,4,,duration_type,1,,duration_value,1,,target_type,1,,target_value,1,,intensity,1,,')

    # Маппинг интенсивности в числовые enum
    def map_intensity(val: str, name_hint: str) -> int:
        v = (val or '').lower()
        name_l = (name_hint or '').lower()
        if 'cool' in name_l or v == 'cooldown':
            return 3
        if 'warm' in name_l or v in ('warmup', 'easy'):
            return 2
        if v == 'rest':
            return 1
        return 0  # active

    def step_seconds(step: Dict) -> int:
        explicit = step.get('duration_seconds')
        if explicit is not None:
            return max(1, int(explicit))
        tss = float(step.get('tss', 0) or 0)
        return int(max(300, round(tss * 60)))

    def target_fields(step: Dict) -> tuple[int, float, str]:
        target = step.get('target')
        if isinstance(target, dict):
            target_type = str(target.get('type') or 'open')
            if target_type == 'power':
                midpoint = (float(target.get('low') or 0) + float(target.get('high') or 0)) / 2.0
                return 4, round(midpoint, 1), 'watts'
            if target_type == 'heart_rate':
                midpoint = (float(target.get('low') or 0) + float(target.get('high') or 0)) / 2.0
                return 1, round(midpoint, 1), 'bpm'
            if target_type == 'pace':
                seconds = float(target.get('fast') or target.get('slow') or 0)
                unit = str(target.get('unit') or '')
                distance = 100.0 if unit == 'seconds_per_100m' else 1000.0
                return 0, round(distance / seconds, 3) if seconds > 0 else 0.0, 'm/s'
            return 2, 0.0, 'open'
        # Legacy role adapter retains its previous HR-zone semantics.
        return 1, 2.0, 'zone'

    # Заполняем шаги
    for i, st in enumerate(steps):
        name = st.get('name', f'Step {i+1}')
        intensity_code = map_intensity(st.get('intensity'), name)
        seconds = step_seconds(st)
        target_type, target_value, target_unit = target_fields(st)
        append(
            'Data,2,workout_step,'
            f'message_index,{i},,'
            f'wkt_step_name,{name},,'
            f'duration_type,0,,'  # 0 = time
            f'duration_time,{seconds},s,'
            f'target_type,{target_type},,'
            f'target_value,{target_value},{target_unit},'
            f'intensity,{intensity_code},,'
        )

    return "\n".join(lines) + "\n"


def try_convert_fit_verbose(csv_bytes: bytes, java_path: str, jar_path: str):
    """Пытается конвертировать CSV → FIT через FitCSVTool.jar.
    Возвращает кортеж: (fit_bytes|None, stdout:str, stderr:str, returncode:int)
    """
    import subprocess
    import tempfile
    import os
    if not jar_path or not os.path.exists(jar_path):
        return None, '', 'FIT_SDK_JAR не задан или файл не найден', 127
    java_cmd = java_path or 'java'
    with tempfile.TemporaryDirectory() as td:
        csv_path = os.path.join(td, 'workout.csv')
        fit_path = os.path.join(td, 'workout.fit')
        with open(csv_path, 'wb') as f:
            f.write(csv_bytes)
        result = subprocess.run([java_cmd, '-jar', jar_path, '-c', csv_path, fit_path], capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(fit_path) and os.path.getsize(fit_path) > 0:
            with open(fit_path, 'rb') as f:
                return f.read(), result.stdout, result.stderr, result.returncode
        return None, result.stdout, result.stderr, result.returncode


def try_convert_fit(csv_bytes: bytes, java_path: str, jar_path: str) -> bytes | None:
    """Упрощённая обёртка: только байты FIT или None."""
    fit_bytes, _, _, rc = try_convert_fit_verbose(csv_bytes, java_path, jar_path)
    return fit_bytes if rc == 0 and fit_bytes else None
