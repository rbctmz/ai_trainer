"""#754: synthetic cloud operator contract; no owner credentials or network."""
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

NOW = datetime(2026, 11, 14, 19, tzinfo=timezone.utc)
REPOSITORY_ID = 'a' * 64
REMOTE_ID = 'b' * 64


def module():
    return importlib.import_module('services.cloud_backups')


def fixture_config(tmp_path):
    from services.automatic_snapshots import _paths
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE activities(activity_id TEXT PRIMARY KEY,date TEXT,sport TEXT,duration_minutes REAL)')
        conn.execute("INSERT INTO activities VALUES ('synthetic','2026-11-14','run',20)")
        conn.execute('CREATE TABLE user_settings(key TEXT PRIMARY KEY,value TEXT)')
        conn.execute("INSERT INTO user_settings VALUES ('dataset_origin','real')")
    conn.close()
    root = tmp_path / 'backups'
    _, _, namespace = _paths(source, root)
    private = tmp_path / 'cloud'
    private.mkdir(mode=0o700)
    config = private / 'config.json'
    data = {'version': 1, 'enabled': True, 'database_path': str(source),
            'backup_root': str(root), 'source_namespace': namespace,
            'repository_url': 's3:https://s3.cloud.ru/ai-trainer-backups/test-only',
            'expected_repository_id': REPOSITORY_ID, 'aws_profile': 'test-only',
            'keychain_service': 'test-only'}
    config.write_text(json.dumps(data))
    config.chmod(0o600)
    return config, data, source, root


def selection(source, root, **changes):
    return module().CloudSelection(str(source), str(root), True, **changes)


class FakeTransport:
    def __init__(self, remote, *, fail=None, repo_id=REPOSITORY_ID):
        self.remote, self.fail, self.repo_id = remote, fail, repo_id
        self.calls = []

    def repository_id(self):
        self.calls.append('repository')
        return self.repo_id

    def backup(self, payload):
        self.calls.append('backup')
        if self.fail == 'backup':
            raise module().CloudError('cloud_network_failed')
        if self.remote.exists():
            shutil.rmtree(self.remote)
        self.remote.mkdir(mode=0o700)
        # Match real restic's explicit two-file upload, excluding SQLite sidecars
        # that readonly fingerprinting can materialize for a WAL-mode snapshot.
        for name in ('snapshot.db', 'manifest.json'):
            shutil.copy2(payload / name, self.remote / name)
        return REMOTE_ID

    def restore(self, snapshot_id, target):
        self.calls.append(('restore', snapshot_id))
        assert snapshot_id == REMOTE_ID
        if self.fail == 'restore':
            raise module().CloudError('cloud_auth_failed')
        shutil.copytree(self.remote, target)
        if self.fail == 'corrupt':
            (target / 'snapshot.db').write_bytes(b'corrupt synthetic object')


def factory(fake):
    return lambda *_args: fake


def run(config, source, root, fake, **kwargs):
    return module()._run_once(config, selection=selection(source, root),
                              transport_factory=factory(fake), **kwargs)


def test_missing_disabled_and_demo_never_open_source_or_start_transport(tmp_path, monkeypatch):
    cloud = module()
    monkeypatch.setattr(cloud, '_selection', lambda: pytest.fail('Settings selection not needed'))
    monkeypatch.setattr(sqlite3, 'connect', lambda *_a, **_k: pytest.fail('no SQLite open'))
    assert cloud.read_cloud_status(tmp_path / 'absent.json')['state'] == 'disabled'
    disabled = tmp_path / 'disabled.json'
    disabled.write_text(json.dumps({'version': 1, 'enabled': False}))
    disabled.chmod(0o600)
    assert cloud._run_once(disabled)['state'] == 'disabled'
    assert cloud.read_cloud_status(tmp_path / 'unknown.json', demo=True)['state'] == 'disabled'


