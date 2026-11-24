"""The activity card renders three paired synthetic trainer workouts."""

from datetime import timedelta
import os
from uuid import UUID, uuid4

from playwright.sync_api import expect
import pytest

from data.database import Database
from data.swim_program_store import confirm_preview, create_preview
from models.activity_intervals import normalize_intervals_payload
from models.planning_checkpoints import build_planning_checkpoint
from models.swim_calendar import SwimCalendarRequest
from services.swim_calendar import confirm_calendar, preview_calendar
from services.swim_delivery import confirm_swim_delivery, preview_swim_delivery
from tests.athlete_clock import athlete_today
from tests.planning_fixtures import seed_checkpoint
from tests.smoke._planning_cycle_regressions import plan
from tests.smoke._swim_program_fixtures import example_program
from tests.smoke.test_swim_series_fact import _observations, _plan
from tests.swim_delivery_fixtures import IntervalsSandbox

pytestmark = pytest.mark.e2e


def test_card_compares_three_paired_swim_programs(web_stack):
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.clear_all_data()
    today = athlete_today()
    seed_checkpoint(db, build_planning_checkpoint(plan(today, days=7)))
    saved = confirm_preview(db, create_preview(db, example_program(), base_revision=0)["preview_id"])
    reviewed = preview_calendar(db, SwimCalendarRequest.model_validate({
        "request_id": str(uuid4()),
        "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
        "operation": {
            "kind": "place",
            "program_id": saved["program_id"],
            "program_revision": saved["revision"],
            "dates": {
                name: (today + timedelta(days=index)).isoformat()
                for index, name in enumerate(("one", "two", "three"))
            },
        },
    }))
    checkpoint = confirm_calendar(db, reviewed["preview_id"])["checkpoint_id"]
    sandbox = IntervalsSandbox()
    page = web_stack.page
    page.set_viewport_size({"width": 390, "height": 900})
    for index, change in enumerate(reviewed["changes"], start=1):
        assignment = change["after"]
        workout_id = assignment["workout_id"]
        preview = preview_swim_delivery(db, uuid4(), UUID(assignment["assignment_id"]), checkpoint)
        delivered = confirm_swim_delivery(db, UUID(preview["preview_id"]), client=sandbox)
        assert delivered["status"] == "provider_verified"
        workout = _plan(workout_id)
        observations = _observations(workout)
        if workout_id == "three":
            observations = observations[:-1]
        activity_id = f"comparison-{workout_id}"
        tss = 100 + index
        db.save_activities([{
            "activity_id": activity_id,
            "date": today.isoformat(),
            "sport": "lap_swimming",
            "duration_minutes": 50,
            "distance_km": workout.distance_meters / 1000,
            "tss": tss,
        }])
        db.save_activity_intervals(activity_id, normalize_intervals_payload({
            "paired_event_id": delivered["provider_event_id"],
            "icu_intervals": [
                {"distance": row.distance_meters, "moving_time": row.active_seconds,
                 "elapsed_time": row.elapsed_seconds}
                for row in observations
            ],
        }))
        page.goto(f"{web_stack.web_base}/activities?demo=1")
        page.get_by_role("row").filter(has=page.get_by_text(str(tss), exact=True)).click()
        section = page.get_by_role("region", name="Серии по заданию тренера")
        expect(section.get_by_text("Интервалы Intervals.icu", exact=False)).to_be_visible()
        expect(section.get_by_text("бассейн по плану 25 м", exact=False)).to_be_visible()
        section.get_by_text("Темп, отрезки и отдых", exact=True).click()
        if workout_id == "one":
            expect(section.get_by_text("разброс 0 с/100 м", exact=False)).to_have_count(4)
            expect(section.get_by_text("0:50", exact=True).first).to_be_visible()
            if screenshot := os.environ.get("AI_TRAINER_SERIES_SCREENSHOT"):
                section.get_by_role("list", name="Темп по кругам").scroll_into_view_if_needed()
                page.screenshot(path=screenshot)
        elif workout_id == "two":
            for pace in ("2:08 /100 м", "2:04 /100 м", "2:00 /100 м"):
                expect(section.get_by_text(pace, exact=True).first).to_be_visible()
        else:
            expect(section.get_by_text("Задание по усилию 50–90%", exact=True).first).to_be_visible()
            expect(section.get_by_text("Открытый отдых · 3 выдоха", exact=True).first).to_be_visible()
            expect(section.get_by_text("Для части тренировки данных не хватило.", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not web_stack.js_errors
