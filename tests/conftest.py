from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from config import db_paths
from config.settings import Settings


LIVE_PREFIXES = (
    "test_real_",
    "test_full_",
)

LIVE_FILES = {
    "test_gemini_api_direct.py",
    "test_hrv_sync.py",
    # #625: standalone diagnostics that open `Database()` against the maintainer's
    # populated local database (no synthetic fixture exists for them). They are
    # excluded from the contributor-safe run rather than silently reading — and
    # writing schema into — dogfood data. Run them with `-m live` against an
    # explicit DATABASE_PATH.
    "test_ai_chat_integration.py",
    "test_ai_tools_system.py",
    "test_final_app.py",
    "test_final_app_integration.py",
    "test_hrv_display.py",
    "test_hrv_logic.py",
    "test_hrv_trend.py",
    "test_improved_formatting.py",
    "test_training_prompts.py",
}

DEBUG_TOKENS = (
    "debug",
    "diagnosis",
)

DEBUG_FILES = {
    "test_sync_chain_debugging.py",
}

#: Not a `.gitignore` event, just a name that must never be *created* by a check.
REPO_ROOT = Path(__file__).resolve().parents[1]


def _arm_path_guard() -> tuple[Path, ...]:
    """Declare the dogfood database as protected for the whole test session (#625).

    Set before any test module is imported so a module-level ``Database()`` — the
    exact shape that let legacy suites write into ``ai_trainer.db`` — fails
    closed at its first connection. The declared paths are absolute and contain
    no personal data beyond a local filesystem path, which never reaches CI
    output: violations report only the invariant and a path classification.
    """
    protected = (db_paths.production_database_path(),) + db_paths.production_sidecar_paths()
    os.environ[db_paths.PROTECTED_PATHS_ENV] = os.pathsep.join(str(path) for path in protected)
    os.environ[db_paths.GUARD_MODE_ENV] = "test"
    # Freeze the dogfood identity for the whole session: tests legitimately rebind
    # Settings.DATABASE_PATH for their own scenarios, and that must not move the
    # boundary the guard enforces.
    os.environ[db_paths.PRODUCTION_DB_ENV] = str(protected[0])
    return protected


PROTECTED_PATHS = _arm_path_guard()

#: The production identity observed when the session armed the guard. Fixtures and
#: tests may rebind ``Settings.DATABASE_PATH`` for their own scenarios, so the
#: armed set must stay inspectable independently of the current settings.
PRODUCTION_DATABASE_AT_ARM_TIME = PROTECTED_PATHS[0]


def _git_toplevel(start: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - no git on PATH
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return Path(completed.stdout.strip()).resolve()


def _inside_checkout(path: Path) -> bool:
    checkout = _git_toplevel(path.parent if path.parent.exists() else Path.cwd())
    if checkout is None:
        return False
    try:
        path.resolve(strict=False).relative_to(checkout)
    except ValueError:
        return False
    return True


@pytest.fixture(scope="session", autouse=True)
def protect_dogfood_database_from_the_test_session() -> None:
    """Stop a session whose *explicitly configured* database is a checkout artifact.

    The 2026-09-20 incident deleted the working database during a diagnostic
    check of `.gitignore` rules run from the repository root. After the #624
    migration this can only fire when ``DATABASE_PATH`` is pointed back into a
    cloned tree, which is exactly the shared-fate coupling this track removes.

    Scope is deliberately narrow: only an explicit ``DATABASE_PATH`` counts. The
    pre-#624 bare default (``ai_trainer.db`` relative to the working directory)
    resolves identically to a test database, so refusing it here would fail the
    suite of every contributor. That case is instead covered by the runtime
    connection guard, which refuses every dogfood write *before* SQLite opens
    the file. Stops the session before the first test — and therefore before the
    first write — naming the invariant without echoing the local path.
    """
    configured = (Settings.DATABASE_PATH or "").strip()
    if not configured:
        return
    real = db_paths.production_database_path()
    if not real.exists() or not _inside_checkout(real):
        return
    pytest.exit(
        "database-path-safety: the configured production database resolves inside "
        "a Git checkout (shared fate with sources, tests and agent operations). "
        "Move it to an application-data directory (#624) or point DATABASE_PATH "
        "at a per-run temporary directory before running tests.",
        returncode=pytest.ExitCode.USAGE_ERROR,
    )


@pytest.fixture(autouse=True)
def isolate_database_paths(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind every test to a per-test temporary database (#625).

    The 2026-09-20 incident showed that isolation cannot depend on caller
    discipline: ambient ``Settings`` previously pointed unbound ``Database()``
    and ``StateManager({})`` helpers at the maintainer's working database, so the
    suite both read real personal history and wrote schema into it. Redirecting
    the *application* construction path here removes that silent fallback while
    the runtime guard keeps refusing dogfood artifacts.

    ``Settings.DATABASE_PATH`` is deliberately NOT rewritten: it is the identity
    the guard compares against, and tests that assert on it (including the
    guardrail suite) must keep seeing the ambient value. Tests that need seeded
    data still pass an explicit path (``Database(...)``,
    ``app.dependency_overrides``).
    """
    directory = tmp_path_factory.mktemp("runtime-db")
    isolated = str(directory / "test_runtime.db")

    import data.database as database_module

    real_database = database_module.Database

    def guarded_database(db_path=None):
        return real_database(db_path or isolated)

    monkeypatch.setattr(database_module, "Database", guarded_database)
    monkeypatch.setattr(Settings, "CHATS_DIR", str(directory / "chats"))


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
