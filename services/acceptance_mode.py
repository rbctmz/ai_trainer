"""Helpers for isolated acceptance-mode launches."""
from __future__ import annotations

from typing import Any

from config.settings import Settings
from state import StateManager

from . import demo_mode as demo_mode_service


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


def bootstrap_session(state: StateManager) -> dict[str, Any]:
    """Seed the isolated acceptance dataset once per browser session."""
    info = runtime_info(state)
    info["seeded"] = False

    if not info["enabled"]:
        return info

    if getattr(state, "acceptance_bootstrapped", False):
        return info

    state.acceptance_bootstrapped = True

    if not info["auto_demo"]:
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