@pytest.mark.parametrize('change', [
    {'enabled': 'false'}, {'version': 2}, {'aws_secret_access_key': 'CANARY-SECRET'},
    {'database_path': 'relative.db'}, {'repository_url': 's3:http://attacker.invalid/bucket'},
    {'repository_url': 's3:https://s3.cloud.ru/ai-trainer-backups/../escape'},
    {'expected_repository_id': 'bad'}, {'source_namespace': 'bad'},
])
def test_invalid_config_is_safe_and_does_not_start_transport(tmp_path, change):
    config, data, source, root = fixture_config(tmp_path)
    data.update(change)
    config.write_text(json.dumps(data))
    result = run(config, source, root, None)
    assert result['state'] == 'degraded'
    assert result['reason_code'] == 'cloud_config_invalid'
    assert 'CANARY' not in json.dumps(result) and str(tmp_path) not in json.dumps(result)
    assert not root.exists()


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'public'])
def test_config_identity_and_permissions_fail_closed(tmp_path, kind):
    config, _data, source, root = fixture_config(tmp_path)
    if kind == 'public':
        config.chmod(0o644)
    else:
        other = config.with_name('other.json')
        if kind == 'symlink':
            other.symlink_to(config)
        else:
            other.hardlink_to(config)
        config = other
    assert run(config, source, root, None)['reason_code'] == 'cloud_config_invalid'
    assert not root.exists()


def test_wrong_selected_source_and_local_disabled_refuse_before_copy(tmp_path):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    for selected in [cloud.CloudSelection(str(source), str(root), False),
                     cloud.CloudSelection(str(source.with_name('other.db')), str(root), True),
                     selection(source, root, acceptance=True)]:
        result = cloud._run_once(config, selection=selected, transport_factory=lambda *_a: pytest.fail('no transport'))
        assert result['state'] == ('disabled' if selected.acceptance else 'degraded')
        assert result['reason_code'] == (None if selected.acceptance else 'cloud_local_backup_unavailable')
    assert not root.exists()


def test_demo_dataset_refuses_before_local_backup(tmp_path):
    config, _data, source, root = fixture_config(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE user_settings SET value='demo'")
    conn.close()
    assert run(config, source, root, None)['reason_code'] == 'cloud_local_backup_unavailable'
    assert not root.exists()


def test_upload_requires_exact_readback_then_unchanged_retry_deduplicates(tmp_path):
    cloud = module()
    config, data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    first = run(config, source, root, fake)
    assert first['state'] == 'ready'
    assert fake.calls == ['repository', 'backup', ('restore', REMOTE_ID)]
    assert set(p.name for p in fake.remote.iterdir()) == {'snapshot.db', 'manifest.json'}
    manifest = json.loads((fake.remote / 'manifest.json').read_text())
    assert manifest['source_namespace'] == data['source_namespace']
    receipt = json.loads(cloud.load_config(config).state_path.read_text())
    assert receipt['remote_snapshot_id'] == REMOTE_ID
    assert receipt['sha256'] == manifest['sha256']
    assert receipt['last_covered_check_at'] == first['last_covered_check_at']
    fake.calls.clear()
    assert run(config, source, root, fake)['state'] == 'ready'
    assert fake.calls == ['repository', ('restore', REMOTE_ID)]
    assert not list(config.parent.glob('attempt-*'))


def test_raw_write_gets_fresh_snapshot_before_hourly_send(tmp_path):
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    assert run(config, source, root, fake)['state'] == 'ready'
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=42')
    conn.close()
    fake.calls.clear()
    assert run(config, source, root, fake)['state'] == 'ready'
    assert 'backup' in fake.calls
    with sqlite3.connect(fake.remote / 'snapshot.db') as conn:
        assert conn.execute('SELECT duration_minutes FROM activities').fetchone()[0] == 42


@pytest.mark.parametrize('failure,reason', [('backup', 'cloud_network_failed'), ('restore', 'cloud_auth_failed'),
                                          ('corrupt', 'cloud_snapshot_invalid')])
def test_failed_upload_or_readback_preserves_verified_receipt_and_source(tmp_path, failure, reason):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    before = run(config, source, root, fake)
    source_bytes = source.read_bytes()
    prior = json.loads(cloud.load_config(config).state_path.read_text())
    fake.fail = failure
    if failure == 'backup':
        with sqlite3.connect(source) as conn:
            conn.execute('UPDATE activities SET duration_minutes=43')
        conn.close()
        source_bytes = source.read_bytes()
    result = run(config, source, root, fake)
    assert result['state'] == 'degraded' and result['reason_code'] == reason
    assert result['last_verified_at'] == before['last_verified_at']
    assert source.read_bytes() == source_bytes
    state = json.loads(cloud.load_config(config).state_path.read_text())
    assert state['remote_snapshot_id'] == prior['remote_snapshot_id']
    assert state['sha256'] == prior['sha256']
    assert not list(config.parent.glob('attempt-*'))


def test_repository_mismatch_does_not_upload_or_adopt(tmp_path):
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote', repo_id='c' * 64)
    result = run(config, source, root, fake)
    assert result['reason_code'] == 'cloud_identity_unknown'
    assert fake.calls == ['repository']
    assert not fake.remote.exists()


def test_status_is_readonly_and_new_local_generation_is_stale(tmp_path, monkeypatch):
    from services.automatic_snapshots import check_snapshot
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    first = run(config, source, root, fake)
    selected = selection(source, root)
    fake.calls.clear()
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, 'connect', lambda *_a, **_k: pytest.fail('status must not open SQLite'))
        assert cloud.read_cloud_status(config, selection=selected)['state'] == 'ready'
        after = datetime.fromisoformat(first['last_verified_at']) + timedelta(hours=25)
        assert cloud.read_cloud_status(config, selection=selected, now=after)['state'] == 'stale'
    assert fake.calls == []
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE activities SET duration_minutes=50')
    conn.close()
    assert check_snapshot(source, root, 'synthetic-new')['state'] == 'ready'
    assert cloud.read_cloud_status(config, selection=selected)['state'] == 'stale'


