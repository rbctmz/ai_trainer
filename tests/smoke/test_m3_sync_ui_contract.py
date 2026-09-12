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


def test_m3_partial_sync_surfaces_actionable_notices() -> None:
    control = SYNC_CONTROL.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")

    assert "notices?: string[];" in types
    assert "result.notices" in control
    assert "formatSyncNotices" in control

# --- Issue #562 M5: recovery-capture readback in the sync line -----------------


def test_m5_terminal_sync_surfaces_the_recovery_capture_readback() -> None:
    """Один и тот же readback для обоих провайдеров: источник — result.recovery_capture."""
    control = SYNC_CONTROL.read_text(encoding="utf-8")

    assert "result.recovery_capture" in control
    assert "formatRecoveryCapture" in control
    assert "RECOVERY_CAPTURE_STATUS_LABELS" in control
    # Все пять состояний контракта отображаются понятным текстом.
    for status in (
        "saved_before_load",
        "saved_too_late",
        "activity_start_missing",
        "ineligible",
        "capture_failed",
    ):
        assert status in control


def test_m5_capture_readback_handles_missing_time_honestly() -> None:
    """null-время не выдумывается: честная формулировка вместо подстановки."""
    control = SYNC_CONTROL.read_text(encoding="utf-8")

    assert "время не определено" in control
    assert "RECOVERY_CAPTURE_UNKNOWN_REASON" in control
    # Локальное время атлета приходит с сервера как ISO со смещением и
    # разбирается как текст: зона браузера в показ не вмешивается.
    assert "observed_at_local" in control
    assert "toLocaleString" not in control
    assert "new Date(" not in control


def test_m5_capture_readback_hides_internal_identifiers() -> None:
    """Идентификаторы, внутренние поля и сырой error в UI не попадают."""
    control = SYNC_CONTROL.read_text(encoding="utf-8")

    for forbidden in (
        "capture_run_id",
        "job_id",
        "episode_refresh",
        "capture.error",
        "capture.snapshot_id",
        "capture.reason ??",
    ):
        assert forbidden not in control


def test_m5_existing_sync_states_survive_the_readback() -> None:
    """running/failed/partial, счётчики, notices и responsive-контур не ломаются."""
    control = SYNC_CONTROL.read_text(encoding="utf-8")

    assert "isTerminalSyncState" in control
    assert 'job.sync_state === "running"' in control
    assert 'job.sync_state === "failed"' in control
    assert 'job.sync_state === "partial"' in control
    assert "result.counts" in control
    assert "formatSyncNotices" in control
    # Подробный вариант — видимый абзац, компактный — прежний responsive-контур.
    assert '<p className="text-xs text-ink-faint">{message}</p>' in control
    assert 'className="hidden text-xs text-ink-faint sm:inline"' in control
