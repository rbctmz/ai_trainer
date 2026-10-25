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
import unicodedata
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

if __package__ in {None, ""}:  # direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database_paths import DatabasePathError  # noqa: E402


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
    try:
        temporary.chmod(0o600)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _prepare_temporary_destination(
    destination: Path, *, label: str, private_parent: bool = False,
) -> Path:
    try:
        destination.parent.mkdir(
            parents=True, exist_ok=True, mode=0o700 if private_parent else 0o777,
        )
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
    validator: Callable[[Path], None] | None = None,
    private_parent: bool = False,
) -> tuple[str, str]:
    _require_different(source, output, labels="database and backup output")
    if output.exists() or output.is_symlink():
        raise SQLiteBackupRestoreError(f"{label} already exists: {output}")

    check_sqlite_database(source)
    temporary = _prepare_temporary_destination(output, label=label, private_parent=private_parent)
    try:
        _copy_sqlite(source, temporary)
        if validator is not None:
            validator(temporary)
        _publish_new_artifact(temporary, output, label=label)
    except SQLiteBackupRestoreError:
        raise
    except OSError as exc:
        raise SQLiteBackupRestoreError(
            f"could not publish {label} {output}: {exc}"
        ) from exc
    finally:
        _cleanup_relocation_temporary(temporary)
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
    private_parent: bool = False,
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

    temporary = _prepare_temporary_destination(
        database_path, label="database", private_parent=private_parent,
    )
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


class DatabaseRelocationError(SQLiteBackupRestoreError):
    """Named refusal; no SQLite row values or driver diagnostics in CLI output."""


