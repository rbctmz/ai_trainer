"""M4 consumer acceptance: explicit input and real refusal, no API interception."""
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_planning_cycle_lifecycle_ui import setup_ended, close_in_ui
from tests.e2e.planning_entry_helpers import declare_entry_limits

pytestmark = pytest.mark.e2e


def entry_step(page):
    page.get_by_role("button", name="Начать новый цикл", exact=True).click()
    page.get_by_role("button", name="Развивать форму Без выдуманной даты гонки", exact=True).click()
    page.get_by_role("checkbox", name=re.compile("Выбираю эту цель")).check()
    page.get_by_role("button", name="Далее", exact=True).click()



def test_missing_starting_data_has_structured_actionable_refusal(web_stack):
    page, db = setup_ended(web_stack)
    close_in_ui(page)
    entry_step(page)
    expect(page.get_by_role("heading", name="История и начальная нагрузка", exact=True)).to_be_visible()
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build?*") as response:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert response.value.status == 422 and response.value.json()["code"] == "entry_dose_required"
    expect(page.get_by_role("heading", name="Нужны данные для начальной нагрузки", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Уточнить историю и ограничения", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    with db._connect() as conn:
        assert conn.execute("SELECT count(*) FROM planning_build_previews").fetchone()[0] == 0
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-710"
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / "entry-missing.png"), full_page=True)
    page.get_by_role("button", name="Уточнить историю и ограничения", exact=True).click()
    expect(page.get_by_role("heading", name="Настройка плана — шаг 2: Доступность", exact=True)).to_be_focused()


@pytest.mark.parametrize("width,theme", [(390, "dark"), (1280, "light")])
def test_explicit_starting_limits_preview_sources_invalidate_and_confirm(web_stack, width, theme):
    page, db = setup_ended(web_stack)
    close_in_ui(page)
    page.set_viewport_size({"width": width, "height": 950})
    page.evaluate("theme => document.documentElement.classList.toggle('dark', theme === 'dark')", theme)
    entry_step(page)
    expect(page.get_by_role("checkbox", name="Указать ограничения: бег", exact=True)).not_to_be_checked()
    declare_entry_limits(page)
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-710"
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / f"entry-input-{width}-{theme}.png"), full_page=True)
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build?*") as response:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert response.value.status == 200, response.value.text()
    result = response.value.json()
    assert result["entry_load"]["can_publish"] is True
    assert response.value.request.post_data_json["initial_dose_limits"]["run"]["weekly_minutes"] == 480
    assert all(cap["source"] == "athlete_declared" for cap in result["entry_load"]["limits"].values())
    page.get_by_role("button", name="Далее", exact=True).click()
    expect(page.get_by_role("heading", name="Начальная нагрузка согласована с ограничениями", exact=True)).to_be_visible()
    page.get_by_text("Записанная история и источники ограничений", exact=True).click()
    expect(page.get_by_text(re.compile("Задано вами: до"))).to_have_count(3)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-710"
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / f"entry-preview-{width}-{theme}.png"), full_page=True)
    # Editing the dose discards the old token; confirmation must use the new one.
    page.get_by_role("navigation", name="Шаги настройки плана").get_by_role("button").nth(1).click()
    page.get_by_label("бег: минут за 7 дней", exact=True).fill("470")
    page.get_by_role("button", name="Далее", exact=True).click()
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    with page.expect_response("**/api/planning/build?*") as updated:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert updated.value.status == 200, updated.value.text()
    assert updated.value.json()["confirmation"]["preview_id"] != result["confirmation"]["preview_id"]
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build/confirm*") as saved:
        page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    assert saved.value.status == 200, saved.value.text()
    assert set(saved.value.request.post_data_json) == {"preview_id", "confirm"}
    assert db.get_current_planning_checkpoint() is not None


def test_infeasible_explicit_dose_and_input_validation_are_not_success(web_stack):
    page, db = setup_ended(web_stack)
    close_in_ui(page)
    entry_step(page)
    # The step transition focuses its heading on the next animation frame.
    # Wait for that observable boundary before testing keyboard activation.
    expect(page.get_by_role("heading", name="Настройка плана — шаг 2: Доступность", exact=True)).to_be_focused()
    checkbox = page.get_by_role("checkbox", name="Указать ограничения: бег", exact=True)
    checkbox.focus()
    page.keyboard.press("Space")
    expect(checkbox).to_be_checked()
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    page.get_by_label("бег: минут за 7 дней", exact=True).fill("1")
    page.get_by_label("бег: занятий за 7 дней", exact=True).fill("1")
    page.get_by_label("бег: максимум минут за занятие", exact=True).fill("2")
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    declare_entry_limits(page, minutes="1", longest="1")
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build?*") as response:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert response.value.status == 422 and response.value.json()["code"] == "entry_dose_infeasible"
    expect(page.get_by_role("heading", name="План не укладывается в ограничения", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
    assert db.get_current_planning_checkpoint() is None
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-710"
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / "entry-infeasible.png"), full_page=True)


def test_coverage_is_explicit_scoped_and_never_inferred_from_sync(web_stack):
    page, _db = setup_ended(web_stack)
    close_in_ui(page)
    entry_step(page)
    page.get_by_label("Полнота записанной истории", exact=True).select_option("user_reported_complete")
    expect(page.get_by_label("История: с", exact=True)).to_have_value("")
    expect(page.get_by_label("История: по (не включая)", exact=True)).to_have_value("")
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    page.get_by_label("История: с", exact=True).fill("2020-01-01")
    # Date comes from server context, without calculating its reference window.
    day = page.request.get(f"{web_stack.api_base}/api/planning/cycles/current?demo=1").json()["athlete_day"]
    page.get_by_label("История: по (не включая)", exact=True).fill(day)
    declare_entry_limits(page)
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build?*") as response:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert response.value.status == 200, response.value.text()
    assert response.value.request.post_data_json["history_coverage"] == {
        "status": "user_reported_complete", "start_date": "2020-01-01", "end_date_exclusive": day}
    assert response.value.json()["entry_load"]["profile"]["completeness"]["status"] == "user_reported_complete"
