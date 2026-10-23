"""Current comparison UI on real temporary-data journeys; preserve older cases."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).parent


def main() -> None:
    module = runpy.run_path(str(ROOT / "docs/reports/2026-10-22-planning-confirmation-s4-m3/capture_owner_cases.py"))
    original = module["capture"]
    namespace = module["main"].__globals__
    namespace["ARTIFACTS"] = OUT

    def capture(page, name: str, *, uncertain: bool = False) -> None:
        original(page, name, uncertain=uncertain)
        if name != "b":
            return
        summary = page.get_by_role("region", name="Резюме плана", exact=True)
        summary.screenshot(path=str(OUT / "prototype-edit-1280-light.png"), animations="disabled")
        page.set_viewport_size({"width": 320, "height": 1100})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        summary.screenshot(path=str(OUT / "prototype-edit-320-light.png"), animations="disabled")
        page.set_viewport_size({"width": 1280, "height": 2200})

    namespace["capture"] = capture
    module["main"]()


if __name__ == "__main__":
    main()
