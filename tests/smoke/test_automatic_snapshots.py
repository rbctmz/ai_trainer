"""#623 — automatic validated snapshots, retention and backup health.

Every path belongs to ``tmp_path``; the maintainer's working database and its
sidecars are never touched. The suite proves the properties the issue names:
silent success is impossible, a repeated sync does not grow the backup set,
retention never drops the newest valid version, and disk-full / permission-denied
/ interrupted-write / corrupt-snapshot failures leave the source and the previous
backup intact.
"""

from __future__ import annotations

import errno
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config.db_paths import DatabasePathViolation
from services.durability import (
    MANIFEST_SUFFIX,
    SNAPSHOT_DIR_ENV,
    SnapshotError,
    SnapshotPolicy,
    apply_retention,
    backup_health,
    count_domains,
    create_snapshot,
    database_generation,
    load_snapshots,
    run_scheduled_snapshot,
    snapshot_after_mutation,
    snapshot_after_sync,
)

pytestmark = pytest.mark.smoke

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _database(path: Path, *, activities: int = 2, checkpoints: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE activities(activity_id TEXT)")
        conn.executemany(
            "INSERT INTO activities VALUES (?)", [(f"a{i}",) for i in range(activities)]
        )
        conn.execute("CREATE TABLE activity_provider_links(activity_id TEXT, provider TEXT)")
        conn.execute("CREATE TABLE planning_checkpoints(id INTEGER, note TEXT)")
        conn.executemany(
            "INSERT INTO planning_checkpoints VALUES (?, ?)", [(i, f"private-note-{i}") for i in range(checkpoints)]
        )
        conn.execute("CREATE TABLE coach_decisions(id INTEGER)")
        conn.execute("CREATE TABLE plan_actual_matches(id INTEGER)")
        conn.execute("CREATE TABLE session_feedback(id INTEGER)")
        conn.execute("CREATE TABLE readiness_snapshots(id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def source(tmp_path: Path) -> Path:
    return _database(tmp_path / "app-data" / "ai_trainer.db")


@pytest.fixture
def snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "app-data" / "snapshots"
    monkeypatch.setenv(SNAPSHOT_DIR_ENV, str(directory))
    return directory


def _policy(**overrides) -> SnapshotPolicy:
    base = {
        "daily_versions": 14,
        "weekly_versions": 8,
        "coalescing_minutes": 30,
        "rpo_hours": 24,
        "rpo_sync_minutes": 15,
    }
    base.update(overrides)
    return SnapshotPolicy(**base)


def _snapshot_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.db"))


# --------------------------------------------------------------------------- #
# Snapshot creation
# --------------------------------------------------------------------------- #


def test_snapshot_carries_manifest_with_aggregates_only(source: Path, snapshots: Path) -> None:
    outcome = create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)

    assert outcome.status == "created"
    manifest = outcome.manifest
    assert manifest is not None
    assert manifest.integrity_check == "ok"
    assert manifest.reason == "post-sync"
    assert manifest.domains["activities"] == 2
    assert manifest.domains["planning_checkpoints"] == 1

    payload = Path(f"{snapshots / manifest.snapshot}{MANIFEST_SUFFIX}").read_text(encoding="utf-8")
    assert "private-note" not in payload, "manifest must not contain personal rows"
    assert "a0" not in payload
    assert manifest.sha256 in payload


def test_manifest_records_schema_and_domain_coverage(source: Path, snapshots: Path) -> None:
    outcome = create_snapshot(source, reason="manual", directory=snapshots, now=NOW)
    manifest = outcome.manifest
    assert manifest is not None

    for domain in ("activities", "activity_provider_links", "planning_checkpoints",
                   "coach_decisions", "plan_actual_matches", "session_feedback",
                   "readiness_snapshots"):
        assert domain in manifest.domains, f"manifest must cover {domain}"
    assert manifest.schema_version == 1


def test_snapshot_is_validated_restorable_copy(source: Path, snapshots: Path) -> None:
    """The artifact must be a real database, not a byte copy of the WAL state."""
    outcome = create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    assert outcome.manifest is not None
    snapshot = snapshots / outcome.manifest.snapshot

    conn = sqlite3.connect(f"{snapshot.as_uri()}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 2
    finally:
        conn.close()


def test_repeated_sync_without_changes_does_not_grow_the_backup_set(
    source: Path, snapshots: Path
) -> None:
    """Cheap falsifying check 3 from #623."""
    first = snapshot_after_sync(source, directory=snapshots, now=NOW)
    second = snapshot_after_sync(source, directory=snapshots, now=NOW + timedelta(minutes=5))

    assert first.status == "created"
    assert second.status == "skipped-unchanged"
    assert len(_snapshot_files(snapshots)) == 1


def test_changed_database_is_snapshotted_again(source: Path, snapshots: Path) -> None:
    snapshot_after_sync(source, directory=snapshots, now=NOW)

    conn = sqlite3.connect(source)
    conn.execute("INSERT INTO activities VALUES ('a-new')")
    conn.commit()
    conn.close()

    second = snapshot_after_sync(source, directory=snapshots, now=NOW + timedelta(minutes=1))
    assert second.status == "created"
    assert len(_snapshot_files(snapshots)) == 2


def test_generation_ignores_unrelated_files(source: Path, tmp_path: Path) -> None:
    """A new ``-wal``-only double must not be confused with a content change."""
    baseline = database_generation(source)
    assert baseline == database_generation(source)
    (tmp_path / "unrelated.db").write_bytes(b"noise")
    assert database_generation(source) == baseline


# --------------------------------------------------------------------------- #
# Daily safety snapshot
# --------------------------------------------------------------------------- #


def test_daily_snapshot_creates_when_database_changed(source: Path, snapshots: Path) -> None:
    outcome = run_scheduled_snapshot(source, directory=snapshots, now=NOW)
    assert outcome.status == "created"
    assert outcome.reason == "scheduled-daily"


def test_daily_snapshot_skips_when_unchanged(source: Path, snapshots: Path) -> None:
    run_scheduled_snapshot(source, directory=snapshots, now=NOW)
    again = run_scheduled_snapshot(source, directory=snapshots, now=NOW + timedelta(days=1))
    assert again.status == "skipped-unchanged"


# --------------------------------------------------------------------------- #
# Coalescing for high-value mutations
# --------------------------------------------------------------------------- #


def test_mutation_inside_the_window_is_coalesced(source: Path, snapshots: Path) -> None:
    """Several writes inside the window share one version, not one snapshot each."""
    policy = _policy(coalescing_minutes=30)
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)

    conn = sqlite3.connect(source)
    conn.execute("INSERT INTO planning_checkpoints VALUES (99, 'a decision')")
    conn.commit()
    conn.close()

    outcome = snapshot_after_mutation(
        source, policy=policy, directory=snapshots, now=NOW + timedelta(minutes=5)
    )
    assert outcome.status == "deferred-coalesced"
    assert len(_snapshot_files(snapshots)) == 1


def test_mutation_after_the_window_snapshots(source: Path, snapshots: Path) -> None:
    """After the window a real change becomes a new restorable version."""
    policy = _policy(coalescing_minutes=30)
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)

    conn = sqlite3.connect(source)
    conn.execute("INSERT INTO coach_decisions VALUES (1)")
    conn.commit()
    conn.close()

    outcome = snapshot_after_mutation(
        source, policy=policy, directory=snapshots, now=NOW + timedelta(minutes=31)
    )
    assert outcome.status == "created"
    assert len(_snapshot_files(snapshots)) == 2


