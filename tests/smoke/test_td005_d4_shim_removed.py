"""BDD gate for TD-005/D4 (#354): deprecated sync_activities shim is gone.

Production code goes through the common ingest funnel
(``services.sync._sync_activities``); the legacy bulk ``Database.sync_activities``
method must not exist and no code path may call it anymore.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]

_CALL_PATTERN = re.compile(r"^\s*(?:db|database)\.sync_activities\(", re.MULTILINE)
_SCAN_DIRS = ("data", "services", "api", "models", "tests")


def test_sync_activities_shim_is_removed():
    database_source = (REPO_ROOT / "data/database.py").read_text(encoding="utf-8")

    assert "def sync_activities" not in database_source

    hits = []
    for directory in _SCAN_DIRS:
        for path in (REPO_ROOT / directory).rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="ignore")
            if _CALL_PATTERN.search(source):
                hits.append(str(path))
    assert hits == [], f"legacy sync_activities callers remain: {hits}"
