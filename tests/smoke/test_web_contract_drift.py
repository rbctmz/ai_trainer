"""Conformance-сверка наблюдаемых HTTP-ответов с контрактом web/lib/types.ts.

Прогоняет сценарии из tests/contracts/registry.json против FastAPI-приложения
(TestClient + подмена get_database) на подготовленных состояниях данных и
валидирует JSON-ответы спеками из tests/contracts/ts_contract.json.

Сеть запрещена: известные провайдерные точки подменяются заглушками
(planning/events, onboarding-обнаружение гонок), а низкоуровневый egress
Intervals/Garmin закрывается guard'ом (NetworkAccessBlocked) — неожиданное
сетевое обращение роняет тест немедленно, а не уходит в сеть.

Семантика сверки — tests/contracts/conformance.py: FAIL только на отсутствие
обязательного TS-поля, несовместимый тип или литерал вне закрытого множества;
необъявленные API-поля печатаются как INFO (ASR-MOD-3, слияние не блокируют).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Query
from fastapi.testclient import TestClient

pytestmark = pytest.mark.smoke

from api.deps import get_database, make_headless_state  # noqa: E402
from api.main import app  # noqa: E402
from api.routers.system import _seed_demo_plan  # noqa: E402
from data.database import Database  # noqa: E402
from services.demo_mode import activate_demo_mode  # noqa: E402
from tests.contracts.conformance import find_extra_fields, validate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "tests" / "contracts"
REGISTRY = json.loads((CONTRACTS_DIR / "registry.json").read_text(encoding="utf-8"))
ARTIFACT = json.loads((CONTRACTS_DIR / "ts_contract.json").read_text(encoding="utf-8"))

KNOWN_STATES = {"empty", "demo", "edge_no_plan", "edge_sparse"}


class NetworkAccessBlocked(RuntimeError):
    """Guard: provider-free тест попытался уйти в сеть."""


# Детерминированная замена discover_intervals_events: гонок нет, деградации нет.
STUB_DISCOVERY = {"oldest": "2025-01-01", "newest": "2026-01-01", "count": 0, "events": [], "read_only": True}


@pytest.fixture(scope="module")
def network_guard():
    """Заглушки известных сетевых точек + fail-closed guard на низкоуровневом egress."""
    import api.planning_service as planning_service
    import data.garmin_client as garmin_client
    import data.garth_client as garth_client
    import services.planning_onboarding as planning_onboarding
    from services.intervals_icu import IntervalsICUClient

    def blocked(*args, **kwargs):
        raise NetworkAccessBlocked("provider-free тест: сетевое обращение запрещено")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(planning_service, "discover_intervals_events", lambda **kwargs: json.loads(json.dumps(STUB_DISCOVERY)))
    monkey.setattr(planning_onboarding, "discover_intervals_events", lambda **kwargs: json.loads(json.dumps(STUB_DISCOVERY)))
    monkey.setattr(IntervalsICUClient, "_request_json", blocked)
    monkey.setattr(garmin_client.GarminClient, "__init__", blocked)
    monkey.setattr(garth_client.GarthClient, "__init__", blocked)
    yield monkey
    monkey.undo()


def test_network_guard_blocks_unexpected_egress(network_guard):
    """Доказательство guard'а: незаглушённый вызов падает немедленно, без сети."""
    from services.intervals_icu import IntervalsICUClient

    client = IntervalsICUClient(api_key="test-key", athlete_id="1")
    with pytest.raises(NetworkAccessBlocked):
        client.list_calendars()


_TEMP_DIR = Path(tempfile.mkdtemp(prefix="web-contract-drift-"))
_CURRENT_DB: dict[str, Database | None] = {"db": None}


def _get_database_override(demo: bool = Query(False)) -> Database:
    """Подмена зависимости: возвращает БД активного состояния сценария."""
    assert _CURRENT_DB["db"] is not None, "состояние не инициализировано"
    return _CURRENT_DB["db"]


