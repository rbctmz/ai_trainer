#!/usr/bin/env python3
"""Create and restore validated offline snapshots of the AI Trainer SQLite DB."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


class SQLiteBackupRestoreError(RuntimeError):
    """Safe, operator-facing backup/restore failure."""


@dataclass(frozen=True)
class BackupReport:
    action: str
    database: str
    artifact: str
    integrity_check: str
    sha256: str


@dataclass(frozen=True)
class RestoreReport:
    action: str
    database: str
    artifact: str
    integrity_check: str
    sha256: str
    rollback: str | None


def _require_stopped_confirmation(confirm_stopped: bool) -> None:
    if not confirm_stopped:
        raise SQLiteBackupRestoreError(
            "refusing to continue without --confirm-stopped; stop every AI "
            "Trainer process that can write this database first"
        )


def _existing_database(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise SQLiteBackupRestoreError(f"{label} must not be a symbolic link: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SQLiteBackupRestoreError(f"{label} does not exist: {candidate}") from exc
    if not resolved.is_file():
        raise SQLiteBackupRestoreError(f"{label} is not a regular file: {resolved}")
    return resolved


def _destination(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink():
        raise SQLiteBackupRestoreError(f"{label} must not be a symbolic link: {candidate}")
    return candidate.resolve(strict=False)


def _require_different(first: Path, second: Path, *, labels: str) -> None:
    if first == second:
        raise SQLiteBackupRestoreError(f"{labels} must be different paths")


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def check_sqlite_database(path: str | Path) -> str:
    """Return ``ok`` only for a readable SQLite database with full integrity."""
    database = _existing_database(path, label="database")
    try:
        conn = _readonly_connection(database)
        try:
            rows = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise SQLiteBackupRestoreError(
            f"integrity check failed for {database}: {exc}"
        ) from exc
    if rows != ["ok"]:
        details = "; ".join(rows) if rows else "no result"
        raise SQLiteBackupRestoreError(
            f"integrity check failed for {database}: {details}"
        )
    return "ok"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temporary_file(destination: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(descriptor)
    temporary = Path(raw_path)
    temporary.chmod(0o600)
    return temporary


def _prepare_temporary_destination(destination: Path, *, label: str) -> Path:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        return _temporary_file(destination)
    except OSError as exc:
        raise SQLiteBackupRestoreError(
            f"could not prepare {label} {destination}: {exc}"
        ) from exc


def _copy_sqlite(source: Path, temporary: Path) -> None:
    try:
        with closing(_readonly_connection(source)) as source_conn:
            with closing(sqlite3.connect(temporary)) as destination_conn:
                source_conn.backup(destination_conn)
                destination_conn.commit()
    except sqlite3.Error as exc:
        raise SQLiteBackupRestoreError(
            f"SQLite snapshot failed for {source}: {exc}"
        ) from exc
    check_sqlite_database(temporary)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_new_artifact(
    temporary: Path,
    destination: Path,
    *,
    label: str,
) -> None:
    """Publish a new artifact atomically without ever replacing another file."""
    _fsync_file(temporary)
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise SQLiteBackupRestoreError(
            f"{label} already exists: {destination}"
        ) from exc
    _fsync_directory(destination.parent)


def _replace_artifact(temporary: Path, destination: Path) -> None:
    _fsync_file(temporary)
    os.replace(temporary, destination)


def _replace_database(temporary: Path, database: Path) -> None:
    """Seam kept separate so the fail-before-replace contract is testable."""
    _replace_artifact(temporary, database)


def _snapshot_to_output(
    source: Path,
    output: Path,
    *,
    label: str = "backup output",
) -> tuple[str, str]:
    _require_different(source, output, labels="database and backup output")
    if output.exists() or output.is_symlink():
        raise SQLiteBackupRestoreError(f"{label} already exists: {output}")

    check_sqlite_database(source)
    temporary = _prepare_temporary_destination(output, label=label)
    try:
        _copy_sqlite(source, temporary)
        _publish_new_artifact(temporary, output, label=label)
    except SQLiteBackupRestoreError:
        raise
    except OSError as exc:
        raise SQLiteBackupRestoreError(
            f"could not publish {label} {output}: {exc}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return check_sqlite_database(output), _sha256(output)


def backup_database(
    database: str | Path,
    output: str | Path,
    *,
    confirm_stopped: bool,
) -> BackupReport:
    """Create one validated, non-overwriting SQLite snapshot."""
    _require_stopped_confirmation(confirm_stopped)
    database_path = _existing_database(database, label="database")
    output_path = _destination(output, label="backup output")
    integrity, digest = _snapshot_to_output(database_path, output_path)
    return BackupReport(
        action="backup",
        database=str(database_path),
        artifact=str(output_path),
        integrity_check=integrity,
        sha256=digest,
    )


def _default_rollback_path(database: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return database.with_name(f"{database.name}.pre-restore-{timestamp}.db")


def _sidecar_quarantine_path(sidecar: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{sidecar.name}.",
        suffix=".pre-restore-sidecar",
        dir=str(sidecar.parent),
    )
    os.close(descriptor)
    quarantine = Path(raw_path)
    quarantine.unlink()
    return quarantine


def _quarantine_sidecars(database: Path) -> list[tuple[Path, Path]]:
    quarantined: list[tuple[Path, Path]] = []
    try:
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(f"{database}{suffix}")
            if not sidecar.exists() and not sidecar.is_symlink():
                continue
            quarantine = _sidecar_quarantine_path(sidecar)
            os.replace(sidecar, quarantine)
            quarantined.append((sidecar, quarantine))
        _fsync_directory(database.parent)
    except OSError as exc:
        recovery_errors: list[str] = []
        for sidecar, quarantine in reversed(quarantined):
            try:
                os.replace(quarantine, sidecar)
            except OSError as recovery_exc:
                recovery_errors.append(f"{sidecar}: {recovery_exc}")
        _fsync_directory(database.parent)
        recovery = (
            f"; recovery failures: {'; '.join(recovery_errors)}"
            if recovery_errors
            else ""
        )
        raise SQLiteBackupRestoreError(
            f"could not quarantine stale SQLite sidecars for {database}: {exc}{recovery}"
        ) from exc
    return quarantined


def _restore_quarantined_sidecars(
    quarantined: list[tuple[Path, Path]],
    *,
    database: Path,
) -> None:
    failures: list[str] = []
    for sidecar, quarantine in reversed(quarantined):
        try:
            os.replace(quarantine, sidecar)
        except OSError as exc:
            failures.append(f"{sidecar}: {exc}")
    _fsync_directory(database.parent)
    if failures:
        raise SQLiteBackupRestoreError(
            "database publication failed and stale sidecar recovery was "
            f"incomplete for {database}: {'; '.join(failures)}"
        )


def _delete_quarantined_sidecars(
    quarantined: list[tuple[Path, Path]],
    *,
    database: Path,
) -> None:
    for _sidecar, quarantine in quarantined:
        quarantine.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{database}{suffix}").unlink(missing_ok=True)
    _fsync_directory(database.parent)


def restore_database(
    backup: str | Path,
    database: str | Path,
    *,
    confirm_stopped: bool,
    rollback_output: str | Path | None = None,
) -> RestoreReport:
    """Restore a validated snapshot, preserving an existing target first."""
    _require_stopped_confirmation(confirm_stopped)
    backup_path = _existing_database(backup, label="backup")
    database_path = _destination(database, label="database")
    _require_different(backup_path, database_path, labels="backup and database")
    check_sqlite_database(backup_path)

    if database_path.exists() and not database_path.is_file():
        raise SQLiteBackupRestoreError(
            f"database is not a regular file: {database_path}"
        )

    temporary = _prepare_temporary_destination(database_path, label="database")
    rollback_path: Path | None = None
    quarantined: list[tuple[Path, Path]] = []
    try:
        _copy_sqlite(backup_path, temporary)

        if database_path.exists():
            current_database = _existing_database(database_path, label="database")
            rollback_path = _destination(
                rollback_output or _default_rollback_path(database_path),
                label="rollback output",
            )
            _require_different(
                rollback_path,
                database_path,
                labels="rollback output and database",
            )
            _require_different(
                rollback_path,
                backup_path,
                labels="rollback output and backup",
            )
            _snapshot_to_output(
                current_database,
                rollback_path,
                label="rollback output",
            )
        elif rollback_output is not None:
            raise SQLiteBackupRestoreError(
                "--rollback-output is only valid when the target database exists"
            )

        quarantined = _quarantine_sidecars(database_path)
        try:
            _replace_database(temporary, database_path)
        except OSError as exc:
            _restore_quarantined_sidecars(
                quarantined,
                database=database_path,
            )
            raise SQLiteBackupRestoreError(
                f"database replace failed for {database_path}: {exc}"
            ) from exc
        try:
            _delete_quarantined_sidecars(
                quarantined,
                database=database_path,
            )
            integrity = check_sqlite_database(database_path)
            digest = _sha256(database_path)
        except (SQLiteBackupRestoreError, OSError) as exc:
            rollback_hint = str(rollback_path) if rollback_path is not None else "none"
            raise SQLiteBackupRestoreError(
                "database was replaced but restore finalization failed for "
                f"{database_path}: {exc}; keep the service stopped; "
                f"rollback={rollback_hint}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)

    return RestoreReport(
        action="restore",
        database=str(database_path),
        artifact=str(backup_path),
        integrity_check=integrity,
        sha256=digest,
        rollback=str(rollback_path) if rollback_path is not None else None,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    default_database = os.environ.get("DATABASE_PATH", "ai_trainer.db")

    backup_parser = subparsers.add_parser("backup", help="create a validated snapshot")
    backup_parser.add_argument("--database", default=default_database)
    backup_parser.add_argument("--output", required=True)
    backup_parser.add_argument("--confirm-stopped", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="restore a validated snapshot")
    restore_parser.add_argument("--database", default=default_database)
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--rollback-output")
    restore_parser.add_argument("--confirm-stopped", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "backup":
            report = backup_database(
                args.database,
                args.output,
                confirm_stopped=args.confirm_stopped,
            )
        else:
            report = restore_database(
                args.backup,
                args.database,
                confirm_stopped=args.confirm_stopped,
                rollback_output=args.rollback_output,
            )
    except (SQLiteBackupRestoreError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
