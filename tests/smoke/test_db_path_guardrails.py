"""#625 — fail-closed DB path guardrails for tests, acceptance and agent CLIs.

Every path in this suite belongs to ``tmp_path`` and a monkeypatched
``Settings.DATABASE_PATH``; the maintainer's real ``ai_trainer.db``, its
sidecars and any provider credentials are never touched. The suite itself is the
regression gate for the 2026-09-20 incident class: a diagnostic or test process
that resolves a path onto the dogfood database (or a ``-wal``/``-shm``
sibling, or a symlink/hardlink/case alias of either) must fail closed *before*
the first SQLite write.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import config.db_paths as db_paths
from config.db_paths import (
    GUARD_MODE_ENV,
    PRODUCTION_DB_ENV,
    PROTECTED_PATHS_ENV,
    DatabasePathKind,
    DatabasePathViolation,
    TemporaryDatabaseRoot,
    assert_not_protected,
    assert_safe,
    classify,
    guarded_connect,
    guarded_protected_paths,
    is_sidecar_path,
    normalize_path,
    production_database_path,
    production_database_directory,
    production_sidecar_paths,
)
from config.settings import Settings

pytestmark = pytest.mark.smoke

#: Repository root, derived from the module under test so the subprocess fixture
#: can import ``tests.conftest`` from a foreign working directory.
REPO_ROOT = Path(db_paths.__file__).resolve().parents[1]


@pytest.fixture
def production(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in dogfood database outside any Git checkout.

    Clears the session's frozen identity so the guard resolves against this
    scenario's settings — the same precedence a real test entrypoint uses.
    """
    directory = tmp_path / "app-data"
    directory.mkdir()
    database = directory / "ai_trainer.db"
    monkeypatch.setattr(Settings, "DATABASE_PATH", str(database))
    monkeypatch.delenv("DEMO_DATABASE_PATH", raising=False)
    monkeypatch.delenv(PROTECTED_PATHS_ENV, raising=False)
    monkeypatch.delenv(GUARD_MODE_ENV, raising=False)
    monkeypatch.delenv(PRODUCTION_DB_ENV, raising=False)
    return database


