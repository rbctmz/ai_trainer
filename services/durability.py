"""Automatic validated snapshots, retention and backup health (#622/#623).

Why this exists
---------------
#293 provides a correct manual snapshot, but a snapshot only exists if an operator
asked for one beforehand. The 2026-09-20 incident therefore had an RPO of about a
month for locally born data (coach decisions, checkpoints, plan/actual matches,
feedback, readiness evidence) while provider-owned history came back from sync.

This module makes snapshots a property of normal operation:

* after a successful provider sync;
* after durable high-value mutations, with a coalescing window;
* once a day, as a safety net, when the database changed at all.

Guarantees encoded here
-----------------------
* a snapshot is produced through the validated #293 primitives (SQLite Backup
  API, atomic no-clobber publish, ``PRAGMA integrity_check``) — a plain copy is
  never used, so committed ``-wal`` pages travel;
* a snapshot is only created when the logical generation changed, so repeated
  syncs without changes do not grow the backup set;
* every artifact carries a manifest with **no personal values**: schema version,
  size, sha256, timestamps, source generation, integrity result and per-domain
  coverage;
* retention never removes the newest valid daily and weekly version, and never
  treats an artifact without a valid manifest as a restore candidate;
* a backup failure never rolls back provider or user data; it becomes a visible
  ``partial``/``degraded`` state instead of a silent success;
* snapshots are stored outside any Git checkout, next to the runtime database.

Non-goals (#623): off-device transport and encryption (#626); changing provider
sync semantics; retaining every version forever; logging personal rows.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from config.db_paths import assert_safe, normalize_path
from data.durability_domains import KEY_DOMAINS
from scripts.sqlite_backup_restore import (
    BackupReport,
    SQLiteBackupRestoreError,
    backup_database,
    check_sqlite_database,
)

__all__ = [
    "SnapshotError",
    "SnapshotManifest",
    "SnapshotRecord",
    "BackupHealth",
    "SnapshotPolicy",
    "SnapshotOutcome",
    "SNAPSHOT_DIR_ENV",
    "MANIFEST_SUFFIX",
    "coalescing_window",
    "snapshot_directory",
    "database_generation",
    "create_snapshot",
    "run_scheduled_snapshot",
    "snapshot_after_sync",
    "snapshot_after_mutation",
    "load_snapshots",
    "apply_retention",
    "backup_health",
]

#: Overrides the snapshot directory (tests and acceptance runs).
SNAPSHOT_DIR_ENV = "AI_TRAINER_SNAPSHOT_DIR"

#: Snapshot artifacts are ``<db-stem>.<UTC timestamp>.db`` + this suffix.
MANIFEST_SUFFIX = ".manifest.json"
SNAPSHOT_DIR_NAME = "snapshots"
WEEKLY_DIR_NAME = "weekly"

MANIFEST_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "snapshot_manifest_schema_version"


class SnapshotError(RuntimeError):
    """Operator-facing snapshot failure. Never carries personal row values."""


@dataclass(frozen=True)
class SnapshotPolicy:
    """Retention and coalescing policy for automatic snapshots."""

    daily_versions: int = 14
    weekly_versions: int = 8
    coalescing_minutes: int = 30
    rpo_hours: int = 24
    rpo_sync_minutes: int = 15


@dataclass(frozen=True)
class SnapshotManifest:
    """Metadata about one snapshot. Contains aggregates only, never row values."""

    schema_version: int
    created_at: str
    snapshot: str
    source: str
    sha256: str
    size_bytes: int
    integrity_check: str
    source_generation: str
    reason: str
    domains: dict[str, int] = field(default_factory=dict)
    source_bytes: int = 0
    schema_version_of_source: int | None = None

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass
class SnapshotRecord:
    """A snapshot file plus its manifest, or the reason it cannot be trusted."""

    path: Path
    manifest: SnapshotManifest | None = None
    problem: str | None = None

    @property
    def valid(self) -> bool:
        return self.manifest is not None and self.problem is None

    @property
    def created_at(self) -> datetime | None:
        if self.manifest is None:
            return None
        try:
            return datetime.fromisoformat(self.manifest.created_at)
        except ValueError:  # pragma: no cover - defensive
            return None


@dataclass
class BackupHealth:
    """Operator-facing backup status, free of personal values."""

    status: str
    snapshot_count: int
    valid_count: int
    last_snapshot_at: str | None
    last_snapshot_age_hours: float | None
    rpo_hours: int
    stale: bool
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SnapshotOutcome:
    """Result of one snapshot attempt: created, skipped, or visibly failed."""

    status: str
    reason: str
    manifest: SnapshotManifest | None = None
    error: str | None = None
    removed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in {"created", "skipped-unchanged"}

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["manifest"] = self.manifest.as_json() if self.manifest else None
        return payload


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def coalescing_window(policy: SnapshotPolicy) -> timedelta:
    return timedelta(minutes=max(0, policy.coalescing_minutes))


def snapshot_directory(
    database: str | os.PathLike[str] | None = None,
    *,
    create: bool = True,
) -> Path:
    """Directory holding automatic snapshots — outside any Git checkout.

    Defaults to a ``snapshots/`` sibling of the runtime database, which #624 moved
    to the platform application-data directory. ``AI_TRAINER_SNAPSHOT_DIR``
    overrides it, which is what tests and acceptance runs use.

    Two refusals: a location that aliases the database or one of its sidecars, and
    a default location that would still sit inside a Git checkout (a pre-#624
    runtime). The second is deliberate — a snapshot sharing fate with the sources
    is not a backup — and the message names the fix instead of failing later.
    """
    from config.db_paths import production_database_path

    base = normalize_path(database) if database is not None else production_database_path()
    override = os.getenv(SNAPSHOT_DIR_ENV, "").strip()
    if override:
        directory = normalize_path(override)
    else:
        directory = base.parent / SNAPSHOT_DIR_NAME

    # Never let a snapshot land on the database itself or a committed WAL page.
    assert_safe(directory / "probe.db", purpose="the snapshot directory")
    if directory == base.parent:
        raise SnapshotError(
            "the snapshot directory must differ from the database directory: "
            f"{directory.parent.name} would hold both the live database and its snapshots, "
            "so retention could delete the live file"
        )
    if not override and _inside_git_checkout(directory) and directory.parent == base.parent:
        raise SnapshotError(
            "the runtime database still lives inside a Git checkout, so a snapshot "
            "beside it would share the same fate; move the database first with "
            "scripts/migrate_database_out_of_checkout.py or set AI_TRAINER_SNAPSHOT_DIR"
        )
    if create:
        if directory.exists() and not directory.is_dir():
            raise SnapshotError(
                f"the snapshot directory resolves to a file, not a directory: {directory.name}"
            )
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    return directory


def _inside_git_checkout(path: Path) -> bool:
    """True when ``path`` sits inside a working tree (best effort, never raising)."""
    import subprocess

    candidate = path if path.exists() else path.parent
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(candidate),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git
        return False
    if completed.returncode != 0 or not completed.stdout.strip():
        return False
    root = normalize_path(completed.stdout.strip())
    try:
        normalize_path(path).relative_to(root)
    except ValueError:
        return False
    return True


def database_generation(database: str | os.PathLike[str]) -> str:
    """Cheap fingerprint of the logical database content.

    Combines the main file and its ``-wal`` companion (size, mtime) with the row
    count of the append-only journal tables, so a sync that wrote nothing and a
    sync that wrote rows are distinguishable without hashing personal data.
    """
    path = normalize_path(database)
    if not path.is_file():
        raise SnapshotError("database does not exist; nothing to snapshot")

    parts: list[str] = []
    for candidate in (path, Path(f"{path}-wal")):
        try:
            info = candidate.stat()
        except OSError:
            parts.append(f"{candidate.name}:absent")
            continue
        parts.append(f"{candidate.name}:{info.st_size}:{info.st_mtime_ns}")

    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        present = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in KEY_DOMAINS:
            if table not in present:
                continue
            count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            parts.append(f"{table}={int(count)}")
    finally:
        connection.close()

    import hashlib

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def count_domains(database: str | os.PathLike[str]) -> dict[str, int]:
    """Per-domain row counts for the manifest. Aggregates only."""
    path = normalize_path(database)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        present = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        return {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in KEY_DOMAINS
            if table in present
        }
    finally:
        connection.close()


def _user_schema_version(database: str | os.PathLike[str]) -> int | None:
    path = normalize_path(database)
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT value FROM user_settings WHERE key = ?", (SCHEMA_VERSION_KEY,)
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _snapshot_stem(database: Path) -> str:
    return database.stem


def _snapshot_name(database: Path, moment: datetime) -> str:
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    return f"{_snapshot_stem(database)}.{stamp}.db"


def _write_manifest(manifest: SnapshotManifest, destination: Path) -> None:
    """Publish the manifest next to the snapshot through an atomic replace."""
    payload = manifest.as_json()
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def load_snapshots(directory: Path) -> list[SnapshotRecord]:
    """Read every snapshot artifact, reporting which ones are not trustworthy."""
    records: list[SnapshotRecord] = []
    if not directory.exists():
        return records

    for snapshot in sorted(directory.rglob("*.db")):
        manifest_path = Path(f"{snapshot}{MANIFEST_SUFFIX}")
        if not manifest_path.is_file():
            records.append(SnapshotRecord(path=snapshot, problem="manifest-missing"))
            continue
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            records.append(SnapshotRecord(path=snapshot, problem=f"manifest-unreadable:{exc}"))
            continue
        if int(payload.get("schema_version", -1)) != MANIFEST_SCHEMA_VERSION:
            records.append(SnapshotRecord(path=snapshot, problem="manifest-schema-unsupported"))
            continue
        try:
            manifest = SnapshotManifest(
                schema_version=int(payload["schema_version"]),
                created_at=str(payload["created_at"]),
                snapshot=str(payload["snapshot"]),
                source=str(payload["source"]),
                sha256=str(payload["sha256"]),
                size_bytes=int(payload["size_bytes"]),
                integrity_check=str(payload["integrity_check"]),
                source_generation=str(payload["source_generation"]),
                reason=str(payload["reason"]),
                domains={str(k): int(v) for k, v in dict(payload.get("domains") or {}).items()},
                source_bytes=int(payload.get("source_bytes") or 0),
                schema_version_of_source=payload.get("schema_version_of_source"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            records.append(SnapshotRecord(path=snapshot, problem=f"manifest-incomplete:{exc}"))
            continue

        problem = None
        if manifest.integrity_check != "ok":
            problem = f"integrity:{manifest.integrity_check}"
        elif manifest.size_bytes != snapshot.stat().st_size:
            problem = "size-mismatch"
        records.append(SnapshotRecord(path=snapshot, manifest=manifest, problem=problem))

    return records


def _latest(records: Iterable[SnapshotRecord]) -> SnapshotRecord | None:
    dated = [record for record in records if record.created_at is not None]
    if not dated:
        return None
    return max(dated, key=lambda record: record.created_at)


def _iso_week_key(moment: datetime) -> tuple[int, int]:
    iso = moment.isocalendar()
    return (iso.year, iso.week)


def apply_retention(
    directory: Path,
    policy: SnapshotPolicy,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Prune the snapshot set, protecting the newest valid daily and weekly copy.

    Daily candidates are artifacts from the last ``daily_versions`` days; weekly
    candidates are one artifact per ISO week for the last ``weekly_versions``
    weeks. Older valid artifacts are promoted to the weekly set when their week
    is not yet represented, otherwise removed. Invalid or manifest-less artifacts
    are never restore candidates and are removed.
    """
    moment = now or _utc_now()
    removed: list[str] = []
    records = load_snapshots(directory)
    if not records:
        return removed

    valid = [record for record in records if record.valid and record.created_at]
    invalid = [record for record in records if not record.valid]

    for record in invalid:
        _remove_artifact(record.path)
        removed.append(record.path.name)

    valid.sort(key=lambda record: record.created_at, reverse=True)
    daily_cutoff = moment - timedelta(days=policy.daily_versions)

    keep: set[Path] = set()
    daily = [record for record in valid if record.created_at >= daily_cutoff]
    weekly_by_key: dict[tuple[int, int], SnapshotRecord] = {}
    for record in valid:
        key = _iso_week_key(record.created_at)
        weekly_by_key.setdefault(key, record)

    weekly_keys = sorted(weekly_by_key, reverse=True)[: policy.weekly_versions]
    for key in weekly_keys:
        keep.add(weekly_by_key[key].path)

    daily_kept = daily[: policy.daily_versions]
    for record in daily_kept:
        keep.add(record.path)

    # Never drop the newest valid daily or the newest valid weekly version.
    newest = valid[0]
    keep.add(newest.path)
    if weekly_keys:
        keep.add(weekly_by_key[weekly_keys[0]].path)

    for record in valid:
        if record.path in keep:
            continue
        if record.path == newest.path:  # pragma: no cover - defensive
            continue
        _remove_artifact(record.path)
        removed.append(record.path.name)

    return removed


