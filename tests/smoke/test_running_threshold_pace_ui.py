"""Static web-contract gates for issue #308.

The Python suites exercise the source-to-plan data path. These assertions keep
the pre-delivery web surface honest without requiring a browser or Node test
runner in the contributor-safe contour.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "web" / "lib" / "types.ts"
PROFILE_CARD = ROOT / "web" / "components" / "dashboard" / "AthleteProfileCard.tsx"
PLANNING_PAGE = ROOT / "web" / "app" / "planning" / "page.tsx"


def test_athlete_profile_web_contract_exposes_explicit_pace_units_and_provenance():
    types = TYPES.read_text(encoding="utf-8")
    card = PROFILE_CARD.read_text(encoding="utf-8")

    assert "threshold_pace_seconds_per_km: number | null" in types
    assert "threshold_pace_source: string | null" in types
    assert "threshold_pace_synced_at: string | null" in types
    assert "Пороговый темп" in card
    assert "formatPace" in card
    assert "threshold_pace_source" in card


def test_planning_export_explains_target_basis_and_formats_pace_ranges():
    source = PLANNING_PAGE.read_text(encoding="utf-8")

    assert "targetBasisLabel" in source
    assert "по пороговому темпу" in source
    assert "по LTHR" in source
    assert "по RPE" in source
    assert 'type === "pace"' in source
    assert "target_provenance" in source
