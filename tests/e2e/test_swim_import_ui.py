"""Swimming workspace acceptance against an owned API/DB, no paid AI calls."""

import re
import json
import urllib.request
from uuid import uuid4
import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

SOURCE = "  🏊 Synthetic trainer source\n100 metres easy\nRest 60–70 seconds\n"


def api_post(web_stack, path, payload):
    request = urllib.request.Request(
        web_stack.api_base + path + ("&" if "?" in path else "?") + "demo=1",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def seeded_draft(web_stack, document, references=None):
    source = api_post(
        web_stack,
        "/api/swim-imports",
        {"source_text": document["source_text"], "request_id": str(uuid4())},
    )
    content = {key: document[key] for key in ("title", "source_spans", "workouts")}
    content["exercise_references"] = references or []
    return api_post(
        web_stack,
        f"/api/swim-imports/{source['import_id']}/parse",
        {"expected_revision": 0, "request_id": str(uuid4()), "content": content},
    )


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
        expect(
            page.get_by_role("heading", name="Программы плавания", exact=True)
        ).to_be_visible()
        page.get_by_label("Текст тренера", exact=True).fill(SOURCE)
        with page.expect_response(re.compile(r"/api/swim-imports(?:\?|$)")) as response:
            page.get_by_role("button", name="Сохранить исходник", exact=True).click()
        assert response.value.status == 200, response.value.text()
        captured = response.value.json()
        assert captured["source_text"] == SOURCE and captured["revision"] == 0
        expect(page).to_have_url(
            re.compile(r"/coach/swim\?draft=" + captured["import_id"])
        )
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(SOURCE)
        page.reload()
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(SOURCE)
        expect(
            page.get_by_role("button", name="Разобрать с Коучем", exact=True)
        ).to_be_visible()
        expect(
            page.get_by_role("button", name="Создать структуру вручную", exact=True)
        ).to_be_visible()
        assert calls == []
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)


def test_program_summary_shows_all_workouts_from_server(web_stack):
    from tests.smoke._swim_import_fixtures import exact_program_v2

    document = exact_program_v2()
    draft = seeded_draft(web_stack, document)
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    summary = page.get_by_role("region", name="Объём программы", exact=True)
    expect(summary).to_contain_text(re.compile(r"6\s?100\s?м"))
    structure = page.get_by_role("region", name="Структура программы", exact=True)
    expect(structure.get_by_role("article")).to_have_count(3)
    for workout, metres in zip(document["workouts"], [2200, 2000, 1900]):
        card = structure.get_by_role("article", name=workout["title"], exact=True)
        expect(card).to_be_visible()
        expect(card).to_contain_text(
            re.compile(str(metres)[0] + r"\s?" + str(metres)[1:] + r"\s?м")
        )
        expect(card).to_contain_text("Бассейн")
    expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(
        document["source_text"]
    )


def test_unknown_time_cycle_is_displayed_without_invented_metres(web_stack):
    from tests.smoke._swim_import_fixtures import rich_program

    draft = seeded_draft(web_stack, rich_program())
    assert draft["summary"]["distance_meters"] is None
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    summary = page.get_by_role("region", name="Объём программы", exact=True)
    expect(summary).to_contain_text("Полная дистанция неизвестна")
    expect(summary).to_contain_text(re.compile(r"1\s?000\s?м"))
    page.get_by_text("Timed cycle", exact=True).click()
    expect(page.get_by_text("Закончить текущий цикл", exact=True)).to_be_visible()
    expect(page.get_by_role("region", name="Структура программы")).to_contain_text(
        "175 м"
    )
    expect(page.get_by_role("region", name="Структура программы")).to_contain_text(
        "25 м"
    )


