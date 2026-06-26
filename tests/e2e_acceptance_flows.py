"""Deep per-flow acceptance probe: connect once, then drive each page.

Connects with real Garmin credentials, then visits Planning, Activities,
HRV, Sleep, and AI Coach in turn, capturing exceptions + characteristic
content that proves real data flows through each surface.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8521/"
REPORT = Path("logs/e2e_flows_report.json")
SCREENSHOT_DIR = Path("logs/e2e_screenshots")


def load_env_creds() -> tuple[str, str]:
    data: dict[str, str] = {}
    for line in Path(".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip().strip('"').strip("'")
    return data["GARMIN_EMAIL"], data["GARMIN_PASSWORD"]


def wait_for_ready(page, timeout_ms: int = 90000) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if page.locator('[data-testid="stStatusWidget"]').count() == 0 and page.locator('[data-testid="stSpinner"]').count() == 0:
            return
        time.sleep(0.5)


def collect_errors(page) -> list[str]:
    """Collect Streamlit exception and alert containers.

    Covers hard `stException` failures and soft `st.error`/`st.warning` alerts
    (`stAlert[kind=error|warning]`). A real Garmin 429 surfaces as an alert,
    so excluding alerts made the probe miss rate-limit failures.
    """
    errs = []
    exc = page.locator('[data-testid="stException"]')
    for i in range(exc.count()):
        errs.append(exc.nth(i).inner_text(timeout=2000)[:400])
    alert = page.locator('[data-testid="stAlert"]')
    for i in range(alert.count()):
        try:
            kind = alert.nth(i).get_attribute("kind", timeout=1000) or ""
        except Exception:
            kind = ""
        if kind in ("error", "warning"):
            errs.append(f"[{kind}] {alert.nth(i).inner_text(timeout=2000)[:400]}")
    return errs


def goto_page(page, label: str) -> dict:
    """Click a primary nav button (rendered in the main area via st.columns)
    or fall back to the sidebar selectbox. Return outcome."""
    result: dict = {"label": label}
    try:
        # primary nav buttons live in the main area, text == short_name
        btn = page.get_by_role("button", name=label, exact=True).first
        clicked = False
        try:
            btn.wait_for(state="visible", timeout=4000)
            btn.click(timeout=4000)
            clicked = True
        except Exception:
            pass

        if not clicked:
            # fallback: sidebar selectbox labelled "Выберите раздел:"
            sb = page.locator('[data-testid="stSidebar"]').get_by_label("Выберите раздел:", exact=False).first
            sb.wait_for(state="visible", timeout=4000)
            sb.select_option(label=label)
            clicked = True

        wait_for_ready(page, 60000)
        time.sleep(1.5)
        errs = collect_errors(page)
        result["exceptions"] = len(errs)
        result["errors"] = errs[:2]
        result["body_excerpt"] = page.locator("body").inner_text(timeout=10000)[:1200]
        result["nav_method"] = "button" if clicked and "button" in repr(btn) else "selectbox"
    except Exception as e:
        result["error"] = f"{e!s}"[:200]
    return result


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    email, password = load_env_creds()
    findings: dict = {"flows": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 1200}).new_page()

        page.goto(URL, wait_until="networkidle", timeout=60000)
        wait_for_ready(page)

        # --- connect: expand the Garmin Connect details if collapsed ---
        details = page.locator("details").first
        is_open = details.evaluate("el => el.open === true")
        if not is_open:
            details.locator("summary").click()
            time.sleep(1.0)
        email_input = page.get_by_label("Email Garmin", exact=False).first
        email_input.wait_for(state="visible", timeout=15000)
        email_input.fill(email)
        pwd_input = page.get_by_label("Пароль Garmin", exact=False).first
        pwd_input.wait_for(state="visible", timeout=15000)
        pwd_input.fill(password)
        page.get_by_role("button", name="Подключиться").first.click()
        wait_for_ready(page, 120000)
        time.sleep(2)
        findings["flows"]["connect_exceptions"] = len(collect_errors(page))
        page.screenshot(path=str(SCREENSHOT_DIR / "flows_00_connected.png"), full_page=True)

        # --- visit each page (short_name from ui/navigation.py _PRIMARY_NAV_ITEMS) ---
        for label, shot in [
            ("Дашборд", "flows_01_dashboard.png"),
            ("План", "flows_02_planning.png"),
            ("Активности", "flows_03_activities.png"),
            ("HRV", "flows_04_hrv.png"),
            ("Сон", "flows_05_sleep.png"),
            ("Коуч", "flows_06_coach.png"),
        ]:
            res = goto_page(page, label)
            page.screenshot(path=str(SCREENSHOT_DIR / shot), full_page=True)
            findings["flows"][label] = res
            print(f"  {label}: exceptions={res.get('exceptions', 'err')}", flush=True)

        # --- AI coach: try sending a message and check for real response ---
        try:
            coach = findings["flows"].get("Коуч", {})
            # find a text area for chat input
            ta = page.get_by_label("сообщение", exact=False).first
            try:
                ta.wait_for(timeout=4000)
            except Exception:
                ta = page.locator('textarea').last
                ta.wait_for(timeout=4000)
            ta.fill("Какая у меня сегодня готовность по данным Garmin?")
            page.keyboard.press("Enter")
            # wait for AI response (up to 60s)
            wait_for_ready(page, 60000)
            time.sleep(3)
            errs = collect_errors(page)
            coach["ai_exceptions"] = len(errs)
            coach["ai_errors"] = errs[:2]
            coach["ai_body_after"] = page.locator("body").inner_text(timeout=10000)[-1500:]
            page.screenshot(path=str(SCREENSHOT_DIR / "flows_07_coach_response.png"), full_page=True)
            findings["flows"]["Коуч"] = coach
            print(f"  Коуч AI response: exceptions={len(errs)}", flush=True)
        except Exception as e:
            findings["flows"]["ai_coach_interaction"] = {"error": f"{e!s}"[:200]}
            print("  AI coach interaction: skipped/failed", str(e)[:120], flush=True)

        browser.close()

    REPORT.write_text(json.dumps(findings, ensure_ascii=False, indent=2))
    print(f"\nreport: {REPORT}", flush=True)
    total_exc = sum(v.get("exceptions", 0) for v in findings["flows"].values() if isinstance(v, dict))
    return 0 if total_exc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