def _remove_artifact(snapshot: Path) -> None:
    """Delete a snapshot and its manifest. Only ever called for snapshot files."""
    if snapshot.parent.name not in {SNAPSHOT_DIR_NAME, WEEKLY_DIR_NAME}:
        raise SnapshotError("refusing to remove an artifact outside the snapshot directory")
    snapshot.unlink(missing_ok=True)
    Path(f"{snapshot}{MANIFEST_SUFFIX}").unlink(missing_ok=True)


def create_snapshot(
    database: str | os.PathLike[str],
    *,
    reason: str,
    policy: SnapshotPolicy | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
    coalesce: bool = False,
) -> SnapshotOutcome:
    """Publish one validated snapshot plus manifest, then apply retention.

    Returns ``skipped-unchanged`` when the logical generation did not move, so a
    repeated sync cannot grow the backup set. Any failure is returned (or raised)
    as a visible state; the source database and previous snapshots are untouched.
    """
    policy = policy or SnapshotPolicy()
    moment = now or _utc_now()
    source = normalize_path(database)
    if not source.is_file():
        raise SnapshotError("database does not exist; nothing to snapshot")

    target_directory = directory or snapshot_directory(source)
    generation = database_generation(source)

    records = load_snapshots(target_directory)
    previous = _latest([record for record in records if record.valid])
    if previous is not None and previous.manifest is not None:
        if previous.manifest.source_generation == generation:
            return SnapshotOutcome(status="skipped-unchanged", reason=reason)
        if (
            coalesce
            and previous.created_at is not None
            and (moment - previous.created_at) < coalescing_window(policy)
        ):
            # A burst of mutations: the newest version is still perfect, so pay
            # for one snapshot per window instead of one per row.
            return SnapshotOutcome(status="deferred-coalesced", reason=reason)
    elif coalesce:
        # No previous snapshot at all, but nothing has been written yet either:
        # the mutation hook must not manufacture a version for an empty change.
        return SnapshotOutcome(status="skipped-unchanged", reason=reason)

    destination = target_directory / _snapshot_name(source, moment)
    suffix = 0
    while destination.exists() or Path(f"{destination}{MANIFEST_SUFFIX}").exists():
        suffix += 1
        destination = target_directory / _snapshot_name(source, moment).replace(
            ".db", f"-{suffix}.db"
        )

    try:
        report: BackupReport = backup_database(source, destination, confirm_stopped=True)
    except (SQLiteBackupRestoreError, OSError) as exc:
        raise SnapshotError(
            f"snapshot failed for reason={reason}; source database and previous "
            f"snapshots are unchanged: {exc}"
        ) from exc

    manifest = SnapshotManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        created_at=moment.astimezone(timezone.utc).isoformat(),
        snapshot=destination.name,
        source=source.name,
        sha256=report.sha256,
        size_bytes=destination.stat().st_size,
        integrity_check=report.integrity_check,
        source_generation=generation,
        reason=reason,
        domains=count_domains(source),
        source_bytes=source.stat().st_size,
        schema_version_of_source=_user_schema_version(source),
    )
    _write_manifest(manifest, Path(f"{destination}{MANIFEST_SUFFIX}"))

    removed = apply_retention(target_directory, policy, now=moment)
    return SnapshotOutcome(
        status="created",
        reason=reason,
        manifest=manifest,
        removed=removed,
    )


