from __future__ import annotations

from datetime import datetime

import pytest

import data.garmin_client as garmin_client_module


pytestmark = pytest.mark.smoke


class _FailingActivitiesClient:
    def get_activities_by_date(self, *_args, **_kwargs):
        raise RuntimeError("activities boom")


class _FailingProfileClient:
    def get_user_profile(self):
        raise RuntimeError("profile boom")


def test_garmin_client_records_activity_errors_without_streamlit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(garmin_client_module, "GARTH_AVAILABLE", False)
    client = garmin_client_module.GarminClient()
    client.is_authenticated = True
    client.client = _FailingActivitiesClient()

    activities = client.get_activities(datetime(2026, 1, 1), datetime(2026, 1, 2))

    assert activities == []
    assert client.pop_last_error() == {
        "context": "activities",
        "message": "Ошибка получения активностей: activities boom",
    }
    assert client.pop_last_error() is None


def test_garmin_client_records_profile_errors_without_streamlit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(garmin_client_module, "GARTH_AVAILABLE", False)
    client = garmin_client_module.GarminClient()
    client.is_authenticated = True
    client.client = _FailingProfileClient()

    profile = client.get_user_profile()

    assert profile is None
    assert client.pop_last_error() == {
        "context": "user_profile",
        "message": "Ошибка получения профиля: profile boom",
    }
