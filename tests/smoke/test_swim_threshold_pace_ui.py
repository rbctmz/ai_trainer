"""Static web-contract gates for issue #362 (swim threshold pace / CSS).

The Python suites exercise the profile-to-TSS data path. These assertions keep
the web surface honest (profile card and types) without requiring a browser or
Node test runner in the contributor-safe contour, mirroring
``test_running_threshold_pace_ui.py`` for issue #308.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "web" / "lib" / "types.ts"
PROFILE_CARD = ROOT / "web" / "components" / "dashboard" / "AthleteProfileCard.tsx"


def test_athlete_profile_web_contract_exposes_swim_pace_units_and_provenance():
    types = TYPES.read_text(encoding="utf-8")
    card = PROFILE_CARD.read_text(encoding="utf-8")

    assert "swim_threshold_pace_seconds_per_100m: number | null" in types
    assert "swim_threshold_pace_source: string | null" in types
    assert "swim_threshold_pace_synced_at: string | null" in types
    assert "Пороговый темп плавания" in card
    assert "formatSwimPace" in card
    assert "swim_threshold_pace_source" in card
