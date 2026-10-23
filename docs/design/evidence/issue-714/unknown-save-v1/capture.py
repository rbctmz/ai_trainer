"""Capture final unknown-save controls without overwriting frozen owner screens."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent


def main() -> None:
    module = runpy.run_path(str(ROOT / "docs/reports/2026-10-22-planning-confirmation-s4-m3/capture_owner_cases.py"))
    capture_original = module["capture"]
    namespace = module["main"].__globals__
    namespace["ARTIFACTS"] = OUT

    def capture(page, name: str, *, uncertain: bool = False) -> None:
        if name != "d":
            return
        capture_original(page, name, uncertain=uncertain)
        # The unknown-result controls belong to the wizard section, outside
        # the summary. Keep that actual status/retry surface in this capture.
        from playwright.sync_api import expect
        expect(page.get_by_role("button", name="Повторить проверку", exact=True)).to_be_visible()
        expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен")).to_be_visible()

    namespace["capture"] = capture
    module["main"]()


if __name__ == "__main__":
    main()
