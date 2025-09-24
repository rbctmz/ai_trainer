from __future__ import annotations

from datetime import datetime
from typing import List, Dict


def _estimate_step_durations(total_tss: float) -> Dict[str, float]:
    """Грубое распределение TSS по шагам: разминка / работа / заминка."""
    total = max(0.0, float(total_tss))
    return {
        'warmup': round(total * 0.15, 1),
        'main': round(total * 0.70, 1),
        'cooldown': round(total * 0.15, 1),
    }


def build_steps_for_sport(total_tss: float, sport: str) -> List[Dict]:
    """Формирует список шагов тренировки для workout_step сообщений.
    Каждый шаг описывает таргет в терминах вида спорта.
    Возвращает список словарей: {'name','intensity','target','tss'}
    """
    sport_l = (sport or 'run').lower()
    dist = _estimate_step_durations(total_tss)

    if 'bike' in sport_l or 'вел' in sport_l:
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target': 'power_zone_1_2', 'tss': dist['warmup']},
            {'name': 'Steady', 'intensity': 'moderate', 'target': 'power_zone_2_3', 'tss': dist['main']},
            {'name': 'Cooldown', 'intensity': 'easy', 'target': 'power_zone_1', 'tss': dist['cooldown']},
        ]
    elif 'swim' in sport_l or 'плав' in sport_l:
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target': 'pace_easy', 'tss': dist['warmup']},
            {'name': 'Steady', 'intensity': 'moderate', 'target': 'pace_mod', 'tss': dist['main']},
            {'name': 'Cooldown', 'intensity': 'easy', 'target': 'pace_easy', 'tss': dist['cooldown']},
        ]
    else:  # run
        return [
            {'name': 'Warmup', 'intensity': 'easy', 'target': 'hr_zone_1_2', 'tss': dist['warmup']},
            {'name': 'Steady', 'intensity': 'moderate', 'target': 'hr_zone_2_3', 'tss': dist['main']},
            {'name': 'Cooldown', 'intensity': 'easy', 'target': 'hr_zone_1', 'tss': dist['cooldown']},
        ]


def generate_fit_csv(workout_name: str, sport: str, steps: List[Dict], created: datetime | None = None) -> str:
    """Генерирует FIT-CSV совместимый с официальными примерами FitCSVTool (WorkoutIndividualSteps.csv).
    Структура:
      - file_id (type=workout, manufacturer=garmin, garmin_product, serial_number, time_created в FIT epoch)
      - workout (wkt_name, num_valid_steps)
      - workout_step (message_index, wkt_step_name, intensity, duration_type, duration_time, target_type, target_hr_zone)

    Примечания:
      - Используем числовые enum для sport, intensity и duration_type.
      - duration задаём в секундах (грубая оценка из tss: max(300, tss*60)).
      - target_type фиксим на 1 (heart_rate) с целевыми зонами 2/3.
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

    # Заполняем шаги
    for i, st in enumerate(steps):
        name = st.get('name', f'Step {i+1}')
        intensity_code = map_intensity(st.get('intensity'), name)
        tss = float(st.get('tss', 0) or 0)
        seconds = int(max(300, round(tss * 60)))
        # target_type: 1 = heart_rate, целевая зона HR: 2 (умолч.)
        target_zone = 2 if intensity_code in (2, 3) else 3
        append(
            'Data,2,workout_step,'
            f'message_index,{i},,'
            f'wkt_step_name,{name},,'
            f'duration_type,0,,'  # 0 = time
            f'duration_time,{seconds},s,'
            f'target_type,1,,'     # 1 = heart_rate
            f'target_hr_zone,{target_zone},,'
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
