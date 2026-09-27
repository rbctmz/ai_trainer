"""Session-bound completion, actionable feedback, and honest partial/unknown states."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from test_today_decision_story_ui import _has_horizontal_overflow

pytestmark = pytest.mark.e2e
FIXTURES = Path(__file__).parent / "fixtures" / "today_preview"


def test_today_completion_by_session(web_stack):
    page = web_stack.page
    projections = json.loads((FIXTURES / "projections.json").read_text())
    current = {"payload": None, "error": False}
    page.route(
        "**/api/today?demo=1",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(current["payload"]),
        ),
    )

    def serve_projection(route):
        sid = route.request.url.split("/")[-1].split("?")[0]
        route.fulfill(
            status=503 if current["error"] else 200,
            content_type="application/json",
            body=json.dumps(projections[sid]),
        )

    page.route("**/api/planning/session-projection/*", serve_projection)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    for scenario in ("completed", "two-completed", "partial-brick"):
        current["payload"] = json.loads((FIXTURES / f"{scenario}.json").read_text())
        for theme, width in (("dark", 1280), ("light", 390)):
            page.add_init_script(f"localStorage.setItem('theme','{theme}')")
            page.set_viewport_size({"width": width, "height": 1100})
            page.goto(web_stack.web_base + "/today", wait_until="networkidle")
            result = page.get_by_role("region", name="Выполнение тренировки")
            if scenario == "completed":
                assert result.count() == 1
                plan = page.get_by_text("Показать план тренировки", exact=True)
                assert plan.is_visible()
                assert not page.get_by_role("img", name="Разминка · 5 мин", exact=False).is_visible()
                assert result.get_by_text("✓ Выполнено", exact=True).is_visible()
                assert result.get_by_text("32 мин", exact=True).is_visible()
                assert result.get_by_text("30 мин", exact=True).is_visible()
                action = result.get_by_text("Оценить тренировку", exact=True)
                action.press("Enter")
                assert result.get_by_role(
                    "heading", name="Оцени тренировку сейчас"
                ).is_visible()
                assert (
                    result.bounding_box()["y"]
                    < page.get_by_role(
                        "heading", name="Вчера · план и факт"
                    ).bounding_box()["y"]
                )
                action.press("Enter")
            elif scenario == "two-completed":
                assert result.count() == 2
                assert (
                    page.locator('[data-session-result="demo-first"]')
                    .get_by_text("✓ Выполнено", exact=True)
                    .is_visible()
                )
                assert (
                    page.locator('[data-session-result="demo-second"]')
                    .get_by_text("Выполнение пока не найдено", exact=True)
                    .is_visible()
                )
            else:
                assert result.count() == 1
                assert result.get_by_text(
                    "◐ Выполнено частично", exact=True
                ).is_visible()
                assert result.get_by_text(
                    "Этап 1: есть запись выполнения", exact=True
                ).is_visible()
                assert result.get_by_text(
                    "Этап 2: запись выполнения не найдена", exact=True
                ).is_visible()
            assert not _has_horizontal_overflow(page)
            if os.environ.get("TODAY_UI_SCREENSHOTS"):
                folder = Path(os.environ["TODAY_UI_SCREENSHOTS"])
                folder.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(folder / f"{scenario}-{width}.png"), full_page=True
                )
    current["payload"] = json.loads((FIXTURES / "two-completed.json").read_text())
    current["payload"]["briefing"] = {
        "frequency": "conflicts_only",
        "is_quiet_day": True,
    }
    page.reload(wait_until="networkidle")
    assert page.get_by_role(
        "button", name="Показать тренировку и показатели"
    ).is_visible()
    assert page.get_by_role("region", name="Выполнение тренировки").count() == 2
    assert (
        page.locator('[data-session-result="demo-first"]')
        .get_by_text("✓ Выполнено", exact=True)
        .is_visible()
    )
    current["payload"] = json.loads((FIXTURES / "completed.json").read_text())
    current["payload"]["feedback"]["prompts"] = []
    current["payload"]["feedback"]["primary"] = None
    ambiguous = deepcopy(projections["demo-done"])
    ambiguous["projection_status"] = "needs_confirmation"
    ambiguous["fact"]["completion_status"] = "needs_confirmation"
    projections["demo-done"] = ambiguous
    page.reload(wait_until="networkidle")
    assert page.get_by_text("Нужно уточнить выполнение", exact=True).is_visible()
    assert page.get_by_role("link", name="Уточнить в плане").is_visible()
    assert not page.get_by_text("✓ Выполнено", exact=True).count()
    current["error"] = True
    page.reload(wait_until="networkidle")
    assert page.get_by_text(
        "Не удалось проверить выполнение.", exact=False
    ).is_visible()
    assert page.get_by_role("button", name="Повторить", exact=True).is_visible()
    current["payload"] = json.loads((FIXTURES / "completed.json").read_text())
    page.reload(wait_until="networkidle")
    assert page.get_by_text("Оценить тренировку", exact=True).is_visible()
    assert not errors
