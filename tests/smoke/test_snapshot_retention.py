"""#623 M4: owned synthetic retention/reset/restore acceptance."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from config.settings import Settings
from data.database import Database
from services import automatic_snapshots as core
from services import snapshot_runtime as runtime
from tests.smoke.test_automatic_snapshots import source_store

BASE = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)


def clock(monkeypatch, value):
    monkeypatch.setattr(core, '_now', lambda: value, raising=False)


def namespace(root):
    return next(path.parent for path in root.glob('*/namespace.json'))


def state(root):
    return json.loads((namespace(root) / 'status.json').read_text())


def copies(root):
    return {p.parent.name: json.loads(p.read_text()) for p in root.glob('*/snapshots/*/manifest.json') if not p.parent.name.startswith('.')}


def change(source, minutes):
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=?', (minutes,))
    conn.close()


def test_retention_keeps_daily_weekly_union_and_latest(tmp_path, monkeypatch):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    published = []
    for index in range(45):
        instant = BASE + timedelta(days=index * 2)
        clock(monkeypatch, instant)
        change(source, index)
        result = core._run(source, root)
        assert result['state'] == 'ready'
        published.append((instant, result['last_snapshot_id']))
    by_day, by_week = {}, {}
    for instant, identity in published:
        by_day[instant.date()] = identity
        by_week[instant.isocalendar()[:2]] = identity
    expected = set(list(by_day.values())[-14:]) | set(list(by_week.values())[-8:])
    assert set(copies(root)) == expected
    assert published[-1][1] in expected
    before = copies(root)
    assert core._run(source, root)['last_snapshot_id'] == published[-1][1]
    assert copies(root) == before


def test_same_day_retention_and_pre_reset_pin_expiry(tmp_path, monkeypatch):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    clock(monkeypatch, BASE)
    first = core._run(source, root, reason='pre_reset')
    assert state(root)['reset_pins'][first['last_snapshot_id']] == (BASE + timedelta(days=14)).isoformat()
    clock(monkeypatch, BASE + timedelta(minutes=1))
    change(source, 31)
    latest = core._run(source, root)
    assert set(copies(root)) == {first['last_snapshot_id'], latest['last_snapshot_id']}
    clock(monkeypatch, BASE + timedelta(hours=1))
    assert core._run(source, root, reason='pre_reset')['last_snapshot_id'] == latest['last_snapshot_id']
    assert state(root)['reset_pins'][latest['last_snapshot_id']] == (BASE + timedelta(days=14, hours=1)).isoformat()
    clock(monkeypatch, BASE + timedelta(days=14))
    change(source, 32)
    after = core._run(source, root)
    assert first['last_snapshot_id'] not in copies(root)
    assert latest['last_snapshot_id'] in copies(root)
    assert after['last_snapshot_id'] in copies(root)
    assert first['last_snapshot_id'] not in state(root)['reset_pins']


@pytest.mark.parametrize('damage', ['missing_state', 'bad_pin', 'bad_snapshot'])
def test_uncertain_catalog_never_prunes(tmp_path, monkeypatch, damage):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    first = core._run(source, root)
    folder = namespace(root)
    if damage == 'missing_state':
        (folder / 'status.json').unlink()
    elif damage == 'bad_pin':
        value = state(root)
        value['reset_pins'] = {first['last_snapshot_id']: 'not a date'}
        (folder / 'status.json').write_text(json.dumps(value))
    else:
        (folder / 'snapshots' / first['last_snapshot_id'] / 'snapshot.db').write_bytes(b'broken')
    change(source, 25)
    result = core._run(source, root)
    assert result['state'] == 'ready'
    assert result['reason_code'] in {'backup_reset_pins_unknown', 'backup_retention_failed'}
    assert first['last_snapshot_id'] in copies(root)
    assert result['last_snapshot_id'] in copies(root)


def test_deletion_failure_keeps_latest_and_reports_maintenance(tmp_path, monkeypatch):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    first = core._run(source, root)
    change(source, 35)
    from pathlib import Path
    native = Path.unlink
    def refuse(path, *args, **kwargs):
        if path.name == 'snapshot.db' and path.parent.name.startswith('.retired-'):
            raise PermissionError('synthetic')
        return native(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', refuse)
        result = core._run(source, root)
    assert result['state'] == 'ready' and result['reason_code'] == 'backup_retention_failed'
    assert state(root)['reason_code'] == 'backup_retention_failed'
    assert len(copies(root)) == 1
    retired = list((namespace(root) / 'snapshots').glob('.retired-*/snapshot.db'))
    assert len(retired) == 1 and first['last_snapshot_id'] in retired[0].parent.name
    assert core._run(source, root)['reason_code'] is None
    assert not retired[0].exists()
    assert set(copies(root)) == {result['last_snapshot_id']}


def selected(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'source.db'))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'DATABASE_PATH', db.db_path)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'copies'))
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    runtime.reset_for_tests()
    return db


def test_product_reset_pins_pre_snapshot_before_deleting(tmp_path, monkeypatch):
    db = selected(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'synthetic before reset')
    original = db._clear_all_data
    observed = []
    def inspect_before_delete(conn):
        pinned = state(tmp_path / 'copies')['reset_pins']
        assert len(pinned) == 1
        copy = namespace(tmp_path / 'copies') / 'snapshots' / next(iter(pinned)) / 'snapshot.db'
        with sqlite3.connect(copy) as check:
            assert check.execute('SELECT reason FROM coach_decisions').fetchone()[0] == 'synthetic before reset'
        with sqlite3.connect(db.db_path, timeout=0) as competing:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                competing.execute("INSERT INTO user_settings(key,value) VALUES ('other','writer')")
        observed.append(copy)
        return original(conn)
    monkeypatch.setattr(db, '_clear_all_data', inspect_before_delete)
    db.clear_all_data()
    assert observed and observed[0].exists()
    assert db.get_coach_decisions(days=36500) == []
    assert len(copies(tmp_path / 'copies')) == 2
    assert runtime.backup_status(db)['state'] == 'ready'


@pytest.mark.parametrize('failure', ['check', 'pin'])
def test_failed_reset_precondition_preserves_source(tmp_path, monkeypatch, failure):
    db = selected(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'must survive')
    if failure == 'check':
        monkeypatch.setattr(runtime, 'check_snapshot', lambda *a: runtime.empty_status('degraded', 'backup_io_error'))
    else:
        native = core._write_json
        def refuse_pin(path, value, **kwargs):
            if path.name == 'status.json' and value.get('reset_pins'):
                raise PermissionError('synthetic')
            return native(path, value, **kwargs)
        monkeypatch.setattr(runtime, 'check_snapshot', lambda source, root, reason: core._run(source, root, reason=reason))
        monkeypatch.setattr(core, '_write_json', refuse_pin)
    with pytest.raises(RuntimeError, match='очистк'):
        db.clear_all_data()
    assert db.get_coach_decisions(days=36500)[0]['reason'] == 'must survive'


def test_unknown_foreign_manual_artifacts_are_never_deleted(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    core._run(source, root)
    output = namespace(root) / 'snapshots'
    unknown = output / 'manual.db'
    unknown.write_bytes(b'operator owned')
    for key, version, identity in [('a' * 32, 99, namespace(root).name), ('b' * 32, 1, 'foreign')]:
        folder = output / key
        folder.mkdir()
        (folder / 'manifest.json').write_text(json.dumps({'version': version, 'source_namespace': identity}))
        (folder / 'snapshot.db').write_bytes(b'never adopt')
    before = {p: p.read_bytes() for p in output.rglob('*') if p.is_file() and p.name == 'manifest.json'}
    change(source, 99)
    assert core._run(source, root)['state'] == 'ready'
    assert unknown.read_bytes() == b'operator owned'
    for path, value in before.items():
        if path.parent.name in {'a' * 32, 'b' * 32}:
            assert path.read_bytes() == value


def test_post_reset_copy_failure_never_replays_or_undoes_reset(tmp_path, monkeypatch):
    db = selected(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'before reset')
    native = runtime.check_snapshot
    seen = []
    def check(source, root, reason):
        seen.append(reason)
        return runtime.empty_status('degraded', 'backup_io_error') if reason == 'post_reset' else native(source, root, reason)
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    db.clear_all_data()
    assert seen == ['pre_reset', 'post_reset']
    assert db.get_coach_decisions(days=36500) == []
    assert runtime.backup_status(db)['state'] == 'degraded'
    assert len(state(tmp_path / 'copies')['reset_pins']) == 1
    assert len(copies(tmp_path / 'copies')) == 1


def test_auto_snapshot_restore_in_fresh_app_preserves_domains_and_reset_rollback(tmp_path, monkeypatch):
    from tests.smoke.test_database_relocation_drill import _seed_domains, _app, _cli, _without_path
    from scripts.sqlite_backup_restore import inspect_relocation_database
    db = selected(tmp_path, monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(Settings, 'AUTO_BACKUP_ENABLED', False)
        metadata = _seed_domains(tmp_path / 'source.db')
    (tmp_path / 'legacy').mkdir()
    before = _app(tmp_path, tmp_path / 'source.db', metadata)
    baseline = inspect_relocation_database(tmp_path / 'source.db')
    db.clear_all_data()
    pinned = next(iter(state(tmp_path / 'copies')['reset_pins']))
    snapshot = namespace(tmp_path / 'copies') / 'snapshots' / pinned / 'snapshot.db'
    assert inspect_relocation_database(snapshot) == baseline
    after_reset = inspect_relocation_database(tmp_path / 'source.db')
    assert after_reset != baseline
    rollback = tmp_path / 'reset-rollback.db'
    _cli(tmp_path, 'restore', '--database', db.db_path, '--backup', snapshot,
         '--rollback-output', rollback, '--confirm-stopped')
    assert inspect_relocation_database(rollback) == after_reset
    assert inspect_relocation_database(tmp_path / 'source.db') == baseline
    assert _without_path(_app(tmp_path, tmp_path / 'source.db', metadata)) == _without_path(before)
    assert snapshot.exists() and pinned in state(tmp_path / 'copies')['reset_pins']


def test_iso_year_boundary_and_nonempty_periods(tmp_path, monkeypatch):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    dates = [datetime(2025, 12, 28, 23, tzinfo=timezone.utc), datetime(2025, 12, 29, tzinfo=timezone.utc),
             datetime(2026, 1, 4, 23, tzinfo=timezone.utc), datetime(2026, 1, 5, tzinfo=timezone.utc)]
    identities = []
    for index, instant in enumerate(dates):
        clock(monkeypatch, instant)
        change(source, 10 + index)
        identities.append(core._run(source, root)['last_snapshot_id'])
    assert len(copies(root)) == 4
    clock(monkeypatch, datetime(2027, 1, 1, tzinfo=timezone.utc))
    # No new generation just because many calendar days passed.
    assert core._run(source, root)['last_snapshot_id'] == identities[-1]
    assert len(copies(root)) == 4


def test_concurrent_pin_and_checks_keep_durable_protection(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    source, root = source_store(tmp_path), tmp_path / 'copies'
    first = core.check_snapshot(source, root, 'pre_reset')
    change(source, 67)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda reason: core.check_snapshot(source, root, reason), ['check', 'pre_reset', 'check']))
    assert all(row['state'] == 'ready' for row in results)
    assert len({row['last_snapshot_id'] for row in results}) == 1
    assert set(copies(root)) == {first['last_snapshot_id'], results[0]['last_snapshot_id']}
    assert set(state(root)['reset_pins']) == set(copies(root))


def test_failed_delete_transaction_keeps_original_and_pin(tmp_path, monkeypatch):
    db = selected(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'rollback original')
    def fail(conn):
        conn.execute('DELETE FROM coach_decisions')
        raise sqlite3.OperationalError('synthetic reset failure')
    monkeypatch.setattr(db, '_clear_all_data', fail)
    with pytest.raises(sqlite3.OperationalError):
        db.clear_all_data()
    assert db.get_coach_decisions(days=36500)[0]['reason'] == 'rollback original'
    assert len(state(tmp_path / 'copies')['reset_pins']) == 1
    assert len(copies(tmp_path / 'copies')) == 1


def test_pin_extension_never_shortens_existing_deadline(tmp_path, monkeypatch):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    clock(monkeypatch, BASE)
    first = core._run(source, root, reason='pre_reset')
    clock(monkeypatch, BASE - timedelta(hours=1))
    assert core._run(source, root, reason='pre_reset')['last_snapshot_id'] == first['last_snapshot_id']
    assert state(root)['reset_pins'][first['last_snapshot_id']] == (BASE + timedelta(days=14)).isoformat()


def test_missing_state_with_only_corrupt_history_keeps_pin_uncertainty(tmp_path):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    first = core._run(source, root, reason='pre_reset')
    folder = namespace(root)
    (folder / 'status.json').unlink()
    (folder / 'snapshots' / first['last_snapshot_id'] / 'snapshot.db').write_bytes(b'broken')
    result = core._run(source, root)
    assert result['state'] == 'ready'
    assert result['reason_code'] == 'backup_reset_pins_unknown'
    assert state(root)['reset_pins_unknown'] is True
    assert first['last_snapshot_id'] in copies(root)


def test_partial_retention_delete_is_resumed_after_file_was_unlinked(tmp_path, monkeypatch):
    import os
    source, root = source_store(tmp_path), tmp_path / 'copies'
    core._run(source, root)
    change(source, 47)
    native = os.unlink
    removed = []
    def interrupted(path, *args, **kwargs):
        result = native(path, *args, **kwargs)
        if not removed and os.path.basename(os.fspath(path)) == 'snapshot.db':
            removed.append(True)
            raise OSError('synthetic crash after unlink')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(os, 'unlink', interrupted)
        failed = core._run(source, root)
    assert removed and failed['state'] == 'ready'
    assert failed['reason_code'] == 'backup_retention_failed'
    retried = core._run(source, root)
    assert retried['state'] == 'ready'
    assert retried['reason_code'] is None
    assert retried['last_snapshot_id'] == failed['last_snapshot_id']


def test_selected_demo_reset_never_enters_real_backup_namespace(tmp_path, monkeypatch):
    db = selected(tmp_path, monkeypatch)
    db.set_user_setting('dataset_origin', 'demo')
    db.save_coach_decision('Monitor', 'demo only')
    assert not (tmp_path / 'copies').exists()
    db.clear_all_data()
    assert db.get_coach_decisions(days=36500) == []
    assert not (tmp_path / 'copies').exists()


def test_worker_crash_after_retired_db_unlink_can_resume_in_new_process(tmp_path):
    import os
    import subprocess
    import sys
    from scripts.scratch_pytest import child_environment
    source, root = source_store(tmp_path), tmp_path / 'copies'
    core.check_snapshot(source, root, 'initial')
    change(source, 83)
    code = '''
import os,sys
from pathlib import Path
from services import automatic_snapshots as core
native = Path.unlink
def stop_after_unlink(path, *args, **kwargs):
    result = native(path, *args, **kwargs)
    if path.name == 'snapshot.db' and path.parent.name.startswith('.retired-'):
        os._exit(74)
    return result
Path.unlink = stop_after_unlink
core._run(sys.argv[1], sys.argv[2])
'''
    child = subprocess.run([sys.executable, '-c', code, str(source), str(root)],
                           env=child_environment(os.environ), text=True, capture_output=True, timeout=15)
    assert child.returncode == 74, child.stderr
    retired = list((namespace(root) / 'snapshots').glob('.retired-*/manifest.json'))
    assert len(retired) == 1 and not (retired[0].parent / 'snapshot.db').exists()
    retried = core.check_snapshot(source, root, 'restart')
    assert retried['state'] == 'ready' and retried['reason_code'] is None
    assert not retired[0].exists()
    assert set(copies(root)) == {retried['last_snapshot_id']}


def test_deactivate_demo_on_selected_real_path_preserves_backup_isolation(tmp_path, monkeypatch):
    from services.demo_mode import deactivate_demo_mode
    from utils.app_state import make_headless_state
    db = selected(tmp_path, monkeypatch)
    state = make_headless_state()
    assert state.database.db_path == db.db_path  # Actual fallback lazy provider.
    db.set_user_setting('dataset_origin', 'demo')
    db.save_coach_decision('Monitor', 'demo only')
    state.demo_mode = True
    deactivate_demo_mode(state)
    assert not state.demo_mode
    assert db.get_coach_decisions(days=36500) == []
    assert not (tmp_path / 'copies').exists()


@pytest.mark.parametrize('metadata', [None, {'version': 99}, {'version': 1, 'source_namespace': 'foreign'}])
def test_unknown_retired_artifacts_are_not_cleanup_permission(tmp_path, metadata):
    source, root = source_store(tmp_path), tmp_path / 'copies'
    core._run(source, root)
    unknown = namespace(root) / 'snapshots' / ('.retired-' + 'a' * 32 + '-' + 'b' * 32)
    unknown.mkdir(mode=0o700)
    (unknown / 'operator.txt').write_text('keep unknown artifact')
    if metadata is not None:
        (unknown / 'manifest.json').write_text(json.dumps(metadata))
    change(source, 98)
    assert core._run(source, root)['state'] == 'ready'
    assert (unknown / 'operator.txt').read_text() == 'keep unknown artifact'
