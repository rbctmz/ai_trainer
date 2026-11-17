"""Versioned technique selection never changes a retained prescription dose."""

import re
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect

from tests.e2e.test_swim_import_ui import seeded_draft
from tests.e2e.test_swim_coach_journey import api_get
from tests.smoke._swim_import_fixtures import rich_program

pytestmark = pytest.mark.e2e


def test_catalog_confirm_pin_version_and_reopen_after_catalog_revision(web_stack):
    page = web_stack.page
    page.goto(web_stack.web_base + "/coach/swim")
    page.get_by_role("link", name="Справочник упражнений", exact=True).click()
    page.get_by_role("button", name="Новое упражнение", exact=True).click()
    form = page.get_by_role("region", name="Определение упражнения", exact=True)
    form.get_by_label("Название упражнения", exact=True).fill("Синтетическая техника")
    form.get_by_label("Вариант", exact=True).fill("Правая рука")
    form.get_by_label("Инструкция техники", exact=True).fill("Исходная синтетическая инструкция")
    form.get_by_label("Бассейн", exact=True).check()
    form.get_by_label("Ласты", exact=True).check()
    form.get_by_role("button", name="Предпросмотр упражнения", exact=True).click()
    preview = page.get_by_role("region", name="Предпросмотр упражнения", exact=True)
    expect(preview).to_contain_text("Исходная синтетическая инструкция")
    preview.get_by_role("button", name="Подтвердить сохранение упражнения", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Упражнение · сохранённая версия 1")).to_be_visible()
    exercise_id = parse_qs(urlparse(page.url).query)["exercise"][0]
    original = api_get(web_stack, f"/api/swim-exercises/{exercise_id}/versions/1")
    draft = seeded_draft(web_stack, rich_program())
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    page.get_by_role("button", name="Изменить: Synthetic swim", exact=True).click()
    editor = page.get_by_role("region", name="Правка элемента", exact=True)
    editor.get_by_label("Действие с элементом", exact=True).select_option("binding")
    picker = editor.get_by_role("region", name="Выбор упражнения", exact=True)
    picker.get_by_label("Поиск упражнения", exact=True).fill("Синтетическая техника")
    picker.get_by_role("button", name="Найти упражнения", exact=True).click()
    picker.get_by_role("button", name="Выбрать: Синтетическая техника — Правая рука · версия 1", exact=True).click()
    editor.get_by_role("button", name="Применить правку", exact=True).click()
    expect(editor).not_to_be_visible()
    linked = api_get(web_stack, f"/api/swim-imports/{draft['import_id']}")
    assert linked["document"]["workouts"] == draft["document"]["workouts"]
    assert linked["document"]["exercise_bindings"][0]["document"] == original["document"]
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
    program_url = page.url
    page.goto(web_stack.web_base + f"/coach/swim?catalog=1&exercise={exercise_id}&exercise_revision=1")
    page.get_by_role("button", name="Создать новую версию упражнения", exact=True).click()
    form = page.get_by_role("region", name="Определение упражнения", exact=True)
    form.get_by_label("Инструкция техники", exact=True).fill("Изменённая синтетическая инструкция")
    form.get_by_role("button", name="Предпросмотр упражнения", exact=True).click()
    page.get_by_role("button", name="Подтвердить сохранение упражнения", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Упражнение · сохранённая версия 2")).to_be_visible()
    page.goto(program_url)
    page.get_by_text(re.compile(r"Техника: Синтетическая техника.*версия 1")).click()
    expect(page.get_by_text("Исходная синтетическая инструкция", exact=True)).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("Изменённая синтетическая инструкция")
    saved = api_get(web_stack, f"/api/swim-programs/{draft['program_id']}/versions/1")
    assert saved["document"] == linked["document"]