def test_foreign_or_corrupt_state_never_becomes_ready(tmp_path):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    assert run(config, source, root, fake)['state'] == 'ready'
    state_path = cloud.load_config(config).state_path
    state = json.loads(state_path.read_text())
    state['repository_id'] = 'd' * 64
    state_path.write_text(json.dumps(state))
    fake.calls.clear()
    assert cloud.read_cloud_status(config, selection=selection(source, root))['state'] == 'degraded'
    assert run(config, source, root, fake)['state'] == 'degraded'
    assert fake.calls == []


def test_stage_is_independent_of_original_before_transport(tmp_path):
    from services.automatic_snapshots import namespace_lock
    config, data, source, root = fixture_config(tmp_path)
    namespace = root / data['source_namespace']
    fake = FakeTransport(tmp_path / 'fake-remote')
    original_backup = fake.backup
    def remove_originals(payload):
        # The local namespace lock must already be free before any network call.
        import time
        with namespace_lock(namespace, deadline=time.monotonic() + .1):
            for directory in (namespace / 'snapshots').iterdir():
                if directory.is_dir():
                    shutil.rmtree(directory)
        return original_backup(payload)
    fake.backup = remove_originals
    assert run(config, source, root, fake)['state'] in {'ready', 'stale'}
    assert (fake.remote / 'snapshot.db').exists()


def test_launchagent_template_has_hourly_calendar_and_no_secrets():
    import plistlib
    path = Path(__file__).resolve().parents[2] / 'deploy/macos/ai-trainer-cloud-backup.plist.example'
    content = plistlib.loads(path.read_bytes())
    assert content['StartCalendarInterval'] == {'Minute': 0}
    assert content['RunAtLoad'] is True
    assert not content.get('KeepAlive')
    assert 'RESTIC_PASSWORD' not in str(content)
    assert 'run' in content['ProgramArguments'] and '--config' in content['ProgramArguments']


def test_failure_receipt_is_written_while_repository_lock_is_held(tmp_path, monkeypatch):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote', fail='backup')
    original = cloud._write_receipt
    def assert_locked(config, value):
        import fcntl
        descriptor = (config.path.parent / 'lock').open('rb')
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            descriptor.close()
        return original(config, value)
    monkeypatch.setattr(cloud, '_write_receipt', assert_locked)
    assert run(config, source, root, fake)['reason_code'] == 'cloud_network_failed'


