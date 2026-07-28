"""Contract for contributor-safe secret scanning (TD-002 / Issue #295)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


WORKFLOW = Path(".github/workflows/secret-scan.yml")
PROBE = Path("scripts/verify_secret_scanner.py")
IGNORE = Path(".gitleaksignore")
CHECKOUT_SHA = "de0fac2e4500dabe0009e67214ff5f5447ce83dd"
GITLEAKS_ACTION_SHA = "e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e"


def _workflow_text() -> str:
    assert WORKFLOW.exists(), "dedicated secret-scan workflow must exist"
    return WORKFLOW.read_text()


def test_secret_scan_workflow_has_contributor_safe_triggers_and_permissions() -> None:
    workflow = _workflow_text()

    assert "\n  pull_request:" in workflow
    assert "\n  push:" in workflow
    assert "      - main" in workflow
    assert "pull_request_target" not in workflow
    assert re.search(r"(?m)^permissions:\n  contents: read$", workflow)
    assert not re.search(r"(?m)^\s+\S+:\s*write\s*$", workflow)


def test_secret_scan_workflow_pins_actions_and_does_not_persist_credentials() -> None:
    workflow = _workflow_text()
    uses = re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", workflow)

    assert uses == [
        f"actions/checkout@{CHECKOUT_SHA}",
        f"gitleaks/gitleaks-action@{GITLEAKS_ACTION_SHA}",
    ]
    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow


def test_secret_scan_workflow_passes_no_application_secrets() -> None:
    workflow = _workflow_text()

    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "secrets." not in workflow
    assert 'GITLEAKS_VERSION: "8.30.1"' in workflow
    assert 'GITLEAKS_ENABLE_COMMENTS: "false"' in workflow
    assert 'GITLEAKS_ENABLE_UPLOAD_ARTIFACT: "false"' in workflow
    assert "GITLEAKS_LICENSE" not in workflow


def test_secret_scan_workflow_scans_current_tree_then_runs_synthetic_probe() -> None:
    workflow = _workflow_text()

    action_index = workflow.index("gitleaks/gitleaks-action@")
    tree_index = workflow.index("gitleaks dir")
    probe_index = workflow.index("python3 scripts/verify_secret_scanner.py")
    assert action_index < tree_index < probe_index
    assert "--redact" in workflow


def test_gitleaks_exceptions_are_only_verified_non_secret_shapes() -> None:
    fingerprints = {
        line
        for line in IGNORE.read_text().splitlines()
        if line and not line.startswith("#")
    }

    assert fingerprints == {
        ".env.example:generic-api-key:37",
        "docs/intervals_primary_quickstart.md:generic-api-key:20",
        "docs/self_hosted_deployment_execplan.md:curl-auth-user:331",
        "tests/smoke/test_garmin_auth_messages.py:generic-api-key:79",
    }
    assert not any("archived/" in fingerprint for fingerprint in fingerprints)


def _write_fake_scanner(path: Path, exit_code: int) -> None:
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    path.chmod(0o755)


def _run_probe(scanner: Path) -> subprocess.CompletedProcess[str]:
    assert PROBE.exists(), "runtime-only synthetic probe must exist"
    return subprocess.run(
        [sys.executable, str(PROBE), "--scanner", str(scanner)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_synthetic_probe_accepts_only_the_detection_exit_code(tmp_path: Path) -> None:
    detected = tmp_path / "detected"
    _write_fake_scanner(detected, 42)
    assert _run_probe(detected).returncode == 0

    clean = tmp_path / "clean"
    _write_fake_scanner(clean, 0)
    clean_result = _run_probe(clean)
    assert clean_result.returncode != 0
    assert "did not detect" in clean_result.stderr

    broken = tmp_path / "broken"
    _write_fake_scanner(broken, 2)
    broken_result = _run_probe(broken)
    assert broken_result.returncode != 0
    assert "failed unexpectedly" in broken_result.stderr


def test_synthetic_probe_does_not_commit_a_complete_token_literal() -> None:
    source = PROBE.read_text()

    assert "--exit-code=42" in source
    assert "--redact" in source
    assert not re.search(r"ghp_[A-Za-z0-9]{36}", source)
    assert not re.search(r"(?:AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16}", source)
