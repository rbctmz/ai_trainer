"""Юнит-тесты экстрактора контракта на fixtures-образцах.

Экстрактор ``web/scripts/extract-contract.mjs`` читает TypeScript-файл и
список корневых типов, извлекает достижимый подграф в нормализованный JSON.
Контракт формата: docs/web_contract_drift_execplan.md (Interfaces and Dependencies).
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
EXTRACTOR = WEB_DIR / "scripts" / "extract-contract.mjs"
FIXTURE = CONTRACTS_DIR / "fixtures" / "sample_types.ts"
UNSUPPORTED_FIXTURE = CONTRACTS_DIR / "fixtures" / "unsupported.ts"
ARTIFACT = CONTRACTS_DIR / "ts_contract.json"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("node недоступен: экстрактор требует Node.js")
    if not (WEB_DIR / "node_modules" / "typescript").exists():
        pytest.skip("web/node_modules/typescript не установлен: выполните npm --prefix web install")


def _run_extractor(source: Path, roots: list[str]) -> dict:
    _require_node()
    assert EXTRACTOR.exists(), (
        f"экстрактор не найден: {EXTRACTOR}. Реализуйте его по "
        "docs/web_contract_drift_execplan.md (этап 2)"
    )
    proc = subprocess.run(
        ["node", str(EXTRACTOR), "--source", str(source), "--roots", ",".join(roots)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"экстрактор упал:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _spec(payload: dict, *path: str) -> dict:
    node = payload["types"]
    for key in path[:-1]:
        node = node[key]["fields"]
    return node[path[-1]]


class TestSampleFixture:
    payload: dict = {}

    @classmethod
    def setup_class(cls) -> None:
        cls.payload = _run_extractor(FIXTURE, ["Root"])

    def test_reachability(self) -> None:
        """Извлекаются только типы, достижимые от корня."""
        names = set(self.payload["types"])
        assert {"Root", "Snapshot", "Factor", "Tone", "Profile", "Pickable", "Extended"} <= names
        assert "Orphan" not in names

    def test_union_literals_and_widening(self) -> None:
        tone = _spec(self.payload, "Snapshot", "tone")["spec"]
        assert tone["kinds"] == ["string"]
        assert tone["widened"] is True
        assert tone["literals"] == ["danger", "warning"]

    def test_closed_literal_union_via_alias(self) -> None:
        mode = _spec(self.payload, "Profile", "mode")["spec"]
        assert mode["widened"] is False
        assert mode["literals"] == ["a", "b"]

    def test_required_vs_optional(self) -> None:
        fields = self.payload["types"]["Snapshot"]["fields"]
        assert fields["tone"]["optional"] is False
        assert fields["optional_note"]["optional"] is True

    def test_null_union(self) -> None:
        score = _spec(self.payload, "Factor", "score")["spec"]
        assert score["kinds"] == ["null", "number"]

    def test_reference_array(self) -> None:
        factors = _spec(self.payload, "Snapshot", "factors")["spec"]
        assert factors["kinds"] == ["array"]
        assert factors["items"]["ref"] == "Factor"

    def test_wildcards(self) -> None:
        meta = _spec(self.payload, "Snapshot", "meta")["spec"]
        assert meta["kinds"] == ["object"] and meta["wildcard"] is False
        assert meta["record_values"] is None  # значения не проверяются, но объект обязателен
        raw = _spec(self.payload, "Snapshot", "raw")["spec"]
        assert raw["wildcard"] is True

    def test_record_value_types(self) -> None:
        counts = _spec(self.payload, "Snapshot", "counts")["spec"]
        assert counts["kinds"] == ["object"] and counts["wildcard"] is False
        assert counts["record_values"]["kinds"] == ["number"]

    def test_record_closed_keys_become_required_fields(self) -> None:
        limits = _spec(self.payload, "Snapshot", "limits")["spec"]
        assert set(limits["fields"]) == {"low", "high"}
        assert limits["fields"]["low"]["optional"] is False
        assert limits["record_values"] is None

    def test_empty_tuple_exact_length(self) -> None:
        empty = _spec(self.payload, "Snapshot", "empty_list")["spec"]
        assert empty["kinds"] == ["array"] and empty["array_length"] == 0
        assert empty["items"] is None

    def test_boolean_and_number_literals(self) -> None:
        lit = _spec(self.payload, "Snapshot", "lit")["spec"]
        assert lit["kinds"] == ["boolean"] and lit["literals"] == [True]
        nums = _spec(self.payload, "Snapshot", "nums")["spec"]
        assert nums["kinds"] == ["number"] and nums["literals"] == [1, 2]

    def test_indexed_access(self) -> None:
        mode = _spec(self.payload, "Root", "mode")["spec"]
        assert mode["literals"] == ["a", "b"] and mode["widened"] is False

    def test_pick(self) -> None:
        pick = _spec(self.payload, "Root", "pick")["spec"]
        assert set(pick["fields"]) == {"a", "b"}

    def test_intersection(self) -> None:
        merged = _spec(self.payload, "Root", "merged")["spec"]
        assert set(merged["fields"]) == {"extra", "a", "b", "c"}

    def test_generic_substitution(self) -> None:
        suggestion = _spec(self.payload, "Root", "suggestion")["spec"]
        assert set(suggestion["fields"]) == {"value", "basis"}
        assert suggestion["fields"]["value"]["spec"]["literals"] == ["a", "b"]

    def test_extends(self) -> None:
        extended = self.payload["types"]["Extended"]["fields"]
        assert set(extended) == {"key", "score", "label"}

    def test_inline_object_array(self) -> None:
        items = _spec(self.payload, "Root", "list")["spec"]["items"]
        assert set(items["fields"]) == {"inner"}

    def test_discriminated_union_variants(self) -> None:
        timeline = _spec(self.payload, "Snapshot", "timeline")["spec"]
        assert timeline["kinds"] == ["null", "object"]
        assert timeline["fields"] is None
        assert [variant["fields"]["kind"]["spec"]["literals"] for variant in timeline["variants"]] == [
            ["event"],
            ["rolling"],
        ]


def test_fail_closed_on_unsupported_syntax() -> None:
    """Условный тип внутри достижимого графа — exit 1 с файлом и подсказкой."""
    _require_node()
    assert EXTRACTOR.exists(), "экстрактор не найден: реализуйте web/scripts/extract-contract.mjs"
    proc = subprocess.run(
        ["node", str(EXTRACTOR), "--source", str(UNSUPPORTED_FIXTURE), "--roots", "Bad"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "unsupported.ts" in proc.stderr


def test_real_types_ts_extracts_all_registry_roots() -> None:
    """Реальный types.ts извлекается по корням реестра без fail-closed."""
    _require_node()
    registry = json.loads((CONTRACTS_DIR / "registry.json").read_text(encoding="utf-8"))
    roots = sorted({entry["interface"] for entry in registry["endpoints"].values()})
    payload = _run_extractor(WEB_DIR / "lib" / "types.ts", roots)
    missing = [name for name in roots if name not in payload["types"]]
    assert not missing, f"корни реестра не найдены в types.ts: {missing}"
    assert set(payload["roots"]) == set(roots)
