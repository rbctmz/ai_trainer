"""Library → dated calendar assembly → preview → confirm on an owned web stack."""

from datetime import date, timedelta

from playwright.sync_api import expect
import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from tests.planning_fixtures import seed_checkpoint
from tests.smoke._planning_cycle_regressions import plan
from tests.smoke._swim_program_fixtures import example_program

pytestmark = pytest.mark.e2e


def test_trainer_workout_confirmation_and_move_appear_in_plan(web_stack):
    page = web_stack.page
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.clear_all_data()
    base = web_stack.api_base
    context = page.request.get(f"{base}/api/planning/cycles/current?demo=1").json()
    today = date.fromisoformat(context["athlete_day"])
    start = today - timedelta(days=today.weekday())
    seed_checkpoint(db, build_planning_checkpoint(plan(start, days=7)))
    created = page.request.post(f"{base}/api/swim-programs/preview?demo=1", data={
        "document": example_program(), "base_revision": 0,
    })
    assert created.status == 200, created.text()
    saved = page.request.post(f"{base}/api/swim-programs/confirm?demo=1", data={
        "preview_id": created.json()["preview_id"], "confirm": True,
    })
    assert saved.status == 200, saved.text()
    program = saved.json()
    page.goto(f"{web_stack.web_base}/coach/swim?program={program['program_id']}&revision=1")
    page.get_by_role("link", name="Назначить даты", exact=True).click(timeout=5000)
    page.get_by_label("Дата: Example one", exact=True).fill(today.isoformat())
    page.get_by_role("button", name="Проверить назначения", exact=True).click()
    review = page.get_by_role("region", name="Предпросмотр календаря", exact=True)
    expect(review).to_contain_text("Длительность и TSS неизвестны")
    assert page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"] == []
    review.get_by_role("button", name="Подтвердить изменения календаря", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Календарь обновлён")).to_be_visible()
    rows = page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"]
    assert len(rows) == 1 and rows[0]["date"] == today.isoformat()
    page.goto(f"{web_stack.web_base}/planning")
    page.get_by_role("button", name="Недели", exact=True).click()
    expect(page.get_by_role("link", name="Example one", exact=True)).to_be_visible()
    expect(page.get_by_text("TSS плавания тренера пока неизвестен", exact=False)).to_be_visible()
