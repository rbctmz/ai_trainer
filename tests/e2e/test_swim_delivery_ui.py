"""Calendar delivery through the actual API with an owned Intervals double."""

from datetime import date, timedelta
import os
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect
import pytest

from data.database import Database
from data.swim_program_store import confirm_preview
from models.planning_checkpoints import build_planning_checkpoint
from models.swim_import import CaptureSource, ParseDraft, PrepareDraft
from services import swim_imports
from tests.planning_fixtures import seed_checkpoint
from tests.smoke._planning_cycle_regressions import plan
from tests.smoke._swim_import_fixtures import exact_program_v2

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("web_stack", ["swim_native"], indirect=True)
@pytest.mark.parametrize(("width", "theme"), [(390, "dark"), (1280, "light")])
def test_calendar_preview_confirm_and_receipt_reload(web_stack, width, theme):
    api = web_stack.api_base
    web = web_stack.web_base
    context = web_stack.page.context.browser.new_context(viewport={"width": width, "height": 900})
    context.add_init_script(f"window.localStorage.setItem('theme', '{theme}');")
    page = context.new_page()
    try:
        db = Database(str(web_stack.tmp_dir / "e2e.db"))
        db.clear_all_data()
        today = page.request.get(f"{api}/api/planning/cycles/current").json()["athlete_day"]
        seed_checkpoint(db, build_planning_checkpoint(plan(date.fromisoformat(today))))
        document = exact_program_v2()
        captured = swim_imports.capture_source(
            db, CaptureSource(source_text=document["source_text"], request_id=str(uuid4())),
        )
        import_id = captured["import_id"]
        draft = swim_imports.parse_draft(db, import_id, ParseDraft(
            request_id=str(uuid4()), expected_revision=captured["revision"],
            content={key: document[key] for key in ("title", "source_spans", "workouts")},
        ), actor="user")
        prepared = swim_imports.prepare_preview(db, import_id, PrepareDraft(
            request_id=str(uuid4()), draft_revision=draft["revision"], base_library_revision=0,
        ))
        saved = confirm_preview(db, prepared["preview_id"])
        root = f"{api}/api/planning/swim-calendar"
        result = page.request.post(f"{root}/preview", data={
            "request_id": str(uuid4()),
            "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
            "operation": {"kind": "place", "program_id": saved["program_id"],
                          "program_revision": saved["revision"], "dates": {"one": today}},
        })
        assert result.ok, result.text()
        reviewed = result.json()
        result = page.request.post(f"{root}/confirm", data={"preview_id": reviewed["preview_id"], "confirm": True})
        assert result.ok, result.text()
        assignment_id = reviewed["changes"][0]["after"]["assignment_id"]
        starting_count = page.request.get(f"{api}/_e2e/swim-delivery-state").json()["creates"]

        page.goto(f"{web}/planning/swim")
        assert page.evaluate("document.documentElement.classList.contains('dark')") == (theme == "dark")
        open_delivery = page.get_by_role("button", name="Доставка на Garmin: Example one", exact=True)
        open_delivery.click()
        panel = page.get_by_role("region", name="Доставка на Garmin", exact=True)
        expect(panel.get_by_role("heading", name="Доставка на Garmin", exact=True)).to_be_focused()
        panel.get_by_role("button", name="Проверить отправку", exact=True).click()
        expect(panel.get_by_role("heading", name="Предпросмотр отправки", exact=True)).to_be_focused()
        expect(panel).to_contain_text(f"{today} · бассейн 25 м · 2200 м")
        expect(panel.get_by_role("list", name="Шаги для Intervals.icu")).to_contain_text("Отдых 50 с")
        expect(panel.get_by_role("list", name="Шаги для Intervals.icu")).to_contain_text("Отдых по Lap")
        assert page.request.get(f"{api}/_e2e/swim-delivery-state").json()["creates"] == starting_count
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        evidence = os.environ.get("AI_TRAINER_SWIM_DELIVERY_EVIDENCE")
        if evidence:
            evidence_dir = Path(evidence)
            evidence_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=evidence_dir / f"swim-delivery-preview-{theme}-{width}.png", full_page=True)
        panel.get_by_role("button", name="Подтвердить отправку в Intervals.icu", exact=True).click()
        expect(panel).to_contain_text("Тренировка сверена в Intervals.icu")
        expect(panel).to_contain_text("Проверьте получение и шаги на Garmin FR255")
        if evidence:
            page.screenshot(path=evidence_dir / f"swim-delivery-receipt-{theme}-{width}.png", full_page=True)
        panel.get_by_role("button", name="Закрыть доставку", exact=True).click()
        expect(open_delivery).to_be_focused()
        tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()

        def show_next_day(route):
            response = route.fetch()
            route.fulfill(response=response, json={**response.json(), "athlete_day": tomorrow})

        page.route("**/api/planning/cycles/current", show_next_day)
        page.reload()
        open_delivery.click(timeout=6000)
        expect(panel).to_contain_text("Тренировка сверена в Intervals.icu")
        assert page.request.get(f"{api}/_e2e/swim-delivery-state").json()["creates"] == starting_count + 1
        receipt = page.request.get(f"{root}/delivery", params={"assignment_id": assignment_id}).json()["receipt"]
        assert receipt["device_verified"] is False
    finally:
        context.close()


