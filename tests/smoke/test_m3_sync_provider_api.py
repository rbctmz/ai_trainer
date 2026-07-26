"""M3 provider discovery and explicit Intervals connection-test contract."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from api.routers import system as system_mod
from services.intervals_icu import IntervalsICUError


pytestmark = pytest.mark.smoke


def _providers_by_source(payload: dict) -> dict[str, dict]:
    return {item["source"]: item for item in payload["providers"]}


def test_m3_provider_discovery_prefers_only_configured_intervals_and_hides_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "m3-super-secret-api-key"
    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", None, raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", None, raising=False)
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_API_KEY", secret, raising=False)
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_ATHLETE_ID", "i123", raising=False)
    monkeypatch.setattr(system_mod.Settings, "PRIMARY_ACTIVITY_SOURCE", "garmin", raising=False)

    payload = system_mod.sync_providers()
    providers = _providers_by_source(payload)

    assert payload["recommended_source"] == "intervals"
    assert providers["garmin"]["configured"] is False
    assert providers["intervals"]["configured"] is True
    assert providers["intervals"]["connection"] == {
        "configured": True,
        "athlete_id": "i123",
        "base_url": "https://intervals.icu",
    }
    assert secret not in json.dumps(payload)


@pytest.mark.parametrize(
    ("primary", "garmin_configured", "intervals_configured", "expected"),
    [
        ("garmin", True, True, "garmin"),
        ("intervals", True, True, "intervals"),
        ("garmin", False, False, "garmin"),
        ("intervals", False, False, "intervals"),
    ],
)
def test_m3_provider_recommendation_respects_primary_and_configuration(
    monkeypatch: pytest.MonkeyPatch,
    primary: str,
    garmin_configured: bool,
    intervals_configured: bool,
    expected: str,
) -> None:
    monkeypatch.setattr(system_mod.Settings, "PRIMARY_ACTIVITY_SOURCE", primary, raising=False)
    monkeypatch.setattr(
        system_mod.Settings,
        "GARMIN_EMAIL",
        "user@example.com" if garmin_configured else None,
        raising=False,
    )
    monkeypatch.setattr(
        system_mod.Settings,
        "GARMIN_PASSWORD",
        "password" if garmin_configured else None,
        raising=False,
    )
    monkeypatch.setattr(
        system_mod.Settings,
        "INTERVALS_ICU_API_KEY",
        "secret" if intervals_configured else None,
        raising=False,
    )

    assert system_mod.sync_providers()["recommended_source"] == expected


def test_m3_intervals_connection_test_returns_only_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_API_KEY", "secret", raising=False)
    monkeypatch.setattr(
        system_mod.intervals_icu_service,
        "test_connection",
        lambda: {
            "ok": True,
            "calendar_count": 2,
            "calendars": [{"id": 1, "name": "Private calendar"}],
        },
    )

    payload = system_mod.test_sync_provider_connection("intervals")

    assert payload == {"ok": True, "source": "intervals", "calendar_count": 2}


def test_m3_intervals_connection_test_fails_explicitly_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_API_KEY", None, raising=False)

    with pytest.raises(HTTPException) as caught:
        system_mod.test_sync_provider_connection("intervals")

    assert caught.value.status_code == 409
    assert "INTERVALS_ICU_API_KEY" in str(caught.value.detail)


def test_m3_intervals_connection_test_maps_provider_error_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(system_mod.Settings, "INTERVALS_ICU_API_KEY", "secret", raising=False)
    monkeypatch.setattr(
        system_mod.intervals_icu_service,
        "test_connection",
        lambda: (_ for _ in ()).throw(IntervalsICUError("provider unavailable")),
    )

    with pytest.raises(HTTPException) as caught:
        system_mod.test_sync_provider_connection("intervals")

    assert caught.value.status_code == 503
    assert caught.value.detail == "provider unavailable"