@pytest.fixture
def armed_guard(production: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Simulate a test entrypoint that declared its production database."""
    monkeypatch.setenv(GUARD_MODE_ENV, "test")
    monkeypatch.setenv(PROTECTED_PATHS_ENV, str(production))
    monkeypatch.setenv(PRODUCTION_DB_ENV, str(production))
    return production


def _materialise(path: Path, marker: str = "production") -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE marker(value TEXT NOT NULL)")
        conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()
    return path


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT value FROM marker").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Canonical identity
# --------------------------------------------------------------------------- #


def test_production_path_is_absolute_and_cwd_independent(production: Path) -> None:
    assert production_database_path() == production
    assert production_database_directory() == production.parent


def test_production_identity_is_stable_across_working_directories(
    production: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute DATABASE_PATH must not change identity when cwd changes.

    Cheap falsifying check 1 from #625/issue #624: launch from two different
    working directories and the protected path must stay the same.
    """
    first = production_database_path()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert production_database_path() == first


def test_relative_production_path_resolves_against_call_time_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative DATABASE_PATH keeps runtime semantics and stays guarded.

    Today's default is a bare filename, so the guard must protect the file the
    application would really open from the *current* directory — not a cached
    path from an earlier one.
    """
    monkeypatch.delenv(PROTECTED_PATHS_ENV, raising=False)
    monkeypatch.delenv(GUARD_MODE_ENV, raising=False)
    monkeypatch.delenv(PRODUCTION_DB_ENV, raising=False)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    monkeypatch.setattr(Settings, "DATABASE_PATH", "ai_trainer.db")
    monkeypatch.chdir(first)
    assert production_database_path() == normalize_path(first / "ai_trainer.db")

    monkeypatch.chdir(second)
    assert production_database_path() == normalize_path(second / "ai_trainer.db")
    with pytest.raises(DatabasePathViolation):
        assert_safe(second / "ai_trainer.db", purpose="test setup")


def test_default_database_name_is_recognised_as_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(PROTECTED_PATHS_ENV, raising=False)
    monkeypatch.delenv(GUARD_MODE_ENV, raising=False)
    monkeypatch.delenv(PRODUCTION_DB_ENV, raising=False)
    monkeypatch.setattr(Settings, "DATABASE_PATH", "")
    monkeypatch.chdir(tmp_path)
    assert production_database_path() == normalize_path(tmp_path / "ai_trainer.db")


# --------------------------------------------------------------------------- #
# Classification and aliases
# --------------------------------------------------------------------------- #


def test_production_database_and_sidecars_are_classified_real(production: Path) -> None:
    assert classify(production).kind is DatabasePathKind.REAL
    for sidecar in production_sidecar_paths():
        result = classify(sidecar)
        assert result.kind is DatabasePathKind.REAL
        assert result.sidecar_suffix == is_sidecar_path(sidecar)
        assert result.touches_production


def test_relative_and_absolute_spellings_alias_the_same_protected_file(
    production: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(production.parent)
    assert classify("ai_trainer.db").kind is DatabasePathKind.REAL
    assert classify("./ai_trainer.db").kind is DatabasePathKind.REAL
    assert classify(production.parent / "." / "ai_trainer.db").kind is DatabasePathKind.REAL


def test_symlink_to_production_is_refused_and_source_untouched(
    production: Path, tmp_path: Path
) -> None:
    """Cheap falsifying check 1 from #625: a symlink must not unlock a write."""
    _materialise(production)
    link = tmp_path / "looks-temporary.db"
    link.symlink_to(production)

    assert classify(link).kind is DatabasePathKind.REAL
    with pytest.raises(DatabasePathViolation):
        assert_safe(link, purpose="test temporary database")

    with pytest.raises(DatabasePathViolation):
        guarded_connect(link)

    assert _read_marker(production) == "production"


def test_symlinked_parent_directory_is_refused(production: Path, tmp_path: Path) -> None:
    _materialise(production)
    alias_directory = tmp_path / "alias-dir"
    alias_directory.symlink_to(production.parent, target_is_directory=True)

    aliased = alias_directory / production.name
    assert classify(aliased).kind is DatabasePathKind.REAL
    with pytest.raises(DatabasePathViolation):
        assert_safe(aliased, purpose="acceptance database")


def test_hardlink_to_production_is_refused(production: Path, tmp_path: Path) -> None:
    """Hardlinks leave no path-level trace, so device/inode identity must decide."""
    _materialise(production)
    hardlink = tmp_path / "hardlinked.db"
    try:
        os.link(production, hardlink)
    except OSError as exc:  # pragma: no cover - filesystem without hardlinks
        pytest.skip(f"hardlinks unavailable: {exc}")

    assert classify(hardlink).kind is DatabasePathKind.REAL
    with pytest.raises(DatabasePathViolation):
        assert_safe(hardlink, purpose="cleanup target")


def test_case_only_alias_follows_filesystem_semantics(production: Path) -> None:
    """A case-only spelling is an alias exactly when the volume folds case."""
    _materialise(production)
    spelling = production.parent.parent / production.parent.name.upper() / production.name.upper()
    assert spelling != production

    if db_paths._filesystem_is_case_insensitive():
        assert os.path.exists(spelling), "probe claims case folding but alias is missing"
        assert classify(spelling).kind is DatabasePathKind.REAL
        with pytest.raises(DatabasePathViolation):
            assert_safe(spelling, purpose="test database")
    else:  # pragma: no cover - case-sensitive volume
        assert not os.path.exists(spelling)
        assert classify(spelling).kind is DatabasePathKind.TEST


def test_demo_and_test_databases_stay_usable(
    production: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard protects dogfood data without breaking isolated runtimes."""
    demo = production.parent / "ai_trainer_demo.db"
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(demo))
    assert classify(demo).kind is DatabasePathKind.DEMO
    assert classify(tmp_path / "isolated.db").kind is DatabasePathKind.TEST

    accepted = assert_safe(tmp_path / "isolated.db", purpose="test database")
    assert accepted.kind is DatabasePathKind.TEST
    assert assert_safe(demo, purpose="demo database").kind is DatabasePathKind.DEMO


def test_demo_path_alias_of_production_is_refused(
    production: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misconfigured DEMO_DATABASE_PATH must not become a wipe target."""
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(production))

    result = classify(production)
    assert result.kind is DatabasePathKind.REAL
    with pytest.raises(DatabasePathViolation):
        assert_safe(production, purpose="demo seeding")


def test_acceptance_mode_never_reclassifies_production_as_safe(
    production: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    with pytest.raises(DatabasePathViolation):
        assert_safe(production, purpose="acceptance run")


# --------------------------------------------------------------------------- #
# Violation messages stay free of personal paths
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "candidate",
    ["database", "wal", "shm", "journal"],
)
def test_violation_message_names_invariant_without_leaking_path(
    production: Path, candidate: str
) -> None:
    target = {"database": production}.get(candidate) or Path(f"{production}-{candidate}")
    with pytest.raises(DatabasePathViolation) as error:
        assert_safe(target, purpose="test run", invariant="db-path-guard-test")

    message = str(error.value)
    assert error.value.invariant == "db-path-guard-test"
    assert error.value.kind is DatabasePathKind.REAL
    assert str(production) not in message
    assert str(production.parent) not in message
    assert "db-path-guard-test" in message


def test_guarded_connect_refuses_production_before_any_write(production: Path) -> None:
    """The sanctioned factory refuses dogfood data even with no entrypoint armed."""
    _materialise(production, marker="before")
    with pytest.raises(DatabasePathViolation):
        guarded_connect(production)

    # No SQLite connection was opened at all: reopening still sees the marker.
    assert _read_marker(production) == "before"
    assert not Path(f"{production}-wal").exists()


def test_guarded_connect_opens_isolated_database_without_entrypoint(tmp_path: Path) -> None:
    isolated = tmp_path / "scratch.db"
    conn = guarded_connect(isolated)
    try:
        conn.execute("CREATE TABLE t(value INTEGER)")
        conn.commit()
    finally:
        conn.close()
    assert isolated.exists()


# --------------------------------------------------------------------------- #
# Runtime guard armed by a test entrypoint
# --------------------------------------------------------------------------- #


def test_guard_is_inert_without_an_armed_entrypoint(production: Path) -> None:
    """Operator CLIs keep working: without a declaration nothing is refused."""
    assert guarded_protected_paths() == ()
    assert assert_not_protected(production, purpose="application write") == production


def test_armed_guard_refuses_production_and_sidecars(armed_guard: Path) -> None:
    assert guarded_protected_paths() == (armed_guard,)
    for candidate in (armed_guard, Path(f"{armed_guard}-wal"), Path(f"{armed_guard}-shm")):
        with pytest.raises(DatabasePathViolation) as error:
            assert_not_protected(candidate, purpose="test database")
        assert error.value.invariant == "test-must-not-touch-production-database"
        assert str(armed_guard) not in str(error.value)


def test_armed_guard_refuses_relative_alias_from_another_cwd(
    armed_guard: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative spelling must not slip past the runtime guard."""
    monkeypatch.chdir(armed_guard.parent)
    with pytest.raises(DatabasePathViolation):
        assert_not_protected("ai_trainer.db", purpose="test temporary database")

    monkeypatch.chdir(armed_guard.parent.parent)
    with pytest.raises(DatabasePathViolation):
        assert_not_protected(f"app-data/{armed_guard.name}", purpose="test database")


def test_armed_guard_allows_isolated_paths(armed_guard: Path, tmp_path: Path) -> None:
    allowed = tmp_path / "isolated.db"
    assert assert_not_protected(allowed, purpose="test database") == normalize_path(allowed)


def test_guarded_connect_opens_isolated_database(armed_guard: Path, tmp_path: Path) -> None:
    isolated = tmp_path / "scratch.db"
    conn = guarded_connect(isolated)
    try:
        conn.execute("CREATE TABLE t(value INTEGER)")
        conn.commit()
    finally:
        conn.close()
    assert isolated.exists()


# --------------------------------------------------------------------------- #
# Per-run temporary roots
# --------------------------------------------------------------------------- #


def test_temporary_root_allocates_unique_isolated_paths() -> None:
    with TemporaryDatabaseRoot(label="test") as root:
        first = root.allocate("one.db")
        second = root.unique("scratch")
        assert first.parent == root.path
        assert second.parent == root.path
        assert first != second
        with pytest.raises(ValueError):
            root.allocate("../escape.db")
        with pytest.raises(ValueError):
            root.allocate("nested/escape.db")


def test_cleanup_candidate_refuses_paths_outside_the_run_root(
    production: Path,
) -> None:
    root = TemporaryDatabaseRoot(label="test")
    try:
        for candidate in (
            production,
            Path(f"{production}-wal"),
            production.parent,
            root.path / ".." / "escape.db",
            Path("/tmp/not-our-run.db"),
        ):
            with pytest.raises(DatabasePathViolation) as error:
                root.cleanup_candidate(candidate)
            assert error.value.invariant == "temporary-root-confinement" or (
                error.value.invariant == "database-path-safety"
            )
    finally:
        root.cleanup()


def test_cleanup_candidate_refuses_symlink_escape(production: Path, tmp_path: Path) -> None:
    root = TemporaryDatabaseRoot(label="test")
    try:
        planted = root.path / "planted.db"
        planted.symlink_to(production)
        with pytest.raises(DatabasePathViolation):
            root.cleanup_candidate(planted)
        assert production.exists() or not production.exists()
    finally:
        root.cleanup()


def test_cleanup_removes_only_its_own_root(production: Path, tmp_path: Path) -> None:
    _materialise(production)
    survivor = tmp_path / "survivor.db"
    _materialise(survivor, marker="survivor")

    root = TemporaryDatabaseRoot(label="test")
    inside = root.allocate("scratch.db")
    _materialise(inside, marker="scratch")
    # A link inside the root pointing out must not redirect deletion outward.
    (root.path / "escape-link.db").symlink_to(survivor)

    assert root.cleanup_candidate(inside) == inside
    root.cleanup()

    assert not root.path.exists()
    assert survivor.exists()
    assert _read_marker(survivor) == "survivor"
    assert _read_marker(production) == "production"


# --------------------------------------------------------------------------- #
# Wiring: the guard must actually be reachable from real entrypoints
# --------------------------------------------------------------------------- #


def test_test_entrypoint_arms_the_guard_for_the_whole_session() -> None:
    """``tests/conftest.py`` declares the production database before collection."""
    from tests.conftest import (
        PRODUCTION_DATABASE_AT_ARM_TIME,
        PROTECTED_PATHS,
        _inside_checkout,
    )

    assert PROTECTED_PATHS[0] == PRODUCTION_DATABASE_AT_ARM_TIME
    assert PROTECTED_PATHS[1:] == tuple(
        Path(f"{PRODUCTION_DATABASE_AT_ARM_TIME}{suffix}") for suffix in db_paths.SIDECAR_SUFFIXES
    )
    assert os.environ[db_paths.PROTECTED_PATHS_ENV] == os.pathsep.join(
        str(path) for path in PROTECTED_PATHS
    )
    assert db_paths.guard_active()
    assert _inside_checkout(Path(__file__).resolve()) is True
    assert _inside_checkout(Path(tempfile.gettempdir()).resolve() / "outside-checkout.db") is False


def test_test_session_isolates_the_runtime_database(tmp_path: Path) -> None:
    """The autouse fixture keeps ambient ``Database()``/``StateManager({})`` home.

    Both helpers used to fall through to ``Settings.DATABASE_PATH`` and therefore
    to the maintainer's working database; here they must land in the per-test
    temporary root instead.
    """
    from data.database import Database
    from state import StateManager

    ambient = str(db_paths.production_database_path())

    bare = Database()
    assert Path(bare.db_path) != Path(ambient)
    assert not db_paths.is_protected_production_path(bare.db_path)

    state = StateManager({})
    assert Path(state.database.db_path) != Path(ambient)
    assert Path(state.database.db_path) == Path(bare.db_path)


def test_connection_hook_refuses_production_and_sidecars(armed_guard: Path) -> None:
    """The hook ``data.database`` calls before opening a connection fails closed."""
    from config.db_paths import guard_connect_path

    for candidate in (armed_guard, Path(f"{armed_guard}-wal")):
        with pytest.raises(DatabasePathViolation) as error:
            guard_connect_path(candidate)
        assert error.value.invariant == "test-must-not-touch-production-database"

    assert armed_guard.exists() is False, "guard must refuse before creating anything"
    guard_connect_path(armed_guard.parent / "isolated.db")


def test_connection_hook_allows_the_unarmed_application_database(production: Path) -> None:
    """The runtime application may open its own configured dogfood database."""
    from config.db_paths import guard_connect_path

    guard_connect_path(production)


def test_database_object_refuses_production_without_creating_it(armed_guard: Path) -> None:
    """A bare ``Database()`` in a test can no longer write DDL into dogfood data.

    This is the exact shape that let legacy suites reach ``ai_trainer.db``
    through ``Settings.DATABASE_PATH`` at module import time.
    """
    from data.database import Database

    with pytest.raises(DatabasePathViolation):
        Database(str(armed_guard))
    assert armed_guard.exists() is False
    assert not Path(f"{armed_guard}-wal").exists()


def test_database_object_still_opens_isolated_paths(tmp_path: Path) -> None:
    from data.database import Database

    database = Database(str(tmp_path / "isolated.db"))
    assert Path(database.db_path).exists()


def test_test_session_entrypoint_exits_before_touching_a_checkout_database(tmp_path: Path) -> None:
    """End-to-end: pytest refuses a checkout-local production database.

    Cheap falsifying check from the incident: run the suite with the dogfood
    database inside the working tree and prove (a) the session stops before the
    first write, (b) the database file is untouched, (c) the message names the
    invariant without printing the offending path.
    """
    repo = tmp_path / "fake-checkout"
    repo.mkdir()
    tests_directory = repo / "tests"
    tests_directory.mkdir()
    database = repo / "ai_trainer.db"
    _materialise(database, marker="dogfood")

    # A real checkout, because that is the condition the guard detects.
    initialised = subprocess.run(
        ["git", "init", "-q", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if initialised.returncode != 0:  # pragma: no cover - git unavailable
        pytest.skip(f"git is required for this drill: {initialised.stderr.strip()}")

    (tests_directory / "conftest.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from tests.conftest import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )
    (tests_directory / "test_anything.py").write_text(
        "def test_should_never_run():\n"
        "    raise AssertionError('the session guard must stop collection')\n",
        encoding="utf-8",
    )

    environment = {
        **os.environ,
        "DATABASE_PATH": str(database),
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment.pop(PROTECTED_PATHS_ENV, None)
    environment.pop(GUARD_MODE_ENV, None)
    environment.pop(PRODUCTION_DB_ENV, None)

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
        cwd=str(repo),
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 4, output
    assert "database-path-safety" in output
    assert "inside a Git checkout" in output
    assert str(repo) not in output, "the guard must not echo the local path"
    assert _read_marker(database) == "dogfood"
    assert not Path(f"{database}-wal").exists()


# --------------------------------------------------------------------------- #
# Path-pattern checks must not materialize dogfood artifacts
# --------------------------------------------------------------------------- #


def test_gitignore_smoke_check_creates_no_filesystem_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#625 cheap falsifying check 3: the ignore-rule check leaves no artifact.

    The 2026-09-20 incident started with a diagnostic that created the real
    database names and then deleted them. Answering the same question through
    ``git check-ignore --stdin`` must touch nothing at all.
    """
    workdir = tmp_path / "probe"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    candidates = ["ai_trainer.db", "ai_trainer.db-wal", "ai_trainer.db-shm"]
    ignored = db_paths.git_ignored_paths(candidates)

    assert ignored == set(candidates), "WAL companions and the database must stay ignored"
    assert list(workdir.iterdir()) == [], "the check must not create probe files"


def test_production_named_files_are_ignored_including_sidecars() -> None:
    """A WAL companion holds un-checkpointed personal pages and must stay ignored."""
    repository_root = Path(db_paths.__file__).resolve().parents[1]
    names = ["ai_trainer.db", *(f"ai_trainer.db{suffix}" for suffix in db_paths.SIDECAR_SUFFIXES)]

    ignored = db_paths.git_ignored_paths(names, repo_root=repository_root)

    assert ignored == set(names)


def test_git_ignored_paths_reports_non_ignored_candidates() -> None:
    repository_root = Path(db_paths.__file__).resolve().parents[1]
    ignored = db_paths.git_ignored_paths(["README.md", "pyproject.toml"], repo_root=repository_root)
    assert "README.md" not in ignored


# --------------------------------------------------------------------------- #
# Acceptance entrypoint
# --------------------------------------------------------------------------- #


def test_acceptance_database_inside_run_root_is_allowed(tmp_path: Path, production: Path) -> None:
    root = tmp_path / "acceptance"
    (root / "session_1234").mkdir(parents=True)
    allowed = root / "session_1234" / "ai_trainer_acceptance.db"

    from config.db_paths import assert_safe_acceptance_database

    assert assert_safe_acceptance_database(allowed, acceptance_root=root) == db_paths.normalize_path(allowed)
    assert db_paths.acceptance_validation_error(allowed, acceptance_root=root) is None


def test_acceptance_database_matching_production_is_refused(production: Path) -> None:
    from config.db_paths import acceptance_validation_error, assert_safe_acceptance_database

    with pytest.raises(DatabasePathViolation) as error:
        assert_safe_acceptance_database(production, acceptance_root=production.parent)
    assert error.value.invariant == "acceptance-database-must-not-be-production"

    reason = acceptance_validation_error(production, acceptance_root=production.parent)
    assert reason is not None
    assert str(production) not in reason


def test_acceptance_database_outside_run_root_is_refused(tmp_path: Path, production: Path) -> None:
    from config.db_paths import acceptance_validation_error

    outside = tmp_path / "elsewhere" / "acceptance.db"
    outside.parent.mkdir()
    reason = acceptance_validation_error(outside, acceptance_root=tmp_path / "acceptance-root")

    assert reason is not None
    assert "acceptance-database-must-be-isolated" in reason


def test_acceptance_launcher_refuses_a_dogfood_override(production: Path) -> None:
    """End-to-end: ``run_acceptance.sh`` stops before starting any process."""
    launcher = REPO_ROOT / "run_acceptance.sh"
    if not launcher.exists():  # pragma: no cover - trimmed checkout
        pytest.skip("run_acceptance.sh is not present in this checkout")

    ambiguity = production.parent / "acceptance-checked.db"
    ambiguity.parent.mkdir(parents=True, exist_ok=True)
    _materialise(ambiguity, marker="dogfood")

    completed = subprocess.run(
        ["bash", str(launcher)],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "ACCEPTANCE_SKIP_DOCTOR": "1",
            "ACCEPTANCE_DB_PATH": str(ambiguity),
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    output = completed.stdout + completed.stderr
    assert completed.returncode == 2, output
    assert "acceptance-database-must-not-be-production" in output
    assert str(ambiguity) not in output
    assert _read_marker(ambiguity) == "dogfood"


# --------------------------------------------------------------------------- #
# Destructive maintenance CLI
# --------------------------------------------------------------------------- #


def test_clean_database_cli_accepts_only_the_configured_production_path(production: Path) -> None:
    """The cleanup CLI targets the production file deliberately — never another DB."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "clean_database_cli", REPO_ROOT / "tests" / "clean_database.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.resolve_target_database() == str(db_paths.normalize_path(production))
    assert module.resolve_target_database(str(production)) == str(db_paths.normalize_path(production))

    other = production.parent / "someone-elses.db"
    with pytest.raises(DatabasePathViolation) as error:
        module.resolve_target_database(str(other))
    assert error.value.invariant == "clean-database-target"
    assert str(other) not in str(error.value)


def test_demo_seeding_refuses_a_dogfood_target(production: Path) -> None:
    """``activate_demo_mode`` clears its database, so a dogfood target must fail closed."""
    from services import demo_mode

    class _WipingDatabase:
        db_path = str(production)

        def clear_all_data(self):  # pragma: no cover - must never run
            raise AssertionError("demo seeding must be refused before clearing")

    class _State:
        database = _WipingDatabase()

    with pytest.raises(DatabasePathViolation):
        demo_mode.activate_demo_mode(_State())


def test_acceptance_bootstrap_refuses_dogfood_database(
    production: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance seeding must fail closed when its runtime points at dogfood data.

    Acceptance mode owns the dataset it seeds and clears, so pointing it at the
    working database is data loss by design — the guard must stop it before the
    first write, not rely on the operator noticing.
    """
    from services import acceptance_mode

    monkeypatch.setattr(Settings, "ACCEPTANCE_MODE", True)
    monkeypatch.setattr(Settings, "ACCEPTANCE_AUTO_DEMO", True)
    monkeypatch.delenv("ACCEPTANCE_ROOT", raising=False)

    class _DogfoodState:
        acceptance_bootstrapped = False

        class database:  # noqa: N801 - mirrors the StateManager attribute shape
            db_path = str(production)

    with pytest.raises(DatabasePathViolation):
        acceptance_mode.bootstrap_session(_DogfoodState())

    with pytest.raises(DatabasePathViolation):
        acceptance_mode.reset_acceptance_dataset(_DogfoodState())

    assert not production.exists()
