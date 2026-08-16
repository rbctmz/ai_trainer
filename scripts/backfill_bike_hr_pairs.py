"""Backfill теневых вело-пар power+HR для существующей истории (#444 S1).

Без этого инструмента bike_hr_quality_pairs наполняется только будущими
синками (окно синка), и dev-отчёт M1 не увидит уже накопленные качественные
пары. Скрипт идемпотентен: upsert по activity_id, повторный запуск только
обновляет признаки.

Запуск:
    python scripts/backfill_bike_hr_pairs.py [--db ai_trainer.db]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.database import Database  # noqa: E402
from services.bike_hr_pairs import record_bike_hr_pair  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ai_trainer.db")
    args = ap.parse_args()

    database = Database(args.db)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM activities ORDER BY date, activity_id").fetchall()
    conn.close()

    recorded = 0
    skipped = 0
    failed = 0
    for row in rows:
        activity = dict(row)
        try:
            if record_bike_hr_pair(database, activity):
                recorded += 1
            else:
                skipped += 1
        except Exception as exc:  # best-effort: одна плохая строка не роняет backfill
            failed += 1
            print(f"⚠️ {activity.get('activity_id')}: {exc}")

    print(
        f"Готово: пар записано={recorded}, пропущено={skipped}, ошибок={failed} "
        f"(всего активностей={len(rows)})"
    )


if __name__ == "__main__":
    main()
