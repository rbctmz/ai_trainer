"""Static product-surface gates for the source-aware M3 sync control."""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "web" / "app" / "dashboard" / "page.tsx"
SYNC_CONTROL = ROOT / "web" / "components" / "sync" / "SyncControl.tsx"
TYPES = ROOT / "web" / "lib" / "types.ts"
ACTIVITIES = ROOT / "web" / "app" / "activities" / "page.tsx"


def test_m3_dashboard_uses_source_aware_sync_control() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    control = SYNC_CONTROL.read_text(encoding="utf-8")

    assert 'from "@/components/sync/SyncControl"' in dashboard
    assert 'useSWR<SyncProvidersResponse>("/api/sync/providers"' in control
    assert 'postJSON<SyncJobResponse>("/api/sync", { source: selectedSource })' in control
    assert "job.source" in control
    assert 'postJSON<SyncProviderTestResponse>("/api/sync/providers/intervals/test"' in control


def test_m3_first_run_copy_does_not_require_garmin() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    activities = ACTIVITIES.read_text(encoding="utf-8")

    assert "Синхронизируйтесь с Garmin" not in dashboard
    assert 'title="Синхронизировать с Garmin Connect"' not in dashboard
    assert "Синхронизируйте Garmin, чтобы увидеть тренировки." not in activities
    assert "INTERVALS_ICU_API_KEY" in dashboard


def test_m3_sync_types_carry_provider_discovery_and_job_source() -> None:
    source = TYPES.read_text(encoding="utf-8")

    assert "export interface SyncProviderStatus" in source
    assert "export interface SyncProvidersResponse" in source
    assert 'source: "garmin" | "intervals" | null;' in source

