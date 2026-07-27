"""M5 contract: Intervals-first UI, Garmin optional, provenance source-aware."""
from __future__ import annotations

from pathlib import Path

import pytest

from services import sync_providers


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
SYNC_CONTROL = ROOT / "web" / "components" / "sync" / "SyncControl.tsx"
SOURCE_LABELS = ROOT / "web" / "lib" / "sourceLabels.ts"
SOURCE_CONSUMERS = (
    ROOT / "web" / "app" / "hrv" / "page.tsx",
    ROOT / "web" / "app" / "sleep" / "page.tsx",
    ROOT / "web" / "components" / "dashboard" / "SleepWidget.tsx",
    ROOT / "web" / "components" / "dashboard" / "AthleteProfileCard.tsx",
)


def test_m5_provider_discovery_presents_intervals_before_optional_garmin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_providers.Settings, "GARMIN_EMAIL", "owner@example.com")
    monkeypatch.setattr(sync_providers.Settings, "GARMIN_PASSWORD", "secret")
    monkeypatch.setattr(sync_providers.Settings, "INTERVALS_ICU_API_KEY", "api-key")
    monkeypatch.setattr(sync_providers.Settings, "PRIMARY_ACTIVITY_SOURCE", "garmin")
    monkeypatch.setattr(
        sync_providers.intervals_icu,
        "connection_info",
        lambda: {"configured": True, "athlete_id": "0"},
    )

    payload = sync_providers.connection_overview()

    assert payload["recommended_source"] == "garmin"
    assert [item["source"] for item in payload["providers"]] == [
        "intervals",
        "garmin",
    ]
    assert payload["providers"][0]["description"] == "Активности и восстановление"
    assert (
        payload["providers"][1]["description"]
        == "Дополнительный источник · необязательно"
    )


def test_m5_onboarding_copy_is_provider_neutral() -> None:
    source = SYNC_CONTROL.read_text(encoding="utf-8")

    assert "Для старта без Garmin" not in source
    assert "Настройте источник данных" in source
    assert "provider.description" in source


def test_m5_recovery_and_profile_surfaces_share_one_source_formatter() -> None:
    assert SOURCE_LABELS.exists()
    labels = SOURCE_LABELS.read_text(encoding="utf-8")

    assert 'garmin: "Garmin Connect"' in labels
    assert 'intervals: "Intervals.icu"' in labels
    assert 'intervals_icu: "Intervals.icu"' in labels
    assert "export function dataSourceLabel" in labels

    for path in SOURCE_CONSUMERS:
        source = path.read_text(encoding="utf-8")
        assert 'from "@/lib/sourceLabels"' in source, path
        assert "function sourceLabel(" not in source, path
        assert "function scoreSourceLabel(" not in source, path


def test_m5_scope_has_no_data_migration_module() -> None:
    """M5 is a UI demotion; M0 already owns history backfill."""

    spec = (
        ROOT / "docs" / "intervals_primary_m5_garmin_demotion_spec.md"
    ).read_text(encoding="utf-8")

    assert "M5 не требует миграции данных" in spec
    assert "M5 не касается `services/activity_ingest.py`" in spec
