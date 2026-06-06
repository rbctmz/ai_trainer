"""Garmin-specific service helpers."""
from __future__ import annotations

from typing import Any, Dict

from state import StateManager


def get_client(state: StateManager):
    """Return an initialized Garmin client instance."""
    return state.garmin_client


def authenticate(state: StateManager, email: str, password: str) -> bool:
    """Authenticate the Garmin client with provided credentials."""
    client = get_client(state)
    if not email or not password:
        return False
    return client.authenticate(email, password)


def disconnect(state: StateManager) -> None:
    """Disconnect the Garmin client and clear session flags."""
    client = get_client(state)
    client.disconnect()


def connection_info(state: StateManager) -> Dict[str, Any]:
    """Return diagnostic info about the Garmin connection."""
    client = get_client(state)
    return client.get_connection_info() or {}


def user_profile(state: StateManager) -> Dict[str, Any] | None:
    """Return the Garmin user profile if available."""
    client = get_client(state)
    return client.get_user_profile()

__all__ = ['get_client', 'authenticate', 'disconnect', 'connection_info', 'user_profile']
