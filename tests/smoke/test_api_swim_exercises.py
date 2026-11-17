"""Exercise catalog API contracts on synthetic owned databases."""

from uuid import uuid4
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from api.deps import get_database
from api.routers.swim_exercises import router
from data.database import Database
from tests.smoke.test_swim_exercise import definition, EXERCISE_ID

pytestmark = pytest.mark.smoke


@pytest.fixture
def client(tmp_path):
    db = Database(str(tmp_path / "api.sqlite"))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as c:
        yield c


def _roundtrip(client):
    p = client.post("/api/swim-exercises/preview", json={"document": definition()})
    assert p.status_code == 200, p.text
    preview = p.json()
    assert client.get("/api/swim-exercises").json() == {"items": []}
    payload = {
        **preview,
        "base_revision": 0,
        "request_id": str(uuid4()),
        "confirm": True,
    }
    saved = client.post("/api/swim-exercises/confirm", json=payload)
    assert saved.status_code == 200, saved.text
    assert (
        client.post("/api/swim-exercises/confirm", json=payload).json() == saved.json()
    )
    assert (
        client.get(f"/api/swim-exercises/{EXERCISE_ID}/versions/1").json()
        == saved.json()
    )
    assert (
        len(
            client.get("/api/swim-exercises", params={"q": "EXAMPLE ALIAS"}).json()[
                "items"
            ]
        )
        == 1
    )
    resolved = client.post(
        "/api/swim-exercises/resolve",
        json={
            "exercise_id": EXERCISE_ID,
            "revision": 1,
            "node_id": "x",
            "distance_meters": 50,
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert (
        resolved.json()["step"]["distance_meters"] == 50
        and resolved.json()["exercise"] == saved.json()
    )
    return payload, resolved.json()


def test_http_preview_confirm_pinned_resolve(client):
    _roundtrip(client)


def test_populated_typescript_contract(client):
    from tests.contracts.conformance import validate
    from tests.smoke.test_contract_extractor import _run_extractor

    root = Path(__file__).resolve().parents[2]
    artifact = _run_extractor(
        root / "web/lib/types.ts",
        [
            "SwimExerciseResolveResponse",
            "SwimExerciseConfirmRequest",
            "SwimExerciseListResponse",
        ],
    )
    payload, resolved = _roundtrip(client)
    assert (
        validate(
            payload, artifact["types"]["SwimExerciseConfirmRequest"], artifact["types"]
        )
        == []
    )
    assert (
        validate(
            client.get("/api/swim-exercises").json(),
            artifact["types"]["SwimExerciseListResponse"],
            artifact["types"],
        )
        == []
    )
    assert (
        validate(
            resolved,
            artifact["types"]["SwimExerciseResolveResponse"],
            artifact["types"],
        )
        == []
    )


@pytest.mark.parametrize("confirmation", [False, 1, "true", None])
def test_explicit_confirmation_and_safe_validation(client, confirmation):
    preview = client.post(
        "/api/swim-exercises/preview", json={"document": definition()}
    ).json()
    response = client.post(
        "/api/swim-exercises/confirm",
        json={
            **preview,
            "base_revision": 0,
            "request_id": str(uuid4()),
            "confirm": confirmation,
        },
    )
    assert response.status_code == 422 and "PRIVATE_CANARY" not in response.text
    assert client.get("/api/swim-exercises").json() == {"items": []}


def test_missing_corrupt_and_no_source_echo(client):
    assert client.get(f"/api/swim-exercises/{EXERCISE_ID}").status_code == 404
    p = client.post(
        "/api/swim-exercises/preview",
        json={"document": {"source_text": "PRIVATE_CANARY"}},
    )
    assert p.status_code == 422 and "PRIVATE_CANARY" not in p.text
    preview = client.post(
        "/api/swim-exercises/preview", json={"document": definition()}
    ).json()
    client.post(
        "/api/swim-exercises/confirm",
        json={
            **preview,
            "base_revision": 0,
            "request_id": str(uuid4()),
            "confirm": True,
        },
    )
    db = client.app.dependency_overrides[get_database]()
    with db._connect() as c:
        c.execute("UPDATE swim_exercise_versions SET document_json='PRIVATE_CANARY'")
    response = client.get(f"/api/swim-exercises/{EXERCISE_ID}")
    assert response.status_code == 503 and "PRIVATE_CANARY" not in response.text


def test_demo_catalog_is_separate_and_preview_does_not_open_database(
    tmp_path, monkeypatch
):
    from api import deps
    from config.settings import Settings

    monkeypatch.setattr(Settings, "DATABASE_PATH", str(tmp_path / "real.sqlite"))
    monkeypatch.setattr(deps, "DEMO_DB_PATH", str(tmp_path / "demo.sqlite"))
    deps._reset_db_cache()
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as handle:
            preview = handle.post(
                "/api/swim-exercises/preview", json={"document": definition()}
            ).json()
            assert not (tmp_path / "real.sqlite").exists()
            assert not (tmp_path / "demo.sqlite").exists()
            payload = {
                **preview,
                "base_revision": 0,
                "request_id": str(uuid4()),
                "confirm": True,
            }
            saved = handle.post("/api/swim-exercises/confirm?demo=1", json=payload)
            assert saved.status_code == 200, saved.text
            assert handle.get("/api/swim-exercises").json() == {"items": []}
            assert len(handle.get("/api/swim-exercises?demo=1").json()["items"]) == 1
    finally:
        deps._reset_db_cache()
