from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

import pytest


pytestmark = pytest.mark.smoke


def _load_doctor_env_module():
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        sys.modules.pop("doctor_env", None)
        module = importlib.import_module("doctor_env")
        return importlib.reload(module)
    finally:
        sys.path.pop(0)


def test_run_python_check_times_out_instead_of_hanging(monkeypatch: pytest.MonkeyPatch):
    doctor_env = _load_doctor_env_module()
    monkeypatch.setenv("AI_TRAINER_DOCTOR_TIMEOUT_SECONDS", "7")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(doctor_env.subprocess, "run", fake_run)

    result = doctor_env.run_python_check("print('ok')")

    assert result.ok is False
    assert result.details == "timed out after 7s"


def test_check_dev_reports_timeout(monkeypatch: pytest.MonkeyPatch):
    doctor_env = _load_doctor_env_module()
    monkeypatch.setenv("AI_TRAINER_DOCTOR_TIMEOUT_SECONDS", "3")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(doctor_env.subprocess, "run", fake_run)

    results = doctor_env.check_dev()

    assert len(results) == 1
    assert results[0].name == "pytest-entrypoint"
    assert results[0].ok is False
    assert results[0].details == "timed out after 3s"


def test_check_workspace_reports_dataless_project_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    doctor_env = _load_doctor_env_module()

    for relative_path in (
        Path("app.py"),
        Path("utils/modern_ui.py"),
        Path("ui/navigation.py"),
        Path("ui/pages/__init__.py"),
    ):
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("# probe\n", encoding="utf-8")

    dataless_target = tmp_path / "utils/modern_ui.py"

    def fake_path_flags(path: Path) -> int:
        if path == dataless_target:
            return doctor_env.SF_DATALESS
        return 0

    monkeypatch.setattr(doctor_env, "_path_flags", fake_path_flags)

    results = doctor_env.check_workspace(base_dir=tmp_path)

    assert [result.name for result in results] == [
        "workspace-location",
        "workspace-availability",
    ]
    assert results[1].ok is False
    assert "utils/modern_ui.py" in results[1].details
    assert "dataless/offloaded workspace files" in results[1].details


def test_check_workspace_import_timeout_mentions_icloud_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    doctor_env = _load_doctor_env_module()

    monkeypatch.setattr(doctor_env, "_find_dataless_workspace_paths", lambda _base_dir: [])
    monkeypatch.setattr(doctor_env, "_is_cloud_backed_workspace_path", lambda _base_dir: True)
    monkeypatch.setattr(
        doctor_env,
        "run_python_check",
        lambda _code, cwd=None: doctor_env.CheckResult(
            name="python-check",
            ok=False,
            details="timed out after 15s",
        ),
    )

    results = doctor_env.check_workspace(base_dir=tmp_path)

    assert [result.name for result in results] == [
        "workspace-location",
        "workspace-imports",
    ]
    assert results[1].ok is False
    assert "timed out after 15s" in results[1].details
    assert "iCloud-backed workspace" in results[1].details
