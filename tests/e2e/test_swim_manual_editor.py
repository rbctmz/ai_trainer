"""Manual rich prescriptions and bounded edits use the same persisted draft."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_swim_import_ui import api_post
from tests.e2e.test_swim_import_ui import seeded_draft
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
        page.reload()
        patch = page.get_by_role("region", name="Правка элемента", exact=True)
        expect(patch.get_by_label("Отдых до, с", exact=True)).to_have_value("90")
        patch.get_by_text("Привязка к исходнику (0)", exact=True).click()
        patch.get_by_label("Выделите фрагмент исходника", exact=True).evaluate("""element => {
            const start = element.value.indexOf('100 м');
            element.focus(); element.setSelectionRange(start, start + 4);
        }""")
        patch.get_by_label("Выделите фрагмент исходника", exact=True).press("Shift+ArrowRight")
        patch.get_by_role("button", name="Привязать выделенный фрагмент", exact=True).click()
        patch.get_by_role("button", name="Применить правку", exact=True).click()
        expect(patch).not_to_be_visible()
        changed = api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")
        assert changed["revision"] == 2
        before = draft["document"]
        before["workouts"][0]["steps"][1]["seconds"]["maximum"] = 90
        start = source_text.index("100 м")
        before["workouts"][0]["steps"][1]["source_spans"] = [{"start": start, "end": start + 5}]
        assert changed["document"] == before
        expect(page.get_by_role("region", name="Структура программы")).to_contain_text(re.compile("60–90 с отдыха"))
        page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
        page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
        saved = api_get(web_stack, f"/api/swim-programs/{raw['program_id']}/versions/1")
        assert saved["document"] == changed["document"] and ai_calls == []
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)


def test_source_gap_acknowledgement_and_unresolved_resolution_are_explicit(web_stack):
    from tests.smoke._swim_import_fixtures import rich_program

    document = rich_program()
    document["source_spans"] = []
    document["workouts"][0]["steps"] = [{
        "kind": "unresolved", "id": "unclear", "instructions": "Synthetic ambiguous instruction",
        "question": "Какова дистанция?", "source_spans": [],
    }]
    draft = seeded_draft(web_stack, document)
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="неразобранные фрагменты")).to_be_visible()
    gaps = page.get_by_role("region", name="Несопоставленные фрагменты", exact=True)
    expect(gaps).to_contain_text(document["source_text"].strip())
    gaps.get_by_role("button", name="Это пояснение, а не задание", exact=True).click()
    gaps.get_by_label("Почему фрагмент не требует шага", exact=True).fill("Синтетический заголовок примера")
    gaps.get_by_role("button", name="Подтвердить пояснение", exact=True).click()
    expect(gaps).not_to_be_visible()
    acknowledged = api_get(web_stack, f"/api/swim-imports/{draft['import_id']}")
    assert acknowledged["acknowledgements"][0]["reason"] == "Синтетический заголовок примера"
    assert acknowledged["summary"]["source_gaps"] == []
    page.get_by_role("button", name="Изменить: Неразобранный элемент", exact=True).click()
    editor = page.get_by_role("region", name="Правка элемента", exact=True)
    expect(editor).to_be_focused()
    editor.get_by_label("Тип элемента", exact=True).select_option("swim")
    editor.get_by_label("Название элемента", exact=True).fill("Уточнённый отрезок")
    editor.get_by_label("Объём шага", exact=True).select_option("distance")
    editor.get_by_label("Дистанция, м", exact=True).fill("100")
    editor.get_by_role("button", name="Применить правку", exact=True).click()
    expect(editor).not_to_be_visible()
    resolved = api_get(web_stack, f"/api/swim-imports/{draft['import_id']}")
    assert resolved["document"]["workouts"][0]["steps"][0]["id"] == "unclear"
    assert resolved["summary"]["distance_meters"] == 100
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    expect(page.get_by_role("region", name="Предпросмотр сохранения")).to_be_visible()