@pytest.mark.parametrize("web_stack", ["swim_native"], indirect=True)
def test_garmin_direct_shows_groups_and_retains_calendar_receipt(web_stack):
    from data.swim_program_store import create_preview
    from tests.swim_delivery_fixtures import garmin_repeat_program

    api = web_stack.api_base
    context = web_stack.page.context.browser.new_context(viewport={"width": 390, "height": 900})
    page = context.new_page()
    try:
        db = Database(str(web_stack.tmp_dir / "e2e.db"))
        db.clear_all_data()
        today = page.request.get(f"{api}/api/planning/cycles/current").json()["athlete_day"]
        seed_checkpoint(db, build_planning_checkpoint(plan(date.fromisoformat(today))))
        draft = create_preview(db, garmin_repeat_program(), base_revision=0)
        program = confirm_preview(db, draft["preview_id"])
        root = f"{api}/api/planning/swim-calendar"
        response = page.request.post(f"{root}/preview", data={
            "request_id": str(uuid4()), "expected_checkpoint_id": db.get_current_planning_checkpoint()["id"],
            "operation": {"kind": "place", "program_id": program["program_id"],
                          "program_revision": program["revision"], "dates": {"one": today}},
        })
        assert response.ok, response.text()
        reviewed = response.json()
        response = page.request.post(f"{root}/confirm", data={"preview_id": reviewed["preview_id"], "confirm": True})
        assert response.ok, response.text()
        state = f"{api}/_e2e/garmin-swim-delivery-state"
        start = page.request.get(state).json()["creates"]
        page.goto(f"{web_stack.web_base}/planning/swim")
        panel = page.get_by_role("region", name="Прямая отправка в Garmin", exact=True)
        open_delivery = page.get_by_role("button", name="Доставка на Garmin: Example one", exact=True)
        open_delivery.click()
        panel.get_by_role("button", name="Предпросмотр прямой отправки").click()
        expect(panel.get_by_role("heading", name="Предпросмотр Garmin")).to_be_focused()
        expect(panel).to_contain_text(f"{today} · бассейн 25 м · 75 м · версия 1")
        expect(panel.get_by_role("list", name="Группы и шаги Garmin")).to_contain_text("2 × · последний отдых пропущен")
        expect(panel).to_contain_text("25 м · упражнение · ласты")
        expect(panel).to_contain_text("Отдых 30 с")
        assert page.request.get(state).json()["creates"] == start
        evidence = os.environ.get("AI_TRAINER_SWIM_DELIVERY_EVIDENCE")
        if evidence:
            evidence_dir = Path(evidence)
            evidence_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=evidence_dir / "garmin-direct-preview.png", full_page=True)
        panel.get_by_role("button", name="Подтвердить отправку в Garmin").click()
        expect(panel).to_contain_text("Назначение в календаре Garmin не подтверждено")
        panel.get_by_role("button", name="Сверить результат Garmin").click()
        expect(panel).to_contain_text(f"Назначение в календаре Garmin сверено на {today}")
        expect(panel).to_contain_text("Синхронизация с часами проверяется отдельно")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.reload()
        open_delivery.click()
        expect(panel.get_by_role("link", name="Открыть тренировку в Garmin")).to_have_attribute(
            "href", "https://connect.garmin.com/app/workout/123?workoutType=swimming",
        )
        assert page.request.get(state).json()["creates"] == start + 1
    finally:
        context.close()