def test_missing_dataset_provenance_is_safe_not_a_traceback(tmp_path):
    config, _data, source, root = fixture_config(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute('DROP TABLE user_settings')
    conn.close()
    result = run(config, source, root, None)
    assert result['reason_code'] == 'cloud_local_backup_unavailable'
    assert not root.exists()


@pytest.mark.parametrize('field', ['last_verified_at', 'last_covered_check_at', 'last_drill_at'])
def test_future_receipt_times_are_not_ready(tmp_path, field):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    run(config, source, root, fake)
    path = cloud.load_config(config).state_path
    state = json.loads(path.read_text())
    state[field] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    path.write_text(json.dumps(state))
    assert cloud.read_cloud_status(config, selection=selection(source, root))['state'] == 'degraded'


def test_busy_caller_does_not_overwrite_active_attempt(tmp_path):
    from services.automatic_snapshots import namespace_lock
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    run(config, source, root, fake)
    path = cloud.load_config(config).state_path
    before = path.read_bytes()
    with namespace_lock(config.parent):
        result = run(config, source, root, fake)
    assert result['reason_code'] == 'cloud_busy' and path.read_bytes() == before


def test_receipt_publish_failure_preserves_previous_success(tmp_path, monkeypatch):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    fake = FakeTransport(tmp_path / 'fake-remote')
    before = run(config, source, root, fake)
    def fail(*_args):
        raise cloud.CloudError('cloud_state_unwritable')
    monkeypatch.setattr(cloud, '_write_receipt', fail)
    result = run(config, source, root, fake)
    assert result['reason_code'] == 'cloud_state_unwritable'
    assert result['last_verified_at'] == before['last_verified_at']


def test_disabled_cli_starts_without_settings_or_database(tmp_path):
    import os
    import subprocess
    import sys
    from scripts.scratch_pytest import child_environment
    command = Path(__file__).resolve().parents[2] / 'scripts/cloud_backup.py'
    missing = tmp_path / 'no-config.json'
    result = subprocess.run([sys.executable, str(command), 'status', '--config', str(missing)],
        env=child_environment(os.environ), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert json.loads(result.stdout)['state'] == 'disabled'
    assert not missing.exists()


def test_fresh_status_preserves_previous_dates_when_local_backup_disabled(tmp_path):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    before = run(config, source, root, FakeTransport(tmp_path / 'fake-remote'))
    selected = cloud.CloudSelection(str(source), str(root), False)
    after = cloud.read_cloud_status(config, selection=selected)
    assert after['state'] == 'degraded'
    assert after['last_verified_at'] == before['last_verified_at']


def test_acceptance_refuses_before_even_reading_owner_config(monkeypatch):
    cloud = module()
    monkeypatch.setenv('ACCEPTANCE_MODE', '1')
    monkeypatch.setattr(cloud, 'load_config', lambda *_a: pytest.fail('must not read config'))
    assert cloud.run_cloud_backup('/not-an-owned-config')['state'] == 'disabled'
    assert cloud.read_cloud_status('/not-an-owned-config')['state'] == 'disabled'


def test_timeout_kills_process_group_cleans_its_work_and_persists_failure(tmp_path, monkeypatch):
    import subprocess
    import sys
    import time
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    before = run(config, source, root, FakeTransport(tmp_path / 'fake-remote'))
    native = subprocess.Popen
    marker = tmp_path / 'must-not-be-written'
    ready = tmp_path / 'grandchild-started'
    child_code = f'import time; from pathlib import Path; Path({str(ready)!r}).write_text("ready"); time.sleep(1.5); Path({str(marker)!r}).write_text("orphan")'
    code = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child_code!r}]); time.sleep(60)'
    def slow(_args, **kwargs):
        process = native([sys.executable, '-c', code], **kwargs)
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists()
        return process
    monkeypatch.setattr(cloud.subprocess, 'Popen', slow)
    monkeypatch.setattr(cloud, 'ATTEMPT_SECONDS', .15)
    result = cloud.run_cloud_backup(config)
    assert result['reason_code'] == 'cloud_timeout'
    assert result['last_verified_at'] == before['last_verified_at']
    time.sleep(1.6)
    assert not marker.exists()
    assert not list(config.parent.glob('attempt-*'))
    state = json.loads(cloud.load_config(config).state_path.read_text())
    assert state['pending'] is False and state['reason_code'] == 'cloud_timeout'


def test_stage_timeout_has_no_network_and_keeps_source(tmp_path, monkeypatch):
    import subprocess
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    source_bytes = source.read_bytes()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('synthetic', 10)
    monkeypatch.setattr(cloud.subprocess, 'run', timeout)
    result = cloud._run_once(config, selection=selection(source, root),
        transport_factory=lambda *_a: pytest.fail('no transport after stage timeout'))
    assert result['reason_code'] == 'cloud_timeout'
    assert source.read_bytes() == source_bytes
    assert not list(config.parent.glob('attempt-*'))


