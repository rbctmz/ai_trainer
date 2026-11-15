"""Cloud GET must remain metadata-only even with enabled/missing stores."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config.settings import Settings
from services import cloud_backups as cloud
from tests.smoke.test_cloud_backups import fixture_config


@pytest.mark.parametrize('mode', ['enabled', 'lost_source', 'missing', 'demo', 'acceptance'])
def test_cloud_get_never_opens_source_or_initializes_dependencies(tmp_path, monkeypatch, mode):
    path, _data, source, root = fixture_config(tmp_path)
    if mode != 'enabled':
        source.unlink()
    monkeypatch.setattr(Settings, 'DATABASE_PATH', str(source))
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(root))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', mode == 'acceptance')
    monkeypatch.setattr(Settings, 'CLOUD_BACKUP_CONFIG', str(path if mode != 'missing' else tmp_path / 'absent'))
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    def forbidden(*_a, **_k):
        pytest.fail('cloud GET must not open SQLite, credentials, or network')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    from data.database import Database
    from api.routers import backup
    monkeypatch.setattr(Database, '__init__', forbidden)
    monkeypatch.setattr(backup, 'get_database', forbidden)
    import services.cloud_backup_transport as transport
    import socket
    monkeypatch.setattr(transport, '_credentials', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    if mode in {'demo', 'acceptance'}:
        monkeypatch.setattr(cloud, 'load_config', forbidden)
    client = TestClient(app)  # No lifespan: test this GET alone.
    response = client.get('/api/backup/cloud/status' + ('?demo=1' if mode == 'demo' else ''))
    assert response.status_code == 200, response.text
    from api.backup_contract import CloudBackupStatus
    result = CloudBackupStatus.model_validate(response.json())
    assert result.state == ({'enabled': 'unknown', 'lost_source': 'degraded'}.get(mode, 'disabled'))
    if mode == 'lost_source':
        assert result.reason_code == 'cloud_local_backup_unavailable'
    assert set(response.json()) == {'state', 'reason_code', 'last_attempt_at', 'last_verified_at',
                                    'last_covered_check_at', 'last_drill_at', 'drill_warning'}
    assert str(tmp_path) not in response.text
    assert source.exists() == (mode == 'enabled') and not root.exists()
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_cloud_contract_rejects_private_fields_and_unknown_reasons():
    from api.backup_contract import CloudBackupStatus
    from pydantic import ValidationError
    value = cloud._public('ready')
    for extra in ({'repository_id': 'CANARY'}, {'reason_code': '/private/secret'}):
        with pytest.raises(ValidationError):
            CloudBackupStatus.model_validate({**value, **extra})
    assert 'CANARY' not in json.dumps(value)
