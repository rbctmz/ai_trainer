"""E2E-контур web-стека запускается отдельной командой.

Обычные прогоны (`-m "not live and not debug"`, CI contributor-safe) не должны
неявно поднимать FastAPI + Next.js + Chromium: тесты с маркером ``e2e``
скипаются, если маркер не выбран явно.
"""

from __future__ import annotations

import re

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    markexpr = config.option.markexpr or ""
    if re.search(r"\be2e\b", markexpr):
        return
    skip = pytest.mark.skip(
        reason="e2e запускается отдельно: python -m pytest -m e2e tests/e2e -q "
        "(поднимает FastAPI + Next.js, требует npm-зависимости web/ и playwright install chromium)"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)
