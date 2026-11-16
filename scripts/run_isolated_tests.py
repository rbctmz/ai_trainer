#!/usr/bin/env python3
"""Run pytest after the owned-scratch boundary is installed, including collection."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.database_paths import ScratchPathError  # noqa: E402
from scripts.scratch_pytest import bootstrap_pytest  # noqa: E402


def main() -> int:
    try:
        bootstrap_pytest()
    except ScratchPathError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    import pytest
    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
