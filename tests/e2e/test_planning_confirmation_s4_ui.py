"""S4 decision acceptance: real synthetic backend; no athlete/provider writes."""
from datetime import date, timedelta
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.planning_entry_helpers import declare_entry_limits
from tests.e2e.test_planning_cycle_lifecycle_ui import close_in_ui, setup_ended

pytestmark = pytest.mark.e2e


def candidate(web_stack, *, mode="training_goal", replace=False, display_fixture=None, refusal_fixture=None):
    page, db = setup_ended(web_stack)
    if not replace:
        close_in_ui(page)
    page.get_by_role("button", name="Начать новый цикл", exact=True).click()
    expect(page.get_by_label("Дата начала цикла")).to_have_value(re.compile(r"\d{4}-\d{2}-\d{2}"))
    start = date.fromisoformat(page.get_by_label("Дата начала цикла").input_value()) + timedelta(days=7)
    if mode == "event_goal":
        start += timedelta(days=(-start.weekday()) % 7)
    page.get_by_label("Дата начала цикла").fill(start.isoformat())
    if mode == "training_goal":
        page.get_by_role("button", name="Развивать форму Без выдуманной даты гонки", exact=True).click()
    elif mode == "manual":
        page.get_by_role("button", name="Ручные фазы Фазы задаёте вы", exact=True).click()
        page.get_by_label("Ручные фазы", exact=True).fill("Base, Base, Build, Recovery, Base, Base, Build, Recovery")
    else:
        event = start + timedelta(days=110)  # Explicit Saturday race fixture.
        page.get_by_label("Дата A-старта", exact=True).fill(event.isoformat())
    page.get_by_role("checkbox", name=re.compile("Выбираю эту цель")).check()
    if replace:
        page.get_by_role("checkbox", name=re.compile("При сохранении нового плана")).check()
    page.get_by_role("button", name="Далее", exact=True).click()
    declare_entry_limits(page)
    page.get_by_role("button", name="Далее", exact=True).click()
    if refusal_fixture is not None:
        page.route("**/api/planning/build?*", lambda route: route.fulfill(status=422, json=refusal_fixture))
    if display_fixture is not None:
        # Legacy/partial presentation only: never confirm a modified response.
        def legacy(route):
            response = route.fetch()
            assert response.status == 200, response.text()
            payload = response.json()
            display_fixture(payload)
            route.fulfill(status=200, json=payload)
        page.route("**/api/planning/build?*", legacy)
    with page.expect_response("**/api/planning/build?*") as response:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert response.value.status == (422 if refusal_fixture else 200), response.value.text()
    result = response.value.json()
    if refusal_fixture:
        return page, db, result
    page.get_by_role("button", name="Далее", exact=True).click()
    expect(page.get_by_role("heading", name="Настройка плана — шаг 4: Подтверждение", exact=True)).to_be_focused()
    return page, db, result


