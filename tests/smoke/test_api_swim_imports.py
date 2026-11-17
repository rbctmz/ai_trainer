"""The source→draft→edit→human-save journey without a provider or personal DB."""

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.deps import get_database
from api.routers.swim_imports import router
from api.routers.swim_programs import router as library_router
from data.database import Database
from tests.smoke._swim_import_fixtures import SOURCE
from tests.smoke.test_swim_import_store import content

pytestmark = pytest.mark.smoke


@pytest.fixture
def client(tmp_path):
    db = Database(str(tmp_path / "api-import.sqlite"))
    app = FastAPI()
    app.include_router(router)
    app.include_router(library_router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as handle:
        yield handle


def _create(client, suffix=""):
    request = {"source_text": SOURCE, "request_id": str(uuid4())}
    result = client.post("/api/swim-imports" + suffix, json=request)
    assert result.status_code == 200, result.text
    return result.json()


def _roundtrip(client):
    empty = _create(client)
    url = f"/api/swim-imports/{empty['import_id']}"
    assert client.get(url).json() == empty and empty["document"] is None
    initial = {"expected_revision": 0, "request_id": str(uuid4()), "content": content()}
    parsed = client.post(url + "/parse", json=initial)
    assert parsed.status_code == 200, parsed.text
    draft = parsed.json()
    first = client.post(
        url + "/preview",
        json={
            "draft_revision": 1,
            "base_library_revision": 0,
            "request_id": str(uuid4()),
        },
    )
    assert first.status_code == 200, first.text
    command = {
        "expected_revision": 1,
        "request_id": str(uuid4()),
        "operation": {"op": "set_title", "title": "Reviewed program"},
    }
    changed = client.post(url + "/patch", json=command)
    assert changed.status_code == 200, changed.text
    assert client.post(url + "/patch", json=command).json() == changed.json()
    assert client.get(url + "/revisions/1").json() == draft
    rejected = client.post(
        "/api/swim-programs/confirm",
        json={"preview_id": first.json()["preview_id"], "confirm": True},
    )
    assert rejected.status_code == 409
    preview = client.post(
        url + "/preview",
        json={
            "draft_revision": 2,
            "base_library_revision": 0,
            "request_id": str(uuid4()),
        },
    )
    assert preview.status_code == 200, preview.text
    saved = client.post(
        "/api/swim-programs/confirm",
        json={"preview_id": preview.json()["preview_id"], "confirm": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["document"] == changed.json()["document"]
    assert saved.json()["summary"]["distance_meters"] is None
    assert (
        client.get(f"/api/swim-programs/{empty['program_id']}").json() == saved.json()
    )
    assert client.get("/api/swim-imports").json()["items"] == [changed.json()]
    return changed.json(), preview.json(), saved.json(), initial, command


def test_full_http_journey(client):
    _roundtrip(client)


@pytest.mark.parametrize(
    "replacement",
    [
        {"actor": "coach"},
        {"source_text": "PRIVATE_CANARY"},
        {"id": "PRIVATE_CANARY"},
        {"source_sha256": "PRIVATE_CANARY"},
    ],
)
def test_parse_cannot_replace_trusted_source_or_identity(client, replacement):
    draft = _create(client)
    result = client.post(
        f"/api/swim-imports/{draft['import_id']}/parse",
        json={
            "expected_revision": 0,
            "request_id": str(uuid4()),
            "content": {**content(), **replacement},
        },
    )
    assert result.status_code == 422
    assert "PRIVATE_CANARY" not in result.text and '"input"' not in result.text
    assert client.get(f"/api/swim-imports/{draft['import_id']}").json() == draft


def test_safe_validation_missing_and_corruption(client):
    bad = client.post(
        "/api/swim-imports", json={"source_text": "PRIVATE_CANARY", "request_id": "bad"}
    )
    assert bad.status_code == 422 and "PRIVATE_CANARY" not in bad.text
    assert client.get(f"/api/swim-imports/{uuid4()}").status_code == 404
    draft = _create(client)
    invalid = client.post(
        f"/api/swim-imports/{draft['import_id']}/patch",
        json={
            "expected_revision": 0,
            "request_id": str(uuid4()),
            "operation": {"op": "replace_program", "source_text": "PRIVATE_CANARY"},
        },
    )
    assert invalid.status_code == 422 and "PRIVATE_CANARY" not in invalid.text
    db = client.app.dependency_overrides[get_database]()
    with db._connect() as conn:
        conn.execute("UPDATE swim_import_sources SET source_text='PRIVATE_CANARY'")
    corrupt = client.get(f"/api/swim-imports/{draft['import_id']}")
    assert corrupt.status_code == 503 and "PRIVATE_CANARY" not in corrupt.text


def test_real_and_demo_sources_are_isolated(tmp_path, monkeypatch):
    from api import deps
    from config.settings import Settings

    monkeypatch.setattr(Settings, "DATABASE_PATH", str(tmp_path / "real.sqlite"))
    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo.sqlite"))
    deps._reset_db_cache()
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as handle:
            draft = _create(handle, "?demo=1")
            assert handle.get("/api/swim-imports").json() == {"items": []}
            assert (
                handle.get(f"/api/swim-imports/{draft['import_id']}").status_code == 404
            )
            assert handle.get("/api/swim-imports?demo=1").json()["items"] == [draft]
    finally:
        deps._reset_db_cache()


def test_populated_typescript_contract(client):
    from tests.contracts.conformance import validate
    from tests.smoke.test_contract_extractor import _run_extractor

    roots = [
        "SwimImportDraftResponse",
        "SwimImportPreviewResponse",
        "SwimProgramAnyVersionResponse",
        "SwimProgramListResponse",
        "SwimImportParseRequest",
        "SwimImportPatchRequest",
    ]
    artifact = _run_extractor(
        Path(__file__).resolve().parents[2] / "web/lib/types.ts", roots
    )
    draft, preview, saved, initial, command = _roundtrip(client)
    payloads = [
        draft,
        preview,
        saved,
        client.get("/api/swim-programs").json(),
        initial,
        command,
    ]
    for name, payload in zip(roots, payloads):
        assert validate(payload, artifact["types"][name], artifact["types"]) == [], name
    tampered = deepcopy(saved)
    tampered["document"]["workouts"][0]["steps"][1]["repeat"]["seconds"] = "not seconds"
    assert validate(
        tampered, artifact["types"]["SwimProgramAnyVersionResponse"], artifact["types"]
    )
    wrong_union = deepcopy(saved)
    wrong_union["document"]["schema_version"] = 1
    assert validate(
        wrong_union,
        artifact["types"]["SwimProgramAnyVersionResponse"],
        artifact["types"],
    )
