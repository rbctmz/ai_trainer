"""Remote-only drill and independent upload/drill evidence, synthetic stores."""
from datetime import timedelta
import json
import shutil

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


def test_hourly_run_drills_initially_and_after_thirty_days_only(tmp_path, monkeypatch):
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
    monkeypatch.setattr(cloud, '_now', lambda: now)
    fake.calls.clear()
    assert run(config, source, root, fake)['last_drill_at'] == now.isoformat()
    assert fake.calls.count('latest') == 1


def test_drill_disabled_and_demo_never_load_credentials(tmp_path, monkeypatch):
    assert cloud._drill_once(tmp_path / 'absent')['state'] == 'disabled'
    monkeypatch.setattr(cloud, 'load_config', lambda *_a: pytest.fail('no owner config in demo'))
    assert cloud.run_cloud_drill(tmp_path / 'absent', demo=True)['state'] == 'disabled'
