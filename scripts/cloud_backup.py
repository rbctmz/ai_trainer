#!/usr/bin/env python3
"""Explicit operator cloud backup command; no implicit init, activation or cleanup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cloud_backups import read_cloud_status, run_cloud_backup, run_cloud_drill  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'run', 'drill'))
    parser.add_argument('--config', required=True, help='absolute private operator config path')
    args = parser.parse_args(argv)
    operation = {'status': read_cloud_status, 'run': run_cloud_backup, 'drill': run_cloud_drill}[args.action]
    result = operation(args.config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result['state'] == 'degraded' or (args.action == 'drill' and result['drill_warning']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
