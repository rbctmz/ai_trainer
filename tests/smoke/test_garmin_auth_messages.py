from __future__ import annotations

import pytest

from data import garmin_client as garmin_client_module


pytestmark = pytest.mark.smoke


def test_summarize_auth_error_prioritizes_rate_limit_over_widget_noise():
    info = garmin_client_module._summarize_auth_error(
        "mobile+cffi returned 429: Mobile login returned 429 — IP rate limited by Garmin; "
        "widget+cffi failed: Widget login: unexpected title 'GARMIN Authentication Application'; "
        "401 Unauthorized (Invalid Username or Password)"
    )

    assert info["kind"] == "rate_limited_with_401"
    assert "429" in info["summary"]
    assert "401 Unauthorized" in info["summary"]
    assert "GARMIN Authentication Application" in info["raw"]


def test_summarize_auth_error_handles_invalid_credentials_only():
    info = garmin_client_module._summarize_auth_error(
        "401 Unauthorized (Invalid Username or Password)"
    )

    assert info["kind"] == "invalid_credentials"
    assert info["summary"] == (
        "Garmin отклонил логин или пароль (401 Unauthorized). "
        "Проверьте введенные учетные данные."
    )


class _FailingGarmin:
    def __init__(self, *_args, **_kwargs):
        pass

    def login(self):
        raise Exception(
            "mobile+cffi returned 429: Mobile login returned 429 — IP rate limited by Garmin; "
            "widget+cffi failed: Widget login: unexpected title 'GARMIN Authentication Application'; "
            "401 Unauthorized (Invalid Username or Password)"
        )


def test_garmin_client_stores_normalized_and_raw_auth_errors(monkeypatch):
    monkeypatch.setattr(garmin_client_module, "Garmin", _FailingGarmin)

    client = garmin_client_module.GarminClient()

    assert client.authenticate("athlete@example.com", "secret") is False
    assert client.is_authenticated is False
    assert client.auth_error_kind == "rate_limited_with_401"
    assert client.auth_error.startswith("Garmin временно ограничил вход с этого IP (429)")
    assert "Invalid Username or Password" in str(client.auth_error_raw)

    connection_info = client.get_connection_info()
    assert connection_info["auth_error"] == client.auth_error
    assert connection_info["auth_error_kind"] == "rate_limited_with_401"
    assert "GARMIN Authentication Application" in str(connection_info["auth_error_raw"])
