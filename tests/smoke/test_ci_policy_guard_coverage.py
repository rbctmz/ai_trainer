"""Rot-guard: тесты, охраняющие CI-политику, обязаны быть под CODEOWNERS (#650).

Политика CI защищена CODEOWNERS (`.github/workflows/`, `.github/scripts/`), а
rot-guard'ы, проверяющие форму этой политики, лежали вне его. При
`required_approving_review_count = 0` ослабить сторожа можно было PR-ом, не
требующим ни одного аппрува, — при том что сама политика аппрув требует.

Тест самозамыкающийся: он сам находит все тестовые файлы, которые читают
защищённые каталоги, и требует, чтобы каждый был покрыт CODEOWNERS. Файл этого
теста тоже подпадает под правило и потому внесён в `.github/CODEOWNERS`.

Проверка намеренно простая и fail-closed: поддержаны шаблон-каталог (`path/` —
префикс) и точный путь; glob-семантика CODEOWNERS не переизобретается.
Незнакомая форма шаблона не проходит молча — она просто не покрывает файл, и
тест падает с готовой строкой для вставки.
"""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

CODEOWNERS = Path(".github/CODEOWNERS")
PROTECTED_DIRS = (".github/workflows", ".github/scripts")
TESTS_ROOT = Path("tests")
OWNER = "@rbctmz"


def _codeowner_entries(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Пары (шаблон, владельцы) в порядке файла; комментарии и пустые строки — мимо."""
    entries: list[tuple[str, tuple[str, ...]]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        entries.append((parts[0], tuple(parts[1:])))
    return entries


def _covers(pattern: str, repo_path: str) -> bool:
    if pattern.endswith("/"):
        return repo_path == pattern.rstrip("/") or repo_path.startswith(pattern)
    return repo_path == pattern


def _owners_for(repo_path: str) -> tuple[str, ...]:
    """Владельцы пути; как в CODEOWNERS, побеждает последний шаблон с владельцами."""
    owners: tuple[str, ...] = ()
    for pattern, pattern_owners in _codeowner_entries(
        CODEOWNERS.read_text(encoding="utf-8")
    ):
        if _covers(pattern, repo_path) and pattern_owners:
            owners = pattern_owners
    return owners


def _ci_policy_guard_tests() -> list[str]:
    guards = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in PROTECTED_DIRS):
            guards.append(path.as_posix())
    return guards


def test_scanner_finds_the_known_guards() -> None:
    """Сторожа переименовали — сканер не должен молча опустеть."""
    guards = _ci_policy_guard_tests()

    for expected in (
        "tests/smoke/test_ci_policy_guard_coverage.py",
        "tests/smoke/test_native_codex_review_integration.py",
        "tests/smoke/test_claude_code_action_workflow.py",
        "tests/smoke/test_dev_workflow_v2_docs.py",
        "tests/smoke/test_secret_scanning_ci.py",
        "tests/smoke/test_workflow_issue_linking.py",
    ):
        assert expected in guards


def test_every_ci_policy_guard_test_is_codeowner_protected() -> None:
    uncovered = [path for path in _ci_policy_guard_tests() if not _owners_for(path)]

    assert not uncovered, (
        "Эти тесты читают .github/workflows или .github/scripts, но не покрыты "
        ".github/CODEOWNERS — ослабить сторожа можно PR-ом без аппрува (#650). "
        "Добавь в .github/CODEOWNERS:\n"
        + "\n".join(f"  {path}  {OWNER}" for path in uncovered)
    )


def test_codeowners_protects_itself() -> None:
    assert _owners_for(".github/CODEOWNERS"), (
        ".github/CODEOWNERS не покрыт сам собой: список владельцев можно "
        "переписать PR-ом, не требующим ревью владельца"
    )


def test_protected_directories_still_have_an_owner() -> None:
    for directory in PROTECTED_DIRS:
        assert _owners_for(directory), f"{directory} больше не под CODEOWNERS"
