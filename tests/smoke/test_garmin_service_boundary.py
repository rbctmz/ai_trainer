from __future__ import annotations

from datetime import datetime

import pytest

from services import garmin as garmin_service


pytestmark = pytest.mark.smoke


class _StubClient:
    def __init__(self, last_error=None):
        self.is_authenticated = True
        self.auth_error = "bad auth"
        self._last_error = last_error

    def get_activities(self, *_args, **_kwargs):
        return [{"id": 1}]

    def pop_last_error(self):
        error = self._last_error
        self._last_error = None
        return error

    def get_user_profile(self):
        return {"displayName": "Greg"}

    def test_garth_connection(self):
        return {"authenticated": True, "test_results": {"profile": "ok"}}

    def get_connection_info(self):
        return {
            "authenticated": self.is_authenticated,
            "using_garth": True,
            "garth_available": True,
            "auth_error": self.auth_error,
            "last_error": self._last_error,
        }


class _StubState:
    def __init__(self, last_error=None):
        self.garmin_client = _StubClient(last_error=last_error)


def test_garmin_service_returns_activities_and_error():
    state = _StubState(last_error={"context": "activities", "message": "boom"})

    activities, error = garmin_service.get_activities_with_error(
        state,
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
    )

    assert activities == [{"id": 1}]
    assert error == {"context": "activities", "message": "boom"}


def test_garmin_service_wraps_profile_and_garth_helpers():
    state = _StubState()

    profile, error = garmin_service.user_profile_with_error(state)

    assert garmin_service.is_authenticated(state) is True
    assert garmin_service.auth_error(state) == "bad auth"
    assert profile == {"displayName": "Greg"}
    assert error is None
    assert garmin_service.test_garth_connection(state)["authenticated"] is True