def _present(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _sqlite_family(path: Path) -> tuple[Path, ...]:
    return tuple(Path(str(path) + suffix) for suffix in ('', '-wal', '-shm', '-journal'))


def _relocation_endpoint(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise DatabaseRelocationError('absolute_path_required')
    if path.is_symlink():
        raise DatabaseRelocationError('symlink_endpoint')
    return path.resolve(strict=False)


def _outside_checkout(path: Path) -> None:
    # Follow physical parents, including aliases into linked worktrees. A .git
    # marker is sufficient to reject; no need to read possibly untrusted gitdir.
    physical_parent = path.resolve(strict=False).parent
    if any(_present(parent / '.git') for parent in (physical_parent, *physical_parent.parents)):
        raise DatabaseRelocationError('output_inside_checkout')


def _empty_output_family(path: Path, *, label: str) -> None:
    if any(_present(member) for member in _sqlite_family(path)):
        raise DatabaseRelocationError(f'{label}_exists')


def _future_alias(first: Path, second: Path) -> bool:
    """Native parent identity plus conservative names for not-yet-created files."""
    def anchor(path: Path) -> tuple[Path, str]:
        tail = [path.name]
        parent = path.parent
        while not _present(parent):
            tail.insert(0, parent.name)
            parent = parent.parent
        key = unicodedata.normalize('NFC', '/'.join(tail)).casefold()
        return parent, key

    first_parent, first_tail = anchor(first)
    second_parent, second_tail = anchor(second)
    return first_tail == second_tail and first_parent.samefile(second_parent)


def _relocation_paths(
    source: str | Path, target: str | Path, rollback: str | Path | None,
) -> tuple[Path, Path, Path | None]:
    paths = [_relocation_endpoint(value) for value in (source, target)]
    if rollback is not None:
        paths.append(_relocation_endpoint(rollback))
    families = [_sqlite_family(path) for path in paths]
    for index, family in enumerate(families):
        for other in families[index + 1:]:
            for first in family:
                for second in other:
                    # Case-only ambiguity is refused even on case-sensitive FS;
                    # casefold is conservative, not proof of native identity.
                    if _future_alias(first, second) or (
                        _present(first) and _present(second) and first.samefile(second)
                    ):
                        raise DatabaseRelocationError('endpoint_namespace_overlap')
    for member in families[0]:
        if member.is_symlink():
            raise DatabaseRelocationError('symlink_endpoint')
    for path in paths[1:]:
        _outside_checkout(path)
    _empty_output_family(paths[1], label='target')
    if len(paths) == 3:
        _empty_output_family(paths[2], label='rollback')
    if not _present(paths[0]):
        raise DatabaseRelocationError('source_missing')
    if not paths[0].is_file():
        raise DatabaseRelocationError('source_not_file')
    return paths[0], paths[1], paths[2] if len(paths) == 3 else None


def _typed_row(row: Sequence[object]) -> bytes:
    """Unambiguous SQLite storage-class encoding, including raw TEXT and BLOB."""
    digest = hashlib.sha256()
    for value in row:
        if value is None:
            tag, data = b'n', b''
        elif isinstance(value, int):
            tag, data = b'i', str(value).encode('ascii')
        elif isinstance(value, float):
            tag, data = b'f', value.hex().encode('ascii')
        elif isinstance(value, str):
            tag, data = b't', value.encode('utf-8')
        elif isinstance(value, bytes):
            tag, data = b'b', value
        else:
            raise DatabaseRelocationError('unsupported_sqlite_value')
        digest.update(tag + len(data).to_bytes(8, 'big') + data)
    return digest.digest()


def inspect_relocation_database(path: Path) -> dict:
    """Fingerprint one readonly transaction; never return personal row contents.

    Sorted row hashes form a multiset, preserving duplicate rows and SQLite
    types. Catalog SQL, identities and raw JSON are hashed without rewriting.
    Virtual/shadow tables are refused rather than partially compared.
    """
    try:
        with closing(_readonly_connection(path)) as conn:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA trusted_schema=OFF')
            conn.execute('BEGIN')
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise DatabaseRelocationError('source_integrity_failed')
            catalog = conn.execute(
                'SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name'
            ).fetchall()
            table_list = conn.execute('PRAGMA main.table_list').fetchall()
            if not table_list or any(row[2] not in ('table', 'view') for row in table_list):
                raise DatabaseRelocationError('unsupported_sqlite_object')
            columns = conn.execute('PRAGMA table_info(activities)').fetchall()
            by_name = {row[1]: row for row in columns}
            pk = [row for row in columns if row[5]]
            if (
                not any(row[0] == 'table' and row[1] == 'activities' for row in catalog)
                or not {'activity_id', 'date', 'sport', 'duration_minutes'} <= by_name.keys()
                or len(pk) != 1 or pk[0][1] != 'activity_id'
                or pk[0][2].upper() != 'TEXT'
            ):
                raise DatabaseRelocationError('unsupported_source_schema')
            tables = {}
            for object_type, name, _, _ in catalog:
                if object_type not in ('table', 'index', 'view', 'trigger'):
                    raise DatabaseRelocationError('unsupported_sqlite_object')
                if object_type != 'table':
                    continue
                identifier = '"' + name.replace('"', '""') + '"'
                rows = sorted(_typed_row(row) for row in conn.execute(f'SELECT * FROM {identifier}'))
                tables[name] = {
                    'rows': len(rows), 'sha256': hashlib.sha256(b''.join(rows)).hexdigest(),
                }
            return {
                'integrity_check': 'ok',
                'schema_sha256': hashlib.sha256(b''.join(_typed_row(row) for row in catalog)).hexdigest(),
                'user_version': conn.execute('PRAGMA user_version').fetchone()[0],
                'application_id': conn.execute('PRAGMA application_id').fetchone()[0],
                'encoding': conn.execute('PRAGMA encoding').fetchone()[0],
                'tables': tables,
            }
    except sqlite3.Error as exc:
        raise DatabaseRelocationError('source_integrity_failed') from exc
    except UnicodeError as exc:
        raise DatabaseRelocationError('unsupported_sqlite_value') from exc


def _verify_relocation_copy(path: Path, expected: dict) -> None:
    if inspect_relocation_database(path) != expected:
        raise DatabaseRelocationError('logical_verification_failed')


def _cleanup_relocation_temporary(path: Path) -> None:
    # These unique mkstemp names belong to this operation, never to endpoints.
    for member in _sqlite_family(path):
        member.unlink(missing_ok=True)


def migrate_database(
    source: str | Path,
    target: str | Path,
    *,
    rollback_output: str | Path | None = None,
    apply: bool = False,
    confirm_stopped: bool = False,
) -> dict:
    """Plan or copy an offline store; never activate it or modify configuration.

    Operator attestation is required for apply. It cannot prevent an external
    writer; source rechecks detect changes but do not replace quiescence.
    """
    report = {
        'status': 'blocked', 'source': str(source), 'target': str(target),
        'rollback_output': str(rollback_output) if rollback_output is not None else None,
        'configuration_changed': False, 'reason': None, 'validation': None,
    }
    try:
        if apply and not confirm_stopped:
            raise DatabaseRelocationError('stopped_confirmation_required')
        if apply and rollback_output is None:
            raise DatabaseRelocationError('rollback_output_required')
        source_path, target_path, rollback_path = _relocation_paths(source, target, rollback_output)
        report.update(source=str(source_path), target=str(target_path),
                      rollback_output=str(rollback_path) if rollback_path is not None else None)
        expected = inspect_relocation_database(source_path)
        report['validation'] = expected
        if not apply:
            report['status'] = 'planned'
            return report
        # Recheck the entire triple immediately before the first write.
        _relocation_paths(source, target, rollback_output)
        assert rollback_path is not None  # required above for apply

        def validate_rollback(temporary: Path) -> None:
            _verify_relocation_copy(temporary, expected)
            _verify_relocation_copy(source_path, expected)
            _outside_checkout(rollback_path)
            _empty_output_family(rollback_path, label='rollback')

        _snapshot_to_output(source_path, rollback_path, label='rollback output',
                            validator=validate_rollback, private_parent=True)
        _outside_checkout(target_path)
        _empty_output_family(target_path, label='target')
        temporary = _prepare_temporary_destination(target_path, label='migration target', private_parent=True)
        try:
            _copy_sqlite(rollback_path, temporary)
            _verify_relocation_copy(temporary, expected)
            if inspect_relocation_database(source_path) != expected:
                raise DatabaseRelocationError('source_changed')
            _outside_checkout(target_path)
            _empty_output_family(target_path, label='target')
            _publish_new_artifact(temporary, target_path, label='migration target')
        finally:
            _cleanup_relocation_temporary(temporary)
        report['status'] = 'copied_not_activated'
    except DatabaseRelocationError as exc:
        report['reason'] = str(exc)
    except (SQLiteBackupRestoreError, OSError, ValueError, RuntimeError):
        # Includes permission/space/URI/path-resolution errors; raw exceptions
        # may contain private SQL text. Existing backup/restore diagnostics stay.
        report['reason'] = 'relocation_io_failed'
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="create a validated snapshot")
    backup_parser.add_argument("--database", default=None)
    backup_parser.add_argument("--output", required=True)
    backup_parser.add_argument("--confirm-stopped", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="restore a validated snapshot")
    restore_parser.add_argument("--database", default=None)
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--rollback-output")
    restore_parser.add_argument("--confirm-stopped", action="store_true")
    migrate_parser = subparsers.add_parser("migrate", help="plan or copy an offline database; never activate")
    migrate_parser.add_argument("--source", required=True)
    migrate_parser.add_argument("--target", required=True)
    migrate_parser.add_argument("--rollback-output")
    migrate_parser.add_argument("--apply", action="store_true")
    migrate_parser.add_argument("--confirm-stopped", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "migrate":
        result = migrate_database(
            args.source, args.target, rollback_output=args.rollback_output,
            apply=args.apply, confirm_stopped=args.confirm_stopped,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 2 if result['status'] == 'blocked' else 0
    try:
        private_parent = False
        if args.database is None:
            # Lazy: explicit offline paths still work when runtime preflight refuses.
            from config.settings import Settings
            args.database = Settings.runtime_database_path()
            private_parent = (
                Settings._DATABASE_PATHS.origin == "platform"
                and args.database == Settings._DATABASE_PATHS.real
            )
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
                private_parent=private_parent,
            )
    except (SQLiteBackupRestoreError, OSError, DatabasePathError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
