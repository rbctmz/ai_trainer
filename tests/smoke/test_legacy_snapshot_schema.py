"""#749: legacy declarations, synthetic stores only; no runtime activation."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from scripts import sqlite_backup_restore as cli
from services.automatic_snapshots import check_snapshot
from services.sqlite_snapshot_core import SnapshotInspectionError, inspect_database


LEGACY_COLUMNS = {
    'activity_id': 'INTEGER', 'date': 'TEXT', 'sport': 'TEXT',
    'duration_minutes': 'REAL',
}
DOMAINS = (
    'activity_provider_links', 'activity_manual_links', 'planning_checkpoints',
    'coach_decisions', 'plan_actual_matches', 'session_feedback', 'readiness_snapshots',
)


def seed_legacy(path: Path, *, populated: bool = True) -> None:
    """Include sparse rowids, duplicate/null/mixed IDs and opaque domain data."""
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE activities(activity_id INTEGER, date TEXT, '
                     'sport TEXT, duration_minutes REAL, payload BLOB)')
        if populated:
            conn.executemany('INSERT INTO activities(rowid,activity_id,date,sport,duration_minutes,payload) '
                             'VALUES (?,?,?,?,?,?)', [
                (101, 749, '2026-11-01', 'run', 20.5, b'\x00\xff'),
                (103, 749, '2026-11-01', 'run', 20.5, b'\x00\xff'),
                (211, None, None, None, None, None),
                (901, 'intervals:synthetic', '2026-11-02', 'bike', 32, b'initial'),
                (905, b'\x01\x02', '2026-11-03', 'swim', 12.75, b''),
            ])
        for name in DOMAINS:
            conn.execute(f'CREATE TABLE "{name}"(id TEXT PRIMARY KEY, raw TEXT, blob BLOB)')
            conn.execute(f'INSERT INTO "{name}" VALUES (?,?,?)',
                         (name + ':synthetic-749', ' {"value": [null, 1]}\n', b'\x00\xfe'))
        conn.executescript('''
            CREATE INDEX legacy_sport ON activities(sport);
            CREATE VIEW legacy_ids AS SELECT activity_id FROM activities;
            CREATE TABLE sequence_probe(id INTEGER PRIMARY KEY AUTOINCREMENT);
            INSERT INTO sequence_probe DEFAULT VALUES;
            DELETE FROM sequence_probe;
            PRAGMA user_version=749;
            PRAGMA application_id=749;
        ''')


def raw_state(path: Path) -> dict:
    """Independent explicit schema/value/rowid oracle, not the new recognizer."""
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        return {
            'catalog': conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall(),
            'columns': conn.execute('PRAGMA table_info(activities)').fetchall(),
            'activities': conn.execute('SELECT rowid,*,typeof(activity_id),typeof(payload) FROM activities ORDER BY rowid').fetchall(),
            'domains': {name: conn.execute(f'SELECT * FROM "{name}"').fetchall() for name in DOMAINS},
            'sequence': conn.execute('SELECT * FROM sqlite_sequence').fetchall(),
            'metadata': (conn.execute('PRAGMA user_version').fetchone(),
                         conn.execute('PRAGMA application_id').fetchone()),
        }


def committed_wal(source: Path) -> None:
    """Leave committed bytes in WAL without an active writer for stopped CLI."""
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('UPDATE activities SET payload=? WHERE rowid=901', (b'wal-only-749',))
        conn.commit()
        main, wal = source.read_bytes(), Path(str(source) + '-wal').read_bytes()
    source.write_bytes(main)
    Path(str(source) + '-wal').write_bytes(wal)
    assert b'wal-only-749' not in main and b'wal-only-749' in wal


def migrate(capsys, source, target, rollback, *flags):
    code = cli.main(['migrate', '--source', str(source), '--target', str(target),
                     '--rollback-output', str(rollback), *flags])
    output = capsys.readouterr()
    assert output.err == ''
    assert 'synthetic-749' not in output.out and 'intervals:synthetic' not in output.out
    return code, json.loads(output.out)


@pytest.mark.parametrize('populated', [False, True])
def test_legacy_cli_plan_apply_preserves_schema_storage_classes_and_wal(tmp_path, capsys, populated):
    source, target, rollback = [tmp_path / n for n in ('old.db', 'target/new.db', 'rollback/pre.db')]
    seed_legacy(source, populated=populated)
    if populated:
        committed_wal(source)
    expected = raw_state(source)
    family = [p for p in (source, Path(str(source) + '-wal')) if p.exists()]
    before = {p: p.read_bytes() for p in family}
    code, preview = migrate(capsys, source, target, rollback)
    assert (code, preview['status'], preview['reason']) == (0, 'planned', None)
    assert preview['configuration_changed'] is False
    assert not target.parent.exists() and not rollback.parent.exists()
    code, result = migrate(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert (code, result['status']) == (0, 'copied_not_activated')
    assert result['configuration_changed'] is False
    for copy in (source, target, rollback):
        assert raw_state(copy) == expected
        assert inspect_database(copy) == preview['validation']
    assert all(p.read_bytes() == value for p, value in before.items())
    if populated:
        rows = expected['activities']
        assert rows[0][1:] == rows[1][1:]  # Duplicate values, distinct implicit rowids.
        assert [row[-2] for row in rows] == ['integer', 'integer', 'null', 'text', 'blob']
        assert rows[3][5] == b'wal-only-749'
    assert migrate(capsys, source, target, rollback, '--apply', '--confirm-stopped')[1]['reason'] == 'target_exists'
    assert raw_state(target) == expected


def test_legacy_automatic_snapshot_new_generation_and_operator_restore(tmp_path, capsys):
    source, root = tmp_path / 'old.db', tmp_path / 'snapshots'
    seed_legacy(source)
    committed_wal(source)
    expected = raw_state(source)
    first = check_snapshot(source, root, 'synthetic')
    assert (first['state'], first['reason_code']) == ('ready', None)
    assert check_snapshot(source, root, 'restart')['last_snapshot_id'] == first['last_snapshot_id']
    assert len(list(root.glob('*/snapshots/*/manifest.json'))) == 1
    assert raw_state(source) == expected
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute('INSERT INTO activities VALUES (749,?,?,?,?)',
                     ('2026-11-04', 'run', 5.25, b'new-committed-749'))
    expected = raw_state(source)
    changed = check_snapshot(source, root, 'synthetic_write')
    assert (changed['state'], changed['reason_code']) == ('ready', None)
    assert changed['last_snapshot_id'] != first['last_snapshot_id']
    manifest_path = next(root.glob(f'*/snapshots/{changed["last_snapshot_id"]}/manifest.json'))
    manifest = json.loads(manifest_path.read_text())
    snapshot = manifest_path.parent / 'snapshot.db'
    assert manifest['fingerprint'] == inspect_database(source)
    assert raw_state(snapshot) == expected
    source_bytes = source.read_bytes()
    # Extract only the closed immutable snapshot into operator-owned scratch.
    extracted = tmp_path / 'restore-input.db'
    extracted.write_bytes(snapshot.read_bytes())
    restored, rollback = tmp_path / 'restore-target.db', tmp_path / 'reset-rollback.db'
    seed_legacy(restored, populated=False)  # Existing reset-like state, not product reset.
    reset_state = raw_state(restored)
    code = cli.main(['restore', '--backup', str(extracted), '--database', str(restored),
                     '--rollback-output', str(rollback), '--confirm-stopped'])
    output = capsys.readouterr()
    assert code == 0 and output.err == ''
    assert json.loads(output.out)['integrity_check'] == 'ok'
    assert raw_state(restored) == expected
    assert raw_state(rollback) == reset_state
    assert source.read_bytes() == source_bytes
    assert raw_state(snapshot) == expected
    assert check_snapshot(source, root, 'after_restore')['last_snapshot_id'] == changed['last_snapshot_id']


@pytest.mark.parametrize('column,declaration', [
    ('activity_id', 'TEXT'), ('activity_id', 'INT'), ('activity_id', 'REAL'),
    ('activity_id', 'INTEGER PRIMARY KEY'), ('date', 'BLOB'), ('date', 'DATE'),
    ('sport', 'INTEGER'), ('duration_minutes', 'TEXT'),
    ('date', 'TEXT PRIMARY KEY'),
    *[(name, None) for name in LEGACY_COLUMNS],
])
def test_legacy_near_miss_is_not_recognized(tmp_path, capsys, column, declaration):
    columns = {**LEGACY_COLUMNS, column: declaration}
    source = tmp_path / 'foreign.db'
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('CREATE TABLE activities(' + ','.join(f'{k} {v}' for k, v in columns.items() if v is not None) + ')')
    target, rollback = tmp_path / 'out/copy.db', tmp_path / 'saved/pre.db'
    before = source.read_bytes()
    code, result = migrate(capsys, source, target, rollback)
    assert (code, result['reason']) == (2, 'unsupported_source_schema')
    with pytest.raises(SnapshotInspectionError, match='^unsupported_source_schema$'):
        inspect_database(source)
    automatic = check_snapshot(source, tmp_path / 'auto', 'synthetic')
    assert automatic['state'] == 'degraded'
    assert not list((tmp_path / 'auto').rglob('snapshot.db'))
    assert not target.parent.exists() and not rollback.parent.exists()
    assert source.read_bytes() == before


def test_legacy_type_names_are_case_insensitive(tmp_path):
    source = tmp_path / 'case.db'
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('CREATE TABLE activities(activity_id integer,date text,sport text,duration_minutes real)')
    assert inspect_database(source)['tables']['activities']['rows'] == 0
