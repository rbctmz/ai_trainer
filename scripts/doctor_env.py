#!/usr/bin/env python3
"""Validate and optionally repair the local AI Trainer Python environment."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys

from repair_streamlit_proto import (
    find_missing_aliases,
    find_purelib_dir,
    find_streamlit_proto_dir,
    patch_proto_init,
    repair_sniffio,
)

SF_DATALESS = 0x40000000
WORKSPACE_IMPORT_PROBE = (
    "from utils.modern_ui import ModernUI; "
    "from ui.navigation import render_primary_navigation; "
    "from ui.pages import render_dashboard_page; "
    "print('workspace-import-ok')"
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _resolve_check_timeout_seconds() -> int:
    raw_value = os.environ.get("AI_TRAINER_DOCTOR_TIMEOUT_SECONDS", "15").strip()
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 15


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_cloud_backed_workspace_path(path: Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    if "Mobile Documents" in resolved.parts:
        return True

    try:
        relative_to_home = resolved.relative_to(Path.home())
    except ValueError:
        return False

    return bool(relative_to_home.parts) and relative_to_home.parts[0] in {"Documents", "Desktop"}


def _iter_workspace_probe_paths(base_dir: Path) -> list[Path]:
    return [
        base_dir / "app.py",
        base_dir / "utils" / "modern_ui.py",
        base_dir / "ui" / "navigation.py",
        base_dir / "ui" / "pages" / "__init__.py",
    ]


def _path_flags(path: Path) -> int:
    try:
        return int(getattr(path.stat(), "st_flags", 0) or 0)
    except FileNotFoundError:
        return 0


def _find_dataless_workspace_paths(base_dir: Path) -> list[Path]:
    return [
        path
        for path in _iter_workspace_probe_paths(base_dir)
        if _path_flags(path) & SF_DATALESS
    ]


def run_python_check(code: str, cwd: str | None = None) -> CheckResult:
    env = os.environ.copy()
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    timeout_seconds = _resolve_check_timeout_seconds()
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="python-check",
            ok=False,
            details=f"timed out after {timeout_seconds}s",
        )
    details = (completed.stdout or completed.stderr or "").strip()
    return CheckResult(
        name="python-check",
        ok=completed.returncode == 0,
        details=details or "ok",
    )


def check_runtime() -> list[CheckResult]:
    results = []

    streamlit_check = run_python_check("import streamlit; print(streamlit.__version__)")
    results.append(
        CheckResult(
            name="streamlit-runtime",
            ok=streamlit_check.ok,
            details=streamlit_check.details,
        )
    )

    sniffio_check = run_python_check(
        "import sniffio; "
        "assert hasattr(sniffio, 'current_async_library'); "
        "assert hasattr(sniffio, 'AsyncLibraryNotFoundError'); "
        "print('sniffio-ok')"
    )
    results.append(
        CheckResult(
            name="sniffio-runtime",
            ok=sniffio_check.ok,
            details=sniffio_check.details,
        )
    )

    return results


def check_dev() -> list[CheckResult]:
    timeout_seconds = _resolve_check_timeout_seconds()
    try:
        pytest_check = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return [
            CheckResult(
                name="pytest-entrypoint",
                ok=False,
                details=f"timed out after {timeout_seconds}s",
            )
        ]
    details = (pytest_check.stdout or pytest_check.stderr or "").strip()
    return [
        CheckResult(
            name="pytest-entrypoint",
            ok=pytest_check.returncode == 0,
            details=details or "pytest not available",
        )
    ]


def check_workspace(base_dir: Path | None = None) -> list[CheckResult]:
    workspace_dir = (base_dir or _workspace_root()).resolve()
    results: list[CheckResult] = []
    cloud_backed = _is_cloud_backed_workspace_path(workspace_dir)

    if cloud_backed:
        location_details = (
            f"workspace is under {workspace_dir}; on macOS this location is often iCloud-backed, "
            "so keep the repo downloaded locally before running Streamlit or pytest"
        )
    else:
        location_details = f"workspace path is local-only: {workspace_dir}"
    results.append(CheckResult(name="workspace-location", ok=True, details=location_details))

    dataless_paths = _find_dataless_workspace_paths(workspace_dir)
    if dataless_paths:
        relative_paths = ", ".join(str(path.relative_to(workspace_dir)) for path in dataless_paths)
        results.append(
            CheckResult(
                name="workspace-availability",
                ok=False,
                details=(
                    f"dataless/offloaded workspace files detected: {relative_paths}. "
                    "Use Finder Download Now/Keep Downloaded or move the repo out of iCloud-backed folders."
                ),
            )
        )
        return results

    import_check = run_python_check(WORKSPACE_IMPORT_PROBE, cwd=str(workspace_dir))
    if import_check.ok:
        details = import_check.details
    elif cloud_backed:
        details = (
            f"{import_check.details}; local module import probe stalled in an iCloud-backed workspace. "
            "Use Finder Download Now/Keep Downloaded or move the repo out of iCloud Drive."
        )
    else:
        details = f"{import_check.details}; local module import probe failed from {workspace_dir}"

    results.append(CheckResult(name="workspace-imports", ok=import_check.ok, details=details))
    return results


def restore_legacy_pyc_files(package_dir: Path) -> int:
    if not package_dir.exists():
        return 0

    repaired = 0
    for pyc_path in sorted(package_dir.rglob("__pycache__/*.pyc")):
        stem = pyc_path.name.split(".cpython-", 1)[0]
        parent = pyc_path.parent.parent
        target_name = "__init__.pyc" if stem == "__init__" else f"{stem}.pyc"
        target_path = parent / target_name

        if target_path.exists():
            continue

        shutil.copy2(pyc_path, target_path)
        repaired += 1
    return repaired


def repair_runtime() -> list[str]:
    messages: list[str] = []
    purelib = find_purelib_dir()
    proto_dir = find_streamlit_proto_dir()

    repaired_sniffio = repair_sniffio(purelib)
    if repaired_sniffio:
        messages.append(f"Repaired {repaired_sniffio} sniffio runtime file(s)")

    missing_aliases = find_missing_aliases(proto_dir)
    if missing_aliases:
        patched = patch_proto_init(proto_dir)
        alias_names = ", ".join(item.name.replace(" 2", "", 1) for item in missing_aliases)
        if patched:
            messages.append(f"Installed Streamlit proto alias repair for: {alias_names}")
        else:
            messages.append(f"Streamlit proto alias repair already installed for: {alias_names}")

    if not messages:
        messages.append("Runtime environment already consistent")
    return messages


def repair_dev() -> list[str]:
    purelib = find_purelib_dir()
    repaired = 0
    for package_name in ("pytest", "_pytest", "pluggy", "iniconfig"):
        repaired += restore_legacy_pyc_files(purelib / package_name)

    if repaired:
        return [f"Restored {repaired} compiled dev dependency module file(s)"]
    return ["Dev dependency packages already have accessible module files"]


def repair_workspace() -> list[str]:
    return [
        "Workspace availability cannot be repaired automatically. "
        "Use Finder Download Now/Keep Downloaded or move the repo out of iCloud-backed folders."
    ]


def print_results(results: list[CheckResult]) -> int:
    failed = [result for result in results if not result.ok]
    for result in results:
        status = "✅" if result.ok else "❌"
        print(f"{status} {result.name}: {result.details}")
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "repair"))
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Target runtime dependencies needed to launch Streamlit.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Target contributor tooling such as pytest.",
    )
    parser.add_argument(
        "--workspace",
        action="store_true",
        help="Target local workspace availability needed to import project modules reliably.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    selected_any_target = args.runtime or args.dev or args.workspace
    target_runtime = args.runtime or not selected_any_target
    target_dev = args.dev or not selected_any_target
    target_workspace = args.workspace or not selected_any_target

    if args.command == "check":
        results: list[CheckResult] = []
        if target_runtime:
            results.extend(check_runtime())
        if target_dev:
            results.extend(check_dev())
        if target_workspace:
            results.extend(check_workspace())
        return print_results(results)

    if target_runtime:
        for message in repair_runtime():
            print(f"🔧 {message}")
    if target_dev:
        for message in repair_dev():
            print(f"🔧 {message}")
    if target_workspace:
        for message in repair_workspace():
            print(f"🔧 {message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
