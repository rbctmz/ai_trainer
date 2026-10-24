"""#677: only a known positive countdown belongs to an actionable event plan."""
from datetime import date, timedelta
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from tests.planning_fixtures import seed_checkpoint
from tests.smoke._planning_cycle_regressions import evidence_bytes, plan

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("case", [
    "ended", "race_day", "future", "past_event_active", "unknown_count", "non_actionable",
])
def test_event_caption_keeps_date_without_misleading_countdown(web_stack, case):
    page = web_stack.page
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.clear_all_data()
    context = page.request.get(f"{web_stack.api_base}/api/planning/cycles/current?demo=1").json()
    today = date.fromisoformat(context["athlete_day"])
    start = today + timedelta(days={"ended": -14, "race_day": -6, "past_event_active": -3}.get(case, 1))
    value = plan(start)
    if case == "past_event_active":
        value["event_date"] = (today - timedelta(days=1)).isoformat()
        value["events"][0]["date"] = value["event_date"]
    seed_checkpoint(db, build_planning_checkpoint(value))
    before = evidence_bytes(db)
    page.unroute_all()
    payloads = []

    def overview(route):
        response = route.fetch()
        assert response.status == 200
        payload = response.json()
        # Legacy/missing or disabled reader display controls only. No modified
        # response is ever confirmed, nor is cycle state recomputed in the UI.
        if case == "unknown_count":
            payload["timeline"]["days_remaining"] = None
        elif case == "non_actionable":
            payload["has_actionable_plan"] = False
        payloads.append(payload)
        route.fulfill(status=200, json=payload)

    page.route("**/api/planning/overview?*", overview)
    page.set_viewport_size({"width": 390 if case == "ended" else 1280, "height": 1100})
    page.goto(f"{web_stack.web_base}/planning?demo=1", wait_until="networkidle")
    page.evaluate("document.documentElement.classList.remove('dark'); document.documentElement.dataset.theme='light'")
    caption = page.get_by_text(re.compile(r"^A-цель: Synthetic Olympic"))
    expect(caption).to_be_visible()
    expect(caption).to_contain_text(value["event_date"])
    assert payloads
    shown = payloads[-1]
    if case == "future":
        days = shown["timeline"]["days_remaining"]
        assert days > 0 and shown["has_actionable_plan"] is True
        expect(caption).to_contain_text(f"осталось {days} дн.")
    else:
        expect(caption).not_to_contain_text("осталось")
    if case == "ended":
        assert shown["cycle_context"]["state"] == "period_ended"
        expect(page.get_by_role("heading", name="Период закончился", exact=True)).to_be_visible()
        expect(page.get_by_text("Текущей фазы нет", exact=True)).to_be_visible()
    elif case in ("race_day", "past_event_active"):
        assert shown["cycle_context"]["state"] == "in_progress"
        assert shown["timeline"]["days_remaining"] == 0
    assert evidence_bytes(db) == before
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifacts = Path(__file__).parents[2] / "docs/design/evidence/issue-677-countdown"
    artifacts.mkdir(parents=True, exist_ok=True)
    caption.screenshot(path=str(artifacts / f"{case}.png"))
