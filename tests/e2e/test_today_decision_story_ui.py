"""Frozen-evidence browser acceptance for #610's Today decision story."""

from __future__ import annotations

from copy import deepcopy
import json
from urllib.request import urlopen

import pytest


pytestmark = pytest.mark.e2e


def _today_payload(api_base: str) -> dict:
    with urlopen(f"{api_base}/api/today?demo=1", timeout=60) as response:
        payload = json.load(response)
    assert payload["decision_story"]["schema_version"] == "today_decision_story_v1"
    payload["state"] = "silence"
    payload["briefing"] = {"frequency": "conflicts_only", "is_quiet_day": True}
    return payload


def _has_horizontal_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth > window.innerWidth")


def test_today_story_owns_compact_and_full_action_at_mobile_and_desktop(web_stack) -> None:
    page = web_stack.page
    payload = _today_payload(web_stack.api_base)
    conflict = deepcopy(payload)
    conflict["decision_story"]["interpretation"].update(
        status="conflicting_evidence",
        summary="Свежая самооценка травмы требует внимания.",
    )
    conflict["decision_story"]["recommendation"].update(
        kind="non_prescriptive_review",
        summary="Проверьте противоречивые данные.",
    )
    conflict["decision_story"]["next_action"].update(
        kind="inspect_evidence",
        summary="Проверьте отмеченное самочувствие перед решением по сессии.",
    )
    conflict["decision_story"]["evidence"] = [
        {
            "kind": "subjective_wellness",
            "key": "injury",
            "source": "intervals",
            "ref": "intervals_subjective_v1",
            "value_label": "Дискомфорт",
            "observation_date": conflict["date"],
            "freshness": "current",
        }
    ]
    conflict["subjective_wellness"] = {
        "status": "current",
        "source": "intervals",
        "date": conflict["date"],
        "age_days": 0,
        "provider_updated_at": None,
        "received_at": None,
        "mapping_version": "intervals_subjective_v1",
        "answered_current_keys": ["injury"],
        "items": [
            {
                "key": "injury",
                "label": "Самооценка травмы",
                "value": 2,
                "state": "present",
                "value_label": "Дискомфорт",
            }
        ],
    }

    current = {"value": conflict}

    def serve_today(route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(current["value"], ensure_ascii=False),
        )

    page.route("**/api/today?demo=1", serve_today)
    try:
        for width in (390, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(f"{web_stack.web_base}/today", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Следующее действие").wait_for(timeout=60_000)
            assert page.get_by_text(
                "Проверьте отмеченное самочувствие перед решением по сессии.",
                exact=True,
            ).is_visible()
            assert page.get_by_text("План в силе", exact=True).count() == 0
            assert page.get_by_role("button", name="Развернуть брифинг").count() == 0
            wellness = page.get_by_role("region", name="Самочувствие из Intervals.icu")
            assert wellness.get_by_text("Дискомфорт", exact=True).is_visible()
            story = page.get_by_role("region", name="Следующее действие")
            assert story.get_by_text("Факт: нет подтверждённых данных").is_visible()
            assert story.get_by_text("Выполнение: данных о выполнении нет").is_visible()
            assert story.get_by_text("not_observed").count() == 0
            assert not _has_horizontal_overflow(page), f"горизонтальный overflow при {width}px"

            evidence_summary = page.get_by_text("Доказательства и версии правил")
            evidence_summary.focus()
            page.keyboard.press("Enter")
            assert story.get_by_text("Самооценка травмы", exact=True).is_visible()
            assert story.get_by_text("Дискомфорт", exact=True).is_visible()
            assert not _has_horizontal_overflow(page), f"overflow после раскрытия при {width}px"

            quiet = deepcopy(payload)
            quiet["decision_story"]["next_action"].update(
                kind="follow_plan",
                summary="Следуйте текущему плану с учётом доступных данных.",
            )
            current["value"] = quiet
            page.reload(wait_until="domcontentloaded")
            page.get_by_role(
                "heading", name="Следуйте текущему плану с учётом доступных данных."
            ).wait_for(timeout=60_000)
            assert page.get_by_role("button", name="Развернуть брифинг").is_visible()
            page.get_by_role("button", name="Развернуть брифинг").click()
            assert page.get_by_role("heading", name="Следующее действие").is_visible()
            assert not _has_horizontal_overflow(page), f"overflow compact/full при {width}px"
            current["value"] = conflict

        assert not web_stack.js_errors, "Ошибки браузера:\n" + "\n".join(web_stack.js_errors)
    except Exception:
        web_stack.capture_failure()
        raise
    finally:
        page.unroute("**/api/today?demo=1", serve_today)
