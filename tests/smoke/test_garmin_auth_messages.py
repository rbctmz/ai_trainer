from __future__ import annotations

import logging

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


def test_summarize_auth_error_handles_portal_403_block():
    info = garmin_client_module._summarize_auth_error(
        "Login failed: All login strategies exhausted: Portal login failed (non-JSON): HTTP 403"
    )

    assert info["kind"] == "portal_forbidden"
    assert "HTTP 403" in info["summary"]
    assert "не на ошибку Planning" in info["summary"]


def test_summarize_auth_error_handles_rate_limit_plus_portal_403():
    info = garmin_client_module._summarize_auth_error(
        "mobile+cffi returned 429: Mobile login returned 429 — IP rate limited by Garmin; "
        "portal+cffi failed: Portal login failed (non-JSON): HTTP 403; "
        "Login failed: All login strategies exhausted: Portal login failed (non-JSON): HTTP 403"
    )

    assert info["kind"] == "rate_limited_with_portal_403"
    assert "429" in info["summary"]
    assert "HTTP 403" in info["summary"]


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


class _PortalForbiddenGarmin:
    def __init__(self, *_args, **_kwargs):
        pass

    def login(self):
        raise Exception(
            "Login failed: All login strategies exhausted: Portal login failed (non-JSON): HTTP 403"
        )


def test_garmin_client_stores_portal_403_auth_error(monkeypatch):
    monkeypatch.setattr(garmin_client_module, "Garmin", _PortalForbiddenGarmin)

    client = garmin_client_module.GarminClient()

    assert client.authenticate("athlete@example.com", "secret") is False
    assert client.auth_error_kind == "portal_forbidden"
    assert "HTTP 403" in str(client.auth_error)
    assert "Portal login failed" in str(client.auth_error_raw)


def test_failed_authentication_emits_structured_log_record(monkeypatch, caplog):
    """A failed Garmin login must be observable through the `garmin_sync`
    logger, not only through a stdout `print`. This is what lets acceptance/E2E
    runs surface a real 429/rate-limit instead of failing silently in logs."""
    monkeypatch.setattr(garmin_client_module, "Garmin", _FailingGarmin)
    caplog.set_level(logging.ERROR, logger="garmin_sync")

    client = garmin_client_module.GarminClient()
    client.authenticate("athlete@example.com", "secret")

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected at least one ERROR record from garmin_sync logger"
    combined = " ".join(r.getMessage() for r in error_records)
    assert "429" in combined
    assert "rate_limited" in combined


def test_successful_authentication_emits_info_log_record(monkeypatch, caplog):
    """A successful login should be observable too, for parity and auditability."""
    class _OkGarmin:
        def __init__(self, *_args, **_kwargs):
            pass

        def login(self):
            return True

    monkeypatch.setattr(garmin_client_module, "Garmin", _OkGarmin)
    caplog.set_level(logging.INFO, logger="garmin_sync")

    client = garmin_client_module.GarminClient()
    assert client.authenticate("athlete@example.com", "secret") is True

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert info_records
