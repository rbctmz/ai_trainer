"""Library → dated calendar assembly → preview → confirm on an owned web stack."""

from datetime import date, timedelta
import os
from pathlib import Path

from playwright.sync_api import expect
import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from tests.planning_fixtures import seed_checkpoint
from tests.smoke._planning_cycle_regressions import plan
from tests.smoke._swim_program_fixtures import example_program

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(("width", "theme"), [(390, "dark"), (1280, "light")])
def test_trainer_workout_confirmation_and_move_appear_in_plan(web_stack, width, theme):
    page = web_stack.page
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.clear_all_data()
    base = web_stack.api_base
    context = page.request.get(f"{base}/api/planning/cycles/current?demo=1").json()
    today = date.fromisoformat(context["athlete_day"])
    tomorrow = today + timedelta(days=1)
    seed_checkpoint(db, build_planning_checkpoint(plan(today, days=7)))
    created = page.request.post(f"{base}/api/swim-programs/preview?demo=1", data={
        "document": example_program(), "base_revision": 0,
    })
    assert created.status == 200, created.text()
    saved = page.request.post(f"{base}/api/swim-programs/confirm?demo=1", data={
        "preview_id": created.json()["preview_id"], "confirm": True,
    })
    assert saved.status == 200, saved.text()
    program = saved.json()
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{web_stack.web_base}/coach/swim?program={program['program_id']}&revision=1")
    page.get_by_role("link", name="Назначить даты", exact=True).click(timeout=5000)
    page.evaluate("""theme => {
        localStorage.setItem('theme', theme);
        document.documentElement.classList.toggle('dark', theme === 'dark');
    }""", theme)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_label("Дата: Example one", exact=True).fill(today.isoformat())
    page.get_by_role("button", name="Проверить назначения", exact=True).click()
    review = page.get_by_role("region", name="Предпросмотр календаря", exact=True)
    expect(review).to_contain_text("Длительность и TSS неизвестны")
    expect(review.get_by_role("heading", name="Предпросмотр календаря")).to_be_focused()
    review.get_by_text("Серии и упражнения", exact=True).click()
    expect(review.get_by_text("500 м", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    evidence_dir = os.environ.get("AI_TRAINER_SWIM_CALENDAR_EVIDENCE")
    if evidence_dir:
        target = Path(evidence_dir)
        target.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=target / f"calendar-preview-{theme}-{width}.png", full_page=True)
    assert page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"] == []
    review.get_by_role("button", name="Подтвердить изменения календаря", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Календарь обновлён")).to_be_visible()
    rows = page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"]
    assert len(rows) == 1 and rows[0]["date"] == today.isoformat()
    first_checkpoint = db.get_current_planning_checkpoint()["id"]
    page.goto(f"{web_stack.web_base}/planning")
    assert page.evaluate("document.documentElement.classList.contains('dark')") == (theme == "dark")
    page.get_by_role("button", name="Недели", exact=True).click()
    expect(page.get_by_role("link", name="Example one", exact=True)).to_be_visible()
    expect(page.get_by_text("TSS плавания тренера пока неизвестен", exact=False)).to_be_visible()
    if evidence_dir:
        page.screenshot(path=Path(evidence_dir) / f"calendar-week-{theme}-{width}.png", full_page=True)
    page.get_by_role("link", name="Календарь тренировок тренера", exact=True).click()
    page.get_by_role("button", name="Перенести: Example one", exact=True).click()
    page.get_by_label("Новая дата", exact=True).fill(tomorrow.isoformat())
    page.get_by_role("button", name="Проверить перенос", exact=True).click()
    expect(review).to_contain_text(today.isoformat())
    expect(review).to_contain_text(tomorrow.isoformat())
    review.get_by_role("button", name="Подтвердить изменения календаря", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Календарь обновлён")).to_be_visible()
    after = page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"]
    assert after == [{**rows[0], "date": tomorrow.isoformat()}]
    history = page.request.get(f"{base}/api/planning/history?demo=1")
    assert history.status == 200, history.text()
    assert any(item["checkpoint_id"] == first_checkpoint for item in history.json()["items"])
    page.get_by_label("Версия плана", exact=True).select_option(str(first_checkpoint))
    page.get_by_role("button", name="Проверить возврат к этой версии", exact=True).click()
    expect(review).to_contain_text(today.isoformat())
    review.get_by_role("button", name="Подтвердить изменения календаря", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Календарь обновлён")).to_be_visible()
    assert page.request.get(f"{base}/api/planning/swim-calendar?demo=1").json()["assignments"] == rows
    db.save_coach_constraint(date=today.isoformat(), kind="forced_rest", cycle_scope="athlete")
    page.goto(f"{web_stack.web_base}/planning")
    page.get_by_role("button", name="Недели", exact=True).click()
    expect(page.get_by_text("На эту дату действует ограничение на плавание.", exact=False)).to_be_visible()
