"""Manual rich prescriptions and bounded edits use the same persisted draft."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_swim_import_ui import api_post
from tests.e2e.test_swim_coach_journey import api_get

pytestmark = pytest.mark.e2e


def test_manual_three_workouts_ranges_attempts_and_exact_patch_without_ai(web_stack):
    page = web_stack.page
    source_text = "🏊 Синтетика\n100 м, отдых 60–70 секунд\n10 минут ОВ\n10–15 попыток, около 10 м\n"
    raw = api_post(web_stack, "/api/swim-imports", {"source_text": source_text, "request_id": "8b94ce90-cfd2-43d6-a766-83039e8fa662"})
    ai_calls = []

    def forbid_ai(route):
        ai_calls.append(route.request.url)
        route.abort()

    page.route("**/api/coach/swim-import*", forbid_ai)
    try:
        page.goto(web_stack.web_base + f"/coach/swim?draft={raw['import_id']}")
        page.get_by_role("button", name="Создать структуру вручную", exact=True).click()
        editor = page.get_by_role("region", name="Ручная структура", exact=True)
        editor.get_by_label("Название программы", exact=True).fill("Синтетическая ручная программа")
        editor.get_by_role("button", name="Привязать весь исходник", exact=True).click()
        for index in range(1, 4):
            editor.get_by_role("button", name="Добавить тренировку", exact=True).click()
            workout = editor.get_by_role("article", name=f"Ручная тренировка {index}", exact=True)
            workout.get_by_label("Название тренировки", exact=True).fill(f"Задание {index}")
            workout.get_by_label("Среда", exact=True).select_option("open_water" if index == 2 else "pool")
            if index != 2:
                workout.get_by_label("Длина бассейна, м", exact=True).fill("25" if index == 1 else "50")
            workout.get_by_role("button", name="Добавить шаг", exact=True).click()
            step = workout.get_by_role("group", name="Элемент 1", exact=True)
            step.get_by_label("Название элемента", exact=True).fill(f"Отрезок {index}")
            step.get_by_label("Объём шага", exact=True).select_option(["distance", "duration", "attempts"][index - 1])
            if index == 1:
                step.get_by_label("Дистанция, м", exact=True).fill("100")
                workout.get_by_role("button", name="Добавить шаг", exact=True).click()
                rest = workout.get_by_role("group", name="Элемент 2", exact=True)
                rest.get_by_label("Тип элемента", exact=True).select_option("rest")
                rest.get_by_label("Режим отдыха", exact=True).select_option("approximate")
                rest.get_by_label("Отдых от, с", exact=True).fill("60")
                rest.get_by_label("Отдых до, с", exact=True).fill("70")
            elif index == 2:
                step.get_by_label("Длительность, с", exact=True).fill("600")
            else:
                step.get_by_label("Попыток от", exact=True).fill("10")
                step.get_by_label("Попыток до", exact=True).fill("15")
                step.get_by_label("Ориентир на попытку, м", exact=True).fill("10")
        page.reload()
        editor = page.get_by_role("region", name="Ручная структура", exact=True)
        expect(editor.get_by_label("Название программы", exact=True)).to_have_value("Синтетическая ручная программа")
        editor.get_by_role("button", name="Записать структуру черновика", exact=True).click()
        summary = page.get_by_role("region", name="Объём программы", exact=True)
        expect(summary).to_contain_text("Полная дистанция неизвестна")
        expect(summary).to_contain_text("100 м")
        draft = api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")
        assert draft["actor"] == "user" and len(draft["document"]["workouts"]) == 3
        assert draft["summary"]["distance_meters"] is None
        assert draft["summary"]["known_distance_meters"] == 100
        page.get_by_role("button", name="Изменить: Отдых", exact=True).click()
        patch = page.get_by_role("region", name="Правка элемента", exact=True)
        patch.get_by_label("Отдых до, с", exact=True).fill("90")
        patch.get_by_role("button", name="Применить правку", exact=True).click()
        changed = api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")
        assert changed["revision"] == 2
        before = draft["document"]
        before["workouts"][0]["steps"][1]["seconds"]["maximum"] = 90
        assert changed["document"] == before
        expect(page.get_by_role("region", name="Структура программы")).to_contain_text(re.compile("60–90 с отдыха"))
        page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
        page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
        saved = api_get(web_stack, f"/api/swim-programs/{raw['program_id']}/versions/1")
        assert saved["document"] == changed["document"] and ai_calls == []
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)
