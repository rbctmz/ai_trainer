"""#624 M1: only synthetic paths/DBs, never the dogfood store."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def paths_module():
    return importlib.import_module("config.database_paths")


def resolve(tmp_path, env=None, platform="linux", home=None, cwd=None):
    return paths_module().resolve_database_paths(
        env or {}, platform=platform, home=str(home or tmp_path / "home"),
        cwd=str(cwd or tmp_path / "launch"),
    )


@pytest.mark.parametrize("platform,home,cwd,expected", [
    ("darwin", "/users/example", "/launch", "/users/example/Library/Application Support/ai_trainer/ai_trainer.db"),
    ("linux", "/users/example", "/launch", "/users/example/.local/share/ai_trainer/ai_trainer.db"),
    ("win32", "C:/Users/example", "C:/launch", "C:/Users/example/AppData/Local/ai_trainer/ai_trainer.db"),
])
def test_platform_defaults_are_pure_and_independent_of_cwd(tmp_path, platform, home, cwd, expected):
    module = paths_module()
    first = module.resolve_database_paths({}, platform=platform, home=home, cwd=cwd)
    second = module.resolve_database_paths({}, platform=platform, home=home, cwd=cwd + "/other")
    assert first.real.replace(chr(92), "/") == expected
    assert first.real == second.real
    assert first.origin == "platform"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("value", ["", "relative/data"])
def test_linux_ignores_nonabsolute_xdg(tmp_path, value):
    assert resolve(tmp_path, {"XDG_DATA_HOME": value}).real.endswith("/.local/share/ai_trainer/ai_trainer.db")


def test_xdg_absolute_override(tmp_path):
    assert resolve(tmp_path, {"XDG_DATA_HOME": str(tmp_path / "xdg")}).real == str(tmp_path / "xdg/ai_trainer/ai_trainer.db")


@pytest.mark.parametrize("value", ["", "relative/data"])
def test_windows_ignores_nonabsolute_localappdata(tmp_path, value):
    selection = paths_module().resolve_database_paths({"LOCALAPPDATA": value}, platform="win32", home="C:/Users/example", cwd="C:/launch")
    assert selection.real.replace(chr(92), "/") == "C:/Users/example/AppData/Local/ai_trainer/ai_trainer.db"


def test_windows_localappdata(tmp_path):
    selection = paths_module().resolve_database_paths({"LOCALAPPDATA": "D:/Local"}, platform="win32", home="C:/Users/example", cwd="C:/launch")
    assert selection.real.replace(chr(92), "/") == "D:/Local/ai_trainer/ai_trainer.db"


@pytest.mark.parametrize("value,tail", [("/data/ai_trainer.db", "/data/ai_trainer.db"), ("chosen.db", "/launch/chosen.db"), ("~/chosen.db", "/home/chosen.db")])
def test_explicit_path_wins_and_normalizes_once(tmp_path, value, tail):
    selection = resolve(tmp_path, {"DATABASE_PATH": value})
    assert selection.real.endswith(tail)
    assert selection.origin == "environment"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_database_override_is_configuration_error(tmp_path, value):
    with pytest.raises(paths_module().DatabasePathError, match="database_path_invalid"):
        resolve(tmp_path, {"DATABASE_PATH": value})


@pytest.mark.parametrize("platform,home", [("unknown", "/home/test"), ("linux", None)])
def test_unresolvable_default_fails_closed(tmp_path, platform, home):
    with pytest.raises(paths_module().DatabasePathError):
        paths_module().resolve_database_paths({}, platform=platform, home=home, cwd=str(tmp_path))


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
@pytest.mark.parametrize("target_exists", [False, True])
def test_separate_legacy_artifact_blocks_before_creation(tmp_path, suffix, target_exists):
    module = paths_module()
    launch = tmp_path / "launch"
    launch.mkdir()
    selection = resolve(tmp_path, cwd=launch)
    target = Path(selection.real)
    if target_exists:
        target.parent.mkdir(parents=True)
        target.write_bytes(b"selected marker")
    legacy = launch / ("ai_trainer.db" + suffix)
    legacy.write_bytes(b"legacy marker")
    with pytest.raises(module.DatabasePathError, match="database_migration_required"):
        module.runtime_database_path(selection, checkout=tmp_path / "checkout")
    assert legacy.read_bytes() == b"legacy marker"
    assert target.exists() is target_exists
    if target_exists:
        assert target.read_bytes() == b"selected marker"
    else:
        assert not target.parent.exists()


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_selected_platform_family_is_not_legacy(tmp_path, suffix):
    initial = resolve(tmp_path)
    target = Path(initial.real)
    target.parent.mkdir(parents=True)
    Path(str(target) + suffix).write_bytes(b"selected marker")
    selection = resolve(tmp_path, cwd=target.parent)
    assert paths_module().runtime_database_path(selection, checkout=tmp_path / "checkout") == str(target)


def test_selected_parent_symlink_not_legacy(tmp_path):
    target = Path(resolve(tmp_path).real)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"marker")
    alias = tmp_path / "alias"
    alias.symlink_to(target.parent, target_is_directory=True)
    assert paths_module().runtime_database_path(resolve(tmp_path, cwd=alias), checkout=tmp_path / "checkout") == str(target)


def test_ambiguous_hardlink_family_fails_closed(tmp_path):
    selection = resolve(tmp_path)
    target = Path(selection.real)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"marker")
    launch = Path(selection.launch_cwd)
    launch.mkdir()
    os.link(target, launch / "ai_trainer.db")
    with pytest.raises(paths_module().DatabasePathError, match="database_path_alias_ambiguous"):
        paths_module().runtime_database_path(selection, checkout=tmp_path / "checkout")


def test_linked_worktree_also_checks_primary_checkout(tmp_path):
    primary = tmp_path / "primary"
    metadata = primary / ".git/worktrees/review"
    metadata.mkdir(parents=True)
    (metadata / "commondir").write_text("../..")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: " + str(metadata))
    (primary / "ai_trainer.db-wal").write_bytes(b"legacy")
    with pytest.raises(paths_module().DatabasePathError, match="database_migration_required"):
        paths_module().runtime_database_path(resolve(tmp_path), checkout=worktree)
    assert not Path(resolve(tmp_path).real).exists()


def test_malformed_git_metadata_refuses(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text("not git metadata")
    with pytest.raises(paths_module().DatabasePathError, match="database_git_metadata_invalid"):
        paths_module().runtime_database_path(resolve(tmp_path), checkout=checkout)


def test_explicit_override_bypasses_legacy_preflight(tmp_path):
    launch = tmp_path / "launch"
    launch.mkdir()
    (launch / "ai_trainer.db").write_bytes(b"legacy")
    selection = resolve(tmp_path, {"DATABASE_PATH": str(tmp_path / "explicit.db")}, cwd=launch)
    assert paths_module().runtime_database_path(selection, checkout=tmp_path / "checkout") == selection.real


@pytest.mark.parametrize("alias_kind", ["same", "symlink", "hardlink"])
def test_demo_alias_refuses_before_open(tmp_path, alias_kind):
    module = paths_module()
    real = tmp_path / "real.db"
    real.write_bytes(b"real marker")
    demo = real if alias_kind == "same" else tmp_path / "demo.db"
    if alias_kind == "symlink":
        demo.symlink_to(real)
    if alias_kind == "hardlink":
        os.link(real, demo)
    with pytest.raises(module.DatabasePathError, match="database_demo_alias"):
        module.validate_demo_path(str(real), str(demo))
    assert real.read_bytes() == b"real marker"


def test_explicit_database_still_reads_and_writes(tmp_path):
    from data.database import Database
    db = Database(str(tmp_path / "explicit.db"))
    with db._connect() as conn:
        conn.execute("INSERT INTO user_settings(key,value) VALUES('624','kept')")
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT value FROM user_settings WHERE key='624'").fetchone()[0] == 'kept'


def test_settings_default_is_absolute_without_creating_database(tmp_path):
    env = dict(os.environ)
    env.pop("DATABASE_PATH", None)
    env.pop("DEMO_DATABASE_PATH", None)
    env.update(HOME=str(tmp_path), XDG_DATA_HOME=str(tmp_path / "xdg"))
    run = subprocess.run([sys.executable, "-c", "from config.settings import Settings; import json; print(json.dumps(Settings.DATABASE_PATH))"], env=env, cwd=tmp_path, capture_output=True, text=True, check=True)
    actual = json.loads(run.stdout)
    assert Path(actual).is_absolute(), actual
    expected = {
        "linux": tmp_path / "xdg/ai_trainer/ai_trainer.db",
        "darwin": tmp_path / "Library/Application Support/ai_trainer/ai_trainer.db",
        "win32": Path(env["LOCALAPPDATA"]) / "ai_trainer/ai_trainer.db",
    }
    assert actual == str(expected[sys.platform])
    assert not Path(actual).exists()


def test_relative_settings_override_is_frozen_at_import(tmp_path):
    env=dict(os.environ, DATABASE_PATH="relative.db")
    run=subprocess.run([sys.executable,"-c","from config.settings import Settings; import os,json; os.chdir('/'); print(json.dumps(Settings.DATABASE_PATH))"],env=env,cwd=tmp_path,capture_output=True,text=True,check=True)
    assert json.loads(run.stdout) == str(tmp_path / "relative.db")


@pytest.fixture
def selected_runtime(tmp_path, monkeypatch):
    from config.settings import Settings
    module = paths_module()
    selection = resolve(tmp_path)
    monkeypatch.setattr(Settings, '_DATABASE_PATHS', selection)
    monkeypatch.setattr(Settings, 'DATABASE_PATH', selection.real)
    monkeypatch.setattr(Settings, 'DEMO_DATABASE_PATH', selection.demo)
    monkeypatch.setattr(module, 'CHECKOUT_ROOT', tmp_path / 'checkout')
    return selection


def test_fresh_default_database_is_private_and_usable(selected_runtime):
    import stat
    from data.database import Database
    db = Database()
    assert db.db_path == selected_runtime.real
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 0
    if os.name == 'posix':
        assert stat.S_IMODE(Path(db.db_path).stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(db.db_path).parent.stat().st_mode) == 0o700


def test_noninitializing_default_does_not_create_paths(selected_runtime):
    from data.database import Database
    assert Database(initialize=False).db_path == selected_runtime.real
    assert not Path(selected_runtime.real).parent.exists()


@pytest.mark.parametrize('surface', ['database', 'dependency', 'api'])
def test_legacy_refusal_applies_to_every_default_open(selected_runtime, surface):
    launch = Path(selected_runtime.launch_cwd)
    launch.mkdir()
    (launch / 'ai_trainer.db-wal').write_bytes(b'legacy')
    with pytest.raises(paths_module().DatabasePathError, match='database_migration_required'):
        if surface == 'database':
            from data.database import Database
            Database()
        elif surface == 'dependency':
            from api.deps import real_database
            real_database()
        else:
            from fastapi.testclient import TestClient
            from api.main import app
            with TestClient(app):
                pytest.fail('startup should refuse')
    assert not Path(selected_runtime.real).parent.exists()


def test_api_health_does_not_create_default_database(selected_runtime, monkeypatch):
    from fastapi.testclient import TestClient
    import api.deps as deps
    from api.main import app
    monkeypatch.setattr(deps, 'DEMO_DB_PATH', selected_runtime.demo)
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
    assert not Path(selected_runtime.real).parent.exists()


def test_demo_dependency_refuses_alias_before_database_constructor(tmp_path, monkeypatch):
    import api.deps as deps
    from config.settings import Settings
    real = tmp_path / 'real.db'
    real.write_bytes(b'real marker')
    monkeypatch.setattr(Settings, 'DATABASE_PATH', str(real))
    monkeypatch.setattr(deps, 'DEMO_DB_PATH', str(real))
    def unexpected_open(*args):
        pytest.fail('database constructor must not be reached')
    monkeypatch.setattr(deps, '_db_for_path', unexpected_open)
    with pytest.raises(paths_module().DatabasePathError, match='database_demo_alias'):
        deps.demo_database()
    assert real.read_bytes() == b'real marker'


def test_backup_cli_default_matches_runtime(selected_runtime, capsys):
    from data.database import Database
    from scripts.sqlite_backup_restore import main
    path = Path(selected_runtime.real)
    path.parent.mkdir(parents=True)
    Database(str(path))
    output = path.parent / 'snapshot.db'
    assert main(['backup', '--output', str(output), '--confirm-stopped']) == 0
    assert json.loads(capsys.readouterr().out)['database'] == str(path)


def test_backup_explicit_path_bypasses_runtime_refusal(tmp_path, selected_runtime, capsys):
    from data.database import Database
    from scripts.sqlite_backup_restore import main
    launch = Path(selected_runtime.launch_cwd)
    launch.mkdir()
    (launch / 'ai_trainer.db').write_bytes(b'legacy')
    explicit = tmp_path / 'explicit.db'
    Database(str(explicit))
    snapshot = tmp_path / 'snapshot.db'
    assert main(['backup', '--database', str(explicit), '--output', str(snapshot), '--confirm-stopped']) == 0
    assert json.loads(capsys.readouterr().out)['database'] == str(explicit)
    assert not Path(selected_runtime.real).exists()


def test_backup_default_reports_refusal_without_traceback(selected_runtime, capsys):
    from scripts.sqlite_backup_restore import main
    launch = Path(selected_runtime.launch_cwd)
    launch.mkdir()
    (launch / 'ai_trainer.db').write_bytes(b'legacy')
    output = launch / 'snapshot.db'
    assert main(['backup', '--output', str(output), '--confirm-stopped']) == 2
    assert 'database_migration_required' in capsys.readouterr().err
    assert not output.exists()
    assert not Path(selected_runtime.real).exists()


def test_dangling_legacy_symlink_is_not_missing(tmp_path):
    selection = resolve(tmp_path)
    launch = Path(selection.launch_cwd)
    launch.mkdir()
    (launch / 'ai_trainer.db').symlink_to(launch / 'missing.db')
    with pytest.raises(paths_module().DatabasePathError, match='database_migration_required'):
        paths_module().runtime_database_path(selection, checkout=tmp_path / 'checkout')


@pytest.mark.parametrize('sidecar', [False, True])
def test_main_symlink_alone_does_not_establish_sqlite_family(tmp_path, sidecar):
    selection = resolve(tmp_path)
    target = Path(selection.real)
    target.parent.mkdir(parents=True)
    target.write_bytes(b'selected')
    launch = Path(selection.launch_cwd)
    launch.mkdir()
    (launch / 'ai_trainer.db').symlink_to(target)
    if sidecar:
        (launch / 'ai_trainer.db-wal').write_bytes(b'legacy WAL')
    with pytest.raises(paths_module().DatabasePathError, match='database_path_alias_ambiguous'):
        paths_module().runtime_database_path(selection, checkout=tmp_path / 'checkout')
    assert target.read_bytes() == b'selected'


def test_unusable_default_parent_reports_named_refusal(tmp_path):
    parent = tmp_path / 'not-a-directory'
    parent.write_bytes(b'keep')
    with pytest.raises(paths_module().DatabasePathError, match='database_path_unwritable'):
        paths_module().prepare_private_database_path(str(parent / 'database.db'))
    assert parent.read_bytes() == b'keep'



def test_platform_data_override_cannot_put_default_inside_checkout(tmp_path):
    checkout = tmp_path / 'checkout'
    selection = resolve(tmp_path, {'XDG_DATA_HOME': str(checkout / 'data')})
    with pytest.raises(paths_module().DatabasePathError, match='database_default_inside_checkout'):
        paths_module().runtime_database_path(selection, checkout=checkout)
    assert not checkout.exists()
