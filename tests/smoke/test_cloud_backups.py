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
        shutil.copytree(payload, self.remote)
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
        assert result['state'] == 'degraded'
        assert result['reason_code'] == 'cloud_local_backup_unavailable'
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
