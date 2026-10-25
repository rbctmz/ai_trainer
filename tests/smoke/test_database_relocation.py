"""#624 M2: only synthetic, explicitly named databases under tmp_path."""
from __future__ import annotations

import errno
import json
import os
import sqlite3
import stat
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

import scripts.sqlite_backup_restore as tool


DOMAINS = (
    'activity_provider_links', 'activity_manual_links', 'planning_checkpoints',
    'coach_decisions', 'plan_actual_matches', 'session_feedback', 'readiness_snapshots',
)


def seed(path: Path, *, populated: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE activities(activity_id TEXT PRIMARY KEY, date DATE, '
                     'sport TEXT, duration_minutes REAL)')
        if populated:
            conn.execute('INSERT INTO activities VALUES (?,?,?,?)',
                         ('private-marker', '2026-10-25', 'run', 30.5))
        for name in DOMAINS:
            conn.execute(f'CREATE TABLE "{name}" (id TEXT PRIMARY KEY, payload TEXT, data BLOB)')
            conn.execute(f'INSERT INTO "{name}" VALUES (?,?,?)',
                         (name + '-identity', ' {"raw": [1, null]}\n', b'\x00\xff'))
        conn.executescript('''
            CREATE TABLE extra_without_pk (a, b, c);
            INSERT INTO extra_without_pk VALUES (1, '1', NULL), (1, '1', NULL),
                                                (1.0, X'31', '');
            CREATE TABLE numbered (id INTEGER PRIMARY KEY AUTOINCREMENT, value TEXT);
            INSERT INTO numbered(value) VALUES ('keep-sequence');
            DELETE FROM numbered;
            CREATE INDEX extra_index ON activities(sport);
            CREATE VIEW extra_view AS SELECT activity_id FROM activities;
            CREATE TRIGGER extra_trigger AFTER INSERT ON activities
              BEGIN INSERT INTO extra_without_pk VALUES (new.activity_id, NULL, NULL); END;
            PRAGMA user_version=42;
            PRAGMA application_id=624;
        ''')


@pytest.fixture
def endpoints(tmp_path):
    source, target, rollback = (tmp_path / 'legacy' / 'old.db',
                                tmp_path / 'store' / 'new.db',
                                tmp_path / 'backups' / 'rollback.db')
    seed(source)
    return source, target, rollback


def cli(capsys, source, target, rollback=None, *extra):
    args = ['migrate', '--source', str(source), '--target', str(target)]
    if rollback is not None:
        args += ['--rollback-output', str(rollback)]
    code = tool.main([*args, *extra])
    captured = capsys.readouterr()
    assert captured.err == ''
    report = json.loads(captured.out)
    assert report['configuration_changed'] is False
    assert 'private-marker' not in captured.out
    assert 'raw' not in captured.out
    return code, report


def assert_no_outputs(target, rollback):
    assert not target.parent.exists()
    assert not rollback.parent.exists()


def test_migrate_cli_readonly_plan(endpoints, capsys):
    source, target, rollback = endpoints
    before = source.read_bytes()
    code, report = cli(capsys, source, target)
    assert code == 0
    assert report['status'] == 'planned'
    assert report['rollback_output'] is None
    assert report['validation']['tables']['activities']['rows'] == 1
    assert report['validation']['tables']['extra_without_pk']['rows'] == 3
    assert source.read_bytes() == before
    assert_no_outputs(target, rollback)


@pytest.mark.parametrize('flags,reason', [
    ([], None), (['--apply'], 'stopped_confirmation_required'),
    (['--apply', '--confirm-stopped'], 'rollback_output_required'),
])
def test_apply_requires_attestation_and_snapshot(endpoints, capsys, flags, reason):
    source, target, rollback = endpoints
    code, report = cli(capsys, source, target, None, *flags)
    assert code == (2 if reason else 0)
    assert report['reason'] == reason
    assert_no_outputs(target, rollback)


def test_apply_preserves_all_domains_schema_values_and_metadata(endpoints, capsys):
    source, target, rollback = endpoints
    expected = tool.inspect_relocation_database(source)
    before = source.read_bytes()
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert code == 0
    assert report['status'] == 'copied_not_activated'
    assert report['validation'] == expected
    assert tool.inspect_relocation_database(target) == expected
    assert tool.inspect_relocation_database(rollback) == expected
    assert source.read_bytes() == before
    if os.name == 'posix':
        for path in (target, rollback):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert (code, report['reason']) == (2, 'target_exists')
    assert tool.inspect_relocation_database(target) == expected


def test_committed_wal_pages_are_copied(endpoints, capsys):
    source, target, rollback = endpoints
    # Rebuild the main+WAL pair after closing the writer, leaving no writer open.
    conn = sqlite3.connect(source)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA wal_autocheckpoint=0')
    conn.execute("UPDATE activities SET duration_minutes=77.25")
    conn.commit()
    main, wal = source.read_bytes(), Path(str(source) + '-wal').read_bytes()
    conn.close()
    source.write_bytes(main)
    Path(str(source) + '-wal').write_bytes(wal)
    assert b'private-marker' in wal
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert (code, report['status']) == (0, 'copied_not_activated')
    for path in (source, target, rollback):
        with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as check:
            assert check.execute('SELECT duration_minutes FROM activities').fetchone() == (77.25,)


@pytest.mark.parametrize('left,right', [(a, b) for a in range(3) for b in range(3) if a != b])
@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
@pytest.mark.parametrize('apply', [False, True])
def test_all_future_family_collisions_before_sqlite(tmp_path, monkeypatch, capsys, left, right, suffix, apply):
    paths = [tmp_path / f'{n}.db' for n in range(3)]
    paths[right] = Path(str(paths[left]) + suffix)
    def must_not_open(*args):
        pytest.fail('namespace validation must precede opening SQLite')
    monkeypatch.setattr(tool, '_readonly_connection', must_not_open)
    code, report = cli(capsys, *paths, *(['--apply', '--confirm-stopped'] if apply else []))
    assert (code, report['reason']) == (2, 'endpoint_namespace_overlap')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('endpoint', [1, 2])
@pytest.mark.parametrize('suffix', ['', '-wal', '-shm', '-journal'])
def test_existing_output_or_sidecar_refused(endpoints, capsys, endpoint, suffix):
    source, target, rollback = endpoints
    existing = Path(str(endpoints[endpoint]) + suffix)
    existing.parent.mkdir()
    existing.write_bytes(b'competitor')
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert code == 2
    assert report['reason'] == ('target_exists' if endpoint == 1 else 'rollback_exists')
    assert existing.read_bytes() == b'competitor'


@pytest.mark.parametrize('kind', ['missing', 'directory', 'invalid', 'empty', 'foreign', 'wrong_pk', 'virtual'])
def test_invalid_or_unsupported_sources(tmp_path, capsys, kind):
    source, target, rollback = [tmp_path / n for n in ('source.db', 'out/new.db', 'backup/old.db')]
    if kind == 'directory':
        source.mkdir()
    elif kind == 'invalid':
        source.write_text('invalid-sqlite')
    elif kind in ('empty', 'foreign', 'wrong_pk', 'virtual'):
        with closing(sqlite3.connect(source)) as conn, conn:
            if kind == 'foreign':
                conn.execute('CREATE TABLE unrelated(a)')
            elif kind == 'wrong_pk':
                conn.execute('CREATE TABLE activities(activity_id TEXT, date, sport, duration_minutes)')
            elif kind == 'virtual':
                conn.execute('CREATE TABLE activities(activity_id TEXT PRIMARY KEY, date, sport, duration_minutes)')
                conn.execute('CREATE VIRTUAL TABLE search USING fts5(body)')
    code, report = cli(capsys, source, target, rollback)
    assert code == 2
    assert report['status'] == 'blocked'
    assert report['reason'] in ('source_missing', 'source_not_file', 'source_integrity_failed',
                                'unsupported_source_schema', 'unsupported_sqlite_object')
    assert_no_outputs(target, rollback)


def test_empty_application_is_supported(tmp_path, capsys):
    source, target = tmp_path / 'empty.db', tmp_path / 'new.db'
    seed(source, populated=False)
    code, report = cli(capsys, source, target)
    assert code == 0
    assert report['validation']['tables']['activities']['rows'] == 0


@pytest.mark.parametrize('endpoint', [0, 1, 2])
def test_relative_endpoint_refused(endpoints, capsys, endpoint):
    paths = list(endpoints)
    paths[endpoint] = Path('relative.db')
    code, report = cli(capsys, *paths)
    assert (code, report['reason']) == (2, 'absolute_path_required')


@pytest.mark.parametrize('endpoint', [1, 2])
@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'case', 'checkout', 'parent_alias'])
def test_output_aliases_and_git_checkout_refused(endpoints, tmp_path, capsys, endpoint, kind):
    paths = list(endpoints)
    source = paths[0]
    alias = tmp_path / 'alias.db'
    if kind == 'symlink':
        alias.symlink_to(source)
    elif kind == 'hardlink':
        os.link(source, alias)
    elif kind == 'case':
        alias = source.with_name(source.name.upper())
    else:
        checkout = tmp_path / 'checkout'
        checkout.mkdir()
        (checkout / '.git').write_text('gitdir: ignored-for-boundary')
        alias = checkout / 'sub/new.db'
        if kind == 'parent_alias':
            link = tmp_path / 'link'
            link.symlink_to(checkout, target_is_directory=True)
            alias = link / 'sub/new.db'
    paths[endpoint] = alias
    code, report = cli(capsys, *paths)
    assert code == 2
    assert report['reason'] in ('symlink_endpoint', 'endpoint_namespace_overlap', 'output_inside_checkout')
    assert not endpoints[1].exists()
    assert not endpoints[2].exists()


