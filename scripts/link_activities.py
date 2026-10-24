#!/usr/bin/env python3
"""Preview an exact Intervals/Garmin link; mutate only an explicitly stopped DB."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.activity_manual_links import manage_manual_link  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--intervals-id', required=True)
    parser.add_argument('--garmin-id', required=True)
    parser.add_argument('--unlink', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-token')
    parser.add_argument('--reason')
    parser.add_argument('--confirm-stopped', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = manage_manual_link(
            args.database, args.intervals_id, args.garmin_id, apply=args.apply,
            unlink=args.unlink, expected_token=args.expected_token,
            reason=args.reason, confirm_stopped=args.confirm_stopped,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result['allowed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
