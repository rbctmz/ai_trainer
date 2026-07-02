from __future__ import annotations

from datetime import datetime

import pytest

import data.garmin_client as garmin_client_module


pytestmark = pytest.mark.smoke

_DATE = datetime(2026, 7, 1)


def _make_client(monkeypatch: pytest.MonkeyPatch, stub) -> garmin_client_module.GarminClient:
    monkeypatch.setattr(garmin_client_module, "GARTH_AVAILABLE", False)
    client = garmin_client_module.GarminClient()
    client.is_authenticated = True
    client.client = stub
    return client


# --- resting heart rate ---


class _ModernRhrStub:
    """garminconnect >= 0.3: get_rhr_day с metricsMap-обёрткой."""

    def get_rhr_day(self, _cdate):
        return {
            "allMetrics": {
                "metricsMap": {
                    "WELLNESS_RESTING_HEART_RATE": [
                        {"value": 48, "calendarDate": "2026-07-01"}
                    ]
                }
            }
        }


class _LegacyRhrStub:
    def get_resting_heart_rate(self, _cdate):
        return {"restingHeartRate": 50}


def test_rhr_modern_client_normalized(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _ModernRhrStub())

    assert client.get_resting_heart_rate(_DATE) == {"restingHeartRate": 48}
    assert client.pop_last_error() is None


def test_rhr_legacy_client_passthrough(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _LegacyRhrStub())

    assert client.get_resting_heart_rate(_DATE) == {"restingHeartRate": 50}


# --- VO2 max ---


class _ModernVo2Stub:
    def get_max_metrics(self, _cdate):
        return [{"generic": {"vo2MaxPreciseValue": 52.3, "fitnessAge": 31}}]


class _LegacyVo2Stub:
    def get_vo2_max(self):
        return {"vo2MaxValue": 51.0, "fitnessAge": 33}


def test_vo2_modern_client_normalized(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _ModernVo2Stub())

    assert client.get_vo2_max() == {"vo2MaxValue": 52.3, "fitnessAge": 31}


def test_vo2_legacy_client_passthrough(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _LegacyVo2Stub())

    assert client.get_vo2_max() == {"vo2MaxValue": 51.0, "fitnessAge": 33}


# --- training readiness ---


class _ModernReadinessStub:
    """garminconnect >= 0.3: обязательный cdate, ответ — список записей."""

    def get_training_readiness(self, cdate):
        assert cdate == datetime.now().strftime("%Y-%m-%d")
        return [{"readinessScore": 78, "calendarDate": cdate}]


class _LegacyReadinessStub:
    def get_training_readiness(self):
        return {"readinessScore": 66}


class _ModernReadinessEmptyStub:
    """garminconnect >= 0.3: cdate обязателен, но readiness за день может отсутствовать."""

    def get_training_readiness(self, _cdate):
        return []


def test_readiness_modern_client_takes_first_entry(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _ModernReadinessStub())

    readiness = client.get_training_readiness()

    assert isinstance(readiness, dict)
    assert readiness["readinessScore"] == 78


def test_readiness_legacy_client_falls_back_to_no_args(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _LegacyReadinessStub())

    assert client.get_training_readiness() == {"readinessScore": 66}


def test_readiness_modern_empty_response_does_not_call_legacy_no_args(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _make_client(monkeypatch, _ModernReadinessEmptyStub())

    assert client.get_training_readiness() is None
    assert client.pop_last_error() is None


# --- error paths ---


class _EmptyStub:
    """Клиент без нужных методов вообще (неожиданная версия библиотеки)."""


def test_rhr_missing_methods_returns_none_without_error(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _EmptyStub())

    assert client.get_resting_heart_rate(_DATE) is None


class _FailingVo2Stub:
    def get_max_metrics(self, _cdate):
        raise RuntimeError("vo2 boom")


def test_vo2_failure_recorded_as_error(monkeypatch: pytest.MonkeyPatch):
    client = _make_client(monkeypatch, _FailingVo2Stub())

    assert client.get_vo2_max() is None
    error = client.pop_last_error()
    assert error is not None
    assert "vo2 boom" in error["message"]
