"""TD-001: contributor-safe SQLite backup/restore and restore drill.

Every path belongs to ``tmp_path``.  The suite never opens the maintainer's
``ai_trainer.db``, a Docker volume, provider credentials, or the network.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from datetime import date
from pathlib import Path

import pytest

import scripts.sqlite_backup_restore as sqlite_tool
from data.database import Database
from scripts.sqlite_backup_restore import (
    SQLiteBackupRestoreError,
    backup_database,
    check_sqlite_database,
    restore_database,
)
from services.activity_ingest import (
    ingest_provider_activity,
    normalize_provider_activity,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _marker_database(path: Path, marker: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE marker(value TEXT NOT NULL)")
    conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


def _activity_snapshot(path: Path) -> tuple:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT activity_id, date, sport, duration_minutes, tss, tss_method "
            "FROM activities WHERE activity_id='293001'"
        ).fetchone()
    finally:
        conn.close()


def _link_snapshot(path: Path) -> tuple:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT canonical_activity_id, provider, provider_activity_id, "
            "match_status FROM activity_provider_links"
        ).fetchone()
    finally:
        conn.close()


def _seed_domain_database(path: Path) -> str:
    day = date.today().isoformat()
    db = Database(str(path))
    candidate = normalize_provider_activity(
        {
            "activity_id": "293001",
            "date": day,
            "sport": "cycling",
            "duration_minutes": 72.0,
            "distance_km": 31.5,
            "source_tss": 64.0,
            "tss": 64.0,
            "tss_method": "power_np",
        },
        "garmin",
    )
    ingest_provider_activity(db, candidate, primary_source="garmin")
    db.save_planning_checkpoint(
        {
            "goal_type": "triathlon",
            "distance": 51.5,
            "weeks_to_race": 8,
            "event_date": day,
            "daily_plan": [],
            "td001_marker": "planning-survived",
        }
    )
    db.sync_wellness_batch(
        [
            {
                "date": day,
                "hrv": {"rmssd": 43.5, "rmssd_source": "intervals"},
                "sleep": {
                    "total_sleep_minutes": 472,
                    "total_sleep_source": "intervals",
                    "sleep_score": 82,
                    "sleep_score_source": "intervals",
                },
                "health": {
                    "resting_hr": 52,
                    "resting_hr_source": "intervals",
                },
            }
        ],
        provider="intervals",
        cursor_value=day,
        primary_source="intervals",
    )
    return day


def test_integrity_check_accepts_sqlite_and_rejects_malformed_file(tmp_path: Path) -> None:
    database = tmp_path / "healthy.db"
    _marker_database(database, "healthy")

    assert check_sqlite_database(database) == "ok"

    malformed = tmp_path / "malformed.db"
    malformed.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(SQLiteBackupRestoreError, match="integrity"):
        check_sqlite_database(malformed)


def test_backup_requires_stopped_acknowledgement(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    output = tmp_path / "backup.db"
    _marker_database(database, "source")

    with pytest.raises(SQLiteBackupRestoreError, match="confirm-stopped"):
        backup_database(database, output, confirm_stopped=False)

    assert not output.exists()


def test_backup_is_valid_private_atomic_snapshot(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    output = tmp_path / "backup.db"
    _marker_database(database, "source")

    report = backup_database(database, output, confirm_stopped=True)

    assert report.action == "backup"
    assert report.database == str(database.resolve())
    assert report.artifact == str(output.resolve())
    assert report.integrity_check == "ok"
    assert report.sha256 == _sha256(output)
    assert _read_marker(output) == "source"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


def test_backup_refuses_existing_output_and_self_copy(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    output = tmp_path / "backup.db"
    _marker_database(database, "source")
    output.write_bytes(b"keep-me")

    with pytest.raises(SQLiteBackupRestoreError, match="already exists"):
        backup_database(database, output, confirm_stopped=True)
    assert output.read_bytes() == b"keep-me"

    with pytest.raises(SQLiteBackupRestoreError, match="different"):
        backup_database(database, database, confirm_stopped=True)
    assert _read_marker(database) == "source"


def test_restore_drill_preserves_activity_link_plan_and_wellness(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.backup.db"
    restored = tmp_path / "clean-volume" / "ai_trainer.db"
    day = _seed_domain_database(source)
    expected_activity = _activity_snapshot(source)
    expected_link = _link_snapshot(source)

    backup_database(source, backup, confirm_stopped=True)
    report = restore_database(
        backup,
        restored,
        confirm_stopped=True,
    )

    assert report.action == "restore"
    assert report.database == str(restored.resolve())
    assert report.artifact == str(backup.resolve())
    assert report.integrity_check == "ok"
    assert report.rollback is None
    assert report.sha256 == _sha256(restored)
    assert check_sqlite_database(restored) == "ok"
    assert _activity_snapshot(restored) == expected_activity

    db = Database(str(restored))
    activities = db.get_activities_by_ids(["293001"])
    assert len(activities) == 1
    assert activities[0]["activity_id"] == "293001"
    assert activities[0]["date"] == day
    assert activities[0]["sport"] == "cycling"
    assert activities[0]["duration_minutes"] == pytest.approx(72.0)

    assert _link_snapshot(restored) == expected_link
    assert expected_link[:3] == ("293001", "garmin", "293001")

    checkpoint = db.get_latest_planning_checkpoint()
    assert checkpoint["td001_marker"] == "planning-survived"

    hrv = db.get_hrv_data(days=2)
    sleep = db.get_sleep_data(days=2)
    health = db.get_daily_health(days=2)
    assert hrv.loc[hrv["date"].dt.strftime("%Y-%m-%d") == day, "rmssd"].iloc[0] == 43.5
    assert hrv.loc[hrv["date"].dt.strftime("%Y-%m-%d") == day, "rmssd_source"].iloc[0] == "intervals"
    assert sleep.loc[
        sleep["date"].dt.strftime("%Y-%m-%d") == day,
        "total_sleep_minutes",
    ].iloc[0] == 472
    assert health.loc[
        health["date"].dt.strftime("%Y-%m-%d") == day,
        "resting_hr",
    ].iloc[0] == 52


def test_restore_existing_target_creates_valid_rollback(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.backup.db"
    target = tmp_path / "target.db"
    rollback = tmp_path / "target.before-restore.db"
    _marker_database(source, "replacement")
    _marker_database(target, "original")
    backup_database(source, backup, confirm_stopped=True)

    report = restore_database(
        backup,
        target,
        confirm_stopped=True,
        rollback_output=rollback,
    )

    assert report.rollback == str(rollback.resolve())
    assert _read_marker(target) == "replacement"
    assert check_sqlite_database(rollback) == "ok"
    assert _read_marker(rollback) == "original"
    assert stat.S_IMODE(rollback.stat().st_mode) == 0o600


def test_invalid_restore_fails_before_mutating_target(tmp_path: Path) -> None:
    backup = tmp_path / "invalid.db"
    target = tmp_path / "target.db"
    rollback = tmp_path / "rollback.db"
    backup.write_text("invalid sqlite", encoding="utf-8")
    _marker_database(target, "original")
    before = _sha256(target)

    with pytest.raises(SQLiteBackupRestoreError, match="integrity"):
        restore_database(
            backup,
            target,
            confirm_stopped=True,
            rollback_output=rollback,
        )

    assert _sha256(target) == before
    assert _read_marker(target) == "original"
    assert not rollback.exists()


def test_restore_replace_failure_keeps_target_and_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.backup.db"
    target = tmp_path / "target.db"
    rollback = tmp_path / "target.before-restore.db"
    _marker_database(source, "replacement")
    _marker_database(target, "original")
    backup_database(source, backup, confirm_stopped=True)
    before = _sha256(target)

    def fail_replace(_temporary: Path, _target: Path) -> None:
        raise OSError("injected final replace failure")

    monkeypatch.setattr(sqlite_tool, "_replace_database", fail_replace)

    with pytest.raises(SQLiteBackupRestoreError, match="replace"):
        restore_database(
            backup,
            target,
            confirm_stopped=True,
            rollback_output=rollback,
        )

    assert _sha256(target) == before
    assert _read_marker(target) == "original"
    assert check_sqlite_database(rollback) == "ok"
    assert _read_marker(rollback) == "original"
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_restore_removes_stale_sidecars(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.backup.db"
    target = tmp_path / "clean-volume" / "ai_trainer.db"
    _marker_database(source, "replacement")
    backup_database(source, backup, confirm_stopped=True)
    target.parent.mkdir()
    sidecars = [Path(f"{target}{suffix}") for suffix in ("-wal", "-shm", "-journal")]
    for sidecar in sidecars:
        sidecar.write_bytes(b"stale")

    restore_database(backup, target, confirm_stopped=True)

    assert _read_marker(target) == "replacement"
    assert all(not sidecar.exists() for sidecar in sidecars)


def test_cli_prints_json_and_missing_acknowledgement_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    _marker_database(database, "source")

    assert (
        sqlite_tool.main(
            [
                "backup",
                "--database",
                str(database),
                "--output",
                str(backup),
                "--confirm-stopped",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["action"] == "backup"
    assert payload["integrity_check"] == "ok"

    second = tmp_path / "second.db"
    assert (
        sqlite_tool.main(
            [
                "backup",
                "--database",
                str(database),
                "--output",
                str(second),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "confirm-stopped" in captured.err
    assert not second.exists()
