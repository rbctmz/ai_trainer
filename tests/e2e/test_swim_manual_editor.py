"""Manual rich prescriptions and bounded edits use the same persisted draft."""

import re
from uuid import uuid4

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
        assert not [error for error in web_stack.js_errors if error.startswith("pageerror:") or "hydration" in error.lower()]
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
    expect(gaps).to_contain_text("Подтверждено как пояснение: Синтетический заголовок примера")
    acknowledged = api_get(web_stack, f"/api/swim-imports/{draft['import_id']}")
    assert acknowledged["acknowledgements"][0]["reason"] == "Синтетический заголовок примера"
    assert acknowledged["summary"]["source_gaps"] == draft["summary"]["source_gaps"]
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


def test_timed_group_effort_and_breath_rest_survive_bounded_form_edits(web_stack):
    from tests.smoke._swim_import_fixtures import rich_program

    draft = seeded_draft(web_stack, rich_program())
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    page.get_by_text("Timed cycle", exact=True).click()
    page.get_by_role("button", name="Изменить: Timed cycle", exact=True).click()
    editor = page.get_by_role("region", name="Правка элемента", exact=True)
    editor.get_by_label("Задать субъективное усилие", exact=True).check()
    editor.get_by_label("Усилие от, %", exact=True).fill("50")
    editor.get_by_label("Усилие до, %", exact=True).fill("90")
    editor.get_by_label("Изменение усилия", exact=True).select_option("across_repetitions")
    editor.get_by_role("button", name="Применить правку", exact=True).click()
    expect(editor).not_to_be_visible()
    page.get_by_role("button", name="Добавить шаг в группу", exact=True).click()
    add = page.get_by_role("region", name="Новый элемент", exact=True)
    add.get_by_label("Тип элемента", exact=True).select_option("rest")
    add.get_by_label("Указаны выдохи в воду", exact=True).check()
    add.get_by_label("Выдохов от", exact=True).fill("3")
    add.get_by_label("Выдохов до", exact=True).fill("4")
    add.get_by_role("button", name="Применить правку", exact=True).click()
    expect(add).not_to_be_visible()
    page.get_by_role("button", name="Изменить: Timed cycle", exact=True).click()
    editor.get_by_label("Отдых после последнего повтора", exact=True).select_option("include")
    editor.get_by_role("button", name="Применить правку", exact=True).click()
    expect(editor).not_to_be_visible()
    changed = api_get(web_stack, f"/api/swim-imports/{draft['import_id']}")
    group = changed["document"]["workouts"][0]["steps"][1]
    assert group["repeat"] == {"kind": "time", "seconds": 1800, "finish": "current_cycle"}
    assert group["effort"] == {"kind": "subjective", "start_percent": 50, "end_percent": 90, "scope": "across_repetitions"}
    assert group["steps"][:2] == draft["document"]["workouts"][0]["steps"][1]["steps"]
    assert group["steps"][-1]["breaths"] == {"minimum": 3, "maximum": 4}
    assert group["steps"][-1]["seconds"] is None and group["last_rest"] == "include"
    assert changed["summary"]["distance_meters"] is None
    assert changed["summary"]["known_distance_meters"] == 1000


def test_initial_manual_structure_pins_selected_exercise_atomically(web_stack):
    exercise = {
        "schema_version": 1, "id": str(uuid4()), "name": "Atomic synthetic technique",
        "variant": "One arm", "instructions": "Version one cue", "environments": ["pool"], "equipment": ["fins"],
    }
    preview = api_post(web_stack, "/api/swim-exercises/preview", {"document": exercise})
    saved = api_post(web_stack, "/api/swim-exercises/confirm", {**preview, "base_revision": 0, "request_id": str(uuid4()), "confirm": True})
    raw = api_post(web_stack, "/api/swim-imports", {"source_text": "Synthetic assignment 150 metres with buoy", "request_id": str(uuid4())})
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={raw['import_id']}")
    page.get_by_role("button", name="Создать структуру вручную", exact=True).click()
    form = page.get_by_role("region", name="Ручная структура", exact=True)
    form.get_by_label("Название программы", exact=True).fill("Atomic manual program")
    form.get_by_role("button", name="Привязать весь исходник", exact=True).click()
    form.get_by_role("button", name="Добавить тренировку", exact=True).click()
    workout = form.get_by_role("article", name="Ручная тренировка 1", exact=True)
    workout.get_by_label("Название тренировки", exact=True).fill("Pool assignment")
    workout.get_by_label("Длина бассейна, м", exact=True).fill("25")
    workout.get_by_role("button", name="Добавить шаг", exact=True).click()
    step = workout.get_by_role("group", name="Элемент 1", exact=True)
    step.get_by_label("Название элемента", exact=True).fill("Original assignment name")
    step.get_by_label("Объём шага", exact=True).select_option("distance")
    step.get_by_label("Дистанция, м", exact=True).fill("150")
    step.get_by_label("Колобашка", exact=True).check()
    step.get_by_label("Инструкция", exact=True).fill("Original assignment cue")
    picker = step.get_by_role("region", name="Выбор упражнения", exact=True)
    picker.get_by_label("Поиск упражнения", exact=True).fill("Atomic synthetic technique")
    picker.get_by_label("Поиск упражнения", exact=True).press("Enter")
    expect(form).to_be_visible()
    assert api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")["revision"] == 0
    picker.get_by_role("button", name="Выбрать: Atomic synthetic technique — One arm · версия 1", exact=True).click()
    new = {**saved["document"], "instructions": "Version two cue"}
    new_preview = api_post(web_stack, "/api/swim-exercises/preview", {"document": new})
    api_post(web_stack, "/api/swim-exercises/confirm", {**new_preview, "base_revision": 1, "request_id": str(uuid4()), "confirm": True})
    form.get_by_role("button", name="Записать структуру черновика", exact=True).click()
    expect(form).not_to_be_visible()
    result = api_get(web_stack, f"/api/swim-imports/{raw['import_id']}")
    binding = result["document"]["exercise_bindings"][0]
    node = result["document"]["workouts"][0]["steps"][0]
    assert binding["revision"] == 1 and binding["document"] == saved["document"]
    assert node["quantity"] == {"kind": "distance", "meters": 150}
    assert node["equipment"] == ["pull_buoy"] and node["instructions"] == "Original assignment cue"