def test_source_endpoint_symlink_refused(endpoints, tmp_path, capsys):
    source, target, rollback = endpoints
    link = tmp_path / 'source-link'
    link.symlink_to(source)
    assert cli(capsys, link, target, rollback)[1]['reason'] == 'symlink_endpoint'


def test_source_in_checkout_is_allowed(endpoints, capsys):
    source, target, rollback = endpoints
    (source.parent / '.git').mkdir()
    assert cli(capsys, source, target, rollback)[0] == 0


@pytest.mark.parametrize('phase', ['rollback_copy', 'target_copy', 'logical', 'source_changed', 'publish', 'permission', 'target_race', 'sidecar_race'])
def test_failure_keeps_source_config_and_valid_snapshot(endpoints, capsys, monkeypatch, phase):
    source, target, rollback = endpoints
    before = source.read_bytes()
    copy = tool._copy_sqlite
    publish = tool._publish_new_artifact
    count = 0
    def injected_copy(origin, temporary):
        nonlocal count
        count += 1
        if (phase == 'rollback_copy' and count == 1) or (phase == 'target_copy' and count == 2):
            raise OSError(errno.ENOSPC, 'simulated full disk')
        copy(origin, temporary)
        if count == 2 and phase == 'logical':
            with closing(sqlite3.connect(temporary)) as conn, conn:
                conn.execute("UPDATE session_feedback SET payload='changed'")
        if count == 2 and phase == 'source_changed':
            with closing(sqlite3.connect(source)) as conn, conn:
                conn.execute('UPDATE activities SET duration_minutes=99')
        if count == 2 and phase in ('target_race', 'sidecar_race'):
            Path(str(target) + ('-wal' if phase == 'sidecar_race' else '')).write_bytes(b'competitor')
    def injected_publish(temporary, output, **kwargs):
        if phase == 'publish' and output == target:
            raise OSError(errno.EIO, 'simulated publication failure')
        publish(temporary, output, **kwargs)
    monkeypatch.setattr(tool, '_copy_sqlite', injected_copy)
    monkeypatch.setattr(tool, '_publish_new_artifact', injected_publish)
    if phase == 'permission':
        def denied(*args, **kwargs):
            raise PermissionError('simulated permission denial')
        monkeypatch.setattr(tool, '_prepare_temporary_destination', denied)
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert code == 2
    assert report['status'] == 'blocked'
    if phase != 'source_changed':
        assert source.read_bytes() == before
    if phase == 'target_race':
        assert target.read_bytes() == b'competitor'
    else:
        assert not target.exists()
    if phase == 'sidecar_race':
        assert Path(str(target) + '-wal').read_bytes() == b'competitor'
    if phase not in ('rollback_copy', 'permission'):
        assert rollback.exists()
        assert tool.inspect_relocation_database(rollback)['tables']['activities']['rows'] == 1
    else:
        assert not rollback.exists()
    assert not list(target.parent.glob('.*.tmp*'))
    assert not list(rollback.parent.glob('.*.tmp*'))


