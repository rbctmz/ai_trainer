"""Юнит-тесты валидатора соответствия (tests/contracts/conformance.py).

Семантика (docs/web_contract_drift_execplan.md): FAIL только при отсутствии
обязательного TS-поля, несовместимом типе наблюдаемого значения или значении
вне закрытого множества литералов. Необъявленные API-поля — INFO-отчёт.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke

from tests.contracts.conformance import find_extra_fields, validate  # noqa: E402


def spec(
    kinds: list[str],
    literals: list | None = None,
    widened: bool = False,
    items: dict | None = None,
    fields: dict | None = None,
    ref: str | None = None,
    wildcard: bool = False,
    variants: list | None = None,
) -> dict:
    return {
        "kinds": kinds,
        "literals": literals or [],
        "widened": widened,
        "items": items,
        "fields": fields,
        "ref": ref,
        "wildcard": wildcard,
        "variants": variants,
    }


def field(inner: dict, optional: bool = False) -> dict:
    return {"optional": optional, "spec": inner}


TYPES = {
    "Snapshot": spec(
        kinds=["object"],
        fields={
            "score": field(spec(["null", "number"])),
            "status": field(spec(["string"], literals=["low", "ready"], widened=True)),
            "state": field(spec(["string"], literals=["empty", "ready"])),
            "factors": field(spec(["array"], items=spec(["string"]))),
            "note": field(spec(["string"]), optional=True),
        },
    ),
    "Envelope": spec(
        kinds=["object"],
        fields={
            "has_data": field(spec(["boolean"])),
            "snapshot": field(spec(["null", "object"], ref="Snapshot")),
        },
    ),
    "Chart": spec(
        kinds=["object"],
        variants=[
            spec(kinds=["object"], fields={"kind": field(spec(["string"], literals=["event"]))}),
            spec(kinds=["object"], fields={"kind": field(spec(["string"], literals=["rolling"]))}),
        ],
    ),
}


class TestValidate:
    def test_ok_payload(self) -> None:
        payload = {
            "has_data": True,
            "snapshot": {"score": 42, "status": "weird-unknown", "state": "ready", "factors": ["a"]},
        }
        assert validate(payload, TYPES["Envelope"], TYPES) == []

    def test_missing_required_field(self) -> None:
        violations = validate({"has_data": True}, TYPES["Envelope"], TYPES)
        assert any("snapshot" in v and "обязательное" in v for v in violations)

    def test_null_allowed_when_in_union(self) -> None:
        assert validate({"score": None, "status": "low", "state": "ready", "factors": []}, TYPES["Snapshot"], TYPES) == []

    def test_null_not_allowed_without_union(self) -> None:
        violations = validate({"has_data": None}, TYPES["Envelope"], TYPES)
        assert violations and "несовместим" in violations[0]

    def test_string_vs_number_incompatible(self) -> None:
        violations = validate({"score": "42", "state": "ready", "factors": []}, TYPES["Snapshot"], TYPES)
        assert any("$.score" in v and "несовместим" in v for v in violations)

    def test_bool_is_not_number(self) -> None:
        violations = validate({"score": True, "state": "ready", "factors": []}, TYPES["Snapshot"], TYPES)
        assert any("$.score" in v for v in violations)

    def test_number_is_not_boolean(self) -> None:
        violations = validate({"has_data": 1}, TYPES["Envelope"], TYPES)
        assert any("$.has_data" in v for v in violations)

    def test_array_element_violation_path(self) -> None:
        violations = validate(
            {"score": 1, "state": "ready", "factors": ["ok", 7]}, TYPES["Snapshot"], TYPES
        )
        assert any("$.factors[1]" in v for v in violations)

    def test_closed_literal_outside_set(self) -> None:
        violations = validate({"score": 1, "state": "unknown", "factors": []}, TYPES["Snapshot"], TYPES)
        assert any("$.state" in v and "литерал" in v for v in violations)

    def test_widened_literal_not_blocking(self) -> None:
        violations = validate({"score": 1, "status": "anything-goes", "state": "ready", "factors": []}, TYPES["Snapshot"], TYPES)
        assert violations == []

    def test_optional_absent_ok_present_invalid_fails(self) -> None:
        ok = validate({"score": 1, "status": "low", "state": "ready", "factors": []}, TYPES["Snapshot"], TYPES)
        assert ok == []
        bad = validate({"score": 1, "status": "low", "state": "ready", "factors": [], "note": 5}, TYPES["Snapshot"], TYPES)
        assert any("$.note" in v for v in bad)

    def test_ref_required_fields_checked_recursively(self) -> None:
        payload = {"has_data": True, "snapshot": {"score": 1, "state": "ready"}}  # нет factors
        violations = validate(payload, TYPES["Envelope"], TYPES)
        assert any("$.snapshot.factors" in v for v in violations)

    def test_wildcard_accepts_anything(self) -> None:
        anything = spec(["object"], wildcard=True)
        assert validate({"x": [1, {"y": None}]}, anything, TYPES) == []

    def test_variants_one_matches(self) -> None:
        for kind in ("event", "rolling"):
            assert validate({"kind": kind}, TYPES["Chart"], TYPES) == []

    def test_variants_none_matches(self) -> None:
        violations = validate({"kind": "unknown"}, TYPES["Chart"], TYPES)
        assert any("вариант" in v for v in violations)


class TestExtraFields:
    def test_extra_field_reported_not_blocking(self) -> None:
        payload = {"has_data": True, "snapshot": None, "new_server_field": 1}
        violations = validate(payload, TYPES["Envelope"], TYPES)
        assert violations == []
        extras = find_extra_fields(payload, TYPES["Envelope"], TYPES)
        assert any("$.new_server_field" in e for e in extras)

    def test_no_extras_for_wildcard(self) -> None:
        payload = {"anything": 1}
        assert find_extra_fields(payload, spec(["object"], wildcard=True), TYPES) == []

    def test_nested_extras(self) -> None:
        payload = {
            "has_data": True,
            "snapshot": {"score": 1, "state": "ready", "factors": [], "extra": "x"},
        }
        extras = find_extra_fields(payload, TYPES["Envelope"], TYPES)
        assert any("$.snapshot.extra" in e for e in extras)
