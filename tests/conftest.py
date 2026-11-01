from __future__ import annotations

from pathlib import Path

import pytest

from config.database_paths import ScratchPathError
from scripts.scratch_pytest import bootstrap_pytest, sqlite_audit_counts

try:
    _scratch = bootstrap_pytest()
except ScratchPathError as exc:
    raise pytest.UsageError(str(exc)) from None

from config.settings import Settings  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    try:
        chosen = config.option.basetemp
        if chosen:
            config.option.basetemp = str(_scratch.validate_directory(Path(chosen), cleanup=True))
        else:
            config.option.basetemp = str(_scratch.root / "pytest")
    except ScratchPathError as exc:
        raise pytest.UsageError(str(exc)) from None


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


@pytest.fixture(autouse=True)
def disable_live_intervals_credentials(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Contributor-safe tests never inherit a developer's live write credential."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", None)


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


def pytest_terminal_summary(terminalreporter) -> None:
    counts = sqlite_audit_counts()
    terminalreporter.write_line(
        f"scratch SQLite (this process): allowed={counts['allowed']} blocked={counts['blocked']}"
    )
