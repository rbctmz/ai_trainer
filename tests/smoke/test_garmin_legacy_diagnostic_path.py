from __future__ import annotations

import pytest

from data import garmin_client as garmin_client_module


pytestmark = pytest.mark.smoke


class _StubGarthClient:
    authenticate_called = False

    def __init__(self):
        self.available = True
        self.unavailable_reason = None

    def authenticate(self, *_args, **_kwargs):
        type(self).authenticate_called = True
        return True

    def disconnect(self):
        return None

    def get_runtime_info(self):
        return {
            "available": True,
            "authenticated": False,
            "username": None,
            "mode": "legacy_diagnostic",
            "fresh_login_supported": False,
            "fresh_login_reason": "deprecated upstream",
            "unavailable_reason": None,
        }

    def test_connection(self):
        return self.get_runtime_info() | {"error": "Не авторизован"}


class _StubGarmin:
    login_called = False

    def __init__(self, email, password):
        self.email = email
        self.password = password

    def login(self):
        type(self).login_called = True


def test_garmin_client_uses_garminconnect_for_fresh_auth(monkeypatch):
    monkeypatch.setattr(garmin_client_module, "GARTH_AVAILABLE", True)
    monkeypatch.setattr(garmin_client_module, "GarthClient", _StubGarthClient)
    monkeypatch.setattr(garmin_client_module, "Garmin", _StubGarmin)
    _StubGarthClient.authenticate_called = False
    _StubGarmin.login_called = False

    client = garmin_client_module.GarminClient()

    assert client.authenticate("athlete@example.com", "secret") is True
    assert client.use_garth is False
    assert client.is_authenticated is True
    assert _StubGarthClient.authenticate_called is False
    assert _StubGarmin.login_called is True


def test_connection_info_exposes_legacy_garth_runtime(monkeypatch):
    monkeypatch.setattr(garmin_client_module, "GARTH_AVAILABLE", True)
    monkeypatch.setattr(garmin_client_module, "GarthClient", _StubGarthClient)

    client = garmin_client_module.GarminClient()
    info = client.get_connection_info()

    assert info["garth_mode"] == "legacy_diagnostic"
    assert info["garth_available"] is True
    assert info["garth_runtime"]["fresh_login_supported"] is False