@pytest.mark.parametrize("width,theme", [(390,"light"),(390,"dark"),(900,"light"),(900,"dark"),(1280,"light"),(1280,"dark")])
def test_frozen_decision_scope_load_and_forecast_are_understandable(web_stack, width, theme):
    page = web_stack.page
    page.set_viewport_size({"width": width, "height": 950})
    page, db, result = candidate(web_stack)
    page.evaluate("theme => {document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.dataset.theme=theme;}", theme)
    summary = page.get_by_role("region", name="Резюме плана", exact=True)
    expect(summary).to_be_visible()
    expect(summary.locator("time").nth(0)).to_have_attribute("datetime", result["lifecycle"]["start_date"])
    expect(summary.locator("time").nth(1)).to_have_attribute("datetime", result["lifecycle"]["end_date"])
    expect(summary).to_contain_text("Триатлон · Олимпийка")
    expect(summary).to_contain_text("Развивать форму")
    expect(summary).to_contain_text(f'{result["totals"]["total_tss"]} TSS')
    expect(summary).to_contain_text(f'{result["totals"]["peak_tss"]} TSS')
    expect(summary).to_contain_text(f'{result["weekly_target"]["target_weekly_tss"]} TSS')
    expect(summary).to_contain_text("Ваш лимит времени")
    expect(summary).to_contain_text("Соревнования в этот план не включены")
    # Extra explanation is available by keyboard without pushing the decision
    # or its actual total behind a disclosure.
    explanation = summary.get_by_text("Как понимать нагрузку", exact=True)
    expect(explanation.locator("..")).not_to_have_attribute("open", "")
    explanation.focus()
    page.keyboard.press("Enter")
    expect(explanation.locator("..")).to_have_attribute("open", "")
    expect(summary).to_contain_text("Общая длительность и число тренировок здесь не показаны")
    page.keyboard.press("Enter")
    expect(page.get_by_text(re.compile("Изменение нагрузки:|нед. rolling|Прогноз CTL / ATL / TSB к старту"))).to_have_count(0)
    expect(page.get_by_text(result["forecast"]["message"], exact=True)).to_have_count(0)
    forecast = page.get_by_role("region", name="Модельный прогноз нагрузки", exact=True)
    expect(forecast).to_contain_text(result["forecast"]["points"][0]["date"])
    table_toggle = forecast.get_by_text("Даты и значения прогноза", exact=True)
    table_toggle.focus()
    page.keyboard.press("Enter")
    row = forecast.get_by_role("row").filter(has_text=result["forecast"]["points"][-1]["date"])
    expect(row).to_contain_text(str(result["forecast"]["points"][-1]["ctl"]))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if width == 390:
        # The full discipline table remains available via its own scroll area.
        weeks = page.get_by_role("region", name="Назначения по неделям", exact=True)
        scroll = weeks.locator("div.overflow-x-auto")
        assert scroll.evaluate("element => element.scrollWidth > element.clientWidth")
        expect(weeks.get_by_role("columnheader", name="Плавание, TSS", exact=True)).to_have_count(1)
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-714/highlight-v1"
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / f"confirmation-{width}-{theme}.png"), full_page=True)
    if (width, theme) in ((390, "dark"), (1280, "light")):
        summary.screenshot(path=str(artifact / f"decision-{width}-{theme}.png"))
    assert db.get_current_planning_checkpoint() is None
    # Summary is the frozen candidate; confirmation still sends identity only.
    with page.expect_response("**/api/planning/build/confirm*") as saved:
        page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    assert saved.value.status == 200, saved.value.text()
    assert set(saved.value.request.post_data_json) == {"preview_id", "confirm"}
    expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()


@pytest.mark.parametrize("width,theme", [(390,"light"),(390,"dark"),(900,"light"),(900,"dark"),(1280,"light"),(1280,"dark")])
def test_edit_different_horizon_has_dated_before_and_after(web_stack, width, theme):
    page, db, _ = candidate(web_stack)
    page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()
    page.get_by_role("button", name="Открыть план в Обзоре", exact=True).click()
    before = db.get_current_planning_checkpoint()["id"]
    page.get_by_role("button", name="Изменить план", exact=True).click()
    page.get_by_role("combobox").nth(2).select_option("4")
    page.get_by_role("button", name="Далее", exact=True).click()
    page.get_by_role("button", name="Далее", exact=True).click()
    with page.expect_response("**/api/planning/build?*") as built:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert built.value.status == 200, built.value.text()
    result = built.value.json()
    assert len(result["preview"]["weekly_tss_before"]) != len(result["preview"]["weekly_tss_after"])
    page.get_by_role("button", name="Далее", exact=True).click()
    summary = page.get_by_role("region", name="Резюме плана", exact=True)
    expect(summary).to_contain_text("Изменение плана")
    comparison = summary.get_by_role("region", name="Было и станет", exact=True)
    expect(comparison).to_be_visible()
    expect(comparison.get_by_role("columnheader", name="Текущий план", exact=True)).to_be_visible()
    expect(comparison.get_by_role("columnheader", name="Предлагаемый план", exact=True)).to_be_visible()
    paired = result["comparison"]
    assert paired["status"] == "complete"
    load = comparison.get_by_role("row").filter(has=page.get_by_role("rowheader", name="Сумма за весь период", exact=True))
    expect(load.get_by_role("cell").nth(0)).to_have_text(f'{paired["before"]["total_tss"]} TSS')
    expect(load.get_by_role("cell").nth(1)).to_have_text(f'{paired["after"]["total_tss"]} TSS')
    period = comparison.get_by_role("row").filter(has=page.get_by_role("rowheader", name="Период плана", exact=True))
    for column, side in enumerate(("before", "after")):
        expect(period.get_by_role("cell").nth(column).locator("time").nth(1)).to_have_attribute("datetime", paired[side]["scope"]["end_date"])
    for changed in (load, period):
        expect(changed).to_contain_text("Изменено")
        expect(changed).to_have_class(re.compile("bg-accent/10"))
    unchanged = comparison.get_by_role("row").filter(has=page.get_by_role("rowheader", name="Подготовка", exact=True))
    expect(unchanged).not_to_contain_text("Изменено")
    expect(unchanged).not_to_have_class(re.compile("bg-accent/10"))
    expect(comparison).to_contain_text("Разница сумм за разные периоды не означает изменение недельной нагрузки")
    page.set_viewport_size({"width": width, "height": 950})
    page.evaluate("theme => {document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.dataset.theme=theme}", theme)
    artifact = Path(__file__).parents[2] / "docs/design/evidence/issue-714/highlight-v1"
    artifact.mkdir(parents=True, exist_ok=True)
    summary.screenshot(path=str(artifact / f"edit-{width}-{theme}.png"))
    expect(page.get_by_role("heading", name="Настройка плана — шаг 4: Подтверждение", exact=True)).to_be_focused()
    schedule = comparison.get_by_text("Изменения расписания по датам", exact=True)
    schedule.focus()
    page.keyboard.press("Enter")
    region = comparison.get_by_role("region", name="Расписание до и после", exact=True)
    expect(region).to_be_visible()
    expect(region.get_by_role("row")).to_have_count(len(paired["days"]) + 1)
    expect(region).to_contain_text("Назначения убраны")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if width == 390:
        assert region.evaluate("element => element.scrollWidth > element.clientWidth")
    expect(page.get_by_text("Сравнение с прежним планом недоступно", exact=False)).to_have_count(0)
    assert any(warning["code"] == "entry_limits_retained" for warning in result["entry_load"]["warnings"])
    expect(summary.get_by_text("Сохранены стартовые ограничения выбранного цикла; новая история показана отдельно.", exact=True)).to_be_visible()
    expect(summary).to_contain_text(f'{result["totals"]["total_tss"]} TSS')
    expect(page.get_by_text(re.compile("Изменение нагрузки:"))).to_have_count(0)
    page.get_by_role("button", name="Отменить", exact=True).click()
    assert db.get_current_planning_checkpoint()["id"] == before


