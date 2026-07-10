"""Architecture contracts for the web-first API boundary."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_coach_api_does_not_depend_on_legacy_ui() -> None:
    imports = _import_roots(REPO_ROOT / "api" / "routers" / "coach.py")

    assert "ui" not in imports


def test_api_modules_do_not_depend_on_legacy_ui() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "api").rglob("*.py"))
        if "ui" in _import_roots(path)
    ]

    assert offenders == []


def test_dashboard_summary_module_is_headless() -> None:
    imports = _import_roots(REPO_ROOT / "models" / "dashboard_summary.py")

    assert imports.isdisjoint({"api", "streamlit", "ui"})
