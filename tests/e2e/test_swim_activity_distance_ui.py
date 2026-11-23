"""The activity card displays source metres from both swim interval lists."""

import os

import pytest
from playwright.sync_api import expect

from data.database import Database
from models.activity_intervals import (
    normalize_garmin_splits_payload,
    normalize_intervals_payload,
)
from tests.athlete_clock import athlete_today

pytestmark = pytest.mark.e2e


def test_swim_activity_card_displays_source_metres(web_stack):
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.clear_all_data()
    db.save_activities(
        [
            {
                "activity_id": "synthetic-swim-card",
                "date": athlete_today().isoformat(),
                "sport": "lap_swimming",
                "duration_minutes": 4,
                "distance_km": 0.25,
                "tss": 8,
            }
        ]
    )
    compact = normalize_intervals_payload(
        {"icu_intervals": [{"distance": 75}, {"distance": 25}]}
    )
    compact["garmin_laps"] = normalize_garmin_splits_payload(
        {"lapDTOs": [{"distance": 75}, {"distance": 25}, {"distance": 0}]}
    )["intervals"]
    compact["garmin_laps"].append({"distance_km": 0.17, "moving_time": 160})
    db.save_activity_intervals("synthetic-swim-card", compact)

    page = web_stack.page
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    page.goto(f"{web_stack.web_base}/activities?demo=1")
    page.get_by_role("row").filter(has_text="плавание").click()
    expect(page.get_by_text("Круги Garmin", exact=True)).to_be_visible()
    expect(page.get_by_text("Интервалы Intervals.icu", exact=True)).to_be_visible()
    for distance in ("75 м", "25 м"):
        expect(page.get_by_text(distance, exact=True)).to_have_count(2)
    expect(page.get_by_text("0 м", exact=True)).to_be_visible()
    expect(page.get_by_text("≈170 м", exact=True)).to_be_visible()
    expect(page.get_by_text("70 м", exact=True)).to_have_count(0)
    expect(page.get_by_text("30 м", exact=True)).to_have_count(0)
    assert not web_stack.js_errors

    if screenshot := os.environ.get("AI_TRAINER_ACTIVITY_SCREENSHOT"):
        page.get_by_text("Структура тренировки", exact=True).locator("..").screenshot(path=screenshot)
