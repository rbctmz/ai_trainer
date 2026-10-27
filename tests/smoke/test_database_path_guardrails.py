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
    from scripts.scratch_pytest import fresh_child_environment
    return fresh_child_environment({
        "PATH": os.defpath, "HOME": str(home), "TMPDIR": str(home),
        "PYTHONPATH": str(ROOT), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python",
    })


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


def test_application_constructor_stays_usable_inside_test_scope(tmp_path):
    env = child_env(tmp_path / "app-home")
    env["DATABASE_PATH"] = str(tmp_path / "app.db")
    from scripts.scratch_pytest import child_environment
    env = child_environment(env)
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


@pytest.mark.parametrize("surface", ["direct", "uri", "settings"])
def test_audit_blocks_late_escape_in_fresh_child(tmp_path, surface):
    import json
    from scripts.scratch_runtime import ScratchScope

    sentinel = tmp_path / "private-sentinel.db"
    with sqlite3.connect(sentinel) as conn:
        conn.execute("CREATE TABLE keep(value TEXT)")
    before = sentinel.read_bytes()
    scope = ScratchScope.create(parent=tmp_path)
    env = child_env(tmp_path / "child-home")
    env.update({
        "AI_TRAINER_SCRATCH_SCOPE": json.dumps(scope.descriptor()),
        "PYTHONPATH": str(ROOT / "scripts/_scratch_site") + os.pathsep + str(ROOT),
        "ESCAPE_TARGET": str(sentinel),
    })
    script = "import os,sqlite3; target=os.environ['ESCAPE_TARGET']; "
    if surface == "settings":
        script += "from config.settings import Settings; Settings.DATABASE_PATH=target; from data.database import Database; Database()"
    elif surface == "uri":
        script += "from pathlib import Path; sqlite3.connect(Path(target).as_uri()+'?mode=rw', uri=True)"
    else:
        script += "sqlite3.connect(target)"
    result = subprocess.run([sys.executable, "-c", script], env=env, cwd=tmp_path, text=True, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "scratch_target_unowned" in result.stderr
    assert str(sentinel) not in result.stderr
    assert sentinel.read_bytes() == before
    scope.cleanup()


def test_receipt_is_not_an_environment_flag_and_damaged_receipt_stops_child(tmp_path):
    import json
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    data = scope.descriptor()
    data["token"] = "not-the-owned-receipt"
    env = child_env(tmp_path / "child-home")
    env.update({"AI_TRAINER_SCRATCH_SCOPE": json.dumps(data),
                "PYTHONPATH": str(ROOT / "scripts/_scratch_site") + os.pathsep + str(ROOT)})
    result = subprocess.run([sys.executable, "-c", "print('SHOULD_NOT_RUN')"], cwd=tmp_path, env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "scratch_identity_unknown: bootstrap\n"
    scope.cleanup()


def test_cleanup_unlinks_nested_symlink_and_keeps_external_directory(tmp_path):
    from scripts.scratch_runtime import ScratchScope

    external = tmp_path / "external"
    external.mkdir()
    (external / "keep").write_text("keep")
    scope = ScratchScope.create(parent=tmp_path)
    (scope.root / "external-link").symlink_to(external, target_is_directory=True)
    scope.cleanup()
    assert (external / "keep").read_text() == "keep"


def test_launcher_and_plain_pytest_both_install_before_collection(tmp_path):
    # Independent project with the same early conftest; launcher installs even
    # before pytest plugin loading. No target override is an implicit real path.
    result = run_collection(tmp_path)
    assert result.returncode == 0
    project = tmp_path / "project"
    env = child_env(tmp_path / "launcher-home")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_isolated_tests.py"), "-q", "-p", "no:cacheprovider", "tests/"], cwd=project, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


@pytest.mark.parametrize("value", ["file:test.db?vfs=unix-none", "file:test.db?mode=ro&mode=rw", "https://localhost/db", "file:test.db?cache=unknown"])
def test_unknown_sqlite_uri_options_fail_closed(value):
    from config.database_paths import ScratchPathError, sqlite_target_path

    with pytest.raises(ScratchPathError, match="scratch_identity_unknown"):
        sqlite_target_path(value)


def test_sqlite_tilde_is_literal_and_cannot_hide_an_outside_filename(tmp_path, monkeypatch):
    from config.database_paths import sqlite_target_path
    from scripts.scratch_runtime import ScratchScope
    from config.database_paths import ScratchPathError

    scope = ScratchScope.create(parent=tmp_path)
    monkeypatch.setenv("HOME", str(scope.root))
    monkeypatch.chdir(tmp_path)
    assert sqlite_target_path("~/escaped.db") == tmp_path / "~/escaped.db"
    with pytest.raises(ScratchPathError, match="scratch_target_unowned"):
        scope.validate_target("~/escaped.db", purpose="test")
    scope.cleanup()


def test_reserved_real_and_demo_sidecars_refuse_even_before_main_exists(tmp_path):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    for name in ("runtime.db", "demo.db"):
        for suffix in ("-wal", "-shm", "-journal"):
            with pytest.raises(ScratchPathError, match="scratch_protected_family"):
                scope.validate_target(scope.root / (name + suffix), purpose="test")
    scope.cleanup()


def test_native_case_alias_in_protected_family_is_detected(tmp_path):
    from config.database_paths import ScratchPathError, assert_disjoint_database_families

    protected = tmp_path / "CaseSensitiveName.db"
    protected.write_text("synthetic")
    alias = tmp_path / "casesensitivename.db"
    if not alias.exists():
        pytest.skip("native case-sensitive filesystem: distinct filenames")
    with pytest.raises(ScratchPathError, match="scratch_protected_family"):
        assert_disjoint_database_families(alias, [protected])


@pytest.mark.parametrize("kind", ["dangling", "loop"])
def test_unresolved_symlinks_fail_closed(tmp_path, kind):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / "bad.db"
    target.symlink_to(scope.root / ("missing.db" if kind == "dangling" else "bad.db"))
    with pytest.raises(ScratchPathError, match="scratch_identity_unknown"):
        scope.validate_target(target, purpose="test")
    scope.cleanup()


def test_inspection_failure_is_safe_and_does_not_disclose_target(tmp_path, monkeypatch):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    target = scope.root / "private-target.db"
    original = Path.resolve

    def unreadable(path, *args, **kwargs):
        if path == target:
            raise PermissionError(str(target))
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", unreadable)
        with pytest.raises(ScratchPathError) as error:
            scope.validate_target(target, purpose="test")
        assert str(target) not in str(error.value)
        assert error.value.__suppress_context__
    scope.cleanup()


def test_snapshot_of_path_candidates_keeps_explicit_default_and_legacy(tmp_path):
    from config.database_paths import database_path_candidates

    home, checkout, launch = [tmp_path / name for name in ("home", "checkout", "launch")]
    for path in (home, checkout, launch):
        path.mkdir()
    env = {"DATABASE_PATH": str(tmp_path / "explicit.db"), "XDG_DATA_HOME": str(home / "data")}
    captured = database_path_candidates(env, platform="linux", home=str(home), cwd=str(launch), checkout=checkout)
    env["DATABASE_PATH"] = str(tmp_path / "later.db")
    assert tmp_path / "explicit.db" in captured
    assert home / "data/ai_trainer/ai_trainer.db" in captured
    assert checkout / "ai_trainer.db" in captured
    assert launch / "ai_trainer.db" in captured
    assert tmp_path / "later.db" not in captured
    assert list(home.iterdir()) == []


def test_native_unicode_alias_is_detected_when_filesystem_normalizes_names(tmp_path):
    from config.database_paths import ScratchPathError, assert_disjoint_database_families

    protected = tmp_path / "caf\u00e9.db"
    protected.write_text("synthetic")
    alias = tmp_path / "cafe\u0301.db"
    if not alias.exists():
        pytest.skip("native filesystem keeps composed/decomposed Unicode distinct")
    with pytest.raises(ScratchPathError, match="scratch_protected_family"):
        assert_disjoint_database_families(alias, [protected])


@pytest.mark.parametrize("uri", [True, False])
def test_memory_uri_has_no_filesystem_effect_with_native_sqlite(tmp_path, uri):
    target = tmp_path / "should-not-exist.db"
    with sqlite3.connect(target.as_uri() + "?mode=memory&cache=shared", uri=uri) as connection:
        connection.execute("CREATE TABLE memory_only(value TEXT)")
    assert not target.exists()


def test_constructed_object_cannot_claim_an_existing_private_directory(tmp_path):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    foreign = tmp_path / "existing-private"
    foreign.mkdir(mode=0o700)
    (foreign / "keep").write_text("keep")
    info = foreign.stat()
    invented = ScratchScope(foreign, (info.st_dev, info.st_ino), "invented", os.getpid())
    with pytest.raises(ScratchPathError, match="scratch_cleanup_unowned"):
        invented.cleanup()
    assert (foreign / "keep").read_text() == "keep"


def test_custom_child_env_cannot_silently_drop_the_guard(tmp_path):
    from config.database_paths import ScratchPathError

    sentinel = tmp_path / "child-escape.db"
    env = {"PATH": os.defpath, "HOME": str(tmp_path), "DATABASE_PATH": str(sentinel)}
    with pytest.raises(ScratchPathError, match="scratch_identity_unknown"):
        subprocess.run([sys.executable, "-c", "import os,sqlite3; sqlite3.connect(os.environ['DATABASE_PATH'])"],
                       cwd=tmp_path, env=env, check=True, capture_output=True, timeout=10)
    assert not sentinel.exists()


@pytest.mark.parametrize("operation", ["attach", "vacuum"])
@pytest.mark.parametrize("inside", [False, True])
@pytest.mark.parametrize("clear_caller_authorizer", [False, True])
def test_sql_open_operations_respect_scope_before_creating_destination(tmp_path, operation, inside, clear_caller_authorizer):
    import json
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    destination = (scope.root if inside else tmp_path) / "destination.db"
    env = child_env(tmp_path / "child-home")
    env.update({"AI_TRAINER_SCRATCH_SCOPE": json.dumps(scope.descriptor()),
                "MAIN": str(scope.root / "main.db"), "DEST": str(destination), "OP": operation,
                "CLEAR_AUTH": "1" if clear_caller_authorizer else "0"})
    script = (
        "import os,sqlite3; c=sqlite3.connect(os.environ['MAIN']); "
        "c.execute('CREATE TABLE keep(value TEXT)'); c.commit(); "
        "c.set_authorizer(None) if os.environ['CLEAR_AUTH']=='1' else None; "
        "quoted=\"'\"+os.environ['DEST'].replace(\"'\",\"''\")+\"'\"; "
        "sql=('ATTACH DATABASE '+quoted+' AS other') if os.environ['OP']=='attach' else ('VACUUM INTO '+quoted); c.execute(sql)"
    )
    result = subprocess.run([sys.executable, "-c", script], env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    if inside:
        assert result.returncode == 0, result.stderr
        assert destination.exists()
    else:
        assert result.returncode != 0
        assert "scratch_target_unowned" in result.stderr
        assert str(destination) not in result.stderr
        assert not destination.exists()
    scope.cleanup()


@pytest.mark.parametrize("main,sidecar", [("Future.db", "future.DB-WAL"), ("caf\u00e9.db", "cafe\u0301.DB-shm")])
def test_future_family_names_refuse_case_and_unicode_ambiguity(tmp_path, main, sidecar):
    from config.database_paths import ScratchPathError, assert_disjoint_database_families

    with pytest.raises(ScratchPathError, match="scratch_protected_family"):
        assert_disjoint_database_families(tmp_path / main, [tmp_path / sidecar])
    assert list(tmp_path.iterdir()) == []


def test_reserved_family_refuses_uppercase_sidecar_before_creation(tmp_path):
    from config.database_paths import ScratchPathError
    from scripts.scratch_runtime import ScratchScope

    scope = ScratchScope.create(parent=tmp_path)
    with pytest.raises(ScratchPathError, match="scratch_protected_family"):
        scope.validate_target(scope.root / "RUNTIME.DB-WAL", purpose="test")
    scope.cleanup()
