"""Early pytest boundary. Product Database never imports this module."""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from config.database_paths import ScratchPathError, assert_disjoint_database_families, database_path_candidates
from scripts.scratch_runtime import ScratchScope, _SCOPE_ENV, scope_from_environment

_scope: ScratchScope | None = None
_guard_installed = False
_pytest_bootstrapped = False
_sqlite_audit = {"allowed": 0, "blocked": 0}
_INITIAL_SELECTION: tuple[str, ...] | None = None
_SITE = Path(__file__).resolve().parent / "_scratch_site"
_REPO = _SITE.parent.parent


def child_environment(env: Mapping[str, str]) -> dict[str, str]:
    """Propagate verified scope receipt and early audit into Python children."""
    if _scope is None:
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap")
    result = dict(env)
    result[_SCOPE_ENV] = json.dumps(_scope.descriptor())
    paths = [str(_SITE), str(_REPO), *result.get("PYTHONPATH", "").split(os.pathsep)]
    result["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(filter(None, paths)))
    return result



def fresh_child_environment(env: Mapping[str, str]) -> dict[str, str]:
    """An independent pytest bootstrap still receives a verified child scope."""
    if _scope is None:
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap")
    parent = _scope.validate_directory(_scope.root / "children")
    parent.mkdir(mode=0o700, exist_ok=True)
    scope = ScratchScope.create(parent=parent)
    result = child_environment(env)
    result[_SCOPE_ENV] = json.dumps(scope.descriptor())
    return result


def _validate_child_handoff(args: tuple[Any, ...], scope: ScratchScope) -> None:
    # A custom env cannot accidentally discard the early child audit. This is
    # a runner boundary, not a sandbox for hostile shell/native programs.
    env = os.environ if args[3] is None else args[3]
    try:
        data = json.loads(env[_SCOPE_ENV])
        root = Path(data["root"]).resolve()
        if not root.is_relative_to(scope.root):
            raise ValueError
        if env.get("PYTHONPATH", "").split(os.pathsep)[0] != str(_SITE):
            raise ValueError
        executable = os.path.basename(os.fsdecode(args[0])).lower()
        if executable.startswith("python"):
            for arg in args[1][1:]:
                if arg in {"-I", "-S", "-E"}:
                    raise ValueError
                if arg in {"-m", "-c"} or not arg.startswith("-"):
                    break
    except (KeyError, TypeError, ValueError, OSError, RuntimeError):
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None

def install_sqlite_guard(scope: ScratchScope) -> None:
    """Audit direct sqlite3 opens, later Settings overrides and credential reads."""
    global _scope, _guard_installed
    if _guard_installed:
        if _scope is None or _scope.descriptor() != scope.descriptor():
            raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap")
        return
    _scope = scope
    try:
        import dotenv
    except ModuleNotFoundError as exc:
        if exc.name != "dotenv":
            raise
        # Standard-library-only helpers (e.g. a shell watchdog's python3)
        # still receive the SQLite/file/network audit without this package.
    else:
        dotenv.load_dotenv = lambda *args, **kwargs: False

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "sqlite3.connect":
            try:
                scope.validate_target(args[0], purpose="sqlite")
            except ScratchPathError:
                _sqlite_audit["blocked"] += 1
                raise
            _sqlite_audit["allowed"] += 1
        elif event == "open" and isinstance(args[0], (str, bytes)):
            name = Path(os.fsdecode(args[0])).name
            if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
                flags = args[2]
                writing_owned_fixture = isinstance(flags, int) and flags & os.O_WRONLY
                if not writing_owned_fixture:
                    raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")
                scope.validate_directory(Path(os.fsdecode(args[0])).parent / name)
        elif event == "subprocess.Popen":
            _validate_child_handoff(args, scope)
        elif event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple) and address[0] not in {"localhost", "127.0.0.1", "::1"}:
                raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")

    sys.addaudithook(audit)
    _guard_installed = True


def bootstrap_pytest() -> ScratchScope:
    """Run before Settings or test imports; explicit foreign overrides refuse."""
    global _scope, _INITIAL_SELECTION, _pytest_bootstrapped
    if _pytest_bootstrapped and _scope is not None:
        for key in ("DATABASE_PATH", "DEMO_DATABASE_PATH"):
            if key in os.environ:
                _scope.validate_target(os.environ[key], purpose="bootstrap")
        return _scope
    if "config.settings" in sys.modules:
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap")
    scope = _scope or scope_from_environment()
    owned = scope is None
    _INITIAL_SELECTION = tuple(map(str, database_path_candidates(
        os.environ, platform=sys.platform, home=str(Path.home()), cwd=str(Path.cwd()), checkout=_REPO,
    )))
    if scope is None:
        scope = ScratchScope.create()
    try:
        for key in ("DATABASE_PATH", "DEMO_DATABASE_PATH"):
            if key in os.environ:
                scope.validate_target(os.environ[key], purpose="bootstrap")
        real = Path(os.environ.get("DATABASE_PATH", str(scope.root / "runtime.db")))
        demo = Path(os.environ.get("DEMO_DATABASE_PATH", str(scope.root / "demo.db")))
        protected = [Path(path) for path in _INITIAL_SELECTION if not Path(path).is_relative_to(scope.root)]
        assert_disjoint_database_families(real, protected)
        assert_disjoint_database_families(demo, [real, *protected])
        scope.validate_target(real, purpose="bootstrap")
        scope.validate_target(demo, purpose="bootstrap")
        for name in ("home", "tmp", "chats"):
            (scope.root / name).mkdir(exist_ok=True)
        # All credentials are removed before Settings can capture them. Live
        # operator tooling uses its own explicit flow, never this test contour.
        for key in list(os.environ):
            if key.endswith(("_API_KEY", "_PASSWORD", "_TOKEN", "_SECRET")) or key in {"GARMIN_EMAIL", "INTERVALS_ICU_ATHLETE_ID"}:
                os.environ.pop(key, None)
        os.environ.update({
            "DATABASE_PATH": str(real), "DEMO_DATABASE_PATH": str(demo),
            "HOME": str(scope.root / "home"), "USERPROFILE": str(scope.root / "home"),
            "XDG_DATA_HOME": str(scope.root / "home/data"), "LOCALAPPDATA": str(scope.root / "home/local"),
            "TMPDIR": str(scope.root / "tmp"), "TEMP": str(scope.root / "tmp"),
            "TMP": str(scope.root / "tmp"), "CHATS_DIR": str(scope.root / "chats"),
            "DEFAULT_AI_PROVIDER": "mock",
        })
        import tempfile
        tempfile.tempdir = None  # It may have cached TMPDIR before conftest.
        install_sqlite_guard(scope)
        os.environ.update(child_environment(os.environ))
        _pytest_bootstrapped = True
        if owned:
            atexit.register(scope.cleanup)
        return scope
    except (OSError, RuntimeError, ValueError):
        if owned:
            scope.cleanup()
        raise ScratchPathError("scratch_target_unowned", purpose="bootstrap") from None


def sqlite_audit_counts() -> dict[str, int]:
    """Aggregate only: no filenames/SQL/values; children report separately."""
    return dict(_sqlite_audit)