def run_scheduled_snapshot(
    database: str | os.PathLike[str],
    *,
    policy: SnapshotPolicy | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> SnapshotOutcome:
    """Daily safety snapshot: create one when the database changed at all."""
    return create_snapshot(
        database,
        reason="scheduled-daily",
        policy=policy,
        directory=directory,
        now=now,
    )


def snapshot_after_sync(
    database: str | os.PathLike[str],
    *,
    policy: SnapshotPolicy | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> SnapshotOutcome:
    """Snapshot after a successful provider sync — or report a visible failure.

    Never raises: a backup failure must not undo data the sync already stored. The
    returned failure state is what makes ``silent success`` impossible.
    """
    return _guarded_snapshot("post-sync", database, policy=policy, directory=directory, now=now)


def snapshot_after_mutation(
    database: str | os.PathLike[str],
    *,
    policy: SnapshotPolicy | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> SnapshotOutcome:
    """Snapshot after a durable high-value mutation, honouring the coalescing window.

    Inside the window the snapshot is deferred (status ``deferred-coalesced``);
    the daily safety snapshot and the next sync close the gap, which is what keeps
    the documented RPO honest instead of promising a snapshot per row.
    """
    policy = policy or SnapshotPolicy()
    return _guarded_snapshot(
        "post-mutation",
        database,
        policy=policy,
        directory=directory,
        now=now,
        coalesce=True,
    )


def _guarded_snapshot(
    reason: str,
    database: str | os.PathLike[str],
    *,
    policy: SnapshotPolicy | None,
    directory: Path | None,
    now: datetime | None,
    coalesce: bool = False,
) -> SnapshotOutcome:
    try:
        return create_snapshot(
            database,
            reason=reason,
            policy=policy,
            directory=directory,
            now=now,
            coalesce=coalesce,
        )
    except (SnapshotError, OSError) as exc:
        return SnapshotOutcome(status="failed", reason=reason, error=str(exc))


def backup_health(
    directory: Path | None = None,
    *,
    policy: SnapshotPolicy | None = None,
    database: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
) -> BackupHealth:
    """Report freshness and trustworthiness of the snapshot set.

    ``degraded`` means the newest valid snapshot is older than the RPO target,
    ``failed`` means there is no trustworthy snapshot at all — in both cases the
    state is visible instead of being masked by a successful sync.
    """
    policy = policy or SnapshotPolicy()
    moment = now or _utc_now()
    target_directory = directory or snapshot_directory(database, create=False)

    records = load_snapshots(target_directory)
    valid = [record for record in records if record.valid]
    problems = [
        f"{record.path.name}: {record.problem}" for record in records if not record.valid
    ]
    previous = _latest(valid)

    age_hours: float | None = None
    last_at: str | None = None
    if previous is not None and previous.created_at is not None:
        last_at = previous.created_at.astimezone(timezone.utc).isoformat()
        age_hours = (moment - previous.created_at).total_seconds() / 3600.0

    stale = age_hours is None or age_hours > policy.rpo_hours
    if previous is None:
        status = "failed"
    elif stale:
        status = "degraded"
    elif problems:
        status = "partial"
    else:
        status = "healthy"

    return BackupHealth(
        status=status,
        snapshot_count=len(records),
        valid_count=len(valid),
        last_snapshot_at=last_at,
        last_snapshot_age_hours=round(age_hours, 3) if age_hours is not None else None,
        rpo_hours=policy.rpo_hours,
        stale=stale,
        problems=problems[:10],
    )


def verify_snapshot(database: str | os.PathLike[str], snapshot: Path) -> str:
    """Integrity check used by drills before a snapshot is treated as restorable."""
    assert_safe(database, purpose="snapshot verification")
    record = _record_for(snapshot)
    if not record.valid:
        raise SnapshotError(f"snapshot is not a valid restore candidate: {record.problem}")
    return check_sqlite_database(snapshot)


def _record_for(snapshot: Path) -> SnapshotRecord:
    for record in load_snapshots(snapshot.parent):
        if record.path == snapshot:
            return record
    return SnapshotRecord(path=snapshot, problem="manifest-missing")


def snapshot_cli(argv: Sequence[str] | None = None) -> int:
    """CLI: take a snapshot now (cron/daily) or print backup health."""
    import argparse

    parser = argparse.ArgumentParser(description="Automatic validated SQLite snapshots (#623)")
    parser.add_argument("action", choices=("snapshot", "health"))
    parser.add_argument("--database", default=None, help="default: configured DATABASE_PATH")
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--reason", default="manual")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from config.db_paths import production_database_path

    database = normalize_path(args.database) if args.database else production_database_path()
    directory = normalize_path(args.snapshot_dir) if args.snapshot_dir else None
    assert_safe(database, purpose="snapshot source", invariant="snapshot-source-safety")

    if args.action == "health":
        payload = backup_health(directory, database=database).as_dict()
    else:
        payload = create_snapshot(database, reason=args.reason, directory=directory).as_dict()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0 if payload.get("status") != "failed" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(snapshot_cli())
