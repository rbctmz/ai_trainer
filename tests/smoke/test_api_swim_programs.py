"""Public HTTP contract on owned SQLite, without launching the application."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from api.deps import get_database
from api.routers.swim_programs import router
from data.database import Database
from tests.smoke._swim_program_fixtures import PROGRAM_ID, example_program

pytestmark = pytest.mark.smoke


@pytest.fixture
def client(tmp_path):
    db = Database(str(tmp_path / "api.sqlite"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as handle:
        yield handle


def test_http_preview_confirm_and_readback(client):
    raw = example_program()
    response = client.post("/api/swim-programs/preview", json={"document": raw, "base_revision": 0})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["summary"]["distance_meters"] == 6100
    assert client.get("/api/swim-programs").json() == {"items": []}
    saved = client.post("/api/swim-programs/confirm", json={"preview_id": preview["preview_id"], "confirm": True})
    assert saved.status_code == 200, saved.text
    value = saved.json()
    assert value["document"]["source_text"] == raw["source_text"]
    assert client.get(f"/api/swim-programs/{PROGRAM_ID}").json() == value
    assert client.get(f"/api/swim-programs/{PROGRAM_ID}/versions/1").json() == value
    assert client.post("/api/swim-programs/confirm", json={"preview_id": preview["preview_id"], "confirm": True}).json() == value
    assert len(client.get("/api/swim-programs").json()["items"]) == 1


@pytest.mark.parametrize("payload", [
    {"document": {"source_text": "PRIVATE_CANARY"}, "base_revision": 0},
    {"document": example_program(), "base_revision": True},
    {"document": example_program(), "base_revision": 0, "PRIVATE_CANARY": "secret"},
])
def test_http_invalid_request_omits_private_input(client, payload):
    result = client.post("/api/swim-programs/preview", json=payload)
    assert result.status_code == 422
    assert "PRIVATE_CANARY" not in result.text and '"input"' not in result.text
    assert client.get("/api/swim-programs").json() == {"items": []}


@pytest.mark.parametrize("confirmation", [False, 1, "true"])
def test_confirm_requires_literal_boolean_true(client, confirmation):
    preview = client.post("/api/swim-programs/preview", json={"document": example_program(), "base_revision": 0}).json()
    result = client.post("/api/swim-programs/confirm", json={"preview_id": preview["preview_id"], "confirm": confirmation})
    assert result.status_code == 422
    assert client.get("/api/swim-programs").json() == {"items": []}


def test_http_stale_missing_and_corrupt_results_are_private(client):
    draft = client.post('/api/swim-programs/preview', json={'document': example_program(), 'base_revision': 0}).json()
    assert client.post('/api/swim-programs/confirm', json={'preview_id': draft['preview_id'], 'confirm': True}).status_code == 200
    stale = client.post('/api/swim-programs/preview', json={'document': example_program(), 'base_revision': 0})
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'swim_program_stale'
    missing = client.get(f'/api/swim-programs/{PROGRAM_ID}/versions/2')
    assert missing.status_code == 404
    db = client.app.dependency_overrides[get_database]()
    conn = db._connect()
    try:
        conn.execute('UPDATE swim_program_versions SET document_json=?', ('PRIVATE_CANARY',))
        conn.commit()
    finally:
        conn.close()
    corrupt = client.get(f'/api/swim-programs/{PROGRAM_ID}')
    assert corrupt.status_code == 503
    assert corrupt.json() == {'detail': {'code': 'swim_program_corrupt'}}
    assert 'PRIVATE_CANARY' not in corrupt.text


def test_routes_select_demo_store_without_touching_real_library(tmp_path, monkeypatch):
    from api import deps
    from config.settings import Settings
    real_path, demo_path = str(tmp_path / 'real.sqlite'), str(tmp_path / 'demo.sqlite')
    monkeypatch.setattr(Settings, 'DATABASE_PATH', real_path)
    monkeypatch.setattr(deps, 'DEMO_DB_PATH', demo_path)
    deps._reset_db_cache()
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as handle:
            draft = handle.post('/api/swim-programs/preview?demo=1', json={'document': example_program(), 'base_revision': 0}).json()
            saved = handle.post('/api/swim-programs/confirm?demo=1', json={'preview_id': draft['preview_id'], 'confirm': True})
            assert saved.status_code == 200, saved.text
            assert handle.get('/api/swim-programs').json() == {'items': []}
            assert len(handle.get('/api/swim-programs?demo=1').json()['items']) == 1
    finally:
        deps._reset_db_cache()


def test_nested_preview_matches_extracted_typescript_contract(client):
    import json
    from pathlib import Path
    from tests.contracts.conformance import validate
    artifact = json.loads((Path(__file__).parents[1] / 'contracts' / 'ts_contract.json').read_text())
    payload = client.post('/api/swim-programs/preview', json={'document': example_program(), 'base_revision': 0}).json()
    spec = artifact['types']['SwimProgramPreviewResponse']
    assert validate(payload, spec, artifact['types']) == []
    payload['document']['workouts'][2]['steps'][3]['steps'][0]['steps'][1]['seconds'] = 'invalid'
    assert validate(payload, spec, artifact['types'])  # Recursion/rest variants are actually checked.
