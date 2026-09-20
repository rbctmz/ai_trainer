"""Helpers for isolated acceptance-mode launches."""
from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from config.db_paths import assert_safe_acceptance_database
from config.settings import Settings

from . import demo_mode as demo_mode_service

if TYPE_CHECKING:
    from state import StateManager


def is_acceptance_mode() -> bool:
    """Return whether the app runs in isolated acceptance mode."""
    return bool(Settings.ACCEPTANCE_MODE)


def auto_demo_enabled() -> bool:
    """Return whether acceptance mode should auto-seed the demo dataset."""
    return is_acceptance_mode() and bool(Settings.ACCEPTANCE_AUTO_DEMO)


def garmin_disabled() -> bool:
    """Return whether real Garmin login is disabled in this runtime."""
    return is_acceptance_mode() and bool(Settings.ACCEPTANCE_DISABLE_GARMIN)


def runtime_info(state: StateManager | None = None) -> dict[str, Any]:
    """Expose user-facing acceptance runtime details."""
    db_path = Settings.DATABASE_PATH
    if state is not None:
        try:
            db_path = state.database.db_path
        except Exception:
            db_path = Settings.DATABASE_PATH

    return {
        "enabled": is_acceptance_mode(),
        "label": Settings.ACCEPTANCE_LABEL,
        "auto_demo": auto_demo_enabled(),
        "garmin_disabled": garmin_disabled(),
        "database_path": db_path,
    }


def _has_existing_isolated_data(state: StateManager) -> bool:
    """Return whether the isolated database already contains seeded or user-generated data."""
    database = state.database
    stats = {}

    try:
        stats = database.get_database_stats()
    except Exception:
        stats = {}

    tracked_counts = [
        int(stats.get("activities", 0) or 0),
        int(stats.get("hrv_data", 0) or 0),
        int(stats.get("sleep_data", 0) or 0),
        int(stats.get("daily_health", 0) or 0),
        int(stats.get("training_status", 0) or 0),
    ]
    if any(count > 0 for count in tracked_counts):
        return True

    try:
        return database.get_latest_planning_checkpoint() is not None
    except Exception:
        return False


def _is_demo_dataset(state: StateManager) -> bool:
    """Return whether the preserved isolated dataset originated from demo mode."""
    return demo_mode_service.dataset_origin(state) == demo_mode_service.DATASET_ORIGIN_DEMO


def bootstrap_session(state: StateManager) -> dict[str, Any]:
    """Seed the isolated acceptance dataset once per browser session."""
    info = runtime_info(state)
    info["seeded"] = False
    info["preserved_existing_data"] = False

    if not info["enabled"]:
        return info

    # Fail closed before any seeding: an acceptance run must never own dogfood data.
    _assert_isolated_acceptance_database(state)

    if getattr(state, "acceptance_bootstrapped", False):
        return info

    state.acceptance_bootstrapped = True

    if not info["auto_demo"]:
        return info

    if _has_existing_isolated_data(state):
        info["preserved_existing_data"] = True
        info["restored_demo_session"] = False
        if _is_demo_dataset(state):
            demo_mode_service.restore_demo_mode_session(state)
            info["restored_demo_session"] = True
        return info

    info["seed_result"] = demo_mode_service.activate_demo_mode(state)
    info["seeded"] = True

    return info


def _assert_isolated_acceptance_database(state: StateManager) -> None:
    """Fail closed before acceptance mode seeds or clears anything (#625).

    Acceptance mode owns the dataset it runs against: it seeds demo rows and can
    reset them. ``ACCEPTANCE_DB_PATH`` is an override in ``run_acceptance.sh``, so
    a typo there previously resolved the production database — and this mode
    would have wiped it. The check runs before the first write and names the
    violated invariant without echoing the local path.
    """
    database_path = getattr(getattr(state, "database", None), "db_path", None) or Settings.DATABASE_PATH
    assert_safe_acceptance_database(database_path)


def reset_acceptance_dataset(state: StateManager) -> dict[str, int]:
    """Recreate the isolated acceptance dataset from scratch."""
    if not is_acceptance_mode():
        raise RuntimeError("Acceptance reset is available only in acceptance mode.")

    _assert_isolated_acceptance_database(state)
    state.acceptance_bootstrapped = True
    return demo_mode_service.activate_demo_mode(state)


__all__ = [
    "auto_demo_enabled",
    "bootstrap_session",
    "garmin_disabled",
    "is_acceptance_mode",
    "reset_acceptance_dataset",
    "runtime_info",
]
