"""Explicit operator writes and disposable scratch targets for legacy tools."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
from functools import wraps
from pathlib import Path
import os
import sqlite3
import sys
from typing import Iterator

from config.database_paths import ScratchPathError
from config.maintenance_guard import validate_maintenance_target


@contextmanager
def writable_target(database_path: str | Path | None = None, *, apply: bool = False,
                    confirm_working_database: bool = False, confirm_stopped: bool = False,
                    backup: str | Path | None = None) -> Iterator[Path]:
    if database_path is not None:
        if not apply:
            raise ScratchPathError('operator_confirmation_required', purpose='bootstrap')
        yield validate_maintenance_target(database_path, apply=True, confirmed=confirm_working_database,
                                          stopped=confirm_stopped, backup=backup)
        return
    from scripts.scratch_pytest import bootstrap_pytest
    from scripts.scratch_runtime import ScratchScope
    parent = bootstrap_pytest()
    scope = ScratchScope.create(parent=parent.root / 'tmp')
    try:
        target = scope.validate_target(scope.root / 'synthetic.db', purpose='bootstrap')
        if target is None:
            raise ScratchPathError('scratch_identity_unknown', purpose='bootstrap')
        yield target
    finally:
        scope.cleanup()


@contextmanager
def _operator_output(database_path):
    from scripts.scratch_runtime import scope_from_environment
    if database_path is not None and scope_from_environment() is None:
        # Legacy generators print row-shaped data; keep operator output aggregate.
        with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink):
            yield
    else:
        yield


_GENERATOR_KEY = object()


class _BoundGeneratorTarget:
    def __init__(self, path, key):
        if key is not _GENERATOR_KEY:
            raise ScratchPathError('operator_confirmation_required', purpose='bootstrap')
        self.path = path


def require_generator_target(target):
    """Reject direct calls to a generator body with an unvalidated path."""
    if not isinstance(target, _BoundGeneratorTarget):
        raise ScratchPathError('operator_confirmation_required', purpose='bootstrap')
    return target.path


def isolated_generator(function):
    @wraps(function)
    def run(database_path=None, *, apply=False, confirm_working_database=False, confirm_stopped=False, backup=None):
        with writable_target(database_path, apply=apply, confirm_working_database=confirm_working_database,
                             confirm_stopped=confirm_stopped, backup=backup) as target:
            with _operator_output(database_path):
                return function(_BoundGeneratorTarget(target, _GENERATOR_KEY))
    return run


def generator_cli(functions: tuple, argv: list[str] | None = None, *, scratch_prelude: tuple = ()) -> int:
    parser = argparse.ArgumentParser(description='Synthetic generator / explicit offline operator action')
    parser.add_argument('--database')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-working-database', action='store_true')
    parser.add_argument('--confirm-stopped', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args(argv)
    try:
        if args.database is not None and not args.apply:
            target = validate_maintenance_target(args.database, apply=False)
            with sqlite3.connect(f'{target.as_uri()}?mode=ro', uri=True) as conn:
                count = conn.execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table'").fetchone()[0]
            print(f'Read-only preview: {count} tables')
            return 0
        with writable_target(args.database, apply=args.apply, confirm_working_database=args.confirm_working_database,
                             confirm_stopped=args.confirm_stopped, backup=args.backup) as target:
            with _operator_output(args.database):
                if args.database is None:
                    for function in scratch_prelude:
                        function.__wrapped__(_BoundGeneratorTarget(target, _GENERATOR_KEY))
                for function in functions:
                    function.__wrapped__(_BoundGeneratorTarget(target, _GENERATOR_KEY))
            if args.database is not None:
                print('Операция завершена')
        return 0
    except (ScratchPathError, FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc) if isinstance(exc, ScratchPathError) else 'scratch_identity_unknown: bootstrap', file=sys.stderr)
        return 2
