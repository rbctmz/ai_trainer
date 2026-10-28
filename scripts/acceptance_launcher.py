"""Own and validate the temporary database for an acceptance launch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database_paths import ScratchPathError, assert_disjoint_database_families
from scripts.scratch_runtime import ScratchScope, scope_from_environment

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "scripts" / "_scratch_site"


def validate_acceptance_child_environment(env: dict[str, str]) -> ScratchScope:
    """Refuse unknown identity or changed targets before application imports."""
    scope = scope_from_environment()
    if scope is None:
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap")
    try:
        real = scope.validate_target(env["DATABASE_PATH"], purpose="bootstrap")
        demo = scope.validate_target(env["DEMO_DATABASE_PATH"], purpose="bootstrap")
        scope.validate_directory(Path(env["CHATS_DIR"]))
        if real is None or demo is None:
            raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")
        assert_disjoint_database_families(real, [demo])
    except (KeyError, TypeError):
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None
    return scope


def prepare_environment(scope: ScratchScope, original: dict[str, str]) -> dict[str, str]:
    """Reject external overrides before doctor, network, seed or server."""
    for key in ("DATABASE_PATH", "DEMO_DATABASE_PATH", "ACCEPTANCE_DB_PATH"):
        if key in original:
            scope.validate_target(original[key], purpose="bootstrap")
    if "CHATS_DIR" in original:
        scope.validate_directory(Path(original["CHATS_DIR"]))
    if ("DATABASE_PATH" in original and "ACCEPTANCE_DB_PATH" in original
            and Path(original["DATABASE_PATH"]).resolve() != Path(original["ACCEPTANCE_DB_PATH"]).resolve()):
        raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")
    env = dict(original)
    for key in list(env):
        if key.endswith(("_API_KEY", "_PASSWORD", "_TOKEN", "_SECRET")) or key in {"GARMIN_EMAIL", "INTERVALS_ICU_ATHLETE_ID"}:
            env.pop(key, None)
    home = scope.root / "home"
    home.mkdir(mode=0o700)
    temporary = scope.root / "tmp"
    temporary.mkdir(mode=0o700)
    env.update({
        "DATABASE_PATH": original.get("ACCEPTANCE_DB_PATH", original.get("DATABASE_PATH", str(scope.root / "acceptance.db"))),
        "DEMO_DATABASE_PATH": original.get("DEMO_DATABASE_PATH", str(scope.root / "demo.db")),
        "CHATS_DIR": original.get("CHATS_DIR", str(scope.root / "chats")),
        "HOME": str(home), "USERPROFILE": str(home),
        "XDG_CONFIG_HOME": str(home / "config"), "XDG_DATA_HOME": str(home / "data"),
        "XDG_CACHE_HOME": str(home / "cache"), "LOCALAPPDATA": str(home / "local"),
        "TMPDIR": str(temporary), "TEMP": str(temporary), "TMP": str(temporary),
        "ACCEPTANCE_MODE": "1", "ACCEPTANCE_DISABLE_GARMIN": "1",
        "ACCEPTANCE_AUTO_DEMO": original.get("ACCEPTANCE_AUTO_DEMO", "1"),
        "DEFAULT_AI_PROVIDER": "mock", "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python",
        "STREAMLIT_SERVER_HEADLESS": "true", "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "AI_TRAINER_SCRATCH_SCOPE": json.dumps(scope.descriptor()),
        "PYTHONPATH": os.pathsep.join([str(SITE), str(ROOT), original.get("PYTHONPATH", "")]),
    })
    real = scope.validate_target(env["DATABASE_PATH"], purpose="bootstrap")
    demo = scope.validate_target(env["DEMO_DATABASE_PATH"], purpose="bootstrap")
    if real is None or demo is None:
        raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")
    assert_disjoint_database_families(real, [demo])
    scope.validate_directory(Path(env["CHATS_DIR"]))
    return env


def main() -> int:
    scope = None
    status = 2
    try:
        parent = os.environ.get("ACCEPTANCE_ROOT")
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True)
        scope = ScratchScope.create(parent=Path(parent) if parent else None)
        env = prepare_environment(scope, dict(os.environ))
        venv = ROOT / "ai_trainer_env" / "bin" / "python"
        python = str(venv) if venv.is_file() else os.environ.get("PYTHON_BIN", sys.executable)
        status = 0
        if os.environ.get("ACCEPTANCE_SKIP_DOCTOR", "0") != "1":
            for check in ("--runtime", "--workspace"):
                result = subprocess.run([python, str(ROOT / "scripts" / "doctor_env.py"), "check", check], env=env, cwd=ROOT, check=False)
                if result.returncode:
                    status = result.returncode
                    break
        if status == 0:
            port = int(os.environ.get("ACCEPTANCE_PORT", "8510"))
            if not 1 <= port <= 65535:
                raise ValueError("invalid port")
            print(f"Acceptance: http://127.0.0.1:{port}", flush=True)
            status = subprocess.run([python, "-m", "streamlit", "run", str(ROOT / "app.py"),
                                     "--server.fileWatcherType", "none", "--server.address", "127.0.0.1",
                                     "--server.port", str(port)],
                                    env=env, cwd=ROOT, check=False).returncode
    except ScratchPathError as exc:
        print(str(exc), file=sys.stderr)
        status = 2
    except (OSError, ValueError):
        print("scratch_identity_unknown: bootstrap", file=sys.stderr)
        status = 2
    finally:
        if scope is not None:
            try:
                scope.cleanup()
            except ScratchPathError as exc:
                print(str(exc), file=sys.stderr)
                status = 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
