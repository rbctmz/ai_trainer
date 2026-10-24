"""Offline preview/apply/unlink for an owner-confirmed exact source pair."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from config.settings import Settings
from data import activity_manual_links as store
from data.database import Database


def manage_manual_link(
    database_path: str | Path, intervals_id: str, garmin_id: str, *,
    apply: bool = False, unlink: bool = False, expected_token: str | None = None,
    reason: str | None = None, confirm_stopped: bool = False,
) -> dict[str, Any]:
    """Preview is read-only; explicit writes revalidate under BEGIN IMMEDIATE."""
    path = Path(database_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("database must be an existing file")
    if not apply:
        with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as conn:
            conn.execute("BEGIN")
            return {"mode": "preview", **store.inspect(conn, intervals_id, garmin_id, unlink=unlink, primary_source=Settings.PRIMARY_ACTIVITY_SOURCE)}
    if not confirm_stopped:
        raise ValueError("confirm stopped writers before applying")
    if not expected_token:
        raise ValueError("expected preview token is required")
    if not unlink and not str(reason or '').strip():
        raise ValueError("a nonempty confirmation reason is required")
    db = Database(str(path), initialize=False)
    conn = db._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        plan = store.inspect(conn, intervals_id, garmin_id, unlink=unlink, primary_source=Settings.PRIMARY_ACTIVITY_SOURCE)
        if plan['token'] != expected_token:
            raise ValueError("stale preview; inspect the pair again")
        if not plan['allowed']:
            raise ValueError("manual activity link blocked: " + '; '.join(plan['blockers']))
        store.initialize(conn)
        cursor = conn.cursor()
        affected = {plan['canonical_id'], garmin_id}
        if unlink and plan['linked']:
            cursor.execute("DELETE FROM activity_manual_links WHERE intervals_activity_id=? AND garmin_activity_id=?", (intervals_id, garmin_id))
            rows = store._rows(conn, """SELECT id,provider,provider_activity_id,canonical_activity_id,
                    external_provider,external_id FROM activity_provider_links
                    WHERE canonical_activity_id=?""", (plan['canonical_id'],))
            coordinates = {garmin_id}
            for row in rows:
                standalone = row['provider_activity_id'] if row['provider'] == 'garmin' else f"intervals_{row['provider_activity_id']}"
                affected.add(standalone)
                cursor.execute("UPDATE activity_provider_links SET canonical_activity_id=?,match_status='unmatched' WHERE id=?", (standalone, row['id']))
                if row['external_provider'] == 'garmin':
                    coordinates.add(row['external_id'])
            for coordinate in coordinates:
                affected |= db._resolve_garmin_coordinate(cursor, coordinate)
            for cid in affected:
                store.clear_caches(conn, cid)
        elif not unlink:
            cursor.execute("""INSERT OR IGNORE INTO activity_manual_links
                (intervals_activity_id,garmin_activity_id,reason) VALUES (?,?,?)""",
                (intervals_id, garmin_id, reason.strip()))
            affected = store.enforce(cursor, affected)
        for cid in affected:
            db._project_canonical(cursor, cid, Settings.PRIMARY_ACTIVITY_SOURCE)
        result = store.inspect(conn, intervals_id, garmin_id, unlink=unlink, primary_source=Settings.PRIMARY_ACTIVITY_SOURCE)
        conn.commit()
        return {**result, "mode": "applied", "before": plan['before'], "after": result['before']}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
