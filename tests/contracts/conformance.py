"""Валидатор соответствия наблюдаемого JSON спецификации из контракта.

Контракт формата ValueSpec — docs/web_contract_drift_execplan.md
(Interfaces and Dependencies); артефакт генерируется
web/scripts/extract-contract.mjs в tests/contracts/ts_contract.json.

Семантика:
- FAIL: отсутствует обязательное TS-поле; несовместимый тип наблюдаемого
  значения (bool != number); значение вне закрытого множества литералов
  (union без расширения ``| string``).
- INFO (не блокирует): API-поле, не объявленное в TS (обратная
  совместимость, ASR-MOD-3).
- Непроверяемо: отсутствующие опциональные поля; присутствующее
  опциональное поле валидируется как обычно.
"""

from __future__ import annotations

from typing import Any

_Kind = str


def observed_kind(value: Any) -> _Kind:
    """JSON-вид значения -> имя вида спецификации (bool проверяется раньше int!)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise TypeError(f"неподдерживаемый тип значения: {type(value)!r}")


def _resolve(spec: dict, types: dict, _depth: int = 0) -> dict:
    """Разрешить ref: kinds/literals/widened уже на месте, fields/items/variants — из цели."""
    if not spec.get("ref") or _depth > 32:
        return spec
    target = types.get(spec["ref"])
    if target is None:
        raise KeyError(f"ссылка на неизвестный тип: {spec['ref']}")
    merged = {**target, **{k: v for k, v in spec.items() if v not in (None, False)}}
    # kinds целевого типа уже включены в ref-спеку экстрактором; объединим на всякий случай
    merged["kinds"] = sorted(set(spec.get("kinds") or []) | set(target.get("kinds") or []))
    return merged


def _literal_violation(path: str, value: Any, spec: dict) -> str | None:
    literals = spec.get("literals") or []
    if not literals or spec.get("widened"):
        return None
    if isinstance(value, (str, bool, int, float)) and not isinstance(value, list):
        if value not in literals:
            return f"{path}: значение {value!r} вне закрытого множества литералов {sorted(map(repr, literals))}"
    return None


def validate(payload: Any, spec: dict, types: dict, path: str = "$") -> list[str]:
    """Список нарушений (FAIL). Пустой список = наблюдаемое совместимо со спецификацией."""
    if spec.get("wildcard"):
        return []
    spec = _resolve(spec, types)

    kind = observed_kind(payload)
    if kind not in spec.get("kinds", []):
        return [f"{path}: вид {kind} несовместим с {sorted(spec['kinds'])} (значение {payload!r})"]

    violation = _literal_violation(path, payload, spec)
    if violation:
        return [violation]

    if kind == "array":
        expected_length = spec.get("array_length")
        if expected_length is not None and len(payload) != expected_length:
            return [f"{path}: длина массива {len(payload)} != {expected_length} (пустой кортеж `[]`)"]
        items = spec.get("items")
        if items is None:
            return []
        violations: list[str] = []
        for index, element in enumerate(payload):
            violations.extend(validate(element, items, types, f"{path}[{index}]"))
        return violations

    if kind == "object":
        variants = spec.get("variants")
        if variants:
            for variant in variants:
                if validate(payload, variant, types) == []:
                    return []
            reasons = "; ".join(
                (validate(payload, variant, types) or ["?"])[0] for variant in variants
            )
            return [f"{path}: значение не подходит ни под один вариант union ({reasons})"]
        fields = spec.get("fields")
        if fields is None:
            # Record<K, V>: все значения проверяются против record_values
            # (null = значения не проверяются, но сам объект уже проверен по kind).
            record_values = spec.get("record_values")
            if record_values is None:
                return []
            violations = []
            for key, value in payload.items():
                violations.extend(validate(value, record_values, types, f"{path}.{key}"))
            return violations
        violations = []
        for name, field_spec in fields.items():
            field_path = f"{path}.{name}"
            if name not in payload:
                if not field_spec.get("optional"):
                    violations.append(f"{field_path}: отсутствует обязательное поле")
                continue
            violations.extend(validate(payload[name], field_spec["spec"], types, field_path))
        return violations

    return []


def find_extra_fields(payload: Any, spec: dict, types: dict, path: str = "$") -> list[str]:
    """INFO-отчёт о полях API, не объявленных в TS (обратно совместимо, не FAIL)."""
    if spec.get("wildcard"):
        return []
    spec = _resolve(spec, types)
    if observed_kind(payload) != "object":
        return []
    variants = spec.get("variants")
    if variants:
        for variant in variants:
            if validate(payload, variant, types) == []:
                return find_extra_fields(payload, variant, types, path)
        return []
    fields = spec.get("fields")
    if fields is None:
        return []
    extras: list[str] = []
    for name in payload:
        if name not in fields:
            extras.append(f"{path}.{name}: необъявленное поле (допустимо, ASR-MOD-3)")
    for name, field_spec in fields.items():
        if name in payload:
            extras.extend(find_extra_fields(payload[name], field_spec["spec"], types, f"{path}.{name}"))
    return extras
