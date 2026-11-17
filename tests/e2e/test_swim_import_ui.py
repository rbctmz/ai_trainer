"""Swimming workspace acceptance against an owned API/DB, no paid AI calls."""

import re
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

SOURCE = "  🏊 Synthetic trainer source\n100 metres easy\nRest 60–70 seconds\n"


def test_source_capture_and_reload_precede_any_ai_work(web_stack):
    page = web_stack.page
    calls = []
    def forbid_ai(route):
        calls.append(route.request.url)
        route.abort()
    page.route("**/api/coach/swim-import*", forbid_ai)
    try:
        page.goto(web_stack.web_base + "/coach")
        page.get_by_role("link", name="Программа тренера", exact=True).click()
        expect(page.get_by_role("heading", name="Программы плавания", exact=True)).to_be_visible()
        page.get_by_label("Текст тренера", exact=True).fill(SOURCE)
        with page.expect_response(re.compile(r"/api/swim-imports(?:\?|$)")) as response:
            page.get_by_role("button", name="Сохранить исходник", exact=True).click()
        assert response.value.status == 200, response.value.text()
        captured = response.value.json()
        assert captured["source_text"] == SOURCE and captured["revision"] == 0
        expect(page).to_have_url(re.compile(r"/coach/swim\?draft=" + captured["import_id"]))
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(SOURCE)
        page.reload()
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(SOURCE)
        expect(page.get_by_role("button", name="Разобрать с Коучем", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="Создать структуру вручную", exact=True)).to_be_visible()
        assert calls == []
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)
