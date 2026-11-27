"""Real isolated HTTP/SQLite + scripted native provider, never a paid AI call."""

import json
import re
import urllib.request

import pytest
from playwright.sync_api import expect

from tests.smoke._swim_import_fixtures import exact_program_v2
from tests.e2e.test_swim_import_ui import api_post, seeded_draft

pytestmark = [pytest.mark.e2e, pytest.mark.parametrize("web_stack", ["swim_native"], indirect=True)]


def api_get(stack, path):
    with urllib.request.urlopen(stack.api_base + path + "?demo=1", timeout=30) as response:
        return json.loads(response.read())


def test_coach_shows_payment_failure_and_retains_source(web_stack):
    page = web_stack.page
    raw = api_post(web_stack, "/api/swim-imports", {
        "source_text": "E2E: 100 м свободно", "request_id": "52762dc5-358e-4d82-a7a2-8fd1c60d3656",
    })
    page.goto(web_stack.web_base + f"/coach/swim?draft={raw['import_id']}")
    page.get_by_role("button", name="Разобрать с Коучем", exact=True).click()
    dialogue = page.get_by_role("region", name="Диалог о программе")
    expect(dialogue.get_by_role("alert")).to_have_text(
        "На балансе провайдера ИИ недостаточно средств. Исходник сохранён."
    )
    expect(dialogue).not_to_contain_text("UNTRUSTED_PROVIDER_CANARY")
    expect(page.get_by_role("button", name="Подготовить предпросмотр", exact=True)).to_be_disabled()
    draft = api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")
    assert draft["revision"] == 0 and draft["source_text"] == raw["source_text"]


def test_coach_whole_program_clarify_preview_confirm_and_no_ai_reopen(web_stack):
    page = web_stack.page
    document = exact_program_v2()
    page.goto(web_stack.web_base + "/coach/swim")
    page.get_by_label("Текст тренера", exact=True).fill(document["source_text"])
    page.get_by_role("button", name="Сохранить исходник", exact=True).click()
    expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(document["source_text"])
    import_id = page.url.split("draft=", 1)[1]
    page.get_by_role("button", name="Разобрать с Коучем", exact=True).click()
    expect(page.get_by_role("region", name="Диалог о программе")).to_contain_text(
        "Оставить бассейн 25 м или выбрать 50 м?"
    )
    expect(page.get_by_role("region", name="Структура программы").get_by_role("article")).to_have_count(3)
    assert api_get(web_stack, "/api/swim-programs")["items"] == []
    page.get_by_label("Запрос Коучу", exact=True).fill("Первую тренировку в бассейне 50 м")
    page.get_by_role("button", name="Отправить Коучу", exact=True).click()
    expect(page.get_by_role("article", name="Example one", exact=True)).to_contain_text("Бассейн · 50 м")
    draft = api_get(web_stack, f"/api/swim-imports/{import_id}")
    assert draft["revision"] == 2 and draft["actor"] == "coach"
    assert draft["source_text"] == document["source_text"]
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    preview = page.get_by_role("region", name="Предпросмотр сохранения", exact=True)
    expect(preview).to_be_visible()
    expect(preview.get_by_role("article")).to_have_count(3)
    expect(preview).to_contain_text(re.compile(r"6\s?100\s?м"))
    assert api_get(web_stack, "/api/swim-programs")["items"] == []
    page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
    expect(page).to_have_url(re.compile(r"program=.*revision=1"))
    saved = api_get(web_stack, f"/api/swim-programs/{draft['program_id']}/versions/1")
    assert saved["document"] == draft["document"]
    assert saved["summary"]["distance_meters"] == 6100
    ai_calls = []

    def forbid_ai(route):
        ai_calls.append(route.request.url)
        route.abort()

    page.route("**/api/coach/swim-import*", forbid_ai)
    try:
        page.reload()
        expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(document["source_text"])
        page.get_by_role("link", name="Все программы", exact=True).click()
        page.get_by_role("region", name="Сохранённые программы").get_by_role("link", name=document["title"], exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
        assert ai_calls == []
        expect(page.locator("body")).not_to_contain_text("UNTRUSTED_COMPLETION_CANARY")
        assert not [error for error in web_stack.js_errors if error.startswith("pageerror:") or "hydration" in error.lower()]
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)


def test_expired_preview_refuses_then_requires_fresh_human_confirmation(web_stack):
    page = web_stack.page
    draft = seeded_draft(web_stack, exact_program_v2())
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    with page.expect_response(re.compile(r"/api/swim-imports/.*/preview")) as response:
        page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    preview_id = response.value.json()["preview_id"]
    api_post(web_stack, f"/_e2e/swim-previews/{preview_id}/expire", {})
    page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Срок предпросмотра истёк")).to_be_visible()
    assert not any(item["program_id"] == draft["program_id"] for item in api_get(web_stack, "/api/swim-programs")["items"])
    page.get_by_role("button", name="Вернуться к черновику", exact=True).click()
    with page.expect_response(re.compile(r"/api/swim-imports/.*/preview")) as response:
        page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    assert response.value.json()["preview_id"] != preview_id
    page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()


def test_unavailable_turn_readback_blocks_preview_until_actual_draft_read(web_stack):
    page = web_stack.page
    raw = api_post(web_stack, "/api/swim-imports", {"source_text": exact_program_v2()["source_text"], "request_id": "45ee288d-fe14-4160-9296-77cfdfddaa41"})
    page.goto(web_stack.web_base + f"/coach/swim?draft={raw['import_id']}")
    expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(raw["source_text"])
    fail_read = {"once": False}

    def unavailable_reply(route):
        response = route.fetch()
        frames = []
        for line in response.text().splitlines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:].strip())
            if event["type"] in ("swim_import", "done"):
                event["readback_status"] = "unavailable"
            if event["type"] == "swim_import":
                event.update(status="error", code="swim_import_storage_unavailable")
            if event["type"] == "token":
                event["content"] = "Не удалось прочитать актуальный черновик."
            frames.append("data: " + json.dumps(event, ensure_ascii=False) + "\n\n")
        fail_read["once"] = True
        route.fulfill(status=200, content_type="text/event-stream", body="".join(frames))

    def fail_current_once(route):
        if route.request.method == "GET" and fail_read["once"]:
            fail_read["once"] = False
            route.abort()
        else:
            route.continue_()

    page.route("**/api/coach/swim-import*", unavailable_reply)
    page.route(f"**/api/swim-imports/{raw['import_id']}?*", fail_current_once)
    try:
        page.get_by_role("button", name="Разобрать с Коучем", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Повторите чтение перед продолжением")).to_be_visible()
        expect(page.get_by_role("button", name="Подготовить предпросмотр", exact=True)).to_be_disabled()
        page.get_by_role("button", name="Обновить черновик", exact=True).click()
        expect(page.get_by_role("region", name="Структура программы").get_by_role("article")).to_have_count(3)
        expect(page.get_by_role("button", name="Подготовить предпросмотр", exact=True)).to_be_enabled()
        assert api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")["revision"] == 1
    finally:
        page.unroute("**/api/coach/swim-import*", unavailable_reply)
        page.unroute(f"**/api/swim-imports/{raw['import_id']}?*", fail_current_once)
