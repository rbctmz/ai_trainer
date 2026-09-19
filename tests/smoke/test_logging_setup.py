"""Логирование приложения: настройка уровня и отсутствие print() в data-слое.

Срез #591: диагностика data-слоя ушла из stdout в `logging`. Проверяется, что
настройка уровня идемпотентна, что неизвестное значение окружения не роняет
приложение, и что сообщения реально доходят до логгера, а не до stdout.
"""
from __future__ import annotations

import logging
from pathlib import Path
import re

import pytest

from utils.logging_setup import LOG_LEVEL_ENV, configure_logging, resolve_log_level

ROOT = Path(__file__).resolve().parents[2]

#: Модули, переведённые с `print()` на `logging` в этом срезе.
DATA_MODULES = (
    "data/garth_client.py",
    "data/data_processor_phase1.py",
    "data/database.py",
    "data/data_processor.py",
)

PRINT_CALL = re.compile(r"(^|[^A-Za-z_.])print\(")


@pytest.fixture
def restore_root_logger():
    """Вернуть корневой логгер в исходное состояние после теста настройки."""
    root = logging.getLogger()
    level = root.level
    before = list(root.handlers)
    yield root
    root.setLevel(level)
    for handler in list(root.handlers):
        if handler not in before:
            root.removeHandler(handler)


def test_resolve_log_level_reads_env_case_insensitively(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LOG_LEVEL_ENV, "debug")
    assert resolve_log_level() == logging.DEBUG


@pytest.mark.parametrize("raw", ["nonsense", "   ", "", "LEVEL 42"])
def test_resolve_log_level_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Опечатка в окружении не роняет приложение и не включает DEBUG."""
    monkeypatch.setenv(LOG_LEVEL_ENV, raw)
    assert resolve_log_level() == logging.INFO


def test_resolve_log_level_explicit_argument_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LOG_LEVEL_ENV, "ERROR")
    assert resolve_log_level("warning") == logging.WARNING


def test_configure_logging_is_idempotent_and_sets_level(restore_root_logger) -> None:
    root = restore_root_logger
    assert configure_logging("DEBUG") == logging.DEBUG
    handlers = [h for h in root.handlers if getattr(h, "_ai_trainer_handler", False)]
    assert len(handlers) == 1
    assert configure_logging("WARNING") == logging.WARNING
    again = [h for h in root.handlers if getattr(h, "_ai_trainer_handler", False)]
    assert len(again) == 1, "повторная настройка не должна добавлять второй хендлер"
    assert root.level == logging.WARNING


@pytest.mark.parametrize("path", DATA_MODULES)
def test_data_modules_log_instead_of_printing(path: str) -> None:
    """В data-слое не остаётся `print()`: диагностика идёт через logging."""
    source = (ROOT / path).read_text(encoding="utf-8")
    assert not PRINT_CALL.search(source), f"{path} всё ещё печатает в stdout"
    assert "logging.getLogger(" in source, f"{path} не объявляет логгер"


def test_phase1_sleep_warning_reaches_the_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Сообщение, которое раньше печаталось, теперь приходит как WARNING-запись."""
    from data.data_processor_phase1 import Phase1DataProcessor

    with caplog.at_level(logging.WARNING, logger="data.data_processor_phase1"):
        assert Phase1DataProcessor.process_sleep_data(None) is None

    messages = [record.getMessage() for record in caplog.records]
    assert any("sleep_raw_data" in message for message in messages), messages
