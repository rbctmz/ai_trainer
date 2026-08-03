"""Test-only fixtures for the TD-005/D4 shim removal.

`legacy_upsert_activities` reproduces the pre-M1 bulk upsert that used to live
in ``Database.sync_activities``. It is intentionally an ORACLE: tests that pin
upsert/dedup semantics (new/updated/skipped) keep exercising the old contract
without the production shim, while production code goes through the common
ingest funnel (``services.sync._sync_activities``).
"""
from __future__ import annotations

from typing import Any


def legacy_upsert_activities(db: Any, activities: list[dict[str, Any]]) -> dict[str, int]:
    """Pre-M1 canonical upsert (legacy ``sync_activities`` semantics)."""
    if not activities:
        return {"new": 0, "updated": 0, "skipped": 0}

    conn = db._connect()
    cursor = conn.cursor()
    activity_columns = [
        column for column in db._ACTIVITY_COLUMN_ORDER if column != "activity_id"
    ]
    update_sql = ", ".join(f"{column}=?" for column in activity_columns)
    insert_columns = ", ".join(db._ACTIVITY_COLUMN_ORDER)
    insert_placeholders = ", ".join("?" for _ in db._ACTIVITY_COLUMN_ORDER)

    cursor.execute("SELECT activity_id FROM activities")
    existing_ids = {row[0] for row in cursor.fetchall()}

    new_count = 0
    updated_count = 0
    skipped_count = 0
    for activity in activities:
        activity_id = db.clean_value(activity.get("activity_id"))
        if not activity_id:
            skipped_count += 1
            continue
        if activity_id in existing_ids:
            values = [db.clean_value(activity.get(column)) for column in activity_columns]
            values.append(activity_id)
            cursor.execute(
                f"UPDATE activities SET {update_sql} WHERE activity_id=?",
                tuple(values),
            )
            updated_count += 1
        else:
            values = tuple(
                db.clean_value(activity.get(column))
                for column in db._ACTIVITY_COLUMN_ORDER
            )
            cursor.execute(
                f"INSERT INTO activities ({insert_columns}) VALUES ({insert_placeholders})",
                values,
            )
            existing_ids.add(activity_id)
            new_count += 1

    conn.commit()
    conn.close()
    return {"new": new_count, "updated": updated_count, "skipped": skipped_count}
