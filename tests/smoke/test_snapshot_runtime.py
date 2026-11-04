"""M3 operation/lifecycle checks use only owned synthetic stores."""
from datetime import datetime, timedelta, timezone
import sqlite3

from config.settings import Settings
from data.database import Database
from services import snapshot_runtime as runtime


def enabled(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'source.db'))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(Settings, 'DATABASE_PATH', db.db_path)
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    runtime.reset_for_tests()
    return db


def test_committed_decision_is_in_snapshot_and_failure_never_undoes_it(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    row = db.save_coach_decision('Monitor', 'synthetic decision')
    status = runtime.backup_status(db)
    assert status['state'] == 'ready'
    copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
    assert len(copies) == 1
    with sqlite3.connect(copies[0]) as conn:
        assert conn.execute('SELECT reason FROM coach_decisions WHERE id=?', (row['id'],)).fetchone()[0] == 'synthetic decision'
    monkeypatch.setattr(runtime, 'check_snapshot', lambda *a: runtime.empty_status('degraded', 'backup_io_error'))
    saved = db.save_coach_decision('Monitor', 'saved despite backup failure')
    assert db.get_coach_decisions()[0]['id'] == saved['id']
    assert runtime.backup_status(db)['state'] == 'degraded'


def test_nested_writes_coalesce_and_partial_error_preserves_commits(tmp_path, monkeypatch):
    import pytest
    db = enabled(tmp_path, monkeypatch)
    calls = []
    def check(*args):
        calls.append(args)
        return runtime.empty_status('ready')
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    with pytest.raises(ValueError, match='business failed'):
        with runtime.backup_operation(db, 'outer'):
            db.save_coach_decision('Monitor', 'first')
            db.save_coach_decision('Monitor', 'second')
            raise ValueError('business failed')
    assert len(calls) == 1
    assert len(db.get_coach_decisions()) == 2


def test_daily_and_failure_retry_are_bounded_and_restart_checks(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    clock = [datetime(2026, 11, 4, 12, tzinfo=timezone.utc)]
    calls = []
    def check(*args):
        calls.append(args)
        return {**runtime.empty_status('degraded', 'backup_io_error'), 'last_checked_at': clock[0].isoformat()}
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    runner = runtime.BackupRuntime(db, now=lambda: clock[0])
    runner.check_due(startup=True)
    runner.check_due()
    runner.check('important')
    assert len(calls) == 1
    clock[0] += timedelta(seconds=60)
    runner.check_due()
    assert len(calls) == 2


def test_disabled_and_demo_never_attempt_snapshot(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    def forbidden(*args):
        raise AssertionError('snapshot forbidden')
    monkeypatch.setattr(runtime, 'check_snapshot', forbidden)
    assert runtime.backup_status(db, demo=True)['state'] == 'disabled'
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', False)
    db.save_coach_decision('Monitor', 'feature disabled')
    assert runtime.backup_status(db)['state'] == 'disabled'


def test_status_read_never_reuses_ready_after_receipt_corruption(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'ready')
    assert runtime.backup_status(db)['state'] == 'ready'
    state = next((tmp_path / 'backups').glob('*/status.json'))
    state.write_text('{broken')
    assert runtime.backup_status(db)['state'] == 'degraded'
    state.unlink()
    assert runtime.backup_status(db)['state'] == 'unknown'


def test_sync_snapshot_follows_final_audit_and_terminal_waits(tmp_path, monkeypatch):
    from api.sync_jobs import SyncJobManager
    import threading
    import time
    db = enabled(tmp_path, monkeypatch)
    manager = SyncJobManager()
    entered, release = threading.Event(), threading.Event()
    allow_sync = threading.Event()
    native = runtime.check_snapshot
    def blocking(*args):
        entered.set()
        assert release.wait(3)
        return native(*args)
    monkeypatch.setattr(runtime, 'check_snapshot', blocking)
    def run_sync(on_progress, *, capture_run_id):
        assert allow_sync.wait(3)
        db.set_user_setting('synthetic_sync', capture_run_id)
        return {'sync_state': 'succeeded', 'title': 'done'}
    # This happy-path test controls stages: initial status/provenance reads
    # finish before the writer. Busy provenance has its own fail-closed test.
    try:
        manager.start_or_get(days=1, run_sync=run_sync, db=db, source='intervals')
    finally:
        allow_sync.set()
    try:
        assert entered.wait(2), manager.status(db)
        assert manager.status(db)['sync_state'] == 'running'
    finally:
        release.set()
    deadline = time.monotonic() + 4
    while manager.status(db)['sync_state'] == 'running' and time.monotonic() < deadline:
        time.sleep(.01)
    terminal = manager.status(db)
    assert terminal['sync_state'] == 'succeeded'
    assert terminal['backup']['state'] == 'ready'
    copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
    assert len(copies) == 1
    with sqlite3.connect(copies[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM coach_decisions WHERE trigger='provider_sync'").fetchone()[0] == 1
        assert conn.execute("SELECT value FROM user_settings WHERE key='synthetic_sync'").fetchone()


def test_sync_backup_failure_keeps_provider_error_and_business_rows(tmp_path, monkeypatch):
    from api.sync_jobs import SyncJobManager
    import time
    db = enabled(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, 'check_snapshot', lambda *a: runtime.empty_status('degraded', 'backup_io_error'))
    for fail in (False, True):
        manager = SyncJobManager()
        def run_sync(on_progress, *, capture_run_id):
            db.set_user_setting('committed', 'yes')
            if fail:
                raise ValueError('provider failure')
            return {'sync_state': 'succeeded', 'notices': ['provider notice']}
        manager.start_or_get(days=1, run_sync=run_sync, db=db)
        deadline = time.monotonic() + 3
        while manager.status(db)['sync_state'] == 'running' and time.monotonic() < deadline:
            time.sleep(.01)
        result = manager.status(db)
        assert result['sync_state'] == ('failed' if fail else 'partial')
        assert result['backup']['state'] == 'degraded'
        assert result['warning_codes'] == ['backup_failed']
        assert db.get_user_setting('committed') == 'yes'
        if fail:
            assert result['error']['message'] == 'provider failure'
        else:
            assert result['result']['notices'][0] == 'provider notice'


def test_daily_external_changes_and_restart_recover_without_pending_flags(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    clock = [datetime.now(timezone.utc)]
    calls = []
    native = runtime.check_snapshot
    def check(*args):
        calls.append(args)
        return native(*args)
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    runner = runtime.BackupRuntime(db, now=lambda: clock[0])
    first = runner.check_due(startup=True)
    assert first['state'] == 'ready'
    runner.check_due()
    assert len(calls) == 1
    db.set_user_setting('external_write', 'new')
    clock[0] += timedelta(days=1)
    second = runner.check_due()
    assert second['last_snapshot_id'] != first['last_snapshot_id']
    db.set_user_setting('crash_gap', 'committed without a snapshot')
    restarted = runtime.BackupRuntime(db, now=lambda: clock[0])
    third = restarted.check_due(startup=True)
    assert third['last_snapshot_id'] != second['last_snapshot_id']
    before = list((tmp_path / 'backups').glob('*/snapshots/*/manifest.json'))
    clock[0] += timedelta(days=3)
    restarted.check_due()
    assert len(list((tmp_path / 'backups').glob('*/snapshots/*/manifest.json'))) == len(before)


def test_unknown_provenance_is_degraded_and_cannot_fail_committed_command(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, '_dataset_origin', lambda *a: (_ for _ in ()).throw(OSError('synthetic path /never/expose')))
    saved = db.save_coach_decision('Monitor', 'committed')
    assert saved['id']
    status = runtime.backup_status(db)
    assert status['state'] == 'degraded'
    assert '/never/expose' not in str(status)
    assert not (tmp_path / 'backups').exists()


def test_all_evidence_domains_and_distinct_handles_share_one_outer_snapshot(tmp_path, monkeypatch):
    from tests.smoke.test_database_relocation_drill import _seed_domains
    db = enabled(tmp_path, monkeypatch)
    with runtime.backup_operation(db, 'synthetic_shared_operation'):
        ids = _seed_domains(tmp_path / 'source.db')  # Creates a second handle on the same selected store.
    copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
    assert len(copies) == 1
    with sqlite3.connect(copies[0]) as conn:
        for table in ('planning_checkpoints', 'coach_decisions', 'plan_actual_matches', 'session_feedback', 'readiness_snapshots'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] > 0
        assert conn.execute('SELECT note FROM session_feedback WHERE id=?', (ids['feedback_id'],)).fetchone()[0] == 'Synthetic easy ride'


def test_plan_preview_never_snapshots_confirm_does_and_retry_preserves_receipt(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.deps import get_database
    from api.main import app
    from tests.smoke._planning_build_confirmation import seeded_db, pin_clock
    from tests.smoke.test_planning_build_commit import prepare
    pin_clock(monkeypatch)
    db = seeded_db(tmp_path, rested=True)
    monkeypatch.setattr(Settings, 'DATABASE_PATH', db.db_path)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    runtime.reset_for_tests()
    shown = prepare(db)
    assert not (tmp_path / 'backups').exists()
    app.dependency_overrides[get_database] = lambda: db
    try:
        client = TestClient(app)  # No lifespan: isolate this command from the startup snapshot.
        from uuid import uuid4
        rejected = client.post('/api/planning/build/confirm', json={'preview_id': str(uuid4()), 'confirm': True})
        assert rejected.status_code == 404
        assert not (tmp_path / 'backups').exists()  # No commit: token lookup is not a save.
        body = {'preview_id': shown['confirmation']['preview_id'], 'confirm': True}
        first = client.post('/api/planning/build/confirm', json=body)
        assert first.status_code == 200, first.text
        assert first.json()['backup']['state'] == 'ready'
        copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
        assert len(copies) == 1
        with sqlite3.connect(copies[0]) as conn:
            assert conn.execute('SELECT state FROM planning_build_previews WHERE preview_id=?', (body['preview_id'],)).fetchone()[0] == 'applied'
            assert conn.execute('SELECT COUNT(*) FROM planning_checkpoints').fetchone()[0] == 1
        repeated = client.post('/api/planning/build/confirm', json=body)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()['confirmation']['replayed']
        assert repeated.json()['plan_id'] == first.json()['plan_id']
        assert len(list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))) == 1
        conn = db._connect()
        try:
            import json
            receipt = json.loads(conn.execute('SELECT applied_response_json FROM planning_build_previews WHERE preview_id=?', (body['preview_id'],)).fetchone()[0])
        finally:
            conn.close()
        assert 'backup' not in receipt  # Live health never changes the durable business receipt.
        # The supported legacy/shared writer is protected without an API adapter.
        current = db.get_current_planning_checkpoint()
        checkpoint = {key: value for key, value in current.items() if key not in {'id', 'created_at'}}
        checkpoint['source'] = 'synthetic_shared_legacy'
        checkpoint['goal_plan_snapshot'] = {**checkpoint['goal_plan_snapshot'], 'checkpoint_parent_id': current['id']}
        legacy = db.save_planning_checkpoint(checkpoint, cycle_context=db.planning_write_context())
        latest_id = runtime.backup_status(db)['last_snapshot_id']
        latest = next((tmp_path / 'backups').glob(f'*/snapshots/{latest_id}/snapshot.db'))
        with sqlite3.connect(latest) as conn:
            assert conn.execute('SELECT MAX(id) FROM planning_checkpoints').fetchone()[0] == legacy['id']
        from tests.smoke.test_planning_cycle_build import close
        context = client.get('/api/planning/cycles/current').json()
        closed = close(client, context)
        assert closed.status_code == 200, closed.text
        assert closed.json()['backup']['state'] == 'ready'
        latest_id = closed.json()['backup']['last_snapshot_id']
        latest = next((tmp_path / 'backups').glob(f'*/snapshots/{latest_id}/snapshot.db'))
        with sqlite3.connect(latest) as conn:
            assert conn.execute('SELECT status FROM planning_cycles WHERE id=?', (context['cycle_id'],)).fetchone()[0] == 'closed'

    finally:
        app.dependency_overrides.pop(get_database, None)
        runtime.reset_for_tests()


def test_concurrent_runtime_checks_use_bounded_core_lock_without_skipping(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    db = enabled(tmp_path, monkeypatch)
    db.set_user_setting('committed', 'both callers must check this store')
    runner = runtime.get_runtime(db)
    anchor = db._connect()  # Keep source WAL identity stable during concurrent readers.
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(runner.check, ['command_one', 'command_two']))
    finally:
        anchor.close()
    assert all(status['state'] == 'ready' for status in statuses)
    assert statuses[0]['last_snapshot_id'] == statuses[1]['last_snapshot_id']
    assert len(list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))) == 1


def test_shared_feedback_correction_and_tombstone_each_protect_final_revision(tmp_path, monkeypatch):
    from api import session_feedback as service
    from tests.smoke.test_post_workout_feedback import _row, _template
    db = enabled(tmp_path, monkeypatch)
    monkeypatch.setattr(service, '_feedback_evidence_for_session', lambda *a, **kw: {
        'row': _row(), 'template': _template(), 'match_revision_id': None,
    })
    values = {'session_id': 'ats_quality', 'client_submission_fingerprint': 'm3-first',
              'completion_status': 'completed', 'completion_pct': 100,
              'session_rpe_1_10': 4, 'quality_rating_1_5': 4}
    at = datetime(2026, 7, 13, 9, tzinfo=timezone.utc)
    first = service.submit_session_feedback(db, values, now_utc=at)['feedback']
    first_copy = runtime.backup_status(db)['last_snapshot_id']
    corrected = service.correct_session_feedback(db, first['id'], {
        **values, 'client_submission_fingerprint': 'm3-correction', 'note': 'Synthetic correction',
    }, now_utc=at + timedelta(minutes=1))['feedback']
    corrected_copy = runtime.backup_status(db)['last_snapshot_id']
    removed = service.tombstone_session_feedback(db, corrected['id'], client_submission_fingerprint='m3-tombstone',
                                                 now_utc=at + timedelta(minutes=2))['feedback']
    copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
    assert len(copies) == 1  # Intermediate same-day copies may be pruned.
    assert len({first_copy, corrected_copy, runtime.backup_status(db)['last_snapshot_id']}) == 3
    status = runtime.backup_status(db)
    latest = next(copy for copy in copies if copy.parent.name == status['last_snapshot_id'])
    with sqlite3.connect(latest) as conn:
        rows = conn.execute('SELECT id,status,revision FROM session_feedback ORDER BY revision').fetchall()
        assert rows == [(first['id'], 'active', 1), (corrected['id'], 'active', 2), (removed['id'], 'tombstone', 3)]


def test_demo_provenance_acceptance_and_foreign_stores_cannot_enable_backup(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    def forbidden(*args):
        raise AssertionError('wrong backup selection')
    monkeypatch.setattr(runtime, 'check_snapshot', forbidden)
    db.set_user_setting('dataset_origin', 'demo')
    db.save_coach_decision('Monitor', 'demo only')
    assert runtime.backup_status(db)['state'] == 'disabled'
    db.set_user_setting('dataset_origin', 'real')
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', True)
    db.save_coach_decision('Monitor', 'acceptance only')
    assert runtime.backup_status(db)['state'] == 'disabled'
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    other = Database(str(tmp_path / 'foreign.db'))
    other.save_coach_decision('Monitor', 'another store')
    assert runtime.backup_status(other)['state'] == 'disabled'
    assert not (tmp_path / 'backups').exists()


def test_today_projection_can_persist_derivations_without_event_backup(tmp_path, monkeypatch):
    from api.today_snapshot import build_today_decision_snapshot
    db = enabled(tmp_path, monkeypatch)
    result = build_today_decision_snapshot(db)
    assert result['operational_state']['backup']['state'] == 'unknown'
    assert db.get_recovery_decisions()  # This read really exercised the derived audit writer.
    assert not (tmp_path / 'backups').exists()


def test_sync_backup_projection_is_consistent_and_idempotent():
    failure = runtime.empty_status('degraded', 'backup_io_error')
    payload = {'sync_state': 'succeeded', 'notices': ['provider notice'],
               'operational_state': {'backup': runtime.empty_status('ready'), 'sync_state': 'succeeded'}}
    projected = runtime.attach_sync_backup(payload, failure)
    assert projected['operational_state']['backup'] == projected['backup'] == failure
    assert projected['operational_state']['sync_state'] == projected['sync_state'] == 'partial'
    repeated = runtime.attach_sync_backup(projected, failure)
    assert repeated['notices'].count(runtime.WARNING) == 1
    assert repeated['warning_codes'] == ['backup_failed']


def test_current_failure_keeps_last_verified_copy_identity(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'known verified copy')
    before = runtime.backup_status(db)
    assert before['last_snapshot_id']
    monkeypatch.setattr(runtime, 'check_snapshot', lambda *a: runtime.empty_status('degraded', 'backup_identity_unknown'))
    db.save_coach_decision('Monitor', 'committed but copy failed')
    after = runtime.backup_status(db)
    assert after['state'] == 'degraded'
    assert after['last_snapshot_id'] == before['last_snapshot_id']
    assert after['last_snapshot_at'] == before['last_snapshot_at']


def test_fresh_application_process_captures_committed_gap_and_stops_own_timer(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    import sys
    from scripts.scratch_pytest import child_environment
    db = enabled(tmp_path, monkeypatch)
    db.save_coach_decision('Monitor', 'before process gap')
    before = runtime.get_runtime(db).check('pre_reset')  # Explicitly keep the baseline for this immutable-copy assertion.
    old = next((tmp_path / 'backups').glob(f"*/snapshots/{before['last_snapshot_id']}/snapshot.db"))
    db.set_user_setting('crash_gap', 'committed before fresh startup')
    env = child_environment({**os.environ, 'DATABASE_PATH': db.db_path,
                             'DEMO_DATABASE_PATH': str(tmp_path / 'demo.db'),
                             'AUTO_BACKUP_ENABLED': '1', 'BACKUP_DIR': str(tmp_path / 'backups'),
                             'ACCEPTANCE_MODE': '0', 'AI_TRAINER_E2E_SCOPE': '0'})
    code = '''
import json
from fastapi.testclient import TestClient
from api.main import app
from api.deps import real_database
from services.snapshot_runtime import get_runtime
with TestClient(app) as client:
    db = real_database()
    runner = get_runtime(db)
    response = client.get('/api/backup/status')
    assert response.status_code == 200
    assert runner._thread is not None and runner._thread.is_alive()
    assert db.get_user_setting('crash_gap') == 'committed before fresh startup'
assert not runner._thread.is_alive()
print(json.dumps(response.json()))
'''
    child = subprocess.run([sys.executable, '-c', code], env=env, text=True, capture_output=True, timeout=30)
    assert child.returncode == 0, child.stderr
    status = json.loads(child.stdout.splitlines()[-1])
    assert status['state'] == 'ready'
    assert status['last_snapshot_id'] != before['last_snapshot_id']
    latest = next((tmp_path / 'backups').glob(f"*/snapshots/{status['last_snapshot_id']}/snapshot.db"))
    with sqlite3.connect(latest) as conn:
        assert conn.execute("SELECT value FROM user_settings WHERE key='crash_gap'").fetchone()[0] == 'committed before fresh startup'
    with sqlite3.connect(old) as conn:
        assert conn.execute("SELECT value FROM user_settings WHERE key='crash_gap'").fetchone() is None


def test_delayed_caller_cannot_replace_a_later_verified_disk_receipt(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    db = enabled(tmp_path, monkeypatch)
    runner = runtime.get_runtime(db)
    published, release = Event(), Event()
    native = runtime.check_snapshot
    def check(source, root, reason):
        result = native(source, root, reason)
        if reason == 'first':
            published.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runner.check, 'first')
        try:
            assert published.wait(3)
            db.set_user_setting('later_generation', 'must remain latest')
            second = runner.check('second')
            assert second['state'] == 'ready'
        finally:
            release.set()
        old_result = first.result(timeout=3)
    assert old_result['last_snapshot_id'] != second['last_snapshot_id']
    assert runner.status()['last_snapshot_id'] == second['last_snapshot_id']


def test_status_provenance_does_not_open_the_product_writer_connection(tmp_path, monkeypatch):
    db = enabled(tmp_path, monkeypatch)
    def forbidden():
        raise AssertionError('status must not run writer pragmas')
    monkeypatch.setattr(db, '_connect', forbidden)
    assert runtime.backup_status(db)['state'] == 'unknown'


def test_locked_source_provenance_refuses_without_waiting_for_writer_timeout(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    db = enabled(tmp_path, monkeypatch)
    locker = sqlite3.connect(db.db_path)
    locker.execute('PRAGMA journal_mode=DELETE')
    locker.execute('BEGIN EXCLUSIVE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        check = pool.submit(runtime.backup_status, db)
        try:
            status = check.result(timeout=.5)
            assert status['state'] == 'degraded'
        finally:
            locker.rollback()
            locker.close()
    assert runtime.backup_status(db)['state'] == 'degraded'
    runner = runtime.get_runtime(db)
    runner.now = lambda: datetime.now(timezone.utc) + timedelta(seconds=61)
    assert runner.check('retry_after_unlock')['state'] == 'ready'


def test_delayed_ready_never_hides_newer_unpersisted_failure(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import services.automatic_snapshots as core
    db = enabled(tmp_path, monkeypatch)
    runner = runtime.get_runtime(db)
    published, release = Event(), Event()
    native = runtime.check_snapshot
    def check(source, root, reason):
        result = native(source, root, reason)
        if reason == 'first':
            published.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runner.check, 'first')
        try:
            assert published.wait(3)
            db.set_user_setting('later_generation', 'not protected yet')
            native_temp = core.tempfile.mkdtemp
            def no_space(*args, **kwargs):
                if kwargs.get('prefix') == '.attempt-':
                    raise OSError('synthetic ENOSPC')
                return native_temp(*args, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(core.tempfile, 'mkdtemp', no_space)
                failed = runner.check('second')
            assert failed['state'] == 'degraded'
        finally:
            release.set()
        assert first.result(timeout=3)['state'] == 'ready'
    assert runner.status()['state'] == 'degraded'
    assert runner.status()['last_checked_at'] == failed['last_checked_at']
    runner.now = lambda: datetime.now(timezone.utc) + timedelta(seconds=61)
    retried = runner.check_due()
    assert retried['state'] == 'ready'
    copy = next((tmp_path / 'backups').glob(f"*/snapshots/{retried['last_snapshot_id']}/snapshot.db"))
    with sqlite3.connect(copy) as conn:
        assert conn.execute("SELECT value FROM user_settings WHERE key='later_generation'").fetchone()[0] == 'not protected yet'
