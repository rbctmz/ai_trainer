"""Visible state first, no lost wellness values, honest freshness in Today pilot."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest
from test_today_decision_story_ui import _has_horizontal_overflow

pytestmark = pytest.mark.e2e


def test_today_visual_state_and_wellness(web_stack):
    page = web_stack.page
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures" / "today_preview" / "ordinary.json"
        ).read_text()
    )
    current = {"payload": payload}

    def serve(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(current["payload"], ensure_ascii=False),
        )

    page.route("**/api/today?demo=1", serve)
    page.add_init_script("localStorage.setItem('theme','dark')")
    try:
        for theme in ("dark", "light"):
            page.add_init_script(f"localStorage.setItem('theme','{theme}')")
            for width in (390, 1280):
                current["payload"] = deepcopy(payload)
                page.set_viewport_size({"width": width, "height": 1100})
                page.goto(web_stack.web_base + "/today", wait_until="networkidle")
                meter = page.get_by_role("meter", name="Восстановление")
                assert meter.count() == 1
                state = page.get_by_role("region", name="Состояние сегодня", exact=True)
                assert state.get_by_role("meter").count() == 1
                assert state.get_by_role("region", name="Самочувствие из Intervals.icu").count() == 1
                assert state.bounding_box()["y"] < page.get_by_role("region", name="Сводка на сегодня").bounding_box()["y"]
                if width == 390:
                    assert (
                        meter.bounding_box()["y"]
                        < page.get_by_text(
                            "Восстановительный бег", exact=True
                        ).bounding_box()["y"]
                    )
                wellness = page.get_by_role(
                    "region", name="Самочувствие из Intervals.icu"
                )
                for item in payload["subjective_wellness"]["items"]:
                    assert wellness.get_by_text(item["label"], exact=True).is_visible()
                assert wellness.get_by_text("Плохое", exact=True).is_visible()
                assert not _has_horizontal_overflow(page)
                summary = page.get_by_text("Подробнее о состоянии", exact=True)
                summary.focus() if hasattr(summary, "focus") else None
                summary.press("Enter")
                assert page.get_by_role(
                    "heading", name="Показатели восстановления", exact=True
                ).is_visible()
                summary.press("Enter")
                if os.environ.get("TODAY_UI_SCREENSHOTS"):
                    folder = Path(os.environ["TODAY_UI_SCREENSHOTS"])
                    folder.mkdir(parents=True, exist_ok=True)
                    page.screenshot(
                        path=str(folder / f"pilot-{theme}-{width}.png"), full_page=True
                    )
        current["payload"] = deepcopy(payload)
        current["payload"]["subjective_wellness"].update(status="stale", age_days=2)
        page.reload(wait_until="networkidle")
        assert page.get_by_text(
            "Прошлая запись — за сегодня ответов нет", exact=False
        ).is_visible()
        assert (
            page.get_by_role("region", name="Самочувствие из Intervals.icu")
            .get_by_text("Плохое", exact=True)
            .is_visible()
        )
        current["payload"]["readiness"] = None
        page.reload(wait_until="networkidle")
        assert page.get_by_role("meter", name="Восстановление").count() == 0
        assert page.get_by_text("Нет оценки", exact=True).is_visible()
        assert not web_stack.js_errors
    finally:
        page.unroute("**/api/today?demo=1", serve)
