"""One current decision for owner evaluation; synthetic UI only."""
from pathlib import Path

from playwright.sync_api import expect

from tests.e2e.conftest import web_stack
from tests.e2e.test_planning_confirmation_s4_ui import candidate


def main() -> None:
    fixture = web_stack.__wrapped__()
    stack = next(fixture)
    try:
        page, db, payload = candidate(stack)
        summary = page.get_by_role("region", name="Резюме плана", exact=True)
        expect(summary.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_be_enabled()
        expect(summary.locator("time").first).to_have_attribute("datetime", payload["lifecycle"]["start_date"])
        for width, theme in [(1280, "light"), (390, "dark"), (320, "light")]:
            page.set_viewport_size({"width": width, "height": 1100})
            page.evaluate("theme => {document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.dataset.theme=theme}", theme)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            summary.screenshot(path=str(Path(__file__).parent / f"prototype-{width}-{theme}.png"), animations="disabled")
        assert db.get_current_planning_checkpoint() is None
        print("One new-plan proposal captured in three viewports; no confirmation or athlete/provider write")
    finally:
        fixture.close()


if __name__ == "__main__":
    main()
