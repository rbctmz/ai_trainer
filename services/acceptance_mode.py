"""Helpers for isolated acceptance-mode launches."""
from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

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


def bootstrap_session(state: StateManager) -> dict[str, Any]:
    """Seed the isolated acceptance dataset once per browser session."""
    info = runtime_info(state)
    info["seeded"] = False
    info["preserved_existing_data"] = False

    if not info["enabled"]:
        return info

    if getattr(state, "acceptance_bootstrapped", False):
        return info

    state.acceptance_bootstrapped = True

    if not info["auto_demo"]:
        return info

    if _has_existing_isolated_data(state):
        demo_mode_service.restore_demo_mode_session(state)
        info["preserved_existing_data"] = True
        return info

    info["seed_result"] = demo_mode_service.activate_demo_mode(state)
    info["seeded"] = True

    return info


def reset_acceptance_dataset(state: StateManager) -> dict[str, int]:
    """Recreate the isolated acceptance dataset from scratch."""
    if not is_acceptance_mode():
        raise RuntimeError("Acceptance reset is available only in acceptance mode.")

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