def test_mutation_without_any_change_takes_no_snapshot(source: Path, snapshots: Path) -> None:
    """A read-only request must not manufacture a version."""
    outcome = snapshot_after_mutation(source, directory=snapshots, now=NOW)
    assert outcome.status == "skipped-unchanged"
    assert _snapshot_files(snapshots) == []


# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #


def _seed_artifacts(directory: Path, source: Path, moments: list[datetime]) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for index, moment in enumerate(moments):
        path = directory / f"ai_trainer.{moment.strftime('%Y%m%dT%H%M%SZ')}.db"
        path.write_bytes(b"sqlite-placeholder")
        Path(f"{path}{MANIFEST_SUFFIX}").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": moment.isoformat(),
                    "snapshot": path.name,
                    "source": source.name,
                    "sha256": "0" * 64,
                    "size_bytes": path.stat().st_size,
                    "integrity_check": "ok",
                    "source_generation": f"gen-{index}",
                    "reason": "seeded",
                    "domains": {},
                }
            ),
            encoding="utf-8",
        )
        created.append(path)
    return created


def test_retention_keeps_newest_valid_daily_and_weekly(source: Path, snapshots: Path) -> None:
    """Retention must never remove the last valid daily or weekly version."""
    moments = [NOW - timedelta(days=offset) for offset in range(40)]
    _seed_artifacts(snapshots, source, moments)

    policy = _policy(daily_versions=14, weekly_versions=8)
    removed = apply_retention(snapshots, policy, now=NOW)

    remaining = load_snapshots(snapshots)
    assert remaining, "retention must never empty the snapshot set"
    valid = [record for record in remaining if record.valid]
    newest = max(valid, key=lambda record: record.created_at)
    assert newest.created_at == NOW, "the newest valid snapshot must survive"
    assert len(valid) <= policy.daily_versions + policy.weekly_versions
    assert removed, "older artifacts beyond the policy should be pruned"


