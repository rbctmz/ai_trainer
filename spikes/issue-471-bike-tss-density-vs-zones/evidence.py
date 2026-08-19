"""Evidence for spike issue-471: planned bike TSS vs zone-implied TSS.

Read-only local analysis. Not imported by the product; product must never
import this file. Reproducible from the repo root with the command in
README.md. Uses only the local athlete SQLite cache; no secrets, no network.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.workout_catalog import _TARGET_DENSITY

DB_PATH = Path(__file__).resolve().parents[2] / "ai_trainer.db"
CHECKPOINT_ID = 119
# FTP, которым power_tss_bike считал фактические станок-сессии (tss_ftp_used).
# Локальные данные атлета; в репозиторий не сохраняются.
FTP = 172.0

STEADY_BUILDERS = {"recovery", "endurance", "progression"}


def implied_tss_for_steps(steps: list[dict], ftp: float) -> float | None:
    total = 0.0
    for step in steps:
        target = step.get("target") or {}
        if str(target.get("type")) != "power":
            return None
        low = float(target.get("low") or 0)
        high = float(target.get("high") or 0)
        mid = (low + high) / 2.0
        hours = float(step.get("duration_seconds") or 0) / 3600.0
        total += hours * 100.0 * (mid / ftp) ** 2
    return round(total, 1)


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select checkpoint_data from planning_checkpoints where id=?", (CHECKPOINT_ID,)
    ).fetchone()
    snapshot = json.loads(row[0])["goal_plan_snapshot"]

    print("== bike sessions: stored plan TSS vs zone-implied TSS (FTP %.0f) ==" % FTP)
    print(f'{"date":<11}{"focus":<28}{"plan_tss":>9}{"plan_/h":>8}{"zone_tss":>9}{"zone_/h":>9}{"delta":>8}')
    steady: dict[str, list[float]] = {}
    interval_rows: list[str] = []
    for template in snapshot.get("session_templates") or []:
        date_str = str(template.get("date"))[:10]
        sessions = template.get("sessions") or []
        if not sessions:
            sessions = [template]
        for session in sessions:
            if str(session.get("sport") or "") != "bike":
                continue
            steps = session.get("materialized_steps") or []
            if not steps:
                continue
            implied = implied_tss_for_steps(steps, FTP)
            if implied is None:
                continue
            param = session.get("parameter_snapshot") or {}
            stored = float(session.get("total_tss") or 0)
            duration = float(param.get("duration_minutes") or session.get("duration_minutes") or 0)
            stored_density = round(stored * 60.0 / duration, 1) if duration else 0.0
            implied_density = round(implied * 60.0 / duration, 1) if duration else 0.0
            delta = round((stored_density / implied_density - 1.0) * 100.0) if implied_density else 0
            builder = str((session.get("definition_snapshot") or {}).get("template_key") or "")
            line = (
                f'{date_str:<11}{(session.get("session_focus") or "")[:26]:<28}'
                f'{stored:>9.1f}{stored_density:>8.1f}{implied:>9.1f}{implied_density:>9.1f}{delta:>7}%'
            )
            print(line)
            # Steady-state (staged, non-repeating) builders: zone midpoints are a
            # fair TSS estimate. Interval builders (tempo/threshold/vo2/
            # neuromuscular/race_pace) are excluded from the strict verdict.
            is_steady = any(key in builder for key in ("recovery", "endurance", "progression"))
            if is_steady:
                steady.setdefault(builder, []).append((stored_density, implied_density, delta))
            else:
                interval_rows.append(line)

    print()
    print("== ground truth: trainer rides vs zone-implied (same dates) ==")
    for activity_id in ("24013043328", "24026706443"):
        actual = conn.execute(
            "select date, tss, tss_method, normalized_power, tss_ftp_used from activities where activity_id=?",
            (activity_id,),
        ).fetchone()
        if actual:
            print(
                f'{actual["date"]}: actual {actual["tss"]} TSS (NP {actual["normalized_power"]}, {actual["tss_method"]})'
            )

    print()
    print("== steady-state builders: mean stored vs zone-implied density ==")
    for builder, values in sorted(steady.items()):
        stored_mean = sum(v[0] for v in values) / len(values)
        implied_mean = sum(v[1] for v in values) / len(values)
        delta_mean = sum(v[2] for v in values) / len(values)
        print(
            f'{builder:<24} stored {stored_mean:>5.1f}/h  zones {implied_mean:>5.1f}/h  delta {delta_mean:>+6.0f}%  (n={len(values)})'
        )

    print()
    print("== _TARGET_DENSITY (used to pick session duration from target_tss) ==")
    for key, value in _TARGET_DENSITY.items():
        print(f'  {key:<16}{value:>5.1f}')

    print()
    print("interval-style sessions excluded from strict verdict (zone midpoints underestimate true interval TSS; would need NP-based modeling):")
    for line in interval_rows:
        print(' ', line)


if __name__ == "__main__":
    main()
