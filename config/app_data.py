"""Platform application-data directory for single-athlete runtime state (#622/#624).

Why this module exists
----------------------
``Settings.DATABASE_PATH`` defaulted to a bare ``ai_trainer.db``, resolved against
the current working directory. In a dogfood checkout that put personal training
history, coach decisions and readiness evidence inside the working tree, sharing
fate with sources, tests and agent operations — the coupling that made the
2026-09-20 deletion unrecoverable.

The default therefore moves to the platform-standard per-user application-data
directory, which no checkout, test run or ``git clean`` touches. An explicit
``DATABASE_PATH`` keeps working and keeps priority; this module only decides what
"no explicit setting" means.

Platform contract (issue #624 asks for documented macOS / Linux / Windows
semantics):

======================  ==========================================================
macOS                   ``~/Library/Application Support/ai_trainer``
Linux/BSD               ``$XDG_DATA_HOME/ai_trainer`` or ``~/.local/share/ai_trainer``
Windows                 ``%LOCALAPPDATA%\\ai_trainer`` (``%APPDATA%`` fallback)
Docker                  unchanged — the image sets ``DATABASE_PATH=/data/ai_trainer.db``
======================  ==========================================================

``AI_TRAINER_APP_DATA`` overrides everything, which is also how tests and
acceptance runs redirect the runtime without touching the settings object.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "APP_DATA_DIR_ENV",
    "DATABASE_NAME",
    "app_data_directory",
    "default_database_path",
    "legacy_repository_database_path",
]

#: Explicit override for the application-data directory (all platforms).
APP_DATA_DIR_ENV = "AI_TRAINER_APP_DATA"

#: Filename of the runtime database inside the application-data directory.
DATABASE_NAME = "ai_trainer.db"


def _expanded(raw: str) -> Path:
    return Path(raw).expanduser()


def app_data_directory() -> Path | None:
    """Return the per-user application-data directory, or ``None`` if unknown.

    ``None`` (no resolvable home directory and no override) rather than a guess:
    callers must keep the previous working-directory behaviour instead of
    inventing a location the operator cannot predict.
    """
    override = os.getenv(APP_DATA_DIR_ENV, "").strip()
    if override:
        return _expanded(override)

    if sys.platform == "darwin":
        home = os.path.expanduser("~")
        if home == "~":
            return None
        return Path(home) / "Library" / "Application Support" / "ai_trainer"

    if os.name == "nt":  # pragma: no cover - covered on Windows CI only
        base = (os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or "").strip()
        if not base:
            return None
        return _expanded(base) / "ai_trainer"

    xdg = os.getenv("XDG_DATA_HOME", "").strip()
    if xdg:
        return _expanded(xdg) / "ai_trainer"

    home = os.path.expanduser("~")
    if home == "~":
        return None
    return Path(home) / ".local" / "share" / "ai_trainer"


def default_database_path() -> str | None:
    """Database location a fresh install uses when ``DATABASE_PATH`` is unset."""
    directory = app_data_directory()
    if directory is None:
        return None
    return str(directory / DATABASE_NAME)


def legacy_repository_database_path(repository_root: str | os.PathLike[str] | None = None) -> Path:
    """Pre-#624 working-copy location, kept for the migration path only.

    This is NOT a runtime default any more: it names the file the migration
    command reads from, and what the operator may keep as an untouched
    pre-migration copy.
    """
    root = Path(repository_root) if repository_root is not None else Path.cwd()
    return root / DATABASE_NAME
