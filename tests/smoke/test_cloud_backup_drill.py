"""Remote-only drill and independent upload/drill evidence, synthetic stores."""
from datetime import timedelta
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from services import cloud_backups as cloud
from tests.smoke.test_cloud_backups import FakeTransport, REMOTE_ID, factory, fixture_config, run, selection


class DrillTransport(FakeTransport):
    def latest_snapshot_id(self):
        self.calls.append('latest')
        return REMOTE_ID


def prepared(tmp_path):
    config, data, source, root = fixture_config(tmp_path)
    # Full real schema and valid domain fixture, rather than a two-table surrogate.
    source.unlink()
    from tests.smoke.test_database_relocation_drill import _seed_domains
    metadata = _seed_domains(source)
    from data.database import Database
    Database(str(source), initialize=False).set_user_setting('dataset_origin', 'real')
    fake = DrillTransport(tmp_path / 'remote')
    result = run(config, source, root, fake)
    assert result['state'] == 'ready', json.dumps(result)
    return config, data, source, root, fake, metadata


def drill(config, fake):
    return cloud._drill_once(config, transport_factory=factory(fake))


def test_drill_recovers_without_any_local_original_or_receipt(tmp_path, monkeypatch):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    source.unlink()
    shutil.rmtree(root)
    state_path = cloud.load_config(config).state_path
    state_path.unlink()
    fake.calls.clear()
    monkeypatch.setattr(cloud, '_binding', lambda *_a: pytest.fail('drill cannot require local source'))
    monkeypatch.setattr(cloud, '_selection', lambda: pytest.fail('drill cannot select/open local source'))
    result = drill(config, fake)
    assert result['last_drill_at'] and result['drill_warning'] is None
    assert result['last_verified_at'] is None and result['last_covered_check_at'] is None
    assert fake.calls == ['repository', 'latest', ('restore', REMOTE_ID)]
    assert not source.exists() and not root.exists()
    assert not list(config.parent.glob('drill-*'))
    assert 'remote_snapshot_id' not in result and str(tmp_path) not in json.dumps(result)


def test_hourly_job_still_runs_due_drill_when_local_source_is_lost(tmp_path):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    source.unlink()
    shutil.rmtree(root)
    cloud.load_config(config).state_path.unlink()
    fake.calls.clear()
    result = run(config, source, root, fake)
    assert result['state'] == 'degraded' and result['reason_code'] == 'cloud_local_backup_unavailable'
    assert result['last_drill_at'] and result['drill_warning'] is None
    assert result['last_verified_at'] is None and result['last_covered_check_at'] is None
    assert fake.calls == ['repository', 'latest', ('restore', REMOTE_ID)]
    assert not source.exists() and not root.exists()


@pytest.mark.parametrize('change', ['disabled', 'demo_path', 'foreign_source', 'foreign_root'])
def test_lost_source_hourly_drill_still_requires_selected_real_opt_in(tmp_path, change):
    config, _data, source, root = fixture_config(tmp_path)
    source.unlink()
    selected = selection(source, root)
    selected = replace(selected, **{
        'disabled': {'local_enabled': False},
        'demo_path': {'demo_database_path': str(source)},
        'foreign_source': {'database_path': str(tmp_path / 'foreign.db')},
        'foreign_root': {'backup_root': str(tmp_path / 'foreign-backups')},
    }[change])
    fake = DrillTransport(tmp_path / 'remote')
    result = cloud._run_once(config, selection=selected, transport_factory=factory(fake))
    assert result['reason_code'] == 'cloud_local_backup_unavailable'
    assert not fake.calls and not source.exists() and not root.exists()


@pytest.mark.parametrize('failure', ['restore', 'corrupt', 'foreign', 'wrong_repository'])
def test_failed_drill_retains_previous_success_and_never_uploads(tmp_path, failure):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    assert drill(config, fake)['drill_warning'] is None
    previous = json.loads(cloud.load_config(config).state_path.read_text())
    before = cloud.inspect_database(source)
    if failure == 'foreign':
        manifest = fake.remote / 'manifest.json'
        value = json.loads(manifest.read_text())
        value['source_namespace'] = 'f' * 64
        manifest.write_text(json.dumps(value))
    elif failure == 'wrong_repository':
        fake.repo_id = 'f' * 64
    else:
        fake.fail = failure
    fake.calls.clear()
    result = drill(config, fake)
    assert result['drill_warning'] == 'cloud_drill_failed'
    for key in ('last_drill_at', 'last_verified_at', 'last_covered_check_at', 'last_attempt_at'):
        assert result[key] == previous.get(key)
    assert 'backup' not in fake.calls and cloud.inspect_database(source) == before
    assert cloud.read_cloud_status(config, selection=selection(source, root))['drill_warning'] == 'cloud_drill_failed'


