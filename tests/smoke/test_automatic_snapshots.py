"""Synthetic acceptance of #623 M2; no automatic runtime activation."""
import sqlite3

import pytest


from services.automatic_snapshots import check_snapshot


def source_store(tmp_path):
    path = tmp_path / 'working.db'
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE activities(activity_id TEXT PRIMARY KEY,date TEXT,sport TEXT,duration_minutes REAL)')
        conn.execute("INSERT INTO activities VALUES ('synthetic','2026-10-29','run',20)")
    conn.close()
    return path


def snapshots(root):
    return list(root.glob('*/snapshots/*/manifest.json'))


def test_snapshot_deduplicates_unchanged_and_keeps_changed_versions(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    assert first['state'] == 'ready'
    assert len(snapshots(root)) == 1
    again = check_snapshot(source, root, 'test')
    assert again['last_snapshot_id'] == first['last_snapshot_id']
    assert len(snapshots(root)) == 1
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=30')
    changed = check_snapshot(source, root, 'test')
    assert changed['state'] == 'ready'
    assert changed['last_snapshot_id'] != first['last_snapshot_id']
    assert len(snapshots(root)) == 2


def test_failed_attempt_preserves_prior_snapshot(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name != 'status.json'}
    source.write_bytes(b'not sqlite')
    result = check_snapshot(source, root, 'test')
    assert result['state'] == 'degraded'
    for path, content in before.items():
        assert path.read_bytes() == content


def test_nonexistent_source_fails_without_creating_it(tmp_path):
    source = tmp_path / 'missing.db'
    result = check_snapshot(source, tmp_path / 'backups', 'test')
    assert result['state'] == 'degraded'
    assert not source.exists()


def test_vacuum_cookie_is_not_a_new_generation(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    with sqlite3.connect(source) as conn:
        conn.execute('VACUUM')
    conn.close()
    assert check_snapshot(source, root, 'test')['last_snapshot_id'] == first['last_snapshot_id']
    assert len(snapshots(root)) == 1


def test_rejects_alias_or_checkout_before_snapshot(tmp_path):
    source = source_store(tmp_path)
    link = tmp_path / 'link.db'
    link.symlink_to(source)
    assert check_snapshot(link, tmp_path / 'backups', 'test')['reason_code'] == 'backup_identity_unknown'
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / '.git').write_text('synthetic')
    assert check_snapshot(source, checkout / 'backups', 'test')['reason_code'] == 'backup_identity_unknown'
    assert not (checkout / 'backups').exists()


def test_publication_failure_preserves_prior_and_cleans_temp(tmp_path, monkeypatch):
    import services.automatic_snapshots as core
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert core._run(source, root)['state'] == 'ready'
    before = {p: p.read_bytes() for p in root.rglob('snapshot.db')}
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=25')
    conn.close()
    def fail(*args):
        raise OSError('synthetic ENOSPC')
    monkeypatch.setattr(core, '_publish', fail)
    assert core._run(source, root)['reason_code'] == 'backup_io_error'
    assert {p: p.read_bytes() for p in root.rglob('snapshot.db')} == before
    assert not list(root.glob('.candidate-*'))


def test_status_failure_preserves_published_copy_and_restart_recovers(tmp_path, monkeypatch):
    import services.automatic_snapshots as core
    source, root = source_store(tmp_path), tmp_path / 'backups'
    original = core._write_json
    def fail_status(path, value, **kwargs):
        if path.name == 'status.json':
            raise OSError('synthetic unwritable')
        return original(path, value, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(core, '_write_json', fail_status)
        assert core._run(source, root)['reason_code'] == 'backup_state_unwritable'
    assert len(snapshots(root)) == 1
    assert check_snapshot(source, root, 'restart')['state'] == 'ready'
    assert len(snapshots(root)) == 1


def test_timeout_kills_worker_and_cleans_parent_owned_temp(tmp_path, monkeypatch):
    import sys
    import subprocess
    import services.automatic_snapshots as core
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert core.check_snapshot(source, root, 'first')['state'] == 'ready'
    native = subprocess.Popen
    def slow(*args, **kwargs):
        return native([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
    monkeypatch.setattr(core.subprocess, 'Popen', slow)
    monkeypatch.setattr(core, 'DEADLINE_SECONDS', .2)
    assert core.check_snapshot(source, root, 'test')['reason_code'] == 'backup_timeout'
    assert not list(root.glob('.attempt-*'))
    import json
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    assert json.loads(state_path.read_text())['reason_code'] == 'backup_timeout'


def test_two_callers_serialize_and_deduplicate(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    source, root = source_store(tmp_path), tmp_path / 'backups'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: check_snapshot(source, root, 'test'), range(2)))
    assert all(item['state'] == 'ready' for item in results)
    assert results[0]['last_snapshot_id'] == results[1]['last_snapshot_id']
    assert len(snapshots(root)) == 1


def test_lock_released_after_owner_killed(tmp_path, monkeypatch):
    import subprocess
    import sys
    from services.automatic_snapshots import _paths
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    _, _, namespace = _paths(source, root)
    code = ('import sys,time; from pathlib import Path; '
            'from services.automatic_snapshots import namespace_lock; '
            'lock=namespace_lock(Path(sys.argv[1])); lock.__enter__(); '
            'print("locked",flush=True); time.sleep(30)')
    process = subprocess.Popen([sys.executable, '-c', code, str(root / namespace)], stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'
        import services.automatic_snapshots as core
        with monkeypatch.context() as patch:
            patch.setattr(core, 'DEADLINE_SECONDS', 2.0)
            assert check_snapshot(source, root, 'busy')['reason_code'] == 'backup_busy'
    finally:
        process.kill()
        process.wait(timeout=5)
    assert check_snapshot(source, root, 'restart')['state'] == 'ready'


def test_concurrent_writer_snapshot_preserves_transaction_invariant(tmp_path):
    import threading
    source, root = source_store(tmp_path), tmp_path / 'backups'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE pairs(a INTEGER,b INTEGER)')
        conn.execute('INSERT INTO pairs VALUES (0,0)')
    conn.close()
    stop, started = threading.Event(), threading.Event()
    failures = []
    def writer():
        try:
            with sqlite3.connect(source) as conn:
                started.set()
                while not stop.is_set():
                    conn.execute('UPDATE pairs SET a=a+1,b=b+1')
                    conn.commit()
                    stop.wait(.002)
            conn.close()
        except Exception as exc:
            failures.append(type(exc).__name__)
    thread = threading.Thread(target=writer)
    thread.start()
    assert started.wait(2)
    try:
        assert check_snapshot(source, root, 'test')['state'] == 'ready'
    finally:
        stop.set()
        thread.join(3)
    assert not thread.is_alive() and not failures
    for manifest in snapshots(root):
        with sqlite3.connect(manifest.parent / 'snapshot.db') as conn:
            assert conn.execute('SELECT COUNT(*) FROM pairs WHERE a<>b').fetchone()[0] == 0
        conn.close()


def test_namespace_respects_native_case_identity(tmp_path):
    import shutil
    from services.automatic_snapshots import _paths
    source = source_store(tmp_path)
    other = tmp_path / 'WORKING.db'
    _, _, first = _paths(source, tmp_path / 'backups')
    if other.exists():
        assert _paths(other, tmp_path / 'backups')[2] == first
    else:
        shutil.copyfile(source, other)
        assert _paths(other, tmp_path / 'backups')[2] != first


def test_published_pair_is_verified_and_corrupt_copy_not_reused(tmp_path):
    import json
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    manifest_path = snapshots(root)[0]
    manifest = json.loads(manifest_path.read_text())
    assert manifest['source_generation'] and manifest['integrity_check'] == 'ok'
    (manifest_path.parent / 'snapshot.db').write_bytes(b'corrupt synthetic backup')
    second = check_snapshot(source, root, 'test')
    assert second['state'] == 'ready'
    assert second['last_snapshot_id'] != first['last_snapshot_id']
    assert len(snapshots(root)) == 2  # Corrupt artifacts are preserved for operator inspection.


def test_publication_never_replaces_foreign_empty_directory(tmp_path):
    import pytest
    from services.automatic_snapshots import _publish
    candidate, foreign = tmp_path / 'candidate', tmp_path / 'foreign'
    candidate.mkdir()
    foreign.mkdir()
    marker = candidate / 'manifest.json'
    marker.write_text('synthetic')
    with pytest.raises(FileExistsError):
        _publish(candidate, foreign)
    assert marker.exists() and list(foreign.iterdir()) == []


def test_existing_reset_pins_survive_check(tmp_path):
    import json
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    state = json.loads(state_path.read_text())
    state['reset_pins'] = {first['last_snapshot_id']: '2099-01-01T00:00:00+00:00'}
    state_path.write_text(json.dumps(state))
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    assert json.loads(state_path.read_text())['reset_pins'] == state['reset_pins']


def test_core_failures_preserve_source_and_previous_copy(tmp_path, monkeypatch):
    import json
    import services.automatic_snapshots as core
    from services.sqlite_snapshot_core import SnapshotInspectionError
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert core._run(source, root)['state'] == 'ready'
    previous = {p: p.read_bytes() for p in root.rglob('snapshot.db')}
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=35')
    conn.close()
    before = source.read_bytes()
    for operation in ('copy_sqlite', 'inspect_database', '_hash', '_write_json'):
        original = getattr(core, operation)
        def fail(*args, **kwargs):
            if operation == 'inspect_database':
                raise SnapshotInspectionError('synthetic')
            if operation == '_write_json' and args[0].name != 'manifest.json':
                return original(*args, **kwargs)
            raise PermissionError('synthetic permission failure')
        with monkeypatch.context() as patch:
            patch.setattr(core, operation, fail)
            assert core._run(source, root)['state'] == 'degraded'
        assert source.read_bytes() == before
        assert {p: p.read_bytes() for p in root.rglob('snapshot.db')} == previous
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    assert json.loads(state_path.read_text())['state'] == 'degraded'


def test_crash_at_publication_recovers_without_overwriting_prior(tmp_path):
    import subprocess
    import sys
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    old = snapshots(root)[0].parent / 'snapshot.db'
    old_bytes = old.read_bytes()
    for after in (False, True):
        with sqlite3.connect(source) as conn:
            conn.execute('UPDATE activities SET duration_minutes=duration_minutes+1')
        conn.close()
        code = '''import os,sys
from services import automatic_snapshots as core
original=core._publish
def die(*args):
    if sys.argv[3]=='after': original(*args)
    os._exit(71)
core._publish=die
core._run(sys.argv[1],sys.argv[2])
'''
        result = subprocess.run([sys.executable, '-c', code, str(source), str(root), 'after' if after else 'before'])
        assert result.returncode == 71
        assert old.read_bytes() == old_bytes
        assert check_snapshot(source, root, 'restart')['state'] == 'ready'
        assert old.read_bytes() == old_bytes


def test_unknown_namespace_is_not_adopted_or_deleted(tmp_path):
    from services.automatic_snapshots import _paths
    source, root = source_store(tmp_path), tmp_path / 'backups'
    _, _, identity = _paths(source, root)
    root.mkdir(mode=0o700)
    unknown = root / identity
    unknown.mkdir(mode=0o700)
    (unknown / 'foreign.txt').write_text('keep')
    result = check_snapshot(source, root, 'test')
    assert result['reason_code'] == 'backup_identity_unknown'
    assert (unknown / 'foreign.txt').read_text() == 'keep'
    assert not (unknown / 'namespace.json').exists()


def test_existing_snapshot_sidecar_alias_refuses_before_inspection(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    external = tmp_path / 'foreign-sentinel'
    external.write_bytes(b'keep')
    db = snapshots(root)[0].parent / 'snapshot.db'
    sidecar = db.with_name(db.name + '-journal')
    sidecar.symlink_to(external)
    result = check_snapshot(source, root, 'test')
    assert result['reason_code'] == 'backup_identity_unknown'
    assert external.read_bytes() == b'keep'
    assert sidecar.is_symlink()


@pytest.mark.parametrize('bad_state', ['{broken synthetic state', '[]', '{"reset_pins":null}', None])
def test_corrupt_status_recovers_health_but_keeps_pins_unknown(tmp_path, bad_state):
    import json
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    if bad_state is None:
        state_path.unlink()
    else:
        state_path.write_text(bad_state)
    for _ in range(2):
        result = check_snapshot(source, root, 'retry')
        assert result['state'] == 'ready'
        assert result['last_snapshot_id'] == first['last_snapshot_id']
        state = json.loads(state_path.read_text())
        assert state['reset_pins_unknown'] is True
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=40')
    conn.close()
    changed = check_snapshot(source, root, 'changed')
    assert changed['state'] == 'ready'
    assert changed['last_snapshot_id'] != first['last_snapshot_id']
    assert json.loads(state_path.read_text())['reset_pins_unknown'] is True


def test_sqlite_copy_error_persists_degraded_and_known_snapshot(tmp_path):
    import json
    source, root = source_store(tmp_path), tmp_path / 'backups'
    first = check_snapshot(source, root, 'test')
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    source.write_bytes(b'not sqlite anymore')
    result = check_snapshot(source, root, 'corrupt-source')
    state = json.loads(state_path.read_text())
    assert result['state'] == state['state'] == 'degraded'
    assert result['last_snapshot_id'] == state['last_snapshot_id'] == first['last_snapshot_id']
    assert state['reason_code'] == result['reason_code'] == 'backup_integrity_failed'


def test_status_identity_refusal_is_not_swallowed_by_recovery(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'backups'
    assert check_snapshot(source, root, 'test')['state'] == 'ready'
    state_path = snapshots(root)[0].parents[2] / 'status.json'
    external = tmp_path / 'external-state'
    external.write_text('{synthetic foreign state')
    state_path.unlink()
    state_path.symlink_to(external)
    result = check_snapshot(source, root, 'retry')
    assert result['reason_code'] == 'backup_identity_unknown'
    assert state_path.is_symlink()
    assert external.read_text() == '{synthetic foreign state'
