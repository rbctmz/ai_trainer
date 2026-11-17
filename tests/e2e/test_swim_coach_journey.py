"""Real isolated HTTP/SQLite + scripted native provider, never a paid AI call."""

import json
import re
import urllib.request

import pytest
from playwright.sync_api import expect

from tests.smoke._swim_import_fixtures import exact_program_v2

pytestmark = [pytest.mark.e2e, pytest.mark.parametrize("web_stack", ["swim_native"], indirect=True)]


def api_get(stack, path):
    with urllib.request.urlopen(stack.api_base + path + "?demo=1", timeout=30) as response:
        return json.loads(response.read())


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
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)
