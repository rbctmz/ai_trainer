"""Static web contract for the source coverage dashboard card (#427)."""
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "web" / "app" / "dashboard" / "page.tsx"
CARD = ROOT / "web" / "components" / "sync" / "DataCoverageCard.tsx"
TYPES = ROOT / "web" / "lib" / "types.ts"


def test_dashboard_renders_permanent_data_coverage_card() -> None:
    dashboard = DASHBOARD.read_text(encoding="utf-8")

    assert 'from "@/components/sync/DataCoverageCard"' in dashboard
    assert "<DataCoverageCard />" in dashboard


def test_coverage_card_supports_30_and_90_days_and_explains_activity_overlap() -> None:
    source = CARD.read_text(encoding="utf-8")

    assert 'useSWR<DataCoverageResponse>(`/api/sync/coverage?days=${days}`' in source
    assert "([30, 90] as const)" in source
    assert "Источники могут пересекаться" in source
    assert "Покрытие ежедневных сигналов" in source


def test_coverage_types_separate_activity_events_from_daily_signal_days() -> None:
    source = TYPES.read_text(encoding="utf-8")

    assert "export interface ActivityCoverage" in source
    assert "canonical_count: number;" in source
    assert "provider_link_counts: Record<SyncSource, number>;" in source
    assert "export interface DailyMetricCoverage" in source
    assert "coverage_pct: number;" in source
    assert "source_days: Record<string, number>;" in source
