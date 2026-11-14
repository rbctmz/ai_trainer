#!/usr/bin/env python3
"""Explicit operator cloud backup command; no implicit init, activation or cleanup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cloud_backups import read_cloud_status, run_cloud_backup  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'run'))
    parser.add_argument('--config', required=True, help='absolute private operator config path')
    args = parser.parse_args(argv)
    result = read_cloud_status(args.config) if args.action == 'status' else run_cloud_backup(args.config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result['state'] == 'degraded' else 0


if __name__ == '__main__':
    raise SystemExit(main())
