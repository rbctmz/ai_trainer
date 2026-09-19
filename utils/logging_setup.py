"""Единая настройка логирования приложения.

Модули пишут диагностику через ``logging.getLogger(__name__)``; без явной настройки
корневой логгер отдаёт только WARNING+ через lastResort-хендлер, поэтому INFO/DEBUG
сообщения исчезали бы. Настройка вызывается из точек входа (``api/main.py``,
``app.py``), а не при импорте библиотечных модулей.

Уровень задаётся через ``AI_TRAINER_LOG_LEVEL`` (по умолчанию INFO). Понижение до
WARNING полезно, когда сторонние библиотеки (httpx и подобные) слишком подробны.
"""
from __future__ import annotations

import logging
import os
import sys

#: Переменная окружения с уровнем логирования приложения.
LOG_LEVEL_ENV = "AI_TRAINER_LOG_LEVEL"

DEFAULT_LEVEL_NAME = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Метка на хендлере: настройка идемпотентна даже если модуль импортирован дважды
# (uvicorn --reload, Streamlit, тесты).
_HANDLER_MARKER = "_ai_trainer_handler"


def resolve_log_level(raw: str | None = None) -> int:
    """Уровень логирования из ``raw`` (по умолчанию — ``AI_TRAINER_LOG_LEVEL``).

    Пустое или неизвестное значение — ``INFO``: опечатка в окружении не должна
    ни ронять приложение, ни включать самый подробный режим.
    """
    candidate = (raw if raw is not None else os.getenv(LOG_LEVEL_ENV, "")).strip().upper()
    if not candidate:
        candidate = DEFAULT_LEVEL_NAME
    resolved = logging.getLevelName(candidate)
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(level: str | int | None = None) -> int:
    """Идемпотентно настроить корневой логгер; возвращает установленный уровень.

    Хендлер добавляется ровно один раз на процесс, чтобы несколько точек входа
    не дублировали каждую запись.
    """
    resolved = level if isinstance(level, int) else resolve_log_level(level)
    root = logging.getLogger()
    if not any(getattr(handler, _HANDLER_MARKER, False) for handler in root.handlers):
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        setattr(handler, _HANDLER_MARKER, True)
        root.addHandler(handler)
    root.setLevel(resolved)
    return resolved