@pytest.mark.parametrize("mode", ["event_goal", "manual"])
def test_event_and_manual_summary_use_applied_candidate_data(web_stack, mode):
    page, _, result = candidate(web_stack, mode=mode)
    summary = page.get_by_role("region", name="Резюме плана", exact=True)
    if mode == "event_goal":
        assert result["goal"]["events"]
        for event in result["goal"]["events"]:
            expect(summary.get_by_text("Соревнования", exact=True).locator("..").locator(f'time[datetime="{event["date"]}"]').first).to_be_visible()
    else:
        expect(summary).to_contain_text("Ручные фазы")
        expect(summary).to_contain_text("Базовая подготовка")
    expect(page.get_by_text(re.compile("Прогноз.*к старту"))).to_have_count(0)


def test_replacement_explains_consequence_before_confirmation(web_stack):
    page, db, result = candidate(web_stack, replace=True)
    assert result["lifecycle"]["closes_cycle_id"]
    before = db.get_current_planning_checkpoint()["id"]
    expect(page.get_by_role("note").filter(has_text="прежний цикл закроется")).to_be_visible()
    page.get_by_role("button", name="Отменить", exact=True).click()
    assert db.get_current_planning_checkpoint()["id"] == before


@pytest.mark.parametrize("state", ["historical", "unknown_current", "missing_values"])
def test_legacy_and_partial_display_does_not_invent_current_or_zero(web_stack, state):
    def fixture(payload):
        if state == "missing_values":
            payload.pop("lifecycle", None)
            payload["totals"] = None
            payload["parameters"] = None
            payload["forecast"] = {"points": [{"date": "2026-01-01", "ctl": None}]}
            payload["goal"]["events"] = None
        else:
            payload["plan_id"] = "synthetic-historical-receipt"
            payload["confirmation"].update(status="applied", replayed=True,
                                           is_current=False if state == "historical" else None)
    page, db, _ = candidate(web_stack, display_fixture=fixture)
    if state == "missing_values":
        summary = page.get_by_role("region", name="Резюме плана", exact=True)
        expect(summary).to_contain_text("Период этого варианта не указан")
        expect(summary).to_contain_text("Нет данных")
        expect(summary).to_contain_text("Лимит времени для этого варианта неизвестен")
        expect(page.get_by_text("Датированные значения прогноза не переданы", exact=False)).to_be_visible()
        # Presentation omissions do not introduce a second publication policy.
        expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_be_enabled()
    else:
        expected = ("Этот вариант уже сохранялся; сейчас действует другой план" if state == "historical"
                    else "Вариант сохранён; его текущий статус не подтверждён")
        expect(page.get_by_text(expected, exact=False)).to_be_visible()
        expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_have_count(0)
        expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
    assert db.get_current_planning_checkpoint() is None


