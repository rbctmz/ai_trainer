"""Synthetic regression checks for scratch and operator entrypoints (#625 M3)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("override", ["ACCEPTANCE_DB_PATH", "DATABASE_PATH", "DEMO_DATABASE_PATH", "CHATS_DIR"])
def test_acceptance_refuses_external_database_before_doctor_or_server(tmp_path, override):
    sentinel = tmp_path / 'synthetic-user.db'
    sentinel.write_bytes(b'unchanged')
    marker = tmp_path / 'runtime-started'
    stub = tmp_path / 'runtime-stub'
    stub.write_text('#!/bin/sh\nprintf started > "$MARKER"\nexit 0\n')
    stub.chmod(0o700)
    env = dict(os.environ, ACCEPTANCE_ROOT=str(tmp_path / 'roots'), ACCEPTANCE_SKIP_DOCTOR='1',
               PYTHON_BIN=str(stub), STREAMLIT_BIN=str(stub), MARKER=str(marker))
    for key in ('DATABASE_PATH', 'DEMO_DATABASE_PATH', 'CHATS_DIR', 'ACCEPTANCE_DB_PATH'):
        env.pop(key, None)
    env[override] = str(sentinel)
    result = subprocess.run(['bash', str(ROOT / 'run_acceptance.sh')], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert 'scratch_target_unowned' in result.stderr
    assert not marker.exists()
    assert sentinel.read_bytes() == b'unchanged'
    assert str(sentinel) not in result.stdout + result.stderr


def test_acceptance_default_runs_in_owned_scope_and_cleans_it(tmp_path):
    marker = tmp_path / 'runtime-observation'
    stub = tmp_path / 'runtime-stub'
    stub.write_text('#!/bin/sh\nprintf "%s\\n%s\\n%s\\n" "$DATABASE_PATH" "$DEMO_DATABASE_PATH" "${GARMIN_PASSWORD-unset}" > "$MARKER"\n')
    stub.chmod(0o700)
    root = tmp_path / 'roots'
    root.mkdir()
    env = dict(os.environ, ACCEPTANCE_ROOT=str(root), ACCEPTANCE_SKIP_DOCTOR='1',
               PYTHON_BIN=str(stub), MARKER=str(marker), GARMIN_PASSWORD='synthetic-secret')
    for key in ('DATABASE_PATH', 'DEMO_DATABASE_PATH', 'CHATS_DIR', 'ACCEPTANCE_DB_PATH'):
        env.pop(key, None)
    result = subprocess.run(['bash', str(ROOT / 'run_acceptance.sh')], env=env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    db, demo, secret = marker.read_text().splitlines()
    assert Path(db).parent == Path(demo).parent
    assert Path(db).parent.parent == root
    assert secret == 'unset'
    assert not Path(db).parent.exists()


@pytest.mark.parametrize("mode", ["ACCEPTANCE_MODE", "AI_TRAINER_E2E_SCOPE"])
def test_acceptance_child_rechecks_environment_before_main(tmp_path, mode):
    import json
    import sys
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    marker = tmp_path / 'child-main-ran'
    env = dict(os.environ,
               AI_TRAINER_SCRATCH_SCOPE=json.dumps(scope.descriptor()),
               DATABASE_PATH=str(tmp_path / 'foreign.db'),
               DEMO_DATABASE_PATH=str(scope.root / 'demo.db'),
               CHATS_DIR=str(scope.root / 'chats'), MARKER=str(marker))
    env[mode] = '1'
    result = subprocess.run([sys.executable, '-c', 'import os; open(os.environ["MARKER"], "w").close()'],
                            env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert not marker.exists()
    assert not (tmp_path / 'foreign.db').exists()
    scope.cleanup()


def test_acceptance_reset_refuses_mismatched_store_before_delete(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from config.settings import Settings
    from config.database_paths import ScratchPathError
    from services import acceptance_mode

    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', True)
    sentinel = tmp_path / 'another.db'
    sentinel.write_bytes(b'unchanged')
    state = SimpleNamespace(database=SimpleNamespace(db_path=str(sentinel)), acceptance_bootstrapped=False)
    calls = []
    monkeypatch.setattr(acceptance_mode.demo_mode_service, 'activate_demo_mode', lambda _state: calls.append(True))
    with pytest.raises(ScratchPathError):
        acceptance_mode.reset_acceptance_dataset(state)
    assert calls == []
    assert not state.acceptance_bootstrapped
    assert sentinel.read_bytes() == b'unchanged'


@pytest.mark.skipif(os.name != 'posix', reason='process-group lifecycle requires POSIX')
def test_acceptance_starts_real_isolated_streamlit_health(tmp_path):
    import importlib.util
    import signal
    import socket
    import sys
    import time
    import urllib.error
    import urllib.request

    if importlib.util.find_spec('streamlit') is None:
        pytest.skip('streamlit is not installed')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    root = tmp_path / 'acceptance-roots'
    root.mkdir()
    env = dict(os.environ, ACCEPTANCE_ROOT=str(root), ACCEPTANCE_SKIP_DOCTOR='1',
               PYTHON_BIN=sys.executable, ACCEPTANCE_PORT=str(port))
    for key in ('DATABASE_PATH', 'DEMO_DATABASE_PATH', 'CHATS_DIR', 'ACCEPTANCE_DB_PATH'):
        env.pop(key, None)
    process = subprocess.Popen(['bash', str(ROOT / 'run_acceptance.sh')], env=env,
                               cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True, text=True)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                    if response.read() == b'ok':
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
        else:
            output = process.communicate(timeout=5)[0] if process.poll() is not None else '<process still running>'
            pytest.fail(f'isolated Streamlit health did not become ready: {output}')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_product_demo_path_cannot_overlap_real_future_sidecar(tmp_path, suffix):
    from config.database_paths import DatabasePathError, validate_demo_path

    real = tmp_path / 'future.db'
    with pytest.raises(DatabasePathError, match='database_demo_alias'):
        validate_demo_path(str(real), str(real) + suffix)
    assert list(tmp_path.iterdir()) == []


def test_direct_repair_apply_requires_operator_consent_before_preview_or_write(tmp_path, monkeypatch):
    from config.database_paths import ScratchPathError
    from scripts import backfill_activity_provider_links as operation
    from scripts import scratch_runtime

    target = tmp_path / 'synthetic-working.db'
    target.write_bytes(b'unchanged')
    monkeypatch.setattr(scratch_runtime, 'scope_from_environment', lambda: None)
    touched = []
    monkeypatch.setattr(operation, 'preview_provider_link_backfill', lambda *args: touched.append('preview'))
    monkeypatch.setattr(operation, 'Database', lambda *args: touched.append('database'))
    with pytest.raises(ScratchPathError, match='operator_confirmation_required'):
        operation.repair_database(target, apply=True, primary_source='garmin')
    assert touched == []
    assert target.read_bytes() == b'unchanged'


def test_network_backfill_requires_explicit_target_before_client_or_sqlite(monkeypatch):
    from scripts import backfill_intervals_distance as operation
    from scripts import scratch_runtime

    touched = []
    monkeypatch.setattr(scratch_runtime, 'scope_from_environment', lambda: None)
    monkeypatch.setattr(operation, 'get_client', lambda: touched.append('provider'))
    monkeypatch.setattr(operation.sqlite3, 'connect', lambda *args, **kwargs: touched.append('database'))
    assert operation.main() == 2
    assert touched == []


def test_operator_backup_must_match_selected_working_database(tmp_path, monkeypatch):
    from config.database_paths import ScratchPathError
    from config.maintenance_guard import validate_maintenance_target
    from data.database import Database
    from scripts import scratch_runtime
    from scripts.sqlite_backup_restore import backup_database

    target = tmp_path / 'synthetic-working.db'
    backup = tmp_path / 'synthetic-backup.db'
    Database(str(target))
    backup_database(target, backup, confirm_stopped=True)
    monkeypatch.setattr(scratch_runtime, 'scope_from_environment', lambda: None)
    validated = validate_maintenance_target(target, apply=True, confirmed=True, stopped=True, backup=backup)
    assert validated == target
    import sqlite3
    with sqlite3.connect(target) as connection:
        connection.execute("INSERT INTO user_settings (key, value) VALUES ('probe', 'changed')")
    with pytest.raises(ScratchPathError, match='operator_confirmation_required'):
        validate_maintenance_target(target, apply=True, confirmed=True, stopped=True, backup=backup)


@pytest.mark.parametrize('kind', ['provider', 'planning', 'bike', 'distance'])
def test_maintenance_cli_apply_requires_confirmation_before_write(tmp_path, monkeypatch, kind):
    from scripts import scratch_runtime
    from scripts import backfill_activity_provider_links, backfill_bike_hr_pairs
    from scripts import backfill_intervals_distance, repair_planning_materialization

    target = tmp_path / 'synthetic-working.db'
    target.write_bytes(b'unchanged')
    monkeypatch.setattr(scratch_runtime, 'scope_from_environment', lambda: None)
    calls = {'provider': backfill_activity_provider_links.main,
             'planning': repair_planning_materialization.main,
             'bike': backfill_bike_hr_pairs.main,
             'distance': backfill_intervals_distance.cli}
    assert calls[kind](['--database', str(target), '--apply']) == 2
    assert target.read_bytes() == b'unchanged'


def test_maintenance_previews_are_read_only_and_do_not_call_provider(tmp_path, monkeypatch):
    from data.database import Database
    from scripts import backfill_bike_hr_pairs, backfill_intervals_distance

    target = tmp_path / 'preview.db'
    Database(str(target))
    touched = []
    monkeypatch.setattr(backfill_intervals_distance, 'get_client', lambda: touched.append('provider'))
    assert backfill_bike_hr_pairs.main(['--database', str(target)]) == 0
    assert backfill_intervals_distance.cli(['--database', str(target)]) == 0
    assert touched == []
    missing = tmp_path / 'missing.db'
    assert backfill_bike_hr_pairs.main(['--database', str(missing)]) == 2
    assert not missing.exists()


@pytest.mark.parametrize('module_name', ['tests.e2e_acceptance_live', 'tests.e2e_acceptance_flows'])
def test_live_acceptance_credentials_require_explicit_opt_in(tmp_path, monkeypatch, module_name):
    import importlib

    module = importlib.import_module(module_name)
    (tmp_path / '.env').write_text('GARMIN_EMAIL=fake\nGARMIN_PASSWORD=fake\n')
    monkeypatch.chdir(tmp_path)
    touched = []
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: touched.append('read') or 'GARMIN_EMAIL=fake\nGARMIN_PASSWORD=fake')
    with pytest.raises(RuntimeError, match='operator_confirmation_required'):
        module.load_env_creds()
    assert touched == []


@pytest.mark.parametrize('module_name', ['tests.e2e_acceptance_live', 'tests.e2e_acceptance_flows'])
def test_live_acceptance_refuses_before_server_or_output_without_opt_in(tmp_path, monkeypatch, module_name):
    import importlib

    module = importlib.import_module(module_name)
    touched = []
    monkeypatch.setattr(module, 'SCREENSHOT_DIR', tmp_path / 'screenshots')
    monkeypatch.setattr(module, 'sync_playwright', lambda: touched.append('browser'))
    with pytest.raises(SystemExit) as error:
        module.main(['--base-url', 'http://127.0.0.1:1'])
    assert error.value.code == 2
    assert touched == []
    assert not (tmp_path / 'screenshots').exists()


@pytest.mark.parametrize(('module_name', 'function_name'), [
    ('tests.add_test_data', 'add_test_activities'),
    ('tests.add_test_data', 'add_test_hrv'),
    ('tests.add_test_hrv_data', 'add_test_hrv_data'),
    ('tests.add_training_data_for_correlation', 'add_realistic_training_data'),
])
def test_legacy_generators_never_use_implicit_working_database(monkeypatch, module_name, function_name):
    import importlib
    module = importlib.import_module(module_name)
    touched = []
    class Observed(Exception):
        pass
    def fake_database(*args):
        touched.append(args)
        raise Observed
    monkeypatch.setattr(module, 'Database', fake_database)
    with pytest.raises(Observed):
        getattr(module, function_name)()
    assert touched and len(touched[0]) == 1
    from scripts.scratch_runtime import scope_from_environment
    scope = scope_from_environment()
    assert Path(touched[0][0]).resolve().is_relative_to(scope.root)


def test_legacy_cleanup_direct_call_refuses_implicit_target_before_open(monkeypatch):
    from config.database_paths import ScratchPathError
    from tests import clean_database

    touched = []
    monkeypatch.setattr(clean_database.sqlite3, 'connect', lambda *args, **kwargs: touched.append('open'))
    with pytest.raises(ScratchPathError, match='operator_confirmation_required'):
        clean_database.clean_database(confirm=False)
    assert touched == []


def test_cleanup_preserves_hrv_without_separate_explicit_option(tmp_path):
    import sqlite3
    from data.database import Database
    from tests.clean_database import clean_database

    target = tmp_path / 'synthetic-clean.db'
    db = Database(str(target))
    db.save_hrv_data({'2026-10-01': {'rmssd': 45.0}})
    with sqlite3.connect(target) as conn:
        before = conn.execute('SELECT COUNT(*) FROM hrv_data').fetchone()[0]
    assert before > 0
    assert clean_database(confirm=False, database_path=target, apply=True)
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hrv_data').fetchone()[0] == before
    assert clean_database(confirm=False, database_path=target, apply=True, delete_all_hrv=True)
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hrv_data').fetchone()[0] == 0


def test_cleanup_preserves_non_test_identifier_with_similar_prefix(tmp_path):
    import sqlite3
    from data.database import Database
    from tests.clean_database import analyze_database, clean_database

    target = tmp_path / 'synthetic-prefix.db'
    Database(str(target))
    with sqlite3.connect(target) as conn:
        conn.executemany('INSERT INTO activities (activity_id, date, sport) VALUES (?, ?, ?)',
                         [('test_1', '2026-10-01', 'running'), ('testX1', '2026-10-01', 'running')])
    assert analyze_database(target)['test_activities'] == 1
    assert clean_database(confirm=False, database_path=target, apply=True)
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT activity_id FROM activities').fetchall() == [('testX1',)]


@pytest.mark.parametrize(('module_name', 'function_name'), [
    ('tests.add_test_data', 'add_test_activities'),
    ('tests.add_test_data', 'add_test_hrv'),
    ('tests.add_test_hrv_data', 'add_test_hrv_data'),
    ('tests.add_training_data_for_correlation', 'add_realistic_training_data'),
])
def test_generator_body_rejects_unvalidated_direct_path(monkeypatch, tmp_path, module_name, function_name):
    import importlib
    from config.database_paths import ScratchPathError

    module = importlib.import_module(module_name)
    touched = []
    monkeypatch.setattr(module, 'Database', lambda *args: touched.append(args))
    with pytest.raises(ScratchPathError, match='operator_confirmation_required'):
        getattr(module, function_name).__wrapped__(tmp_path / 'unvalidated.db')
    assert touched == []


def test_hrv_diagnostic_reports_sort_mismatch_without_exposing_rows(tmp_path):
    from data.database import Database
    from tests.check_hrv_table_sorting import check_data_types_and_sorting

    target = tmp_path / 'synthetic-hrv.db'
    db = Database(str(target))
    db.save_hrv_data({'2026-09-30': {'rmssd': 45}, '2026-10-01': {'rmssd': 46}})
    report = check_data_types_and_sorting(target)
    assert report['rows'] == 2
    assert report['formatted_sort_matches_chronological'] is False
    assert '2026-' not in str(report)


def test_live_sleep_sync_requires_confirmation_before_target_validation(monkeypatch):
    from tests import force_fresh_sync_test

    touched = []
    monkeypatch.setattr(force_fresh_sync_test, 'validate_maintenance_target', lambda *a, **kw: touched.append('target'))
    assert not force_fresh_sync_test.force_sync_yesterday('/unused', apply=True)
    assert touched == []


def test_confirmed_operator_repair_accepts_matching_synthetic_backup(tmp_path, monkeypatch):
    from data.database import Database
    from scripts import scratch_runtime
    from scripts.backfill_activity_provider_links import repair_database
    from scripts.sqlite_backup_restore import backup_database

    target = tmp_path / 'operator-test.db'
    backup = tmp_path / 'operator-test-backup.db'
    Database(str(target))
    backup_database(target, backup, confirm_stopped=True)
    monkeypatch.setattr(scratch_runtime, 'scope_from_environment', lambda: None)
    result = repair_database(target, apply=True, primary_source='garmin',
                             confirm_working_database=True, confirm_stopped=True, backup=backup)
    assert result['mode'] == 'apply'
    assert 'applied' in result


@pytest.mark.parametrize('module_name', [
    'scripts.backfill_activity_provider_links', 'scripts.repair_planning_materialization',
])
def test_maintenance_module_import_does_not_load_settings_before_gate(module_name):
    import subprocess
    import sys

    probe = ('import importlib, sys; importlib.import_module(sys.argv[1]); '
             "assert 'config.settings' not in sys.modules")
    result = subprocess.run([sys.executable, '-c', probe, module_name], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
