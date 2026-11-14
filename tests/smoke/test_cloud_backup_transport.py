"""Offline adapter characterization; never consult owner's profile or Keychain."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from scripts.scratch_pytest import child_environment
from tests.smoke.test_cloud_backups import fixture_config, selection


def test_real_restic_local_roundtrip_uses_identical_adapter_without_cloud(tmp_path, monkeypatch):
    import services.cloud_backups as cloud
    import services.cloud_backup_transport as transport
    binary = shutil.which('restic') or ('/opt/homebrew/bin/restic' if Path('/opt/homebrew/bin/restic').exists() else None)
    if binary is None:
        pytest.skip('native restic optional in contributor CI; no download/install in tests')
    repo = tmp_path / 'encrypted-local-repository'
    env = child_environment({**os.environ, 'RESTIC_PASSWORD': 'synthetic-only-password'})
    initialized = subprocess.run([binary, '-r', str(repo), 'init', '--repository-version', '2'],
        env=env, capture_output=True, text=True, timeout=20)
    assert initialized.returncode == 0
    read = subprocess.run([binary, '-r', str(repo), 'cat', 'config'],
        env=env, capture_output=True, text=True, timeout=20)
    assert read.returncode == 0
    repo_id = json.loads(read.stdout)['id']
    config, data, source, root = fixture_config(tmp_path)
    data['expected_repository_id'] = repo_id
    config.write_text(json.dumps(data))
    monkeypatch.setattr(transport, 'RESTIC_EXECUTABLE', binary)
    monkeypatch.setattr(transport, '_credentials', lambda *_a: ('test-key', 'test-secret', 'synthetic-only-password'))
    def local_factory(config, work, deadline):
        return transport.ResticTransport(replace(config, repository_url=str(repo)), work, deadline)
    result = cloud._run_once(config, selection=selection(source, root), transport_factory=local_factory)
    assert result['state'] == 'ready'
    first = json.loads(cloud.load_config(config).state_path.read_text())['remote_snapshot_id']
    again = cloud._run_once(config, selection=selection(source, root), transport_factory=local_factory)
    assert again['state'] == 'ready'
    assert json.loads(cloud.load_config(config).state_path.read_text())['remote_snapshot_id'] == first
    assert (repo / 'config').read_bytes()[:16] != b'SQLite format 3\x00'


def test_transport_scrubs_inherited_secrets_and_never_passes_password_in_args(tmp_path, monkeypatch):
    import services.cloud_backups as cloud
    import services.cloud_backup_transport as transport
    config, _data, _source, _root = fixture_config(tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-canary')
    monkeypatch.setenv('AWS_SESSION_TOKEN', 'synthetic-token-canary')
    monkeypatch.setenv('RESTIC_PASSWORD_COMMAND', 'false')
    monkeypatch.setattr(transport, '_credentials', lambda *_a: ('synthetic-key', 'synthetic-secret', 'synthetic-password'))
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, 'restic 0.19.1 synthetic', '')
    monkeypatch.setattr(transport.subprocess, 'run', fake_run)
    adapter = transport.ResticTransport(cloud.load_config(config), tmp_path, time.monotonic() + 5)
    args, options = calls[0]
    assert 'synthetic-password' not in str(args)
    assert options['env']['RESTIC_PASSWORD'] == 'synthetic-password'
    for name in ('OPENAI_API_KEY', 'AWS_SESSION_TOKEN', 'RESTIC_PASSWORD_COMMAND'):
        assert name not in adapter.env


@pytest.mark.parametrize('code,reason', [(10, 'cloud_identity_unknown'), (11, 'cloud_busy'),
                                       (12, 'cloud_auth_failed'), (1, 'cloud_network_failed')])
def test_restic_failures_do_not_include_output_or_secret(tmp_path, monkeypatch, code, reason):
    import services.cloud_backups as cloud
    import services.cloud_backup_transport as transport
    config, _data, _source, _root = fixture_config(tmp_path)
    monkeypatch.setattr(transport, '_credentials', lambda *_a: ('synthetic-key', 'synthetic-secret', 'synthetic-password'))
    monkeypatch.setattr(transport.subprocess, 'run', lambda args, **_kw: subprocess.CompletedProcess(args, code, 'CANARY secret/path', 'CANARY secret/path'))
    with pytest.raises(cloud.CloudError) as caught:
        transport.ResticTransport(cloud.load_config(config), tmp_path, time.monotonic() + 5)
    assert str(caught.value) == reason and 'CANARY' not in str(caught.value)


def test_keychain_api_disables_interaction_and_restores_flag(monkeypatch):
    import services.cloud_backups as cloud
    import services.cloud_backup_transport as transport
    actions = []
    class Function:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    class Library:
        SecKeychainGetUserInteractionAllowed = Function(lambda pointer: setattr(pointer._obj, 'value', 1) or 0)
        SecKeychainSetUserInteractionAllowed = Function(lambda value: actions.append(int(getattr(value, 'value', value))) or 0)
        SecKeychainFindGenericPassword = Function(lambda *_a: -25308)
        SecKeychainItemFreeContent = Function(lambda *_a: 0)
    monkeypatch.setattr(transport.sys, 'platform', 'darwin')
    monkeypatch.setattr(transport.ctypes, 'CDLL', lambda *_a: Library())
    with pytest.raises(cloud.CloudError, match='^cloud_credentials_unavailable$'):
        transport._keychain_password('synthetic-only-service')
    assert actions == [0, 1]


@pytest.mark.parametrize('contents', [
    '[DEFAULT]\naws_access_key_id=canary\naws_secret_access_key=canary\n[synthetic-backups]\n',
    '[other-profile]\naws_access_key_id=canary\naws_secret_access_key=canary\n',
])
def test_credentials_refuse_profile_fallback_before_keychain(tmp_path, monkeypatch, contents):
    import services.cloud_backups as cloud
    import services.cloud_backup_transport as transport
    config, _data, _source, _root = fixture_config(tmp_path)
    home = tmp_path / 'synthetic-home'
    (home / '.aws').mkdir(parents=True)
    credentials = home / '.aws/credentials'
    credentials.write_text(contents)
    credentials.chmod(0o600)
    monkeypatch.setattr(transport.Path, 'home', lambda: home)
    monkeypatch.setattr(transport, '_keychain_password', lambda *_a: pytest.fail('no Keychain for invalid profile'))
    with pytest.raises(cloud.CloudError, match='^cloud_credentials_unavailable$'):
        transport._credentials(cloud.load_config(config))