def test_structured_readiness_refusal_is_explained_without_confirm(web_stack):
    refusal = {"detail": "План содержит неполные назначения", "code": "plan_not_ready", "retryable": False,
               "build_readiness": {"status": "blocked", "can_confirm": False,
                                   "blockers": [{"code": "prescription_missing", "date": "2026-11-01"},
                                                {"code": "load_inconsistent", "date": None}]}}
    page, db, _ = candidate(web_stack, refusal_fixture=refusal)
    alert = page.get_by_role("alert").filter(has_text="План не готов к сохранению")
    expect(alert).to_contain_text("2026-11-01: Для этого дня не подготовлено полное задание")
    expect(alert).to_contain_text("Нагрузка назначения не согласована с планом")
    expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    assert db.get_current_planning_checkpoint() is None


@pytest.mark.parametrize("state", ["partial", "legacy", "historical"])
def test_comparison_unknown_and_legacy_receipt_keep_protocol_meaning(web_stack, state):
    def fixture(payload):
        if state == "legacy":
            payload.pop("comparison")
        elif state == "historical":
            payload["plan_id"] = "synthetic-historical-comparison"
            payload["confirmation"].update(status="applied", replayed=True, is_current=False)
        else:
            comparison = payload["comparison"]
            comparison.update(status="partial", counts=None)
            comparison["before"]["scope"] = None
            comparison["before"]["total_tss"] = None
            comparison["before"]["parameters"]["available_hours"] = None
    page, db, result = candidate(web_stack, replace=True, display_fixture=fixture)
    current = db.get_current_planning_checkpoint()["id"]
    if state == "legacy":
        expect(page.get_by_text("В этом предложении нет данных для сравнения с прежним планом.", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_be_enabled()
    else:
        comparison = page.get_by_role("region", name="Было и станет", exact=True)
        expect(comparison).to_be_visible()
        if state == "historical":
            expect(comparison.get_by_role("columnheader", name="Было в предложении", exact=True)).to_be_visible()
            expect(comparison.get_by_role("columnheader", name="Текущий план", exact=True)).to_have_count(0)
            expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
        else:
            row = comparison.get_by_role("row").filter(has=page.get_by_role("rowheader", name="Сумма за весь период", exact=True))
            expect(row.get_by_role("cell").nth(0)).to_have_text("Нет данных")
            expect(row).not_to_contain_text("Изменено")
            expect(row).not_to_have_class(re.compile("bg-accent/10"))
            expect(row.get_by_role("cell").nth(1)).to_have_text(f'{result["comparison"]["after"]["total_tss"]} TSS')
            expect(comparison.get_by_role("note")).to_contain_text("не означает ноль или отдых")
            expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_be_enabled()
    assert db.get_current_planning_checkpoint()["id"] == current


def test_changed_rest_phase_is_visible_on_both_sides(web_stack):
    def fixture(payload):
        comparison = payload["comparison"]
        comparison["days"] = [{
            "date": comparison["after"]["scope"]["start_date"],
            "change": "changed",
            "before": {"state": "rest", "phase": "Base", "tss": 0, "sessions": []},
            "after": {"state": "rest", "phase": "Recovery", "tss": 0, "sessions": []},
        }]
        comparison["counts"] = {"added": 0, "removed": 0, "changed": 1, "unchanged": 0}

    # Read-only presentation fixture: no modified response is confirmed.
    page, db, _ = candidate(web_stack, replace=True, display_fixture=fixture)
    current = db.get_current_planning_checkpoint()["id"]
    comparison = page.get_by_role("region", name="Было и станет", exact=True)
    comparison.get_by_text("Изменения расписания по датам", exact=True).click()
    schedule = comparison.get_by_role("region", name="Расписание до и после", exact=True)
    row = schedule.get_by_role("row").filter(has_text="Назначения изменены")
    for index, phase in enumerate(("Базовая подготовка", "Восстановление")):
        cell = row.get_by_role("cell").nth(index)
        expect(cell).to_contain_text("Отдых · 0 TSS")
        expect(cell).to_contain_text(phase)
    page.get_by_role("button", name="Отменить", exact=True).click()
    assert db.get_current_planning_checkpoint()["id"] == current
