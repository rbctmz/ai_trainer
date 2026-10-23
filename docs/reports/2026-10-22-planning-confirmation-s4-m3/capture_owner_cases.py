"""Синтетические экраны S4 для приёмки владельцем, без личной SQLite."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect

from tests.e2e.conftest import web_stack
from tests.e2e.test_planning_confirmation_s4_ui import candidate

ARTIFACTS = Path(__file__).parent


def capture(page, name: str, *, uncertain: bool = False) -> None:
    """Снимок реального DOM от заголовка мастера до действий сохранения."""
    page.set_viewport_size({"width": 1280, "height": 2200})
    page.evaluate("document.documentElement.classList.remove('dark'); document.documentElement.dataset.theme='light'; window.scrollTo(0,0)")
    title = page.get_by_role("heading", name="Настройка плана — шаг 4: Подтверждение", exact=True)
    summary = page.get_by_role("region", name="Резюме плана", exact=True)
    action = page.locator("section").filter(has=page.get_by_role("button", name="Повторить проверку" if uncertain else "Подтвердить и сохранить", exact=True)).last
    if not uncertain:  # Only a wizard step transition moves focus to its title.
        expect(title).to_be_focused()
    expect(page.get_by_role("navigation", name="Шаги настройки плана").get_by_role("button").nth(3)).to_have_attribute("aria-current", "step")
    assert action.count() == 1
    heading_box, summary_box, action_box = title.bounding_box(), summary.bounding_box(), action.bounding_box()
    assert heading_box and summary_box and action_box
    top = max(0, heading_box["y"] - 24)
    page.screenshot(path=str(ARTIFACTS / f"owner-{name}.png"), animations="disabled", clip={
        "x": max(0, summary_box["x"] - 8), "y": top,
        "width": summary_box["width"] + 16,
        "height": action_box["y"] + action_box["height"] + 8 - top,
    })


def facts(result: dict) -> dict:
    return {"lifecycle": result["lifecycle"], "totals": result["totals"],
            "available_hours": result["parameters"]["available_hours"],
            "target_weekly_tss": result["weekly_target"]["target_weekly_tss"]}


def main() -> None:
    fixture = web_stack.__wrapped__()
    stack = next(fixture)
    recorded = {}
    http_errors = []
    stack.page.on("response", lambda response: http_errors.append({"path": urlsplit(response.url).path, "status": response.status}) if response.status >= 400 else None)
    try:
        page, db, result = candidate(stack)
        recorded["A"] = facts(result)
        capture(page, "a")
        assert db.get_current_planning_checkpoint() is None
        page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
        expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()
        page.get_by_role("button", name="Открыть план в Обзоре", exact=True).click()
        before = db.get_current_planning_checkpoint()["id"]
        page.get_by_role("button", name="Изменить план", exact=True).click()
        page.get_by_role("combobox").nth(2).select_option("4")
        page.get_by_role("button", name="Далее", exact=True).click()
        page.get_by_role("button", name="Далее", exact=True).click()
        with page.expect_response("**/api/planning/build?*") as response:
            page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
        assert response.value.status == 200, response.value.text()
        result = response.value.json()
        page.get_by_role("button", name="Далее", exact=True).click()
        recorded["B"] = facts(result)
        capture(page, "b")
        page.get_by_role("button", name="Отменить", exact=True).click()
        assert db.get_current_planning_checkpoint()["id"] == before

        page, db, result = candidate(stack, replace=True)
        recorded["C"] = facts(result)
        assert result["lifecycle"]["closes_cycle_id"]
        before = db.get_current_planning_checkpoint()["id"]
        capture(page, "c")
        page.get_by_role("button", name="Отменить", exact=True).click()
        assert db.get_current_planning_checkpoint()["id"] == before

        page, db, result = candidate(stack)
        recorded["D"] = {"transport_simulation": "commit succeeds; response aborted before browser receipt"}
        sent = []

        def lose(route):
            sent.append(route.request.post_data_json)
            assert route.fetch().status == 200
            route.abort("failed")

        page.route("**/api/planning/build/confirm*", lose)
        page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен")).to_be_visible()
        expect(page.get_by_role("button", name="Отменить", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="Назад", exact=True)).to_be_disabled()
        capture(page, "d", uncertain=True)
        page.unroute("**/api/planning/build/confirm*", lose)
        with page.expect_response("**/api/planning/build/confirm*") as retry:
            page.get_by_role("button", name="Повторить проверку", exact=True).click()
        receipt = retry.value.json()
        assert receipt["confirmation"]["replayed"] is True
        assert receipt["confirmation"]["preview_id"] == sent[0]["preview_id"]
        assert set(sent[0]) == {"preview_id", "confirm"}
        expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()
        recorded["D"].update(replayed=True, same_identity=True, identity_only=True)
        # Disabled provider event discovery and the explicit response loss emit
        # network console errors; neither is an unhandled JavaScript exception.
        assert all(item == {"path": "/api/planning/events", "status": 503} for item in http_errors), http_errors
        expected_console = {
            "console[error]: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
            "console[error]: Failed to load resource: net::ERR_FAILED",
        }
        assert all(message in expected_console for message in stack.js_errors), stack.js_errors
        recorded["diagnostics"] = {"http_errors": http_errors, "console_errors": stack.js_errors, "unhandled_js_errors": 0}
        (ARTIFACTS / "case-oracle.json").write_text(json.dumps(recorded, ensure_ascii=False, indent=2) + "\n")
        print("4 real-DOM owner cases captured; temporary commits/cancels/retry checked; no unhandled JS errors; provider/transport diagnostics classified")
    finally:
        fixture.close()


if __name__ == "__main__":
    main()
