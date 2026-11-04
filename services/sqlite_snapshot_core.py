"""Shared SQLite snapshot primitives; no Settings or operator side effects."""
from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
from typing import Sequence


class SnapshotInspectionError(RuntimeError):
    """Named integrity or unsupported-schema refusal."""


def readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def copy_sqlite(source: Path, target: Path, *, connect=readonly_connection) -> None:
    with closing(connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst, pages=256, sleep=0.01)
        dst.commit()


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
            raise SnapshotInspectionError('unsupported_sqlite_value')
        digest.update(tag + len(data).to_bytes(8, 'big') + data)
    return digest.digest()


def inspect_database(path: Path, *, connect=readonly_connection) -> dict:
    """Fingerprint one readonly transaction; never return personal row contents.

    Sorted row hashes form a multiset, preserving duplicate rows and SQLite
    types. Catalog SQL, identities and raw JSON are hashed without rewriting.
    Virtual/shadow tables are refused rather than partially compared.
    """
    try:
        with closing(connect(path)) as conn:
            conn.execute('PRAGMA query_only=ON')
            conn.execute('PRAGMA trusted_schema=OFF')
            conn.execute('BEGIN')
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise SnapshotInspectionError('source_integrity_failed')
            catalog = conn.execute(
                'SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name'
            ).fetchall()
            table_list = conn.execute('PRAGMA main.table_list').fetchall()
            if not table_list or any(row[2] not in ('table', 'view') for row in table_list):
                raise SnapshotInspectionError('unsupported_sqlite_object')
            columns = conn.execute('PRAGMA table_info(activities)').fetchall()
            by_name = {row[1]: row for row in columns}
            pk = [row for row in columns if row[5]]
            if (
                not any(row[0] == 'table' and row[1] == 'activities' for row in catalog)
                or not {'activity_id', 'date', 'sport', 'duration_minutes'} <= by_name.keys()
                or len(pk) != 1 or pk[0][1] != 'activity_id'
                or pk[0][2].upper() != 'TEXT'
            ):
                raise SnapshotInspectionError('unsupported_source_schema')
            tables = {}
            for object_type, name, _, _ in catalog:
                if object_type not in ('table', 'index', 'view', 'trigger'):
                    raise SnapshotInspectionError('unsupported_sqlite_object')
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
        raise SnapshotInspectionError('source_integrity_failed') from exc
    except UnicodeError as exc:
        raise SnapshotInspectionError('unsupported_sqlite_value') from exc

