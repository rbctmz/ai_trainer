"""Synthetic live components: responsive geometry, primary contrast and focus."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest
from playwright.sync_api import expect

from tests.e2e.test_swim_import_ui import seeded_draft
from tests.smoke._swim_import_fixtures import exact_program_v2

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def contrast(foreground, background):
    def luminance(value):
        channels = [int(x) / 255 for x in re.findall(r"\d+", value)[:3]]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
        return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_program_geometry_primary_contrast_and_optional_synthetic_evidence(web_stack):
    page = web_stack.page
    draft = seeded_draft(web_stack, exact_program_v2())
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    expect(page.get_by_role("region", name="Структура программы")).to_be_visible()
    action = page.get_by_role("button", name="Подготовить предпросмотр", exact=True)
    expect(action).to_be_enabled()
    capture = os.environ.get("AI_TRAINER_CAPTURE_SWIM_EVIDENCE") == "1"
    records = []
    try:
        for theme in ("light", "dark"):
            page.evaluate("theme => { localStorage.setItem('theme', theme); document.documentElement.classList.toggle('dark', theme === 'dark'); }", theme)
            for width in (1280, 390, 320):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (theme, width)
                colors = action.evaluate("element => {const css=getComputedStyle(element); return {fg: css.color, bg: css.backgroundColor, height: element.getBoundingClientRect().height};}")
                assert contrast(colors["fg"], colors["bg"]) >= 4.5, (theme, width, colors)
                assert colors["height"] >= 44
                if capture and width != 320:
                    folder = ROOT / "docs/design/evidence/issue-772"
                    folder.mkdir(parents=True, exist_ok=True)
                    filename = f"program-{theme}-{width}.png"
                    page.screenshot(path=str(folder / filename), full_page=True)
                    records.append({"file": filename, "theme": theme, "viewport": {"width": width, "height": 900}, "colors": colors})
        if capture:
            files = sorted((ROOT / "web/components/swim").glob("*.tsx")) + [ROOT / "web/components/swim/styles.ts", ROOT / "web/app/coach/swim/page.tsx", ROOT / "web/lib/swim-api.ts"]
            hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
            metadata = {"fixture": "exact_program_v2 anonymous synthetic", "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "source_sha256": hashes, "screenshots": records, "limitations": "Real components/API/temp DB; no owner acceptance, screen-reader certification or live AI quality inference."}
            (ROOT / "docs/design/evidence/issue-772/metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    finally:
        page.set_viewport_size({"width": 1280, "height": 900})
        page.evaluate("localStorage.setItem('theme', 'light'); document.documentElement.classList.remove('dark');")


def test_inline_editor_keyboard_focus_returns_to_origin(web_stack):
    page = web_stack.page
    draft = seeded_draft(web_stack, exact_program_v2())
    page.goto(web_stack.web_base + f"/coach/swim?draft={draft['import_id']}")
    trigger = page.get_by_role("article", name="Example one", exact=True).get_by_role("button", name="Изменить тренировку", exact=True)
    trigger.click()
    editor = page.get_by_role("region", name="Правка тренировки", exact=True)
    expect(editor).to_be_focused()
    page.keyboard.press("Tab")
    expect(editor.get_by_label("Что изменить", exact=True)).to_be_focused()
    editor.get_by_role("button", name="Отменить правку", exact=True).click()
    expect(trigger).to_be_focused()
