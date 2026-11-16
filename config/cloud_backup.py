"""Pure cloud-operator configuration; importing this never loads .env or SQLite."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from config.database_paths import resolve_database_paths


def cloud_context_disabled(*, demo: bool = False, acceptance: bool = False) -> bool:
    return demo or acceptance or os.getenv('ACCEPTANCE_MODE', '0').strip().lower() in {'1', 'true', 'yes', 'on'}


def cloud_config_path() -> str:
    """Resolve only, independently of a database/BACKUP_DIR override."""
    if 'CLOUD_BACKUP_CONFIG' in os.environ:
        return os.environ['CLOUD_BACKUP_CONFIG']
    platform_env = {key: os.environ[key] for key in ('LOCALAPPDATA', 'XDG_DATA_HOME') if key in os.environ}
    default = resolve_database_paths(platform_env, platform=sys.platform, home=str(Path.home()), cwd=str(Path.cwd()))
    return str(Path(default.real).parent / 'cloud' / 'config.json')


def cloud_worker_environment() -> dict[str, str]:
    allowed = ('HOME', 'PATH', 'TMPDIR', 'LANG', 'PYTHONPATH', 'AI_TRAINER_SCRATCH_SCOPE',
               'DATABASE_PATH', 'DEMO_DATABASE_PATH', 'BACKUP_DIR', 'AUTO_BACKUP_ENABLED',
               'ACCEPTANCE_MODE', 'PRIMARY_ACTIVITY_SOURCE', 'PRIMARY_WELLNESS_SOURCE',
               'LOCALAPPDATA', 'XDG_DATA_HOME')
    return {key: os.environ[key] for key in allowed if key in os.environ}
