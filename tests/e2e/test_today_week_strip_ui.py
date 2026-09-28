"""Readable weekly plan/actual statuses and accessible day details on Today."""

import json
import os
from pathlib import Path

import pytest

from test_today_decision_story_ui import _has_horizontal_overflow

pytestmark = pytest.mark.e2e
FIXTURES = Path(__file__).parent / "fixtures" / "today_preview"


def test_today_week_strip_status_and_details(web_stack):
    page = web_stack.page
    today = json.loads((FIXTURES / "ordinary.json").read_text())
    adherence = json.loads((FIXTURES / "adherence.json").read_text())
    page.route(
        "**/api/today**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(today, ensure_ascii=False),
        ),
    )
    page.route(
        "**/api/adherence**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(adherence, ensure_ascii=False),
        ),
    )

    week = page.get_by_role("region", name="Неделя · план и факт")
    for theme in ("light", "dark"):
        page.add_init_script(f"localStorage.setItem('theme','{theme}')")
        for width in (390, 978, 1280):
            page.set_viewport_size({"width": width, "height": 1100})
            page.goto(web_stack.web_base + "/today?demo=1", wait_until="networkidle")
            week = page.get_by_role("region", name="Неделя · план и факт")
            assert week.is_visible()
            assert week.locator("p").first.inner_text().startswith(
                "Сопоставлено занятий: 0 из 4"
            )
            days = week.get_by_role("listitem")
            assert days.count() == len(adherence["days"])
            for index, item in enumerate(adherence["days"]):
                day = days.nth(index)
                assert day.get_by_text(item["date"][8:10] + "." + item["date"][5:7], exact=False).is_visible()
                assert day.get_by_text(
                    {
                        "missed": "Пропущено",
                        "unplanned": "Вне плана",
                        "rest": "Отдых",
                    }[item["status"]],
                    exact=True,
                ).first.is_visible()

            first = days.first
            detail = first.get_by_text("План и факт", exact=True)
            detail.focus()
            detail.press("Enter")
            assert first.get_by_text("Факт по плану", exact=True).is_visible()
            assert first.get_by_text("28 TSS", exact=True).is_visible()
            detail.press("Enter")
            assert not _has_horizontal_overflow(page)

            if os.environ.get("TODAY_UI_SCREENSHOTS"):
                folder = Path(os.environ["TODAY_UI_SCREENSHOTS"])
                folder.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(folder / f"week-{theme}-{width}.png"), full_page=True
                )

    today["yesterday"]["rows"] = [
        {
            "session_id": "catalog-session",
            "name": "Recovery Run",
            "tss": 20,
            "actual_total_tss": 18,
            "adherence": "exact",
        },
        {
            "session_id": "custom-session",
            "name": "Greg's river loop",
            "tss": 20,
            "actual_total_tss": 18,
            "adherence": "exact",
        },
    ]
    page.set_viewport_size({"width": 390, "height": 1100})
    page.goto(web_stack.web_base + "/today?demo=1", wait_until="networkidle")
    yesterday = page.locator("section").filter(
        has=page.get_by_role("heading", name="Вчера · план и факт")
    )
    assert yesterday.get_by_text("Восстановительный бег", exact=True).is_visible()
    assert yesterday.get_by_text("Greg's river loop", exact=True).is_visible()

    touch_context = page.context.browser.new_context(
        viewport={"width": 390, "height": 1100}, has_touch=True
    )
    touch_context.add_init_script("localStorage.setItem('theme','light'); localStorage.setItem('demo','1')")
    touch_context.route(
        "**/api/today*",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(today, ensure_ascii=False),
        ),
    )
    touch_context.route(
        "**/api/adherence**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(adherence, ensure_ascii=False),
        ),
    )
    touch_page = touch_context.new_page()
    touch_page.goto(web_stack.web_base + "/today?demo=1", wait_until="networkidle")
    first_touch_day = touch_page.get_by_role("region", name="Неделя · план и факт").get_by_role("listitem").first
    first_touch_day.get_by_text("План и факт", exact=True).tap()
    assert first_touch_day.get_by_text("Факт по плану", exact=True).is_visible()
    touch_context.close()