@pytest.fixture(scope="module")
def app_override():
    """Подмена get_database на время модуля; обязательное восстановление после."""
    app.dependency_overrides[get_database] = _get_database_override
    yield app
    app.dependency_overrides.pop(get_database, None)
    _CURRENT_DB["db"] = None


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_artifact_is_fresh() -> None:
    """Артефакт соответствует своим источникам — без Node (sha256 types.ts и registry).

    Ловит забытую регенерацию после правки types.ts/реестра: именно это уронило бы
    CI job web-contract (contract:extract --check).
    """
    meta = ARTIFACT["meta"]
    assert meta["source_sha256"] == _sha256(REPO_ROOT / "web" / "lib" / "types.ts"), (
        "web/lib/types.ts изменён без регенерации tests/contracts/ts_contract.json; "
        "выполните npm --prefix web run contract:extract"
    )
    assert meta["registry_sha256"] == _sha256(CONTRACTS_DIR / "registry.json"), (
        "tests/contracts/registry.json изменён без регенерации артефакта; "
        "выполните npm --prefix web run contract:extract"
    )


def _build_state(state_name: str) -> Database:
    db = Database(str(_TEMP_DIR / f"{state_name}.db"))
    if state_name in {"demo", "edge_no_plan"}:
        activate_demo_mode(make_headless_state(db))
    if state_name == "demo":
        _seed_demo_plan(db)
    if state_name == "edge_sparse":
        recent = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        db.save_activities(
            [
                {
                    "activity_id": "sparse-1",
                    "date": recent,
                    "sport": "cycling",
                    "duration_minutes": 60,
                    "distance_km": 30.0,
                    "tss": 55.0,
                }
            ]
        )
    return db


_CLIENTS: dict[str, tuple[Database, TestClient]] = {}


def _state(state_name: str) -> tuple[Database, TestClient]:
    assert state_name in KNOWN_STATES, f"неизвестное состояние: {state_name}"
    if state_name not in _CLIENTS:
        _CLIENTS[state_name] = (_build_state(state_name), TestClient(app))
    return _CLIENTS[state_name]


def _resolve_param(db: Database, client: TestClient, source: str) -> str:
    """Декларативные источники параметров пути из реестра."""
    if source == "first_activity_id":
        rows = db.get_activities(days=90)
        assert rows, "first_activity_id: в состоянии нет активностей"
        return str(rows[0]["activity_id"])
    if source == "first_feedback_session_id":
        response = client.get("/api/session-feedback/prompts")
        prompts = response.json().get("prompts") if response.status_code == 200 else None
        if prompts:
            return str(prompts[0]["session_id"])
        return "no-feedback-session"  # история пуста, но кон тракт 200
    raise AssertionError(f"неизвестный источник параметра пути: {source}")


def _cases():
    cases = []
    for path, entry in sorted(REGISTRY["endpoints"].items()):
        interface = entry["interface"]
        for scenario in entry["scenarios"]:
            cases.append(pytest.param(path, interface, scenario, id=f"{scenario['state']}-{path}"))
    return cases


@pytest.mark.parametrize(("path", "interface", "scenario"), _cases())
def test_endpoint_scenario(path: str, interface: str, scenario: dict, network_guard, app_override) -> None:
    db, client = _state(scenario["state"])
    _CURRENT_DB["db"] = db

    url = path
    for name, source in (scenario.get("path_params") or {}).items():
        url = url.replace(f"{{{name}}}", _resolve_param(db, client, source))

    response = client.get(url, params=scenario.get("query_params"))
    assert response.status_code == scenario["expect"], (
        f"GET {url} -> {response.status_code}: {response.text[:300]}"
    )

    payload = response.json()
    spec = ARTIFACT["types"][interface]
    violations = validate(payload, spec, ARTIFACT["types"])
    assert not violations, f"GET {url}: дрейф контракта\n" + "\n".join(violations)

    for line in find_extra_fields(payload, spec, ARTIFACT["types"]):
        print(f"INFO {url}: {line}")
