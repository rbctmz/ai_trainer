from __future__ import annotations

import pytest

from data import garth_client as garth_client_module


pytestmark = pytest.mark.smoke


class _BrokenGarthModule:
    def connectapi(self, *_args, **_kwargs):
        return {}


def test_probe_garth_support_detects_missing_login_api():
    supported, reason = garth_client_module._probe_garth_support(_BrokenGarthModule())

    assert supported is False
    assert reason is not None
    assert "login" in reason


def test_garth_client_skips_broken_runtime_without_throwing(monkeypatch):
    monkeypatch.setattr(garth_client_module, "GARTH_SUPPORTED", False)
    monkeypatch.setattr(
        garth_client_module,
        "GARTH_UNAVAILABLE_REASON",
        "garth package is missing required API: login",
    )
    monkeypatch.setattr(garth_client_module, "_GARTH_IMPORT_ERROR", None)

    client = garth_client_module.GarthClient()

    assert client.authenticate("athlete@example.com", "secret") is False
    assert client.is_authenticated is False
    assert client.auth_error == "garth package is missing required API: login"


class _LegacyCapableGarthModule:
    def login(self, *_args, **_kwargs):
        raise AssertionError("fresh garth login should not be attempted")

    def connectapi(self, *_args, **_kwargs):
        return {}


def test_garth_client_disables_fresh_login_even_when_api_exists(monkeypatch):
    monkeypatch.setattr(garth_client_module, "GARTH_SUPPORTED", True)
    monkeypatch.setattr(garth_client_module, "GARTH_UNAVAILABLE_REASON", None)
    monkeypatch.setattr(garth_client_module, "_GARTH_IMPORT_ERROR", None)
    monkeypatch.setattr(garth_client_module, "garth", _LegacyCapableGarthModule())

    client = garth_client_module.GarthClient()

    assert client.authenticate("athlete@example.com", "secret") is False
    assert client.is_authenticated is False
    assert "deprecated upstream" in client.auth_error
