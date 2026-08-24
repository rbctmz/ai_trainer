"""Unit contract for the athlete_profile store (TD-006 slice 1, #371).

The persistence layer extracted from ``data/database.py`` owns the table DDL,
the additive pace-column migration and the append-only save/latest-row read.
``Database`` keeps the same public methods as thin facades, so the existing
``test_athlete_profile.py`` / API-contract suites guard the facade while these
tests pin the store itself.
"""
from __future__ import annotations

import sqlite3

import pytest

from data.athlete_profile_store import (
    AthleteProfileStore,
    create_athlete_profile_table,
    ensure_athlete_profile_columns,
)


pytestmark = pytest.mark.smoke


def _connect(tmp_path, name="profile_store.db"):
    return sqlite3.connect(str(tmp_path / name))


def _clean(value):
    """Minimal stand-in for Database.clean_value: scalars pass through."""
    return value


def _full_profile(**overrides):
    profile = {
        "ftp": 159.0,
        "weight_kg": 93.9,
        "lthr": 163.0,
        "threshold_pace_seconds_per_km": 375.0,
        "threshold_pace_source": "intervals_icu",
        "threshold_pace_synced_at": "2026-07-29 06:00:00",
        "swim_threshold_pace_seconds_per_100m": 138.0,
        "swim_threshold_pace_source": "intervals_icu",
        "swim_threshold_pace_synced_at": "2026-08-03 06:00:00",
        "source": "intervals_icu",
    }
    profile.update(overrides)
    return profile


def test_create_table_then_save_get_round_trip(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)

    AthleteProfileStore(conn, _clean).save(_full_profile())
    got = AthleteProfileStore(conn, _clean).get()

    assert got["ftp"] == 159.0
    assert got["weight_kg"] == 93.9
    assert got["lthr"] == 163.0
    assert got["threshold_pace_seconds_per_km"] == 375.0
    assert got["threshold_pace_source"] == "intervals_icu"
    assert got["swim_threshold_pace_seconds_per_100m"] == 138.0
    assert got["swim_threshold_pace_source"] == "intervals_icu"
    assert got["source"] == "intervals_icu"
    assert got["synced_at"] is not None
    conn.close()


def test_get_returns_none_when_empty(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)

    assert AthleteProfileStore(conn, _clean).get() is None
    conn.close()


def test_latest_row_wins(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)
    store = AthleteProfileStore(conn, _clean)

    store.save(_full_profile(ftp=159.0))
    store.save(_full_profile(ftp=161.0))

    assert store.get()["ftp"] == 161.0
    conn.close()


def test_save_stamps_synced_at_when_omitted(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)

    AthleteProfileStore(conn, _clean).save(
        {
            "ftp": 159.0,
            "weight_kg": 93.9,
            "lthr": 163.0,
            "threshold_pace_seconds_per_km": 375.0,
            "threshold_pace_source": "intervals_icu",
            "source": "intervals_icu",
        }
    )
    got = AthleteProfileStore(conn, _clean).get()

    assert got["threshold_pace_synced_at"] is not None
    assert got["swim_threshold_pace_seconds_per_100m"] is None
    conn.close()


def test_save_preserves_explicit_synced_at(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)

    AthleteProfileStore(conn, _clean).save(
        _full_profile(threshold_pace_synced_at="2026-07-29 06:00:00")
    )
    got = AthleteProfileStore(conn, _clean).get()

    assert got["threshold_pace_synced_at"] == "2026-07-29 06:00:00"
    conn.close()


def test_pace_threshold_timeline_preserves_snapshot_and_source(tmp_path):
    conn = _connect(tmp_path)
    create_athlete_profile_table(conn)
    conn.executemany(
        """
        INSERT INTO athlete_profile (
            threshold_pace_seconds_per_km,
            threshold_pace_source,
            threshold_pace_synced_at,
            source,
            synced_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                300.0,
                "intervals_icu",
                "2026-07-01 06:00:00",
                "intervals_icu",
                "2026-07-01 06:00:00",
            ),
            (
                285.0,
                "intervals_icu",
                "2026-08-20 06:00:00",
                "intervals_icu",
                "2026-08-20 06:00:00",
            ),
        ],
    )

    store = AthleteProfileStore(conn, _clean)
    timeline = store.pace_threshold_timeline("run")

    assert [row["value"] for row in timeline] == [300.0, 285.0]
    assert timeline[-1] == {
        "snapshot_at": "2026-08-20 06:00:00",
        "value": 285.0,
        "source": "intervals_icu",
        "observed_at": "2026-08-20 06:00:00",
    }
    assert store.pace_threshold_timeline("bike") == []
    conn.close()


def test_legacy_schema_migrates_additively(tmp_path):
    conn = _connect(tmp_path)
    conn.execute(
        """
        CREATE TABLE athlete_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ftp REAL,
            weight_kg REAL,
            lthr REAL,
            source TEXT,
            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO athlete_profile (ftp, weight_kg, lthr, source) VALUES (?, ?, ?, ?)",
        (159.0, 93.9, 163.0, "intervals_icu"),
    )
    conn.commit()

    ensure_athlete_profile_columns(conn)

    columns = {row[1] for row in conn.execute("PRAGMA table_info(athlete_profile)")}
    for column in (
        "threshold_pace_seconds_per_km",
        "threshold_pace_source",
        "threshold_pace_synced_at",
        "swim_threshold_pace_seconds_per_100m",
        "swim_threshold_pace_source",
        "swim_threshold_pace_synced_at",
    ):
        assert column in columns
    row = conn.execute("SELECT ftp, lthr FROM athlete_profile").fetchone()
    assert row[0] == 159.0
    assert row[1] == 163.0
    conn.close()
