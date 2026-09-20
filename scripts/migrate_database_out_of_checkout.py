#!/usr/bin/env python3
"""Move the dogfood SQLite database out of the Git checkout (#622/#624).

Why this exists
---------------
``database-path-safety`` default now points at the platform application-data
directory, so a fresh install never shares fate with a working tree. An existing
dogfood install keeps whatever ``DATABASE_PATH`` already says — usually the
repository root — and therefore needs one explicit, validated move.

What this command guarantees
----------------------------
* it reads the legacy source and never deletes, truncates or rewrites it;
* it copies through the validated #293 snapshot primitives (SQLite Backup API),
  so committed ``-wal`` pages travel with it — a plain file copy would lose them;
* it never chooses between two candidates: a non-empty target stops the run and
  prints both sides for the operator to decide;
* a snapshot of the source is published first, so the pre-migration state stays
  restorable even if a later step fails;
* failure at any step leaves the source readable and publishes no partial target;
* aggregate counts only — no personal rows in output, logs or dry-run.

Usage
-----
    # aggregate report, changes nothing
    python scripts/migrate_database_out_of_checkout.py --dry-run

    # stop every AI Trainer process first, then:
    python scripts/migrate_database_out_of_checkout.py --confirm-stopped
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.app_data import (
    APP_DATA_DIR_ENV,
    DATABASE_NAME,
    app_data_directory,
    legacy_repository_database_path,
)
from config.db_paths import (
    assert_operator_action_target,
    normalize_path,
    production_database_path,
)
from scripts.sqlite_backup_restore import (
    SQLiteBackupRestoreError,
    backup_database,
    check_sqlite_database,
)

# Domains whose preservation the issue requires proof of — shared with the
# automatic snapshot manifest so both agree on what "the data survived" means.
from data.durability_domains import KEY_DOMAINS  # noqa: E402  (path bootstrap above)

EXIT_OK = 0
EXIT_REFUSED = 2


class MigrationError(RuntimeError):
    """Operator-facing, fail-closed migration failure."""


@dataclass
class MigrationPlan:
    """What the command intends to do, computed before anything is written."""

    source: str
    target: str
    rollback: str
    source_counts: dict[str, int] = field(default_factory=dict)
    target_counts: dict[str, int] = field(default_factory=dict)
    source_bytes: int = 0
    repos: list[str] = field(default_factory=list)


@dataclass
class MigrationReport:
    action: str
    status: str
    source: str
    target: str
    rollback: str | None
    integrity_check: str | None
    sha256: str | None
    domains: dict[str, int] = field(default_factory=dict)
    source_preserved: bool = True
    notes: list[str] = field(default_factory=list)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def count_domains(database: str | os.PathLike[str]) -> dict[str, int]:
    """Aggregate per-domain row counts — never personal values."""
    path = normalize_path(database)
    if not path.is_file():
        return {}
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        present = _table_names(connection)
        return {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in KEY_DOMAINS
            if table in present
        }
    finally:
        connection.close()


def _attached_repositories(path: Path) -> list[str]:
    """Checkout roots the path lives in, if any (reported, never guessed around)."""
    import subprocess

    found: list[str] = []
    resolved = normalize_path(path)
    for candidate in dict.fromkeys([resolved.parent, Path.cwd()]):
        if not candidate.exists():
            continue
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
            break
        if completed.returncode != 0 or not completed.stdout.strip():
            continue
        root = normalize_path(completed.stdout.strip())
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        found.append(str(root))
    return found


def _require_existing_source(source: Path) -> Path:
    if source.is_symlink():
        raise MigrationError(f"source must not be a symbolic link: {source.name}")
    resolved = normalize_path(source)
    if not resolved.is_file():
        raise MigrationError(f"source database does not exist: {resolved}")
    try:
        check_sqlite_database(resolved)
    except SQLiteBackupRestoreError as exc:
        raise MigrationError(f"source database failed validation: {exc}") from exc
    return resolved


def _require_distinct(source: Path, target: Path, *, target_as_given: Path | None = None) -> None:
    given = target_as_given if target_as_given is not None else target
    if Path(os.fspath(given)).is_symlink():
        raise MigrationError(
            "target must not be a symbolic link; refusing to publish through an alias"
        )
    if source == target:
        raise MigrationError(
            "source and target resolve to the same file; refusing to migrate in place"
        )
    if target.exists() and source.exists():
        try:
            if os.path.samefile(source, target):
                raise MigrationError(
                    "target is a hardlink alias of the source; refusing to migrate"
                )
        except OSError as exc:  # pragma: no cover - defensive
            raise MigrationError(f"could not compare source and target: {exc}") from exc


def build_plan(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    rollback: str | os.PathLike[str] | None = None,
    timestamp: str | None = None,
) -> MigrationPlan:
    """Validate both sides and describe the move without writing anything."""
    source_path = normalize_path(source)
    raw_target = Path(os.fspath(target)).expanduser()
    target_path = normalize_path(target)

    source_path = _require_existing_source(source_path)
    _require_distinct(source_path, target_path, target_as_given=raw_target)

    source_counts = count_domains(source_path)
    if not any(source_counts.values()):
        raise MigrationError(
            "source database contains no rows in the key domains; refusing to treat an "
            "empty file as a migration"
        )

    target_counts: dict[str, int] = {}
    if target_path.exists():
        if not target_path.is_file() or target_path.is_symlink():
            raise MigrationError(f"target is not a regular file: {target_path}")
        target_counts = count_domains(target_path)

    stamp = timestamp or _utc_stamp()
    rollback_path = normalize_path(
        rollback or Path(f"{target_path}.pre-migration-{stamp}.db")
    )
    if rollback_path in {source_path, target_path}:
        raise MigrationError("rollback output must differ from source and target")

    return MigrationPlan(
        source=str(source_path),
        target=str(target_path),
        rollback=str(rollback_path),
        source_counts=source_counts,
        target_counts=target_counts,
        source_bytes=source_path.stat().st_size,
        repos=_attached_repositories(source_path),
    )


def _utc_stamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _require_no_ambiguous_target(plan: MigrationPlan) -> None:
    """Never pick a winner between two databases that both hold data."""
    populated = {name: count for name, count in plan.target_counts.items() if count}
    if populated:
        details = ", ".join(f"{name}={count}" for name, count in sorted(populated.items()))
        raise MigrationError(
            "target already contains data; refusing to choose between two databases. "
            f"target domains: {details}. Inspect both sides yourself, then move or "
            "remove the target deliberately (this command never deletes a database)."
        )


def _require_operator_confirmation(plan: MigrationPlan, *, confirm_stopped: bool) -> None:
    if not confirm_stopped:
        raise MigrationError(
            "refusing to migrate without --confirm-stopped; stop every AI Trainer "
            "process that can write the source database first"
        )
    print("⚠️  Moving the working database out of the Git checkout")
    print(f"   source (kept as-is): {plan.source}")
    print(f"   target:              {plan.target}")
    print(f"   rollback snapshot:   {plan.rollback}")


def migrate_database(
    source: str | os.PathLike[str],
    target: str | os.PathLike[str],
    *,
    confirm_stopped: bool,
    rollback: str | os.PathLike[str] | None = None,
    dry_run: bool = False,
    allow_empty_target: bool = False,
    timestamp: str | None = None,
) -> MigrationReport:
    """Publish a validated copy of ``source`` at ``target``; never delete either."""
    plan = build_plan(source, target, rollback=rollback, timestamp=timestamp)

    if dry_run:
        return MigrationReport(
            action="migrate",
            status="dry-run",
            source=plan.source,
            target=plan.target,
            rollback=None,
            integrity_check=None,
            sha256=None,
            domains=plan.source_counts,
            notes=[
                f"source size: {plan.source_bytes} bytes",
                *(
                    [f"target already has data in: {', '.join(sorted(plan.target_counts))}"]
                    if any(plan.target_counts.values())
                    else []
                ),
                *(
                    [f"source lives inside a Git checkout: {plan.repos[0]}"]
                    if plan.repos
                    else []
                ),
            ],
        )

    _require_operator_confirmation(plan, confirm_stopped=confirm_stopped)
    _require_no_ambiguous_target(plan)

    if normalize_path(plan.target).exists() and not allow_empty_target:
        raise MigrationError(
            "target already exists; pass --allow-empty-target only when you have "
            "verified it holds no data this migration would hide"
        )

    try:
        rollback_report = backup_database(
            plan.source,
            plan.rollback,
            confirm_stopped=True,
        )
    except SQLiteBackupRestoreError as exc:
        raise MigrationError(f"could not publish the rollback snapshot: {exc}") from exc

    try:
        published = backup_database(
            plan.source,
            plan.target,
            confirm_stopped=True,
        )
    except SQLiteBackupRestoreError as exc:
        raise MigrationError(
            "migration failed while publishing the target; source database is "
            f"untouched and the pre-migration snapshot is at {plan.rollback}: {exc}"
        ) from exc

    target_counts = count_domains(plan.target)
    missing = [
        table
        for table, count in plan.source_counts.items()
        if count and target_counts.get(table, 0) < count
    ]
    if missing:
        raise MigrationError(
            "target is missing rows for: "
            f"{', '.join(sorted(missing))}; source is untouched and the pre-migration "
            f"snapshot is at {plan.rollback}. Do not delete anything yet."
        )

    return MigrationReport(
        action="migrate",
        status="migrated",
        source=plan.source,
        target=plan.target,
        rollback=str(plan.rollback),
        integrity_check=published.integrity_check,
        sha256=published.sha256,
        domains=target_counts,
        notes=[
            f"rollback snapshot sha256: {rollback_report.sha256}",
            "source database left in place; delete it only after you verified the "
            "application runs against the new path",
        ],
    )


def update_env_file(
    env_path: str | os.PathLike[str],
    database_path: str,
    *,
    dry_run: bool = False,
) -> str:
    """Point an explicit ``DATABASE_PATH`` in a ``.env`` file at the new location.

    An explicit ``DATABASE_PATH`` outranks the new default, so a dogfood install
    that pins the repository path keeps pointing there until this line is updated.
    Comments, ordering and every other line are preserved; a timestamped backup of
    the previous file is written before the change.
    """
    path = Path(env_path).expanduser()
    if not path.is_file():
        raise MigrationError(f"env file does not exist: {path}")

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    replacement = f"DATABASE_PATH={database_path}\n"
    updated: list[str] = []
    found = False
    for line in lines:
        if line.lstrip().startswith("DATABASE_PATH="):
            prefix = line[: len(line) - len(line.lstrip())]
            updated.append(f"{prefix}{replacement}")
            found = True
        else:
            updated.append(line)

    if not found:
        if updated and not updated[-1].endswith("\n"):
            updated[-1] = f"{updated[-1]}\n"
        updated.append(f"\n# #624: database moved out of the Git checkout\n{replacement}")

    if dry_run:
        return "dry-run"

    mode = path.stat().st_mode
    backup = path.with_name(f"{path.name}.pre-migration-{_utc_stamp()}")
    backup.write_text(original, encoding="utf-8")
    os.chmod(backup, mode)
    path.write_text("".join(updated), encoding="utf-8")
    os.chmod(path, mode)
    return str(backup)


def resolve_default_target() -> Path:
    """Application-data target, refusing a location inside a checkout."""
    directory = app_data_directory()
    if directory is None:
        raise MigrationError(
            f"no application-data directory is resolvable; set {APP_DATA_DIR_ENV} "
            "to the directory that should hold the runtime database"
        )
    return assert_operator_action_target(
        directory / DATABASE_NAME,
        purpose="the database migration target",
        invariant="migration-target-must-leave-the-checkout",
    )


def resolve_default_source() -> Path:
    """Legacy location: the configured path when it is a checkout artifact."""
    configured = production_database_path()
    if configured.is_file():
        return configured
    return normalize_path(legacy_repository_database_path())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None, help="legacy database (default: configured path)")
    parser.add_argument("--target", default=None, help="new database location (default: app data)")
    parser.add_argument("--rollback-output", default=None, help="pre-migration snapshot path")
    parser.add_argument("--dry-run", action="store_true", help="report aggregates only")
    parser.add_argument("--confirm-stopped", action="store_true")
    parser.add_argument(
        "--allow-empty-target",
        action="store_true",
        help="permit publishing over an existing target that holds no data",
    )
    parser.add_argument(
        "--update-env",
        default=None,
        metavar="PATH",
        help="also point DATABASE_PATH in this env file at the new location",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = Path(args.source) if args.source else resolve_default_source()
        target = Path(args.target) if args.target else resolve_default_target()
        report = migrate_database(
            source,
            target,
            confirm_stopped=args.confirm_stopped,
            rollback=args.rollback_output,
            dry_run=args.dry_run,
            allow_empty_target=args.allow_empty_target,
        )
    except (MigrationError, SQLiteBackupRestoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    if args.update_env:
        try:
            env_backup = update_env_file(args.update_env, report.target, dry_run=args.dry_run)
        except MigrationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        report.notes.append(
            f"env file updated; previous version kept at {env_backup}"
            if env_backup != "dry-run"
            else "env file would be updated with the new DATABASE_PATH"
        )

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_report(report)

    if report.status == "dry-run":
        print("\nDry run only — nothing was written. Stop every AI Trainer process, then re-run with --confirm-stopped.")
    return EXIT_OK


def _print_report(report: MigrationReport) -> None:
    print(f"\n📦 {report.status}")
    print(f"   source: {report.source}")
    print(f"   target: {report.target}")
    if report.rollback:
        print(f"   rollback: {report.rollback}")
    if report.integrity_check:
        print(f"   integrity: {report.integrity_check}")
    if report.domains:
        print("   domains: " + ", ".join(f"{k}={v}" for k, v in sorted(report.domains.items())))
    for note in report.notes:
        print(f"   • {note}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
