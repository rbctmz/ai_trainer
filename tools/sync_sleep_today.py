#!/usr/bin/env python3
"""
Minimal sync helper to fetch recent sleep (including last night)
and store by wake-up date. Uses .env GARMIN_EMAIL/PASSWORD.
"""
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from config.settings import Settings
from data.garmin_client import GarminClient
from data.database import Database
from data.data_processor_phase1 import Phase1DataProcessor


def main(days: int = 3):
    email = Settings.GARMIN_EMAIL
    password = Settings.GARMIN_PASSWORD
    if not email or not password:
        print("❌ GARMIN_EMAIL/GARMIN_PASSWORD не заданы в .env")
        return 1

    db = Database()
    client = GarminClient()
    print(f"🔐 Авторизация в Garmin как {email}...")
    if not client.authenticate(email, password):
        print(f"❌ Авторизация не удалась: {client.auth_error}")
        return 2

    today = datetime.now().date()
    start = today - timedelta(days=days - 1)
    saved = {}

    for i in range(days):
        d = start + timedelta(days=i)
        print(f"😴 Получаем сон за {d.isoformat()}...")
        raw = client.get_sleep_data(datetime.combine(d, datetime.min.time()))
        if not raw:
            print("  • Нет данных")
            continue
        processed = Phase1DataProcessor.process_sleep_data(raw)
        if not processed:
            print("  • Не удалось обработать")
            continue
        date_key = processed.get('sleep_date') or d.strftime('%Y-%m-%d')
        res = db.sync_sleep_data({date_key: processed})
        saved[date_key] = res
        print(f"  • Сохранено для {date_key}: {res}")

    # Отчет о последней записи в БД
    import sqlite3
    conn = sqlite3.connect(Settings.DATABASE_PATH)
    cur = conn.cursor()
    cur.execute("SELECT date, bedtime, wakeup_time, total_sleep_minutes FROM sleep_data ORDER BY date DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        print(f"\n✅ Последняя запись сна в БД: {row[0]} (сон {row[1]}–{row[2]}, {row[3]} мин)")
    else:
        print("\n⚠️ В БД нет записей сна")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