def test_replaced_work_root_is_preserved_instead_of_deleted(tmp_path):
    cloud = module()
    old = None
    with pytest.raises(cloud.CloudError, match='cloud_identity_unknown'):
        with cloud._owned_work(tmp_path, prefix='attempt-') as work:
            old = work.with_name('old-owned-root')
            work.rename(old)
            work.mkdir()
            (work / 'foreign-sentinel').write_text('keep')
    assert old is not None and old.exists()
    assert (work / 'foreign-sentinel').read_text() == 'keep'


def test_worker_environment_preserves_scratch_guard_without_provider_secrets(monkeypatch):
    cloud = module()
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-secret')
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'synthetic-wrong-owner')
    monkeypatch.setenv('RESTIC_PASSWORD', 'synthetic-wrong-password')
    child = cloud._child_env()
    assert 'AI_TRAINER_SCRATCH_SCOPE' in child
    assert all(key not in child for key in ('OPENAI_API_KEY', 'AWS_ACCESS_KEY_ID', 'RESTIC_PASSWORD'))


def test_dataset_switch_during_snapshot_refuses_before_network(tmp_path, monkeypatch):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    original = cloud.snapshots.check_snapshot
    def switched(*args):
        with sqlite3.connect(source) as conn:
            conn.execute("UPDATE user_settings SET value='demo'")
        conn.close()
        return original(*args)
    monkeypatch.setattr(cloud.snapshots, 'check_snapshot', switched)
    fake = FakeTransport(tmp_path / 'fake-remote')
    assert run(config, source, root, fake)['state'] == 'degraded'
    assert fake.calls == [] and not fake.remote.exists()


def test_config_change_during_snapshot_cannot_change_stage_binding(tmp_path, monkeypatch):
    cloud = module()
    config, data, source, root = fixture_config(tmp_path)
    original = cloud.snapshots.check_snapshot
    def changed(*args):
        result = original(*args)
        data['aws_profile'] = 'changed-profile'
        config.write_text(json.dumps(data))
        return result
    monkeypatch.setattr(cloud.snapshots, 'check_snapshot', changed)
    fake = FakeTransport(tmp_path / 'fake-remote')
    assert run(config, source, root, fake)['state'] == 'degraded'
    assert fake.calls == [] and not fake.remote.exists()


def test_enabled_public_worker_stages_before_refusing_missing_synthetic_credentials(tmp_path, monkeypatch):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    monkeypatch.setenv('DATABASE_PATH', str(source))
    monkeypatch.setenv('BACKUP_DIR', str(root))
    monkeypatch.setenv('AUTO_BACKUP_ENABLED', '1')
    monkeypatch.delenv('ACCEPTANCE_MODE', raising=False)
    result = cloud.run_cloud_backup(config)
    assert result['reason_code'] == 'cloud_credentials_unavailable'
    state = cloud.snapshots.read_snapshot_status(source, root)
    assert state['state'] == 'ready'
    assert not list(config.parent.glob('attempt-*'))


@pytest.mark.parametrize('bad_time', [123, [], {}])
def test_corrupt_timestamp_type_returns_safe_degraded_status(tmp_path, bad_time):
    cloud = module()
    config, data, source, root = fixture_config(tmp_path)
    receipt = {'version': 1, 'repository_id': data['expected_repository_id'],
               'source_namespace': data['source_namespace'], 'last_attempt_at': bad_time}
    path = cloud.load_config(config).state_path
    path.write_text(json.dumps(receipt))
    path.chmod(0o600)
    result = cloud.read_cloud_status(config, selection=selection(source, root))
    assert result['state'] == 'degraded' and result['reason_code'] == 'cloud_identity_unknown'


@pytest.mark.parametrize('change', [{'version': 999}, {'source_namespace': 'f' * 64},
    {'snapshot_id': 'e' * 32}, {'integrity_check': 'failed'}, {'size': -1},
    {'fingerprint': {}}, {'created_at_utc': 123}])
def test_status_rejects_foreign_or_corrupt_local_manifest_metadata(tmp_path, change):
    cloud = module()
    config, _data, source, root = fixture_config(tmp_path)
    assert run(config, source, root, FakeTransport(tmp_path / 'fake-remote'))['state'] == 'ready'
    receipt = json.loads(cloud.load_config(config).state_path.read_text())
    path = root / cloud.load_config(config).source_namespace / 'snapshots' / receipt['snapshot_id'] / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest.update(change)
    path.write_text(json.dumps(manifest))
    assert cloud.read_cloud_status(config, selection=selection(source, root))['state'] != 'ready'
