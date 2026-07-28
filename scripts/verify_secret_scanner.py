#!/usr/bin/env python3
"""Prove that the configured scanner detects a runtime-only synthetic token."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


DETECTION_EXIT_CODE = 42


def _synthetic_access_key_id() -> str:
    """Build an AWS-shaped identifier without storing it as a source literal."""
    prefix = "".join(("A", "K", "I", "A"))
    payload = "".join(("A2B3", "C4D5", "E6F7", "G2H3"))
    return prefix + payload


def verify_scanner(scanner: str) -> None:
    """Require the scanner to return the dedicated leak-detection exit code."""
    with tempfile.TemporaryDirectory(prefix="ai-trainer-secret-probe-") as raw_dir:
        probe_dir = Path(raw_dir)
        (probe_dir / "synthetic.txt").write_text(
            f"aws_access_key_id = {_synthetic_access_key_id()}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                scanner,
                "dir",
                "--redact",
                "--no-banner",
                "--exit-code=42",
                str(probe_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    if result.returncode == DETECTION_EXIT_CODE:
        print("Gitleaks detected the runtime-only synthetic secret.")
        return
    if result.returncode == 0:
        raise RuntimeError("secret scanner did not detect the synthetic secret")
    detail = (result.stderr or result.stdout).strip()
    raise RuntimeError(
        f"secret scanner failed unexpectedly with exit {result.returncode}: {detail}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scanner", default="gitleaks")
    args = parser.parse_args()
    try:
        verify_scanner(args.scanner)
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