def test_lost_confirm_response_retries_exact_preview_once(web_stack):
    from tests.smoke._swim_import_fixtures import exact_program_v2

    draft = seeded_draft(web_stack, exact_program_v2())
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    expect(page.get_by_role("region", name="Предпросмотр сохранения")).to_be_visible()
    attempts = []

    def lose_first_response(route):
        attempts.append(route.request.post_data_json)
        response = route.fetch()
        assert response.status == 200
        if len(attempts) == 1:
            route.abort()
        else:
            route.fulfill(response=response)

    page.route("**/api/swim-programs/confirm*", lose_first_response)
    try:
        page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Результат сохранения")).to_be_visible()
        expect(page.get_by_role("region", name="Предпросмотр сохранения")).to_be_visible()
        page.get_by_role("button", name="Повторить подтверждение", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Сохранённая версия 1")).to_be_visible()
        assert attempts[0] == attempts[1]
        with urllib.request.urlopen(web_stack.api_base + f"/api/swim-programs/{draft['program_id']}?demo=1", timeout=30) as response:
            assert json.loads(response.read())["revision"] == 1
    finally:
        page.unroute("**/api/swim-programs/confirm*", lose_first_response)


def test_concurrent_draft_change_rejects_preview_and_preserves_source(web_stack):
    from tests.smoke._swim_import_fixtures import exact_program_v2

    draft = seeded_draft(web_stack, exact_program_v2())
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    page.get_by_role("button", name="Подготовить предпросмотр", exact=True).click()
    expect(page.get_by_role("region", name="Предпросмотр сохранения")).to_be_visible()
    api_post(web_stack, f"/api/swim-imports/{draft['import_id']}/patch", {
        "expected_revision": 1, "request_id": str(uuid4()),
        "operation": {"op": "set_title", "title": "Concurrent human correction"},
    })
    page.get_by_role("button", name="Подтвердить сохранение программы", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Черновик изменился")).to_be_visible()
    page.get_by_role("button", name="Вернуться к черновику", exact=True).click()
    page.get_by_role("button", name="Обновить черновик", exact=True).click()
    expect(page.get_by_role("heading", name="Concurrent human correction", exact=True)).to_be_visible()
    expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(draft["source_text"])
    with pytest.raises(urllib.error.HTTPError) as failed:
        urllib.request.urlopen(web_stack.api_base + f"/api/swim-programs/{draft['program_id']}?demo=1", timeout=30)
    assert failed.value.code == 404


def test_missing_native_provider_keeps_source_and_manual_action(web_stack):
    from tests.smoke._swim_import_fixtures import exact_program_v2

    raw = api_post(web_stack, "/api/swim-imports", {
        "source_text": exact_program_v2()["source_text"], "request_id": str(uuid4()),
    })
    page = web_stack.page
    page.goto(web_stack.web_base + f"/coach/swim?draft={raw['import_id']}")
    page.get_by_role("button", name="Разобрать с Коучем", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="структуру")).to_be_visible()
    expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(raw["source_text"])
    expect(page.get_by_role("button", name="Создать структуру вручную", exact=True)).to_be_enabled()


def test_lost_capture_response_recovers_input_and_replays_same_source(web_stack):
    page = web_stack.page
    page.goto(web_stack.web_base + "/coach/swim")
    page.get_by_label("Текст тренера", exact=True).fill(SOURCE)
    attempts, retained = [], []

    def lose_once(route):
        if route.request.method != "POST":
            route.continue_()
            return
        attempts.append(route.request.post_data_json)
        response = route.fetch()
        retained.append(response.json()["import_id"])
        if len(attempts) == 1:
            route.abort()
        else:
            route.fulfill(response=response)

    page.route(re.compile(r".*/api/swim-imports(?:\?.*)?$"), lose_once)
    try:
        page.get_by_role("button", name="Сохранить исходник", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Не удалось получить подтверждение")).to_be_visible()
        page.reload()
        expect(page.get_by_label("Текст тренера", exact=True)).to_have_value(SOURCE)
        page.get_by_role("button", name="Сохранить исходник", exact=True).click()
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(SOURCE)
        assert attempts[0] == attempts[1] and retained[0] == retained[1]
        expect(page).to_have_url(re.compile(retained[0]))
    finally:
        page.unroute(re.compile(r".*/api/swim-imports(?:\?.*)?$"), lose_once)


def test_legacy_v1_saved_program_is_readable_without_ai_or_conversion(web_stack):
    from tests.smoke._swim_program_fixtures import example_program

    document = example_program()
    preview = api_post(web_stack, "/api/swim-programs/preview", {"document": document, "base_revision": 0})
    saved = api_post(web_stack, "/api/swim-programs/confirm", {"preview_id": preview["preview_id"], "confirm": True})
    assert saved["document"]["schema_version"] == 1
    page = web_stack.page
    ai_calls = []

    def forbid_ai(route):
        ai_calls.append(route.request.url)
        route.abort()

    page.route("**/api/coach/swim-import*", forbid_ai)
    try:
        page.goto(web_stack.web_base + f"/coach/swim?program={saved['program_id']}&revision=1")
        expect(page.get_by_role("region", name="Объём программы")).to_contain_text(re.compile(r"6\s?100\s?м"))
        expect(page.get_by_label("Исходный текст", exact=True)).to_have_value(document["source_text"])
        expect(page.get_by_role("region", name="Структура программы").get_by_role("article")).to_have_count(3)
        assert ai_calls == []
    finally:
        page.unroute("**/api/coach/swim-import*", forbid_ai)
