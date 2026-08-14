"""Инвентаризация API-вызовов web против реестра контракта.

Гарантирует, что каждый GET-вызов фронтенда (``useSWR``/``fetcher`` с путём
``/api/*``) либо зарегистрирован в ``tests/contracts/registry.json``, либо явно
исключён (аннотация ``// api-contract: exclude:`` или секция ``excluded``).
POST/PUT/DELETE инвентаризируются для отчёта, но вне conformance-сверки.

Контракт: docs/web_contract_drift_execplan.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
CONTRACTS_DIR = REPO_ROOT / "tests" / "contracts"
REGISTRY_PATH = CONTRACTS_DIR / "registry.json"
INVENTORY_SCRIPT = WEB_DIR / "scripts" / "inventory-api-calls.mjs"

KNOWN_STATES = {"empty", "demo", "edge_no_plan", "edge_sparse"}


def _load_registry() -> dict:
    assert REGISTRY_PATH.exists(), f"реестр контракта не найден: {REGISTRY_PATH}"
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_schema() -> None:
    """Схема реестра: эндпоинты с интерфейсом и >=1 сценарием; исключения с причиной."""
    registry = _load_registry()
    endpoints = registry.get("endpoints")
    assert isinstance(endpoints, dict) and endpoints, "секция endpoints пуста или отсутствует"
    for path, entry in endpoints.items():
        assert path.startswith("/api/"), f"путь вне /api/: {path}"
        assert isinstance(entry.get("interface"), str) and entry["interface"], f"{path}: пустой interface"
        scenarios = entry.get("scenarios")
        assert isinstance(scenarios, list) and scenarios, f"{path}: нет сценариев"
        for scenario in scenarios:
            state = scenario.get("state")
            assert state in KNOWN_STATES, f"{path}: неизвестное состояние {state!r}"
            assert scenario.get("expect") == 200, f"{path}: conformance проверяет только expect=200"
    for item in registry.get("excluded", []):
        assert str(item.get("path", "")).startswith("/api/"), f"исключение вне /api/: {item}"
        assert isinstance(item.get("reason"), str) and item["reason"], f"исключение без причины: {item}"


def _run_inventory() -> dict:
    if shutil.which("node") is None:
        pytest.skip("node недоступен: инвентаризация требует Node.js")
    if not (WEB_DIR / "node_modules" / "typescript").exists():
        pytest.skip(
            "web/node_modules/typescript не установлен: выполните npm --prefix web install "
            "(или npm --prefix web ci)"
        )
    assert INVENTORY_SCRIPT.exists(), (
        f"инвентаризатор не найден: {INVENTORY_SCRIPT}. Реализуйте его по "
        "docs/web_contract_drift_execplan.md (этап 1)"
    )
    proc = subprocess.run(
        ["node", str(INVENTORY_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"инвентаризатор упал:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _is_excluded(excluded: list[dict], path: str | None, file: str) -> bool:
    for item in excluded:
        if item.get("file") and item["file"] != file:
            continue
        if item["path"] == path:
            return True
    return False


def test_inventory_matches_registry() -> None:
    """Каждый GET фронтенда зарегистрирован или исключён; реестр не содержит мёртвых путей."""
    inventory = _run_inventory()
    registry = _load_registry()
    endpoints = set(registry["endpoints"])
    excluded = registry.get("excluded", [])

    calls = inventory.get("calls")
    assert isinstance(calls, list) and calls, "инвентаризация не нашла ни одного вызова — сломан обход"
    gets = [c for c in calls if c["method"] == "GET"]
    assert gets, "инвентаризация не нашла ни одного GET-вызова — сломан обход"

    problems: list[str] = []
    covered: set[str] = set()
    for call in gets:
        location = f"{call['file']}:{call['line']}"
        if call.get("unresolved"):
            if not call.get("annotated") and not _is_excluded(excluded, None, call["file"]):
                problems.append(
                    f"{location}: неразрешимый динамический путь {call['unresolved']!r} "
                    "без аннотации // api-contract: exclude: или записи в excluded"
                )
            continue
        for resolved in call["paths"]:
            norm = resolved["path"]
            covered.add(norm)
            if norm in endpoints:
                # Реестр обязан отражать тип, который реально использует web.
                if call.get("type_source") == "lib/types" and call.get("type"):
                    expected = registry["endpoints"][norm]["interface"]
                    if call["type"] != expected:
                        problems.append(
                            f"{location}: GET {norm} использует тип {call['type']}, "
                            f"а реестр объявляет {expected}"
                        )
                continue
            if _is_excluded(excluded, norm, call["file"]):
                continue
            problems.append(f"{location}: GET {norm} не зарегистрирован и не исключён")

    assert not problems, "Проблемы инвентаризации:\n" + "\n".join(problems)

    dead = endpoints - covered
    assert not dead, f"реестр содержит пути, которые фронтенд не вызывает: {sorted(dead)}"


def test_inventory_captures_mutations() -> None:
    """POST/PUT/DELETE инвентаризируются (отчёт), но не требуют регистрации."""
    inventory = _run_inventory()
    methods = {c["method"] for c in inventory["calls"]}
    assert "POST" in methods, "инвентаризация не нашла POST-мутаций — сломан обход"
