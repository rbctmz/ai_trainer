"""Exact operator-confirmed activity identity decisions (#720).

Provider facts remain untouched. All writes run in the caller's transaction.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any


CACHES = ("activity_intervals", "activity_power_curves", "bike_hr_quality_pairs")


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS activity_manual_links (
        intervals_activity_id TEXT PRIMARY KEY NOT NULL,
        garmin_activity_id TEXT NOT NULL UNIQUE,
        reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def _rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, args)
    names = [column[0] for column in cursor.description or []]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def exists(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity_manual_links'").fetchone())


def preferred_intervals_id(conn: sqlite3.Connection, canonical_id: str) -> str | None:
    if not exists(conn):
        return None
    row = conn.execute(
        "SELECT intervals_activity_id FROM activity_manual_links WHERE 'intervals_' || intervals_activity_id=?",
        (str(canonical_id),),
    ).fetchone()
    return str(row[0]) if row else None


def clear_caches(conn: sqlite3.Connection, activity_id: str) -> None:
    for table in CACHES:
        conn.execute(f'DELETE FROM "{table}" WHERE CAST(activity_id AS TEXT)=?', (str(activity_id),))


def _contains_identity(value: Any, identities: set[str]) -> bool:
    if isinstance(value, dict):
        return any(_contains_identity(v, identities) for v in value.values())
    if isinstance(value, list):
        return any(_contains_identity(v, identities) for v in value)
    return isinstance(value, (str, int)) and str(value) in identities


def reference_blockers(conn: sqlite3.Connection, identities: set[str]) -> list[str]:
    """Refuse authored/immutable references; rebuildable caches are excluded."""
    if not identities:
        return []
    blockers = []
    excluded = {"activities", "activity_provider_links", "activity_manual_links", *CACHES}
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    for (table,) in tables:
        if table in excluded or table.startswith("sqlite_"):
            continue
        quoted = '"' + table.replace('"', '""') + '"'
        columns = [r[1] for r in conn.execute(f'PRAGMA table_info({quoted})')]
        if "activity_id" in columns:
            marks = ','.join('?' for _ in identities)
            count = conn.execute(
                f'SELECT COUNT(*) FROM {quoted} WHERE CAST(activity_id AS TEXT) IN ({marks})',
                tuple(sorted(identities)),
            ).fetchone()[0]
            if count:
                blockers.append(f"authored reference in {table}: {count}")
        for column in columns:
            if not column.endswith("_json"):
                continue
            qcol = '"' + column.replace('"', '""') + '"'
            for (raw,) in conn.execute(f'SELECT {qcol} FROM {quoted} WHERE {qcol} IS NOT NULL'):
                try:
                    value = json.loads(raw)
                except (ValueError, TypeError):
                    # An opaque ledger cannot establish that an identity is absent.
                    blockers.append(f"unreadable ledger in {table}.{column}")
                    break
                if _contains_identity(value, identities):
                    blockers.append(f"authored reference in {table}.{column}")
                    break
    return blockers


def _payload(link: dict[str, Any] | None) -> dict[str, Any]:
    try:
        result = json.loads((link or {}).get("provider_payload") or "null")
    except (ValueError, TypeError):
        result = None
    return result if isinstance(result, dict) else {}


def _utc(raw: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def _compatible(original: dict[str, Any], garmin: dict[str, Any]) -> bool:
    cycling = {"cycling", "virtual_ride", "virtualride", "indoor_cycling", "biking", "ride"}
    if str(original.get("sport")).lower() not in cycling or str(garmin.get("sport")).lower() not in cycling:
        return False
    start = _utc(original.get("started_at_utc"))
    if start is None or start != _utc(garmin.get("started_at_utc")):
        return False
    try:
        durations = [float(row["duration_minutes"]) for row in (original, garmin)]
    except (ValueError, TypeError, KeyError):
        return False
    # Intervals normalizes seconds to minutes rounded to three decimal places.
    # Use that same precision so a source difference of one second is accepted.
    tolerance = round(1 / 60, 3)
    return all(math.isfinite(d) and d > 0 for d in durations) and abs(durations[0] - durations[1]) <= tolerance + 1e-9


def _totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"count": len(rows), **{
        key: round(sum(float(row.get(key) or 0) for row in rows), 4)
        for key in ("duration_minutes", "distance_km", "tss")
    }}


def inspect(conn: sqlite3.Connection, intervals_id: str, garmin_id: str, *, unlink: bool = False, pending_projection: bool = False, primary_source: str = "garmin") -> dict[str, Any]:
    """Build a read-only pair preview and an opaque state/revalidation token."""
    if not intervals_id or intervals_id != intervals_id.strip() or not garmin_id.isdigit():
        raise ValueError("explicit Intervals id and numeric Garmin id are required")
    target = f"intervals_{intervals_id}"
    links = _rows(conn, """SELECT * FROM activity_provider_links
        WHERE (provider='intervals' AND provider_activity_id=?)
           OR (provider='garmin' AND provider_activity_id=?)
           OR (external_provider='garmin' AND external_id=?)
        ORDER BY provider, provider_activity_id""", (intervals_id, garmin_id, garmin_id))
    original = next((r for r in links if r['provider'] == 'intervals' and r['provider_activity_id'] == intervals_id), None)
    garmin = next((r for r in links if r['provider'] == 'garmin' and r['provider_activity_id'] == garmin_id), None)
    decisions = _rows(conn, """SELECT * FROM activity_manual_links
        WHERE intervals_activity_id=? OR garmin_activity_id=? ORDER BY intervals_activity_id""",
        (intervals_id, garmin_id)) if exists(conn) else []
    linked = any(r['intervals_activity_id'] == intervals_id and r['garmin_activity_id'] == garmin_id for r in decisions)
    blockers = []
    if not original or not garmin or not _payload(original) or not _payload(garmin):
        blockers.append("both source identities and payloads must exist")
    if any(r['intervals_activity_id'] != intervals_id or r['garmin_activity_id'] != garmin_id for r in decisions):
        blockers.append("conflicting manual association")
    canonical_ids = {str(r['canonical_activity_id']) for r in links}
    activities = []
    for cid in sorted(canonical_ids):
        activities.extend(_rows(conn, "SELECT * FROM activities WHERE CAST(activity_id AS TEXT)=?", (cid,)))
    if not pending_projection and len(activities) != len(canonical_ids):
        blockers.append("missing canonical activity")
    known = {(r['provider'], r['provider_activity_id']) for r in links}
    for cid in canonical_ids:
        siblings = _rows(conn, "SELECT provider,provider_activity_id FROM activity_provider_links WHERE canonical_activity_id=?", (cid,))
        if any((r['provider'], r['provider_activity_id']) not in known for r in siblings):
            blockers.append("unsupported existing group")
    claimants = [r for r in links if r['provider'] == 'intervals' and r['external_provider'] == 'garmin' and r['external_id'] == garmin_id]
    if not unlink:
        if original and (original['external_provider'] is not None or original['external_id'] is not None):
            blockers.append("original must be standalone Intervals identity")
        if original and original['canonical_activity_id'] != target:
            blockers.append("original canonical identity changed")
        if len(claimants) > 1:
            blockers.append("ambiguous Garmin coordinate")
        if not _compatible(_payload(original), _payload(garmin)):
            blockers.append("incompatible cycling start or duration")
        blockers.extend(reference_blockers(conn, canonical_ids - {target}))
    # Unlink keeps the target canonical, restores Garmin-coordinate canonicals,
    # and does not move any authored references attached to the survivor.
    chosen = _payload(original)
    returned = next((r for r in claimants if r is not original), None)
    normal_payload = _payload(returned) if primary_source == "intervals" and returned else _payload(garmin)
    after_rows = activities if (unlink and not linked) or (not unlink and linked) else (
        [chosen] if not unlink else [chosen, normal_payload]
    )
    state = {"links": links, "activities": activities, "decisions": decisions,
             "blockers": blockers, "unlink": unlink, "primary_source": primary_source}
    token = hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()
    return {"allowed": not blockers, "blockers": blockers, "linked": linked,
            "intervals_id": intervals_id, "garmin_id": garmin_id, "canonical_id": target,
            "operation": "unlink" if unlink else "link", "token": token,
            "before": _totals(activities), "after": _totals(after_rows)}


def enforce(cursor: sqlite3.Cursor, affected: set[str]) -> set[str]:
    """Reapply only manual decisions touched by this ingest, within its transaction."""
    conn = cursor.connection
    if not exists(conn) or not affected:
        return affected
    keys = tuple(sorted(str(x) for x in affected))
    marks = ','.join('?' for _ in keys)
    decisions = _rows(conn, f"""SELECT * FROM activity_manual_links
        WHERE garmin_activity_id IN ({marks})
           OR 'intervals_' || intervals_activity_id IN ({marks})""", keys + keys)
    for decision in decisions:
        iid, gid = decision['intervals_activity_id'], decision['garmin_activity_id']
        plan = inspect(conn, iid, gid, pending_projection=True)
        if not plan['allowed']:
            raise ValueError("manual activity link blocked: " + '; '.join(plan['blockers']))
        target = plan['canonical_id']
        rows = _rows(conn, """SELECT id, canonical_activity_id FROM activity_provider_links
            WHERE (provider='intervals' AND provider_activity_id=?)
               OR (provider='garmin' AND provider_activity_id=?)
               OR (external_provider='garmin' AND external_id=?)""", (iid, gid, gid))
        for row in rows:
            previous = str(row['canonical_activity_id'])
            affected.add(previous)
            if previous != target:
                clear_caches(conn, previous)
            cursor.execute("UPDATE activity_provider_links SET canonical_activity_id=?,match_status='matched' WHERE id=?", (target, row['id']))
        affected.add(target)
    return affected
