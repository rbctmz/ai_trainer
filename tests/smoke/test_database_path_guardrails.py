"""#625: characterize refusal before collection and scratch identity boundaries."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def child_env(home: Path) -> dict[str, str]:
    home.mkdir(exist_ok=True)
    return {
        "PATH": os.defpath, "HOME": str(home), "TMPDIR": str(home),
        "PYTHONPATH": str(ROOT), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python",
    }


def run_collection(tmp_path: Path, *, override: str | None = None, extra: tuple[str, ...] = ()):
    project = tmp_path / "project"
    tests = project / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/conftest.py", tests / "conftest.py")
    (project / "pytest.ini").write_text("[pytest]\naddopts = -ra\n")
    (project / ".env").write_text("SHOULD_NOT_LOAD_625=private-sentinel\n")
    (tests / "test_probe.py").write_text(
        "import os, sqlite3\nfrom config.settings import Settings\n"
        "with sqlite3.connect(Settings.DATABASE_PATH) as c:\n"
        "    c.execute('CREATE TABLE collection_write(value TEXT)')\n"
        "def test_owned():\n    assert 'SHOULD_NOT_LOAD_625' not in os.environ\n"
    )
    env = child_env(tmp_path / "home")
    if override is not None:
        env["DATABASE_PATH"] = override
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra, "tests/"],
        cwd=project, env=env, capture_output=True, text=True, timeout=30,
    )


def test_external_override_refused_before_collection_without_disclosing_path(tmp_path):
    sentinel = tmp_path / "private-owner.db"
    with sqlite3.connect(sentinel) as conn:
        conn.execute("CREATE TABLE keep(value TEXT)")
    before = sentinel.read_bytes()
    result = run_collection(tmp_path, override=str(sentinel))
    assert result.returncode != 0, result.stdout
    assert "scratch_target_unowned" in result.stdout + result.stderr
    assert str(sentinel) not in result.stdout + result.stderr
    assert sentinel.read_bytes() == before


def test_default_collection_uses_owned_store_without_loading_dotenv(tmp_path):
    result = run_collection(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert not (tmp_path / "project/ai_trainer.db").exists()


def test_existing_foreign_basetemp_refused_before_pytest_deletes_it(tmp_path):
    sentinel_dir = tmp_path / "must-keep"
    sentinel_dir.mkdir()
    (sentinel_dir / "marker").write_text("keep")
    result = run_collection(tmp_path, extra=("--basetemp", str(sentinel_dir)))
    assert result.returncode != 0
    assert "scratch_cleanup_unowned" in result.stdout + result.stderr
    assert (sentinel_dir / "marker").read_text() == "keep"


def test_owned_scope_allows_own_files_and_cleanup_is_idempotent(tmp_path):
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    path = scope.root / "own.db"
    assert scope.validate_target(path, purpose="test") == path
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ok(value TEXT)")
    scope.validate_target(path, purpose="test")
    scope.cleanup()
    scope.cleanup()
    assert not path.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_protected_family_blocks_future_names(tmp_path, suffix):
    from config.database_paths import ScratchPathError, assert_disjoint_database_families

    target = tmp_path / "future.db"
    with pytest.raises(ScratchPathError, match="scratch_protected_family"):
        assert_disjoint_database_families(target, [Path(str(target) + suffix)])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "parent_symlink", "hardlink"])
def test_foreign_aliases_and_links_are_not_owned(tmp_path, kind):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    protected = tmp_path / "external.db"
    protected.write_text("keep")
    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / "alias.db"
    if kind == "hardlink":
        os.link(protected, target)
    elif kind == "symlink":
        target.symlink_to(protected)
    else:
        (scope.root / "link").symlink_to(tmp_path, target_is_directory=True)
        target = scope.root / "link/external.db"
    with pytest.raises(ScratchPathError):
        scope.validate_target(target, purpose="test")
    scope.cleanup()
    assert protected.read_text() == "keep"


def test_sqlite_uri_parsing_cannot_escape_scope(tmp_path):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    assert scope.validate_target(":memory:", purpose="test") is None
    assert scope.validate_target("file::memory:?cache=shared", purpose="test") is None
    assert scope.validate_target((scope.root / "a.db").as_uri()+"?mode=ro", purpose="test") == scope.root / "a.db"
    for target in ((tmp_path / "external.db").as_uri(), "file:a.db?vfs=unknown", "file:a.db?mode=memory&vfs=unknown"):
        with pytest.raises(ScratchPathError):
            scope.validate_target(target, purpose="test")
    scope.cleanup()


def test_application_constructor_stays_usable_without_test_hooks(tmp_path):
    env = child_env(tmp_path / "app-home")
    env["DATABASE_PATH"] = str(tmp_path / "app.db")
    result = subprocess.run(
        [sys.executable, "-c", "import dotenv; dotenv.load_dotenv=lambda *a,**k:False; "
         "from data.database import Database; d=Database(); "
         "c=d._connect(); c.execute('CREATE TABLE compatibility(value TEXT)'); "
         "c.execute(\"INSERT INTO compatibility VALUES ('ok')\"); c.commit(); "
         "print(c.execute('SELECT value FROM compatibility').fetchone()[0]); c.close()"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_scope_rejects_replaced_root_without_removing_foreign_data(tmp_path):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    original = scope.root.with_name(scope.root.name + "-old")
    scope.root.rename(original)
    scope.root.mkdir()
    (scope.root / "foreign").write_text("keep")
    with pytest.raises(ScratchPathError, match="scratch_cleanup_unowned"):
        scope.cleanup()
    assert (scope.root / "foreign").read_text() == "keep"
    shutil.rmtree(original)
