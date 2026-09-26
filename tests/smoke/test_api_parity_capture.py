"""Контракт маскирования в scripts/api_parity_capture.py (#645).

Скрипт сравнивает снятия ответов API на двух ревизиях. Метки времени и ICS UID
маскируются: они отличаются на каждом запросе по устройству и не входят в
контракт payload. Но маска не должна скрывать регрессию формата — иначе смена
представления поля пройдёт сравнение незамеченной.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_capture_module():
    """Загрузить scripts/api_parity_capture.py по пути: scripts не пакет."""
    spec = importlib.util.spec_from_file_location(
        "api_parity_capture", REPO_ROOT / "scripts" / "api_parity_capture.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mask_ignores_the_value_but_keeps_the_format() -> None:
    normalise = _load_capture_module().normalise

    # Значение не влияет: две разные метки одной формы неотличимы.
    assert normalise('"2026-01-01T00:00:00Z"') == normalise('"2026-09-09T11:22:33Z"')
    # Форма влияет: потерянный T или Z — регрессия представления, а не шум.
    assert normalise('"2026-01-01T00:00:00Z"') != normalise('"2026-01-01 00:00:00"')
    assert normalise('"2026-01-01T00:00:00Z"') != normalise('"2026-01-01T00:00:00"')
    assert normalise('"2026-01-01T00:00:00+03:00"') != normalise('"2026-01-01T00:00:00Z"')


def test_date_only_values_are_compared_exactly() -> None:
    normalise = _load_capture_module().normalise

    assert normalise('"2026-01-01"') == '"2026-01-01"'
    assert normalise('"2026-01-01"') != normalise('"2026-01-02"')


def test_ics_uid_is_masked() -> None:
    normalise = _load_capture_module().normalise

    assert normalise("UID:0123456789abcdef0123456789abcdef") == "UID:<normalised>"