def test_hourly_run_drills_initially_and_after_thirty_days_only(tmp_path):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    result = cloud.read_cloud_status(config, selection=selection(source, root))
    assert result['last_drill_at'] and result['drill_warning'] is None
    fake.calls.clear()
    assert run(config, source, root, fake)['state'] == 'ready'
    assert 'latest' not in fake.calls
    now = cloud._now()
    state_path = cloud.load_config(config).state_path
    receipt = json.loads(state_path.read_text())
    receipt['last_drill_at'] = (now - timedelta(days=30)).isoformat()
    state_path.write_text(json.dumps(receipt))
    fake.calls.clear()
    assert cloud._instant(run(config, source, root, fake)['last_drill_at']) >= now
    assert fake.calls.count('latest') == 1


def test_drill_disabled_and_demo_never_load_credentials(tmp_path, monkeypatch):
    assert cloud._drill_once(tmp_path / 'absent')['state'] == 'disabled'
    monkeypatch.setattr(cloud, 'load_config', lambda *_a: pytest.fail('no owner config in demo'))
    assert cloud.run_cloud_drill(tmp_path / 'absent', demo=True)['state'] == 'disabled'


@pytest.mark.parametrize('condition', ['foreign_receipt', 'busy', 'receipt_write', 'inspection', 'interruption'])
def test_drill_refusals_preserve_source_and_remote(tmp_path, monkeypatch, condition):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    state_path = cloud.load_config(config).state_path
    previous = json.loads(state_path.read_text())
    before_source = cloud.inspect_database(source)
    before_remote = {p.name: p.read_bytes() for p in fake.remote.iterdir()}
    fake.calls.clear()
    if condition == 'foreign_receipt':
        state_path.write_text(json.dumps({**previous, 'source_namespace': 'f' * 64}))
        damaged = state_path.read_bytes()
        result = drill(config, fake)
        assert result['reason_code'] == 'cloud_identity_unknown' and not fake.calls
        assert state_path.read_bytes() == damaged
    elif condition == 'busy':
        with cloud.snapshots.namespace_lock(config.parent, deadline=time.monotonic() + 1):
            result = drill(config, fake)
        assert result['reason_code'] == 'cloud_busy' and not fake.calls
        assert json.loads(state_path.read_text()) == previous
    elif condition == 'receipt_write':
        def fail(*_a):
            raise cloud.CloudError('cloud_state_unwritable')
        monkeypatch.setattr(cloud, '_write_receipt', fail)
        result = drill(config, fake)
        assert result['reason_code'] == 'cloud_state_unwritable'
        assert json.loads(state_path.read_text()) == previous
    else:
        import services.cloud_backup_drill as domains
        def fail(*_a):
            raise (KeyboardInterrupt() if condition == 'interruption' else OSError('private synthetic canary'))
        monkeypatch.setattr(domains, 'verify_domains', fail)
        if condition == 'interruption':
            with pytest.raises(KeyboardInterrupt):
                drill(config, fake)
            interrupted = json.loads(state_path.read_text())
            assert interrupted == {**previous, 'drill_pending': True}
            assert cloud.read_cloud_status(config, selection=selection(source, root))['drill_warning'] == 'cloud_drill_failed'
        else:
            result = drill(config, fake)
            assert result['drill_warning'] == 'cloud_drill_failed'
            assert result['last_drill_at'] == previous['last_drill_at']
    assert cloud.inspect_database(source) == before_source
    assert before_remote == {p.name: p.read_bytes() for p in fake.remote.iterdir()}
    assert 'backup' not in fake.calls and not list(config.parent.glob('drill-*'))


def test_public_drill_worker_records_failure_without_source_or_selection(tmp_path):
    config, _data, source, root = fixture_config(tmp_path)
    source.unlink()
    result = cloud.run_cloud_drill(config)
    assert result['drill_warning'] == 'cloud_drill_failed'
    assert result['last_verified_at'] is None and result['last_drill_at'] is None
    assert not source.exists() and not root.exists()
    assert not list(config.parent.glob('attempt-*'))


def test_transient_drill_receipt_error_keeps_newly_verified_upload(tmp_path, monkeypatch):
    config, _data, source, root, fake, _metadata = prepared(tmp_path)
    state_path = cloud.load_config(config).state_path
    previous = json.loads(state_path.read_text())
    previous['last_drill_at'] = (cloud._now() - timedelta(days=31)).isoformat()
    state_path.write_text(json.dumps(previous))
    from data.database import Database
    Database(str(source), initialize=False).set_user_setting('new-upload-canary', 'synthetic')
    actual = cloud._write_receipt
    calls = []
    def transient(config, receipt):
        calls.append(receipt.copy())
        if len(calls) == 3:
            raise cloud.CloudError('cloud_state_unwritable')
        actual(config, receipt)
    monkeypatch.setattr(cloud, '_write_receipt', transient)
    result = run(config, source, root, fake)
    committed = json.loads(state_path.read_text())
    assert committed['snapshot_id'] != previous['snapshot_id']
    assert committed['last_verified_at'] == calls[1]['last_verified_at']
    assert result['last_verified_at'] == committed['last_verified_at']
    assert committed['last_drill_at'] == previous['last_drill_at']
    assert result['drill_warning'] == 'cloud_drill_failed'
    assert committed['reason_code'] is None