def test_multiset_digest_distinguishes_types_duplicates_and_raw_json(endpoints):
    source, _, _ = endpoints
    before = tool.inspect_relocation_database(source)
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute('DELETE FROM extra_without_pk WHERE rowid=1')
    assert tool.inspect_relocation_database(source) != before
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("INSERT INTO extra_without_pk VALUES (1,'1',NULL)")
    assert tool.inspect_relocation_database(source) == before
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("UPDATE extra_without_pk SET a='1' WHERE rowid=2")
    assert tool.inspect_relocation_database(source) != before


def test_cli_avoids_settings_and_dotenv(endpoints, tmp_path):
    source, target, _ = endpoints
    script = Path(tool.__file__).resolve()
    # Explicit migrate works despite invalid runtime configuration, before Settings import.
    env = {k: v for k, v in os.environ.items() if k in (
        'PATH', 'TMPDIR', 'PYTHONPATH', 'AI_TRAINER_TEST_ROOT', 'PYTHONDONTWRITEBYTECODE',
    )}
    env.update(HOME=str(tmp_path), DATABASE_PATH=' ', XDG_DATA_HOME=str(tmp_path / 'home'))
    result = subprocess.run([sys.executable, str(script), 'migrate', '--source', str(source),
                             '--target', str(target)], cwd=tmp_path, env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'planned'
    assert not target.exists()


@pytest.mark.parametrize('sql', [
    "UPDATE session_feedback SET payload=json(payload)",
    "UPDATE activity_provider_links SET id='new-identity'",
    'UPDATE sqlite_sequence SET seq=99',
    'PRAGMA user_version=43',
    'PRAGMA application_id=625',
    'DROP VIEW extra_view',
    'DROP TRIGGER extra_trigger',
    'DROP INDEX extra_index',
])
def test_fingerprint_detects_raw_json_identity_schema_and_metadata(endpoints, sql):
    source, _, _ = endpoints
    before = tool.inspect_relocation_database(source)
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(sql)
    assert tool.inspect_relocation_database(source) != before


@pytest.mark.parametrize('output_index', [1, 2])
def test_publish_link_race_never_overwrites(endpoints, capsys, monkeypatch, output_index):
    source, target, rollback = endpoints
    victim = endpoints[output_index]
    original_link = tool.os.link
    def racing_link(temporary, destination):
        if destination == victim:
            destination.write_bytes(b'competing-publisher')
        original_link(temporary, destination)
    monkeypatch.setattr(tool.os, 'link', racing_link)
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert (code, report['status']) == (2, 'blocked')
    assert victim.read_bytes() == b'competing-publisher'
    assert not list(victim.parent.glob('.*.tmp*'))
    if output_index == 1:
        assert tool.inspect_relocation_database(rollback)['integrity_check'] == 'ok'
    else:
        assert not target.exists()


def test_corrupt_rollback_not_published(endpoints, monkeypatch, capsys):
    source, target, rollback = endpoints
    copy = tool._copy_sqlite
    def corrupt(origin, temporary):
        copy(origin, temporary)
        temporary.write_bytes(b'corrupt-snapshot')
    monkeypatch.setattr(tool, '_copy_sqlite', corrupt)
    code, report = cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')
    assert (code, report['reason']) == (2, 'source_integrity_failed')
    assert not rollback.exists()
    assert not target.exists()
    assert not list(rollback.parent.glob('.*.tmp*'))


def test_unsupported_application_view_and_composite_pk(tmp_path, capsys):
    for name, sql in (
        ('view', 'CREATE VIEW activities AS SELECT 1 AS activity_id, NULL AS date, NULL AS sport, NULL AS duration_minutes'),
        ('composite', 'CREATE TABLE activities(activity_id TEXT, date, sport, duration_minutes, PRIMARY KEY(activity_id,date))'),
    ):
        source = tmp_path / (name + '.db')
        with closing(sqlite3.connect(source)) as conn, conn:
            conn.execute(sql)
        assert cli(capsys, source, tmp_path / 'new.db')[1]['reason'] == 'unsupported_source_schema'


def test_supported_extra_without_rowid_and_generated_values(endpoints, capsys):
    source, target, rollback = endpoints
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.executescript('''
          CREATE TABLE compact(id TEXT PRIMARY KEY, n INTEGER) WITHOUT ROWID;
          INSERT INTO compact VALUES ('a', 7);
          CREATE TABLE calculated(n INTEGER, doubled INTEGER GENERATED ALWAYS AS (n*2) STORED);
          INSERT INTO calculated(n) VALUES (3);
        ''')
    expected = tool.inspect_relocation_database(source)
    assert cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')[0] == 0
    assert tool.inspect_relocation_database(target) == expected


def test_resolved_parent_native_identity_and_unicode_names(tmp_path):
    parent = tmp_path / 'é'
    parent.mkdir()
    alias = tmp_path / 'e\u0301'
    if not alias.exists():
        alias.symlink_to(parent, target_is_directory=True)
    assert tool._future_alias(parent / 'new.db', alias / 'NEW.db')
    assert tool._future_alias(tmp_path / 'future-é/new.db', tmp_path / 'future-e\u0301/new.db')
    assert not tool._future_alias(parent / 'first.db', alias / 'second.db')


def test_private_temporary_permission_failure_is_cleaned(endpoints, capsys, monkeypatch):
    source, target, rollback = endpoints
    original_chmod = Path.chmod
    def denied(path, *args, **kwargs):
        if path.name.endswith('.tmp'):
            raise PermissionError('simulated chmod denial')
        return original_chmod(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'chmod', denied)
    assert cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')[0] == 2
    assert not rollback.exists()
    assert not target.exists()
    assert list(rollback.parent.iterdir()) == []


@pytest.mark.parametrize('publication', [1, 2])
def test_fsync_failure_after_publication_retains_valid_artifact(endpoints, capsys, monkeypatch, publication):
    source, target, rollback = endpoints
    expected = tool.inspect_relocation_database(source)
    fsync = tool._fsync_directory
    calls = 0
    def failed_sync(parent):
        nonlocal calls
        calls += 1
        if calls == publication:
            raise OSError(errno.EIO, 'simulated durability error after link')
        fsync(parent)
    monkeypatch.setattr(tool, '_fsync_directory', failed_sync)
    assert cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')[0] == 2
    assert tool.inspect_relocation_database(rollback) == expected
    if publication == 1:
        assert not target.exists()
    else:
        assert tool.inspect_relocation_database(target) == expected
        assert cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')[1]['reason'] == 'target_exists'
    assert not list(rollback.parent.glob('.*.tmp*'))
    assert not list(target.parent.glob('.*.tmp*'))


def test_current_application_ddl_and_populated_local_domains(tmp_path, capsys):
    from data.database import Database

    source, target, rollback = [tmp_path / n for n in ('current.db', 'store/new.db', 'backup/old.db')]
    Database(str(source))
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("INSERT INTO activities(activity_id,date,sport,duration_minutes) VALUES ('a','2026-10-25','run',25)")
        for table in DOMAINS:
            # Exercise actual application DDL with synthetic payloads. This is
            # storage preservation, not model-valid event/restart acceptance M3.
            required = [row for row in conn.execute(f'PRAGMA table_info("{table}")')
                        if row[3] and row[4] is None and not (row[5] and row[2] == 'INTEGER')]
            values = {}
            for row in required:
                name, declared = row[1], row[2]
                values[name] = (1 if declared in ('INTEGER', 'REAL') else
                                ' {"synthetic": true} ' if name.endswith(('_json', '_data')) else
                                'synthetic-' + name)
            if table == 'activity_provider_links':
                values.update(canonical_activity_id='a', provider='intervals', provider_activity_id='a')
            identifiers = ','.join('"' + name + '"' for name in values)
            placeholders = ','.join('?' for _ in values)
            conn.execute(f'INSERT INTO "{table}" ({identifiers}) VALUES ({placeholders})', list(values.values()))
    def independent_snapshot(path):
        with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as conn:
            schema = conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            rows = {name: conn.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
                    for kind, name, _, _ in schema if kind == 'table'}
            return schema, rows
    expected = independent_snapshot(source)
    assert all(len(expected[1][name]) == 1 for name in DOMAINS)
    assert cli(capsys, source, target, rollback, '--apply', '--confirm-stopped')[0] == 0
    assert independent_snapshot(target) == expected
    assert independent_snapshot(rollback) == expected
