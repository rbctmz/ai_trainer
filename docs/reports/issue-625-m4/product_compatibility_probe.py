#!/usr/bin/env python3
"""Run an ordinary product/demo lifecycle using only private synthetic files.

Run from an isolated source snapshot with dependencies installed. This is a
single-use acceptance probe, not a production launcher or runtime guard.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.scratch_runtime import ScratchScope  # noqa: E402

CHILD = r'''
import logging, os, sqlite3, sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
root = Path(os.environ['PROBE_ROOT']).resolve()
seen = []
def audit(event, args):
    if event == 'sqlite3.connect':
        raw = str(args[0])
        if raw == ':memory:' or raw.startswith('file::memory:'):
            return
        value = unquote(urlsplit(raw).path) if raw.startswith('file:') else raw
        path = Path(value).resolve()
        if not path.is_relative_to(root):
            raise PermissionError('product probe blocked foreign sqlite')
        seen.append(path.name)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = Path(os.fsdecode(args[0])).name
        if name == '.env' or name.startswith('.env.'):
            raise PermissionError('product probe blocked dotenv')
    if event == 'socket.connect':
        raise PermissionError('product probe blocked network')
sys.addaudithook(audit)
import dotenv
dotenv.load_dotenv = lambda *a, **kw: False
logging.disable(logging.CRITICAL)
from data.database import Database
from fastapi.testclient import TestClient
from api.main import app
assert 'AI_TRAINER_SCRATCH_SCOPE' not in os.environ
if sys.argv[1] == 'seed':
    real = Database()
    real.set_user_setting('m4_synthetic_marker', 'present')
    with TestClient(app) as client:
        result = client.post('/api/demo/seed')
        assert result.status_code == 200 and result.json()['seeded']
    with sqlite3.connect(os.environ['DEMO_DATABASE_PATH']) as con:
        assert con.execute('SELECT COUNT(*) FROM activities').fetchone()[0] > 0
else:
    assert Database().get_user_setting('m4_synthetic_marker') == 'present'
    with TestClient(app) as client:
        result = client.post('/api/demo/clear')
        assert result.status_code == 200 and result.json()['cleared']
    assert Database().get_user_setting('m4_synthetic_marker') == 'present'
    with sqlite3.connect(os.environ['DEMO_DATABASE_PATH']) as con:
        assert con.execute('SELECT COUNT(*) FROM activities').fetchone()[0] == 0
assert seen and set(seen) <= {'product.db', 'demo.db'}
print('phase=' + sys.argv[1] + ' sqlite_connects=' + str(len(seen)) + ' status=PASS')
'''


def main() -> int:
    scope = ScratchScope.create()
    try:
        home = scope.root / 'home'
        home.mkdir()
        env = {
            'PATH': os.environ.get('PATH', ''), 'HOME': str(home),
            'TMPDIR': str(scope.root), 'PYTHONPATH': str(ROOT),
            'PROBE_ROOT': str(scope.root), 'DEFAULT_AI_PROVIDER': 'mock',
            'DATABASE_PATH': str(scope.root / 'product.db'),
            'DEMO_DATABASE_PATH': str(scope.root / 'demo.db'),
            'CHATS_DIR': str(scope.root / 'chats'),
            'PYTHONDONTWRITEBYTECODE': '1',
            'PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION': 'python',
        }
        for phase in ('seed', 'restart-and-clear'):
            result = subprocess.run([sys.executable, '-c', CHILD, phase], cwd=ROOT,
                                    env=env, text=True, capture_output=True, timeout=120)
            if result.returncode:
                print('product compatibility probe failed at ' + phase, file=sys.stderr)
                return 1
            print(result.stdout.strip())
        return 0
    finally:
        scope.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