def test_combined_worker_timeout_in_drill_phase_keeps_upload_health(tmp_path, monkeypatch):
    import sys
    config, _data, source, root, _fake, _metadata = prepared(tmp_path)
    state_path = cloud.load_config(config).state_path
    previous = json.loads(state_path.read_text())
    # Simulate a child after its verified upload was durably committed.
    phase = {**previous, 'drill_pending': True}
    code = ('import time; from pathlib import Path; '
            f'Path({str(state_path)!r}).write_text({json.dumps(phase)!r}); time.sleep(60)')
    native = subprocess.Popen
    def hanging(_args, **kwargs):
        return native([sys.executable, '-c', code], **kwargs)
    monkeypatch.setattr(cloud.subprocess, 'Popen', hanging)
    monkeypatch.setattr(cloud, 'ATTEMPT_SECONDS', .3)
    # Public status uses explicit test selection, never the owner's source.
    monkeypatch.setattr(cloud, '_selection', lambda: selection(source, root))
    result = cloud.run_cloud_backup(config)
    receipt = json.loads(state_path.read_text())
    assert result['state'] == 'ready' and result['reason_code'] is None
    assert result['drill_warning'] == 'cloud_drill_failed'
    assert receipt['last_verified_at'] == previous['last_verified_at']
    assert receipt['last_drill_at'] == previous['last_drill_at']
    assert receipt['reason_code'] is None and receipt['drill_pending'] is False
    assert not list(config.parent.glob('attempt-*'))


def test_encrypted_native_drill_after_local_loss_preserves_fresh_domain_readers(tmp_path, monkeypatch):
    import services.cloud_backup_transport as transport
    import services.cloud_backup_drill as domains
    from scripts.scratch_pytest import child_environment
    from tests.smoke.test_database_relocation_drill import _app, _without_path, ORIGINAL, WAL_MARKER
    binary = shutil.which('restic') or ('/opt/homebrew/bin/restic' if Path('/opt/homebrew/bin/restic').exists() else None)
    if binary is None:
        pytest.skip('native restic not installed; no dependency download in tests')
    config, data, source, root, _fake, metadata = prepared(tmp_path)
    baseline = _app(tmp_path, source, metadata)
    assert baseline['checkpoint_id'] == metadata['checkpoint_id']
    assert baseline['activities'] == [ORIGINAL]
    assert baseline['match']['id'] == metadata['match_id']
    assert baseline['feedback']['id'] == metadata['feedback_id']
    assert baseline['readiness'][0]['id'] == metadata['readiness_id']
    assert baseline['decisions'][0]['reason'] == WAL_MARKER
    assert len(baseline['providers']) == 2 and len(baseline['manual']) == 1
    repo = tmp_path / 'encrypted-recovery-repo'
    env = child_environment({**cloud._child_env(), 'RESTIC_PASSWORD': 'synthetic-drill-password'})
    init = subprocess.run([binary, '-r', str(repo), 'init', '--repository-version', '2'],
                          env=env, capture_output=True, text=True, timeout=20)
    assert init.returncode == 0
    raw = subprocess.run([binary, '-r', str(repo), '--json', 'cat', 'config'],
                         env=env, capture_output=True, text=True, timeout=20)
    assert raw.returncode == 0
    data['expected_repository_id'] = json.loads(raw.stdout)['id']
    config.write_text(json.dumps(data))
    # Fake-repository receipt is foreign to the newly provisioned test repo.
    cloud.load_config(config).state_path.unlink()
    monkeypatch.setattr(transport, 'RESTIC_EXECUTABLE', binary)
    monkeypatch.setattr(transport, '_credentials', lambda *_a: ('synthetic', 'synthetic', 'synthetic-drill-password'))
    def local_factory(config, work, deadline):
        return transport.ResticTransport(replace(config, repository_url=str(repo)), work, deadline)
    result = cloud._run_once(config, selection=selection(source, root), transport_factory=local_factory)
    assert result['state'] == 'ready' and result['last_drill_at'], result
    source.unlink()
    for suffix in ('-wal', '-shm', '-journal'):
        Path(str(source) + suffix).unlink(missing_ok=True)
    shutil.rmtree(root)
    cloud.load_config(config).state_path.unlink()
    recovered = []
    actual = domains.verify_domains
    def fresh_readers(path):
        actual(path)
        first = _app(tmp_path, path, metadata)
        second = _app(tmp_path, path, metadata)
        assert _without_path(first) == _without_path(second) == _without_path(baseline)
        recovered.append(first)
    monkeypatch.setattr(domains, 'verify_domains', fresh_readers)
    started = time.monotonic()
    result = cloud._drill_once(config, transport_factory=local_factory)
    elapsed = time.monotonic() - started
    assert result['last_drill_at'] and result['drill_warning'] is None, result
    assert len(recovered) == 1 and elapsed < 30 * 60
    assert result['last_verified_at'] is None and result['last_covered_check_at'] is None
    assert not source.exists() and not root.exists()
    assert not list(config.parent.glob('drill-*'))
    print(f'synthetic encrypted full-domain recovery RTO={elapsed:.3f}s')
