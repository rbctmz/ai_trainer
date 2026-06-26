"""Garmin-specific service helpers."""
from __future__ import annotations

from datetime import datetime
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


def auth_error(state: StateManager) -> str | None:
    """Return the latest authentication error if present."""
    return get_client(state).auth_error


def is_authenticated(state: StateManager) -> bool:
    """Return whether the Garmin client is authenticated."""
    return bool(get_client(state).is_authenticated)


def disconnect(state: StateManager) -> None:
    """Disconnect the Garmin client and clear session flags."""
    client = get_client(state)
    client.disconnect()


def connection_info(state: StateManager) -> Dict[str, Any]:
    """Return diagnostic info about the Garmin connection."""
    client = get_client(state)
    return client.get_connection_info() or {}


def pop_last_error(state: StateManager) -> Dict[str, Any] | None:
    """Return and clear the latest Garmin client error."""
    return get_client(state).pop_last_error()


def get_activities_with_error(
    state: StateManager,
    start_date: datetime,
    end_date: datetime,
    limit: int = 100,
) -> tuple[list[Any], Dict[str, Any] | None]:
    """Return Garmin activities plus any client error surfaced during retrieval."""
    client = get_client(state)
    activities = client.get_activities(start_date, end_date, limit=limit)
    return activities, client.pop_last_error()


def user_profile(state: StateManager) -> Dict[str, Any] | None:
    """Return the Garmin user profile if available."""
    client = get_client(state)
    return client.get_user_profile()


def user_profile_with_error(state: StateManager) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    """Return the Garmin user profile plus any retrieval error."""
    client = get_client(state)
    profile = client.get_user_profile()
    return profile, client.pop_last_error()


def test_garth_connection(state: StateManager) -> Dict[str, Any]:
    """Run garth diagnostic checks through the client."""
    return get_client(state).test_garth_connection()


__all__ = [
    "auth_error",
    "authenticate",
    "connection_info",
    "disconnect",
    "get_activities_with_error",
    "get_client",
    "is_authenticated",
    "pop_last_error",
    "test_garth_connection",
    "user_profile",
    "user_profile_with_error",
]
