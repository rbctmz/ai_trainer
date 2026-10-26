"""Bounded #625 M1 characterization; synthetic stores only, no runtime guard."""
from __future__ import annotations

import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[3]
BASELINE = "12615561218bf2b5e5288d3a5ed2f9cf01f11145"


def main() -> None:
    revision = subprocess.check_output(["git", "rev-parse", BASELINE], cwd=REPO, text=True).strip()
    archive = subprocess.check_output(["git", "archive", BASELINE], cwd=REPO)
    with tempfile.TemporaryDirectory(prefix="ai-trainer-625-m1-") as temporary:
        root = Path(temporary).resolve()
        source = root / "source"
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            for member in bundle.getmembers():
                if member.issym() or member.islnk() or Path(member.name).is_absolute() or ".." in Path(member.name).parts:
                    raise RuntimeError("source archive contains unsafe member")
            bundle.extractall(source)
        for name in ("home", "tmp", "chats", "session"):
            (root / name).mkdir()
        env = {
            "PATH": os.defpath,
            "HOME": str(root / "home"),
            "TMPDIR": str(root / "tmp"),
            "DATABASE_PATH": str(root / "selected.db"),
            "DEMO_DATABASE_PATH": str(root / "demo.db"),
            "CHATS_DIR": str(root / "chats"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION": "python",
            "DEFAULT_AI_PROVIDER": "mock",
        }
        # The audit is an experiment containment measure, not the proposed guard.
        bootstrap = f'''
import os, sys, json, socket
from pathlib import Path
from urllib.parse import unquote, urlsplit
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
root = Path({str(root)!r})
sys.path.insert(0, {str(source)!r})
def audit(event, args):
    if event == "sqlite3.connect":
        raw = str(args[0])
        if raw != ":memory:":
            path = unquote(urlsplit(raw).path) if raw.startswith("file:") else raw
            if not Path(path).resolve().is_relative_to(root):
                raise PermissionError("probe SQLite escaped owned root")
    if event == "socket.connect":
        raise PermissionError("probe network blocked")
    if event == "open" and isinstance(args[0], (str, bytes)):
        name = Path(os.fsdecode(args[0])).name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            raise PermissionError("probe credential file blocked")
sys.addaudithook(audit)
'''
        probe = bootstrap + '''
from config.database_paths import resolve_database_paths, validate_demo_path
original = resolve_database_paths({"DATABASE_PATH": str(root/"protected.db")}, platform=sys.platform, home=str(root/"home"), cwd=str(root))
rebound = resolve_database_paths({"DATABASE_PATH": str(root/"scratch.db")}, platform=sys.platform, home=str(root/"home"), cwd=str(root))
alias = root/"protected.db"
alias.write_text("synthetic sentinel")
(root/"alias.db").symlink_to(alias)
os.link(alias, root/"hardlink.db")
try:
    validate_demo_path(str(alias), str(alias)+"-wal")
    sidecar = "allowed"
except Exception:
    sidecar = "blocked"
import pytest
outcomes = []
class Recorder:
    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            outcomes.append(report.outcome)
result = pytest.main(["tests/test_hrv_logic.py", "-q", "--basetemp="+str(root/"pytest")], plugins=[Recorder()])
created_before_inspection = (root/"selected.db").is_file()
assert created_before_inspection, "legacy test did not create a database"
import sqlite3
with sqlite3.connect(root/"selected.db") as conn:
    tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
print("M1_JSON="+json.dumps({"rebound_path_differs": original.real != rebound.real, "symlink_samefile": alias.samefile(root/"alias.db"), "hardlink_samefile": alias.samefile(root/"hardlink.db"), "demo_sidecar_selection": sidecar, "legacy_pytest_exit": int(result), "legacy_case_outcomes": outcomes, "legacy_created_database_before_inspection": created_before_inspection, "legacy_table_count": tables}))
'''
        child = subprocess.run([sys.executable, "-c", probe], cwd=source, env=env, text=True, capture_output=True, timeout=45)
        if child.returncode:
            raise RuntimeError("synthetic Python probe failed; no personal paths were used")
        marker = next(line[8:] for line in child.stdout.splitlines() if line.startswith("M1_JSON="))
        observations = json.loads(marker)
        candidates = ("ai_trainer.db", "ai_trainer.db-wal", "ai_trainer.db-shm", "ai_trainer.db-journal")
        ignored = subprocess.run(["git", "-c", f"core.excludesFile={os.devnull}", "-c", "core.bare=false", "--work-tree="+str(source), "check-ignore", "--no-index", "--stdin"], cwd=REPO, env=env, input="\n".join(candidates)+"\n", text=True, capture_output=True, timeout=5)
        if ignored.returncode not in (0, 1):
            raise RuntimeError("read-only gitignore probe failed")
        observations["gitignore_ignored_candidates"] = ignored.stdout.splitlines()
        observations["gitignore_created_artifacts"] = any((source/name).exists() for name in candidates)
        # Launch the real shell script but replace Python/Streamlit with a stub.
        # It cannot import the application, open SQLite or start a service.
        stub = root / "python-stub"
        stub.write_text('#!/bin/sh\nif [ "$3" = "--version" ]; then exit 0; fi\nprintf "%s" "$DATABASE_PATH" > "$HOME/observed-target"\n')
        stub.chmod(0o700)
        acceptance_env = {**env, "PYTHON_BIN": str(stub), "STREAMLIT_BIN": str(stub), "ACCEPTANCE_SKIP_DOCTOR": "1", "ACCEPTANCE_ROOT": str(root/"session"), "ACCEPTANCE_DB_PATH": str(root/"outside-session.db")}
        launch = subprocess.run(["/bin/bash", "run_acceptance.sh"], cwd=source, env=acceptance_env, capture_output=True, timeout=10)
        observations["acceptance_exit"] = launch.returncode
        observations["acceptance_passed_external_target_to_stub"] = (root/"home/observed-target").read_text() == acceptance_env["ACCEPTANCE_DB_PATH"]
        calls = []
        for path in sorted((source/"tests").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Database" and not node.args and not node.keywords:
                    calls.append(f"{path.relative_to(source)}:{node.lineno}")
        print(json.dumps({"baseline_sha": revision, "observations": observations, "direct_zero_argument_Database_calls_static_only": calls, "runtime_scope": "one legacy pytest case, pure paths, stub acceptance; NOT full-suite coverage"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
