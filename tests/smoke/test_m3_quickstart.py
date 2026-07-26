"""Executable documentation gates for the Intervals-only Docker handoff."""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
QUICKSTART = ROOT / "docs" / "intervals_primary_quickstart.md"
ENV_EXAMPLE = ROOT / ".env.example"


def test_m3_quickstart_covers_the_complete_first_plan_path() -> None:
    source = QUICKSTART.read_text(encoding="utf-8")

    required = [
        "cp .env.example .env",
        "INTERVALS_ICU_API_KEY",
        "PRIMARY_ACTIVITY_SOURCE=intervals",
        "docker compose up -d --build",
        "http://localhost:8080",
        "Intervals.icu",
        "/planning",
        "/today",
        "docker compose down",
        "docker compose down -v",
    ]
    for item in required:
        assert item in source

    assert "GARMIN_EMAIL" in source
    assert "GARMIN_PASSWORD" in source
    assert "оставьте пустыми" in source


def test_m3_env_example_is_safe_to_copy_for_intervals_only_start() -> None:
    source = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "GARMIN_EMAIL=\n" in source
    assert "GARMIN_PASSWORD=\n" in source
    assert "INTERVALS_ICU_API_KEY=\n" in source
    assert "PRIMARY_ACTIVITY_SOURCE=garmin" in source
    assert "your_intervals_icu_api_key_here" not in source
    assert "your_garmin_password" not in source

