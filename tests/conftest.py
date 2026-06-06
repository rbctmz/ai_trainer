from __future__ import annotations

from pathlib import Path

import pytest


LIVE_PREFIXES = (
    "test_real_",
    "test_full_",
)

LIVE_FILES = {
    "test_gemini_api_direct.py",
    "test_hrv_sync.py",
}

DEBUG_TOKENS = (
    "debug",
    "diagnosis",
)

DEBUG_FILES = {
    "test_sync_chain_debugging.py",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        path = Path(str(item.fspath))
        name = path.name
        normalized = path.as_posix()

        if "/tests/smoke/" in normalized:
            item.add_marker(pytest.mark.smoke)

        if name.startswith(LIVE_PREFIXES) or name in LIVE_FILES:
            item.add_marker(pytest.mark.live)

        if any(token in name for token in DEBUG_TOKENS) or name in DEBUG_FILES:
            item.add_marker(pytest.mark.debug)
