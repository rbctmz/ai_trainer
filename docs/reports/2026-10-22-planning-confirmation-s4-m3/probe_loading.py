"""S4-11: видимые loading/error и повторная сборка без нового назначения."""
from __future__ import annotations

from playwright.sync_api import expect

from tests.e2e.conftest import web_stack
from tests.e2e.test_planning_confirmation_s4_ui import candidate


def main() -> None:
    fixture = web_stack.__wrapped__()
    stack = next(fixture)
    try:
        page, db, _ = candidate(stack)
        page.get_by_role("button", name="Назад", exact=True).click()
        page.get_by_role("button").filter(has=page.get_by_text("×0.90", exact=True)).click()
        expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
        held = []
        page.route("**/api/planning/build?*", lambda route: held.append(route))
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
        expect(page.get_by_role("button", name="Собираю план…", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
        assert len(held) == 1
        held[0].abort("failed")  # Controlled build transport failure, no fake token.
        expect(page.get_by_role("alert")).to_be_visible()
        expect(page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True)).to_be_enabled()
        expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
        expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
        assert db.get_current_planning_checkpoint() is None
        print("S4-11 loading disabled, explicit error, rebuild available; no confirm or active checkpoint")
    finally:
        fixture.close()


if __name__ == "__main__":
    main()
