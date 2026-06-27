from __future__ import annotations

from datetime import datetime, timedelta

from data.garmin_client import GARTH_AVAILABLE, GarminClient
from data.garth_client import GarthClient


def test_garmin_client_exposes_current_garth_runtime_contract():
    """GarminClient exposes garth as legacy diagnostics, not fresh auth."""
    client = GarminClient()

    connection_info = client.get_connection_info()

    assert connection_info["authenticated"] is False
    assert connection_info["using_garth"] is False
    assert connection_info["garth_mode"] == "legacy_diagnostic"
    assert connection_info["auth_error"] is None
    assert connection_info["auth_error_raw"] is None
    assert connection_info["auth_error_kind"] is None

    if GARTH_AVAILABLE:
        assert client.garth_client is not None

        runtime = connection_info["garth_runtime"]
        assert runtime is not None
        assert connection_info["garth_available"] == bool(runtime["available"])
        assert runtime["authenticated"] is False
        assert runtime["mode"] == "legacy_diagnostic"
        assert runtime["fresh_login_supported"] is False
        assert "fresh_login_reason" in runtime
    else:
        assert client.garth_client is None
        assert connection_info["garth_available"] is False
        assert connection_info["garth_runtime"] is None


def test_garth_health_methods_return_none_without_authentication():
    """Legacy garth data methods must stay inert without an authenticated session."""
    garth_client = GarthClient()
    test_date = datetime.now() - timedelta(days=1)

    assert garth_client.is_authenticated is False
    assert garth_client.get_sleep_data_garth(test_date) is None
    assert garth_client.get_hrv_data_garth(test_date) is None
    assert garth_client.get_wellness_comprehensive(test_date) is None


def test_garmin_client_does_not_use_garth_without_authentication():
    client = GarminClient()
    test_date = datetime.now() - timedelta(days=1)

    assert client.get_sleep_data(test_date) is None
    assert client.use_garth is False

    connection_info = client.get_connection_info()
    assert connection_info["authenticated"] is False
    assert connection_info["using_garth"] is False


def test_garth_diagnostic_surface_is_available_without_live_login():
    garmin_client = GarminClient()
    garth_client = GarthClient()

    assert hasattr(garmin_client, "get_sleep_data")
    assert hasattr(garmin_client, "test_garth_connection")
    assert hasattr(garmin_client, "get_connection_info")
    assert hasattr(garth_client, "get_runtime_info")
    assert hasattr(garth_client, "test_connection")

    connection_info = garmin_client.get_connection_info()
    required_keys = {
        "authenticated",
        "using_garth",
        "garth_available",
        "garth_mode",
        "garth_runtime",
        "auth_error",
        "auth_error_raw",
        "auth_error_kind",
        "last_error",
    }
    assert required_keys <= connection_info.keys()

    diagnostic_info = garmin_client.test_garth_connection()
    assert diagnostic_info["mode"] == "legacy_diagnostic"
    assert diagnostic_info["authenticated"] is False
    assert diagnostic_info["fresh_login_supported"] is False
