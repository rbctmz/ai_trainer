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
import sysconfig

from repair_streamlit_proto import (
    find_missing_aliases,
    find_purelib_dir,
    find_streamlit_proto_dir,
    patch_proto_init,
    repair_sniffio,
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def run_python_check(code: str) -> CheckResult:
    env = os.environ.copy()
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
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
    pytest_check = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        capture_output=True,
        text=True,
    )
    details = (pytest_check.stdout or pytest_check.stderr or "").strip()
    return [
        CheckResult(
            name="pytest-entrypoint",
            ok=pytest_check.returncode == 0,
            details=details or "pytest not available",
        )
    ]


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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    target_runtime = args.runtime or not args.dev
    target_dev = args.dev or not args.runtime

    if args.command == "check":
        results: list[CheckResult] = []
        if target_runtime:
            results.extend(check_runtime())
        if target_dev:
            results.extend(check_dev())
        return print_results(results)

    if target_runtime:
        for message in repair_runtime():
            print(f"🔧 {message}")
    if target_dev:
        for message in repair_dev():
            print(f"🔧 {message}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
