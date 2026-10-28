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


def test_acceptance_child_rechecks_environment_before_main(tmp_path):
    import json
    import sys
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    marker = tmp_path / 'child-main-ran'
    env = dict(os.environ, ACCEPTANCE_MODE='1',
               AI_TRAINER_SCRATCH_SCOPE=json.dumps(scope.descriptor()),
               DATABASE_PATH=str(tmp_path / 'foreign.db'),
               DEMO_DATABASE_PATH=str(scope.root / 'demo.db'),
               CHATS_DIR=str(scope.root / 'chats'), MARKER=str(marker))
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
