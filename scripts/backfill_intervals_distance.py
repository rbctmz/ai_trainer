#!/usr/bin/env python3
"""Backfill distance_km для Intervals-активностей (#417).

Дистанция существовала только в Intervals.icu, а старые provider_payload её
не несли (баг #417: list_activities не запрашивал distance). Скрипт делает
bounded read-only запрос list_activities (после #418 поле distance в полях) и
обновляет:

- activity_provider_links.provider_payload — добавляет distance_km, чтобы
  будущая репроекция канонической активности её сохранила;
- activities.distance_km — метры → км.

Идемпотентен: повторный запуск при тех же данных ничего не меняет.
Требует настроенного INTERVALS_ICU_API_KEY (живой read-only вызов).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.activity_store import ACTIVITY_COLUMN_ORDER  # noqa: E402
from config.settings import Settings  # noqa: E402
from services.intervals_icu import IntervalsICUError, get_client  # noqa: E402


def _meters_to_km(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        metres = float(value)
    except (TypeError, ValueError):
        return None
    if metres < 0:
        return None
    return round(metres / 1000.0, 2)


def main(*, client=None, database_path: str | None = None) -> int:
    """Run the backfill; injectable boundaries keep the real path hermetic in tests."""
    client = client or get_client()
    if not client.is_configured():
        print(
            "INTERVALS_ICU_API_KEY не настроен — backfill невозможен.",
            file=sys.stderr,
        )
        return 2

    conn = sqlite3.connect(database_path or Settings.DATABASE_PATH)
    try:
        cursor = conn.cursor()
        primary_source = str(
            getattr(Settings, "PRIMARY_ACTIVITY_SOURCE", "") or "garmin"
        ).strip().lower()
        cursor.execute("SELECT MIN(date) FROM activities")
        min_date = cursor.fetchone()[0]
        oldest = (
            date.fromisoformat(str(min_date)[:10])
            if min_date
            else date.today() - timedelta(days=150)
        )
        newest = date.today()
        print(f"Запрашиваю активности Intervals.icu за {oldest}..{newest}")
        by_id: dict[str, float | None] = {}
        window_start = oldest
        while window_start <= newest:
            window_end = min(window_start + timedelta(days=89), newest)
            print(f"  окно {window_start}..{window_end}")
            try:
                rows = client.list_activities(window_start, window_end)
            except IntervalsICUError as exc:
                print(f"Ошибка Intervals.icu: {exc}", file=sys.stderr)
                return 1
            for row in rows:
                raw_id = row.get("id")
                if raw_id is None:
                    continue
                by_id[str(raw_id)] = _meters_to_km(row.get("distance"))
            window_start = window_end + timedelta(days=1)

        cursor.execute(
            "SELECT id, canonical_activity_id, provider_activity_id, provider_payload "
            "FROM activity_provider_links WHERE provider='intervals'"
        )
        links = cursor.fetchall()
        updated_activities = 0
        updated_payloads = 0
        unchanged = 0
        skipped = 0
        for link_id, canonical_id, provider_activity_id, payload_json in links:
            km = by_id.get(str(provider_activity_id))
            if km is None:
                skipped += 1  # нет дистанции в API / активность вне окна
                continue

            # P1: если у канонической есть Garmin-линк и primary=garmin,
            # activities.distance_km не трогаем — авторитетна Garmin-дистанция;
            # payload intervals-линка всё равно обновляем (для проекции при
            # primary=intervals). Для intervals-only канонических — заполняем.
            cursor.execute(
                "SELECT 1 FROM activity_provider_links "
                "WHERE canonical_activity_id=? AND provider='garmin' LIMIT 1",
                (canonical_id,),
            )
            has_garmin = cursor.fetchone() is not None
            intervals_authoritative = primary_source == "intervals" or not has_garmin

            cursor.execute(
                f"SELECT {', '.join(ACTIVITY_COLUMN_ORDER)} FROM activities "
                "WHERE activity_id=?",
                (canonical_id,),
            )
            activity_row = cursor.fetchone()
            if activity_row is None:
                skipped += 1
                continue
            canonical_row = dict(zip(ACTIVITY_COLUMN_ORDER, activity_row))

            new_payload: str | None = None
            payload: Any = None
            if payload_json:
                try:
                    payload = json.loads(payload_json)
                except (TypeError, ValueError):
                    payload = None
            # P2: никогда не пишем урезанный снапшот — если payload отсутствует
            # или неполный, строим полный из текущей канонической строки.
            if not isinstance(payload, dict) or not payload.get("date"):
                payload = dict(canonical_row)
                payload["distance_km"] = km
                new_payload = json.dumps(payload, ensure_ascii=False)
            elif payload.get("distance_km") != km:
                payload["distance_km"] = km
                new_payload = json.dumps(payload, ensure_ascii=False)
            if new_payload is not None:
                cursor.execute(
                    "UPDATE activity_provider_links SET provider_payload=? WHERE id=?",
                    (new_payload, link_id),
                )
                updated_payloads += 1

            if intervals_authoritative and canonical_row.get("distance_km") != km:
                cursor.execute(
                    "UPDATE activities SET distance_km=? WHERE activity_id=?",
                    (km, canonical_id),
                )
                updated_activities += 1
            elif canonical_row.get("distance_km") == km:
                unchanged += 1
            else:
                # Garmin-primary и дистанция уже есть — не перезаписываем (P1).
                unchanged += 1

        conn.commit()
        print(f"Проверено links: {len(links)}")
        print(f"  обновлено activities: {updated_activities}")
        print(f"  обновлено payload'ов: {updated_payloads}")
        print(f"  без изменений: {unchanged}")
        print(
            "  пропущено (нет дистанции в API / вне окна / нет канонической): "
            f"{skipped}"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
