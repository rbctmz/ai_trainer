"""Server-owned backup API and safe additive operational contracts."""
import sqlite3
from fastapi.testclient import TestClient
from api.backup_contract import BackupStatus
from api.deps import get_database
from api.main import app
from api.operational_state import build_operational_state
from config.settings import Settings
from data.database import Database
from services import snapshot_runtime as runtime


def test_status_check_contract_and_foreign_path_refusal(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'selected.db'))
    monkeypatch.setattr(Settings, 'DATABASE_PATH', db.db_path)
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    runtime.reset_for_tests()
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app, backend_options={}) as client:
            status = client.get('/api/backup/status')
            assert status.status_code == 200
            assert BackupStatus.model_validate(status.json()).state == 'ready'  # lifespan startup
            before = db.get_database_stats()
            for body in ({'database_path': '/foreign/private.db'}, {'backup_root': '/foreign'}, {'confirm': True}):
                assert client.post('/api/backup/check', json=body).status_code == 422
            checked = client.post('/api/backup/check', json={})
            assert checked.status_code == 200
            assert checked.json()['state'] == 'ready'
            assert db.get_database_stats() == before
            assert str(tmp_path) not in checked.text
            assert client.post('/api/backup/check?demo=1', json={}).json()['state'] == 'disabled'
            assert client.get('/api/backup/status?demo=1').json()['state'] == 'disabled'
            assert build_operational_state(db, has_data=False)['backup']['state'] == 'ready'
            copies = list((tmp_path / 'backups').glob('*/snapshots/*/snapshot.db'))
            assert len(copies) == 1
            with sqlite3.connect(copies[0]) as conn:
                assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        app.dependency_overrides.pop(get_database, None)
        runtime.reset_for_tests()


def test_disabled_status_is_read_only(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'disabled.db'))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', False)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'never-created'))
    assert runtime.backup_status(db)['state'] == 'disabled'
    assert not (tmp_path / 'never-created').exists()


def test_disabled_backup_endpoints_do_not_initialize_selected_source(tmp_path, monkeypatch):
    source = tmp_path / 'not-opened.db'
    monkeypatch.setattr(Settings, 'DATABASE_PATH', str(source))
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', False)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'not-created'))
    client = TestClient(app)  # No application startup or other data request.
    assert client.get('/api/backup/status').json()['state'] == 'disabled'
    assert client.post('/api/backup/check', json={}).json()['state'] == 'disabled'
    assert not source.exists()
    assert not (tmp_path / 'not-created').exists()