def test_retention_never_removes_the_only_snapshot(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    assert apply_retention(snapshots, _policy(daily_versions=0, weekly_versions=0), now=NOW + timedelta(days=400)) == []
    assert len(_snapshot_files(snapshots)) == 1


def test_invalid_artifacts_are_not_restore_candidates(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    orphan = snapshots / "ai_trainer.19990101T000000Z.db"
    orphan.write_bytes(b"partial write, no manifest")

    records = load_snapshots(snapshots)
    orphans = [record for record in records if record.path == orphan]
    assert orphans and not orphans[0].valid
    assert orphans[0].problem == "manifest-missing"

    apply_retention(snapshots, _policy(), now=NOW)
    assert not orphan.exists(), "incomplete artifacts must be pruned"
    assert len(_snapshot_files(snapshots)) == 1


def test_corrupt_manifest_marks_artifact_untrusted(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    snapshot = _snapshot_files(snapshots)[0]
    Path(f"{snapshot}{MANIFEST_SUFFIX}").write_text("{ not json", encoding="utf-8")

    record = [item for item in load_snapshots(snapshots) if item.path == snapshot][0]
    assert not record.valid
    assert record.problem is not None and "manifest-unreadable" in record.problem


def test_retention_removes_only_snapshot_artifacts(source: Path, snapshots: Path) -> None:
    """A stray file outside the snapshot directory must never be deleted."""
    stranger = source.parent / "important.db"
    stranger.write_bytes(b"not a snapshot")

    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    apply_retention(snapshots, _policy(daily_versions=0, weekly_versions=0), now=NOW + timedelta(days=90))

    assert stranger.exists(), "retention must not reach outside the snapshot directory"


# --------------------------------------------------------------------------- #
# Backup health
# --------------------------------------------------------------------------- #


def test_health_is_healthy_for_a_fresh_snapshot(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    health = backup_health(snapshots, now=NOW + timedelta(hours=1))

    assert health.status == "healthy"
    assert health.valid_count == 1
    assert health.stale is False
    assert health.last_snapshot_age_hours == pytest.approx(1.0)


def test_health_is_degraded_beyond_the_rpo_window(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    health = backup_health(snapshots, policy=_policy(rpo_hours=24), now=NOW + timedelta(hours=25))

    assert health.status == "degraded"
    assert health.stale is True


def test_health_fails_without_any_trustworthy_snapshot(snapshots: Path) -> None:
    snapshots.mkdir(parents=True, exist_ok=True)
    health = backup_health(snapshots, now=NOW)

    assert health.status == "failed"
    assert health.snapshot_count == 0
    assert health.last_snapshot_at is None


def test_health_is_partial_when_artifacts_are_untrusted(source: Path, snapshots: Path) -> None:
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    (snapshots / "ai_trainer.19990101T000000Z.db").write_bytes(b"orphan")

    health = backup_health(snapshots, now=NOW + timedelta(minutes=1))

    assert health.status == "partial"
    assert health.problems and "manifest-missing" in health.problems[0]


# --------------------------------------------------------------------------- #
# Failure modes: the source and the previous backup must survive
# --------------------------------------------------------------------------- #


def test_failed_backup_never_rolls_back_data_and_is_visible(
    source: Path, snapshots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup failure must not be masked by a successful sync."""
    import services.durability as durability

    def failing_backup(*_args, **_kwargs):
        raise durability.SQLiteBackupRestoreError("disk full (ENOSPC)")

    monkeypatch.setattr(durability, "backup_database", failing_backup)

    outcome = snapshot_after_sync(source, directory=snapshots, now=NOW)

    assert outcome.status == "failed"
    assert outcome.error is not None and "ENOSPC" in outcome.error
    assert source.exists(), "the database must survive a failed backup"
    assert _snapshot_files(snapshots) == []


def test_disk_full_leaves_previous_snapshot_restorable(
    source: Path, snapshots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cheap falsifying check 2 from #623."""
    first = create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    assert first.manifest is not None
    previous = snapshots / first.manifest.snapshot

    conn = sqlite3.connect(source)
    conn.execute("INSERT INTO activities VALUES ('a-later')")
    conn.commit()
    conn.close()

    import services.durability as durability

    def enospc_backup(database, output, *, confirm_stopped):
        raise durability.SQLiteBackupRestoreError(
            f"could not publish backup output {output}: [Errno 28] No space left on device"
        )

    monkeypatch.setattr(durability, "backup_database", enospc_backup)
    outcome = snapshot_after_sync(source, directory=snapshots, now=NOW + timedelta(minutes=10))

    assert outcome.status == "failed"
    assert previous.exists(), "the last valid backup must survive a disk-full run"
    record = [item for item in load_snapshots(snapshots) if item.path == previous][0]
    assert record.valid, "the previous snapshot must remain a restore candidate"
    assert sqlite3.connect(source).execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 3


def test_permission_denied_is_reported_and_source_survives(
    source: Path, snapshots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import services.durability as durability

    def denied_backup(database, output, *, confirm_stopped):
        raise PermissionError(errno.EACCES, "Permission denied", str(output))

    monkeypatch.setattr(durability, "backup_database", denied_backup)

    with pytest.raises(SnapshotError):
        create_snapshot(source, reason="manual", directory=snapshots, now=NOW)

    outcome = snapshot_after_sync(source, directory=snapshots, now=NOW)
    assert outcome.status == "failed"
    assert source.exists()


def test_interrupted_publish_leaves_previous_version_restorable(
    source: Path, snapshots: Path
) -> None:
    """Cheap falsifying check 1 from #623: kill between temp write and promotion."""
    create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    valid_before = [record for record in load_snapshots(snapshots) if record.valid]
    assert len(valid_before) == 1

    # Simulate the interrupted write: a temporary artifact that never got published.
    (snapshots / ".ai_trainer.20260920T130000Z.db.abc.tmp").write_bytes(b"half written")

    records = load_snapshots(snapshots)
    valid_after = [record for record in records if record.valid]
    assert len(valid_after) == 1, "the previous version must stay restorable"
    assert valid_after[0].path == valid_before[0].path


def test_snapshot_of_missing_database_is_refused(tmp_path: Path, snapshots: Path) -> None:
    with pytest.raises(SnapshotError, match="does not exist"):
        create_snapshot(tmp_path / "absent.db", reason="manual", directory=snapshots, now=NOW)


# --------------------------------------------------------------------------- #
# Location safety
# --------------------------------------------------------------------------- #


def test_snapshot_directory_must_not_alias_the_database(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot directory sharing the database directory risks deleting it."""
    monkeypatch.setenv(SNAPSHOT_DIR_ENV, str(source.parent))
    with pytest.raises(SnapshotError, match="must differ from the database directory"):
        create_snapshot(source, reason="manual", now=NOW)
    assert source.exists()

    # The alias itself is refused too: a "probe" that resolves onto live data.
    monkeypatch.setenv(SNAPSHOT_DIR_ENV, str(source))
    with pytest.raises((DatabasePathViolation, SnapshotError)):
        create_snapshot(source, reason="manual", now=NOW)
    assert source.exists()


def test_default_snapshot_directory_is_a_sibling_of_the_database(
    source: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(SNAPSHOT_DIR_ENV, raising=False)
    import services.durability as durability

    directory = durability.snapshot_directory(source)
    assert directory.parent == source.parent
    assert directory.name == "snapshots"
    assert not directory.is_relative_to(Path(tmp_path / ".git"))


def test_domain_counts_are_read_only(source: Path) -> None:
    before = source.stat().st_mtime_ns
    counts = count_domains(source)
    assert counts["activities"] == 2
    assert source.stat().st_mtime_ns == before


# --------------------------------------------------------------------------- #
# Restore from an automatic snapshot (existing #293 drill still applies)
# --------------------------------------------------------------------------- #


def test_automatic_snapshot_restores_into_a_temp_target(source: Path, snapshots: Path, tmp_path: Path) -> None:
    """An automatic snapshot must be restorable by the #293 drill unchanged."""
    from scripts.sqlite_backup_restore import restore_database

    outcome = create_snapshot(source, reason="post-sync", directory=snapshots, now=NOW)
    assert outcome.manifest is not None
    snapshot = snapshots / outcome.manifest.snapshot

    target = tmp_path / "restore-drill" / "ai_trainer.db"
    report = restore_database(snapshot, target, confirm_stopped=True)

    assert report.integrity_check == "ok"
    conn = sqlite3.connect(f"{target.as_uri()}?mode=ro", uri=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM planning_checkpoints").fetchone()[0] == 1
    finally:
        conn.close()
    assert source.exists(), "the drill must never replace the production database"


# --------------------------------------------------------------------------- #
# Integration: a successful sync leaves a snapshot or a visible failure
# --------------------------------------------------------------------------- #


def _run_sync_job(database: Path, run_sync) -> dict:
    """Drive the real job manager synchronously and return the public snapshot."""
    from api.sync_jobs import SyncJobManager

    manager = SyncJobManager()
    payload = manager.start_or_get(days=7, run_sync=run_sync, db=None, source="intervals")
    job_id = payload["job_id"]
    manager._run_job(job_id, "capture-run", run_sync, "intervals", 7, _DatabaseHandle(database))
    return manager.status()


class _DatabaseHandle:
    """Minimal handle: the hook only needs ``db_path``."""

    def __init__(self, path: Path) -> None:
        self.db_path = str(path)


def test_successful_sync_creates_a_snapshot_via_the_job_manager(
    source: Path, snapshots: Path
) -> None:
    def run_sync(on_progress, *, capture_run_id: str):
        return {"sync_state": "succeeded", "title": "ok", "summary": "1 activity"}

    status = _run_sync_job(source, run_sync)

    result = status["result"]
    assert result["data_durability"]["status"] == "created"
    assert result["data_durability"]["domains"]["activities"] == 2
    assert len(_snapshot_files(snapshots)) == 1
    assert status["sync_state"] == "succeeded"


def test_backup_failure_does_not_fail_the_sync(
    source: Path, snapshots: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silent success is impossible, but a backup problem never discards synced data."""
    import services.durability as durability

    def failing(*_args, **_kwargs):
        raise durability.SnapshotError("simulated backup failure")

    monkeypatch.setattr(durability, "backup_database", failing)

    def run_sync(on_progress, *, capture_run_id: str):
        return {"sync_state": "succeeded", "title": "ok", "summary": "1 activity"}

    status = _run_sync_job(source, run_sync)

    assert status["sync_state"] == "succeeded", "synced data must not be rolled back"
    durability_state = status["result"]["data_durability"]
    assert durability_state["status"] == "failed"
    assert "simulated backup failure" in durability_state["error"]
    assert source.exists()


def test_job_without_database_handle_skips_the_hook(source: Path) -> None:
    from api.sync_jobs import SyncJobManager

    manager = SyncJobManager()
    payload = manager.start_or_get(
        days=7,
        run_sync=lambda on_progress, *, capture_run_id: {"sync_state": "succeeded"},
        db=None,
        source="intervals",
    )
    manager._run_job(
        payload["job_id"],
        "capture-run",
        lambda on_progress, *, capture_run_id: {"sync_state": "succeeded"},
        "intervals",
        7,
        None,
    )
    assert "data_durability" not in (manager.status()["result"] or {})


def test_mutation_dependency_invokes_the_hook_once_per_request(source: Path) -> None:
    """The API dependency routes every mutating request through the durability hook."""
    import services.durability as durability
    from api.deps import snapshot_after_mutation

    calls: list[str] = []

    def recording_hook(db_path, **_kwargs):
        calls.append(str(db_path))
        return durability.SnapshotOutcome(status="created", reason="post-mutation")

    original = durability.snapshot_after_mutation
    durability.snapshot_after_mutation = recording_hook
    try:
        snapshot_after_mutation(db=_DatabaseHandle(source))
    finally:
        durability.snapshot_after_mutation = original

    assert calls == [str(source)]


def test_mutation_dependency_ignores_a_handle_without_a_path() -> None:
    from api.deps import snapshot_after_mutation

    assert snapshot_after_mutation(db=object()) is None


def test_mutation_dependency_never_breaks_the_request(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A durability failure must not bubble into the product write path."""
    import services.durability as durability
    from api.deps import snapshot_after_mutation

    monkeypatch.setattr(
        durability,
        "snapshot_after_mutation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert snapshot_after_mutation(db=_DatabaseHandle(source)) is None


def test_mutation_dependency_skips_a_handle_without_a_path() -> None:
    from api.deps import snapshot_after_mutation

    assert snapshot_after_mutation(db=object()) is None
