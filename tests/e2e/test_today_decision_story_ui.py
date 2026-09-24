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
            expand = page.get_by_role("button", name="Развернуть брифинг")
            expand.focus()
            assert expand.evaluate("element => document.activeElement === element")
            page.keyboard.press("Enter")
            assert page.get_by_role("heading", name="Следующее действие").is_visible()
            assert not _has_horizontal_overflow(page), f"overflow compact/full при {width}px"

            pending = {
                "id": 42,
                "date": payload["date"],
                "action": "recovery_replan",
                "status": "pending",
                "params": {},
                "preview": {},
            }
            blocked = deepcopy(conflict)
            blocked["state"] = "conflict_actionable"
            blocked["pending_proposal"] = pending
            current["value"] = blocked
            page.reload(wait_until="domcontentloaded")
            page.get_by_role("heading", name="Следующее действие").wait_for(timeout=60_000)
            assert page.get_by_text(
                "Проверьте отмеченное самочувствие перед решением по сессии.",
                exact=True,
            ).is_visible()
            assert page.get_by_text(
                "Изменение попадёт в активный план только после подтверждения."
            ).count() == 0

            allowed = deepcopy(payload)
            allowed["state"] = "conflict_actionable"
            allowed["pending_proposal"] = pending
            allowed["decision_story"]["next_action"].update(
                kind="review_proposal",
                summary="Рассмотрите предложение по корректировке.",
                enabled=True,
            )
            current["value"] = allowed
            page.reload(wait_until="domcontentloaded")
            approval_notice = page.get_by_text(
                "Изменение попадёт в активный план только после подтверждения."
            )
            approval_notice.wait_for(timeout=60_000)
            assert approval_notice.is_visible()
            assert not _has_horizontal_overflow(page), f"overflow proposal при {width}px"
            current["value"] = conflict

        assert not web_stack.js_errors, "Ошибки браузера:\n" + "\n".join(web_stack.js_errors)
    except Exception:
        web_stack.capture_failure()
        raise
    finally:
        page.unroute("**/api/today?demo=1", serve_today)


def test_today_loading_empty_error_and_stale_states_are_accessible(web_stack) -> None:
    page = web_stack.page
    url = f"{web_stack.web_base}/today"
    page.set_viewport_size({"width": 390, "height": 900})
    page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
    failed_responses: list[tuple[int, str, str, str]] = []
    page.on(
        "response",
        lambda response: failed_responses.append(
            (
                response.status,
                response.url,
                response.request.resource_type,
                response.request.headers.get("referer", ""),
            )
        )
        if response.status >= 400
        else None,
    )
    initial_console_errors = len(web_stack.js_errors)
    page.add_init_script(
        """(() => {
          const shouldDelay = window.sessionStorage.getItem('delay-today-once') !== 'done';
          window.sessionStorage.setItem('delay-today-once', 'done');
          const original = window.fetch.bind(window);
          window.__todayOriginalFetch = original;
          window.__todayFetchStarted = false;
          window.fetch = async (...args) => {
            const requestUrl = typeof args[0] === 'string' ? args[0] : args[0].url;
            if (shouldDelay && requestUrl.includes('/api/today')) {
              window.__todayFetchStarted = true;
              await new Promise(resolve => { window.__releaseTodayFetch = resolve; });
            }
            return original(...args);
          };
        })();"""
    )
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.__todayFetchStarted === true")
    loading = page.get_by_role("status", name="Загрузка страницы Сегодня")
    assert loading.is_visible()
    page.evaluate("window.__releaseTodayFetch()")
    page.get_by_role("heading", name="Следующее действие").wait_for(timeout=60_000)
    assert not _has_horizontal_overflow(page)

    def fail_today(route) -> None:
        route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "temporary failure"}),
        )

    page.route("**/api/today?demo=1", fail_today)
    page.reload(wait_until="domcontentloaded")
    error = page.get_by_role("alert").filter(has_text="Не удалось загрузить «Сегодня».")
    error.wait_for(timeout=60_000)
    assert error.is_visible()
    assert not _has_horizontal_overflow(page)
    page.unroute("**/api/today?demo=1", fail_today)

    payload = _today_payload(web_stack.api_base)
    empty = deepcopy(payload)
    empty["state"] = "no_plan"

    def serve_empty(route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(empty, ensure_ascii=False),
        )

    page.route("**/api/today?demo=1", serve_empty)
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("heading", name="Следующее действие").wait_for(timeout=60_000)
    page.get_by_text(
        "Построй план — и этот экран каждое утро будет отвечать на вопрос",
        exact=False,
    ).wait_for()
    planning_link = page.get_by_role("link", name="Открыть планирование")
    assert planning_link.is_visible()
    assert planning_link.get_attribute("href") == "/planning"
    assert not _has_horizontal_overflow(page)

    empty.pop("decision_story")
    page.reload(wait_until="domcontentloaded")
    unavailable = page.get_by_role("alert").filter(has_text="История решения недоступна.")
    unavailable.wait_for(timeout=60_000)
    assert unavailable.is_visible()
    assert not _has_horizontal_overflow(page)
    page.unroute("**/api/today?demo=1", serve_empty)

    stale = deepcopy(payload)
    stale["state"] = "silence"
    stale["briefing"] = {"frequency": "conflicts_only", "is_quiet_day": True}
    stale["decision_story"]["next_action"].update(
        kind="follow_plan", summary="Следуйте текущему плану."
    )
    readiness_evidence = next(
        item for item in stale["decision_story"]["evidence"] if item.get("kind") == "readiness"
    )
    readiness_evidence.update(freshness="stale", observation_date="2026-09-23")

    def serve_stale(route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(stale, ensure_ascii=False),
        )

    page.route("**/api/today?demo=1", serve_stale)
    for width in (390, 1280):
        page.set_viewport_size({"width": width, "height": 900})
        page.reload(wait_until="domcontentloaded")
        expand = page.get_by_role("button", name="Развернуть брифинг")
        expand.wait_for(timeout=60_000)
        expand.focus()
        page.keyboard.press("Enter")
        story = page.get_by_role("region", name="Следующее действие")
        evidence = story.get_by_text("Доказательства и версии правил")
        evidence.focus()
        page.keyboard.press("Enter")
        story.get_by_text("свежесть: устарело", exact=False).wait_for()
        assert not _has_horizontal_overflow(page), f"overflow stale state при {width}px"
    new_console_errors = web_stack.js_errors[initial_console_errors:]
    expected_http_error = [
        error for error in new_console_errors
        if "server responded with a status of 503" in error
    ]
    unexpected_console_errors = [error for error in new_console_errors if error not in expected_http_error]
    assert len(expected_http_error) == 1, "Ожидался один контролируемый HTTP 503"
    assert [item[:3] for item in failed_responses] == [
        (503, f"{web_stack.web_base}/api/today?demo=1", "fetch")
    ], f"Неожиданные неуспешные ответы: {failed_responses}"
    assert not unexpected_console_errors, (
        "Ошибки браузера:\n" + "\n".join(unexpected_console_errors)
        + f"\nHTTP responses: {failed_responses}"
    )
    page.unroute("**/api/today?demo=1", serve_stale)
    page.unroute("**/favicon.ico")
