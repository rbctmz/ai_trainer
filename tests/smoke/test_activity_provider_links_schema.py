"""Schema contract for `activity_provider_links` (ADR-0008 / #269, M0).

RED→GREEN by construction: without the CHECK/UNIQUE constraints these inserts
would succeed; with them (ADR-0008) invalid rows raise. This pins the NEW schema
contract that the broad smoke ("1039 passed" = no regression) does not — per the
M0 schema review: re-init idempotency, UNIQUE(provider, provider_activity_id),
allowed `match_status`, null-pair external identity, chosen orphan-link policy,
and the `PRIMARY_ACTIVITY_SOURCE` fail-fast.
"""
from __future__ import annotations

import sqlite3

import pytest

from config.settings import _primary_activity_source
from data.database import Database


def _conn(path: str) -> sqlite3.Connection:
    # autocommit: a rejected INSERT does not poison the next one in these tests
    return sqlite3.connect(path, isolation_level=None)


def _link(**over):
    row = {
        "canonical_activity_id": "act_1",
        "provider": "garmin",
        "provider_activity_id": "g_1",
        "external_provider": None,
        "external_id": None,
        "provider_tss": 84.0,
        "match_status": "unmatched",
    }
    row.update(over)
    return row


def _insert(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """INSERT INTO activity_provider_links
           (canonical_activity_id, provider, provider_activity_id,
            external_provider, external_id, provider_tss, match_status)
           VALUES (:canonical_activity_id, :provider, :provider_activity_id,
                   :external_provider, :external_id, :provider_tss, :match_status)""",
        row,
    )


def test_reinit_idempotent_and_columns(tmp_path):
    p = str(tmp_path / "s.db")
    Database(p)
    Database(p)  # double init must be safe (ASR-MOD-3)
    conn = _conn(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(activity_provider_links)")}
    conn.close()
    assert {
        "canonical_activity_id", "provider", "provider_activity_id",
        "external_provider", "external_id", "provider_tss",
        "match_status", "imported_at",
    } <= cols


def test_unique_provider_activity(tmp_path):
    p = str(tmp_path / "s.db"); Database(p)
    conn = _conn(p)
    _insert(conn, _link())
    with pytest.raises(sqlite3.IntegrityError):
        # same (provider, provider_activity_id), different canonical → rejected
        _insert(conn, _link(canonical_activity_id="act_2"))
    conn.close()


def test_match_status_check(tmp_path):
    p = str(tmp_path / "s.db"); Database(p)
    conn = _conn(p)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, _link(match_status="totally_bogus"))
    for ok in ("matched", "ambiguous", "unmatched"):
        _insert(conn, _link(provider_activity_id=f"g_{ok}", match_status=ok))
    conn.close()


def test_external_identity_null_pair(tmp_path):
    p = str(tmp_path / "s.db"); Database(p)
    conn = _conn(p)
    with pytest.raises(sqlite3.IntegrityError):  # id without namespace
        _insert(conn, _link(external_id="123", external_provider=None))
    with pytest.raises(sqlite3.IntegrityError):  # namespace without id
        _insert(conn, _link(provider_activity_id="g_2", external_provider="strava"))
    # both present → allowed
    _insert(conn, _link(provider_activity_id="g_3", external_id="123", external_provider="strava"))
    conn.close()


def test_link_is_logical_not_db_foreign_key(tmp_path):
    """ADR-0008: the canonical link is LOGICAL (no SQLite FOREIGN KEY). A link whose
    canonical_activity_id has no `activities` row must INSERT — no-orphan is a
    logical invariant enforced by ingest (M1), not the schema."""
    p = str(tmp_path / "s.db"); Database(p)
    conn = _conn(p)
    _insert(conn, _link(canonical_activity_id="no_such_canonical"))  # must not raise
    conn.close()


def test_primary_activity_source_default_and_fail_fast(monkeypatch):
    monkeypatch.delenv("PRIMARY_ACTIVITY_SOURCE", raising=False)
    assert _primary_activity_source() == "garmin"  # backward-compatible default
    monkeypatch.setenv("PRIMARY_ACTIVITY_SOURCE", "intervals")
    assert _primary_activity_source() == "intervals"
    monkeypatch.setenv("PRIMARY_ACTIVITY_SOURCE", "garmin_typo")
    with pytest.raises(ValueError):  # unknown config → fail-fast, never guess
        _primary_activity_source()
