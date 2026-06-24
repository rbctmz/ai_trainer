"""Live end-to-end acceptance probe via Playwright against running Streamlit.

Runs against http://localhost:8521 (launched separately). Verifies the full
websocket-rendered UI, not just the static shell. Reports per-flow outcomes.

Drives the real Garmin login flow (credentials from .env) to take the app
past demo onboarding and verify that the dashboard renders the real
already-synced data.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8521/"
REPORT = Path("logs/e2e_acceptance_report.json")
SCREENSHOT_DIR = Path("logs/e2e_screenshots")


def load_env_creds() -> tuple[str | None, str | None]:
    """Read GARMIN_EMAIL / GARMIN_PASSWORD from .env without importing app."""
    env = Path(".env")
    if not env.exists():
        return None, None
    data: dict[str, str] = {}
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data.get("GARMIN_EMAIL"), data.get("GARMIN_PASSWORD")


def wait_for_ready(page, timeout_ms: int = 60000) -> None:
    """Wait until Streamlit finished rendering (no spinner, status gone)."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        # st.status container shows "Running..." while executing
        running = page.locator('[data-testid="stStatusWidget"]').count()
        spinners = page.locator('[data-testid="stSpinner"]').count()
        if running == 0 and spinners == 0:
            return
        time.sleep(0.5)
    # not fatal; continue


def collect_errors(page) -> list[str]:
    """Collect Streamlit exception and alert containers rendered into the DOM.

    Covers both hard failures (`stException`) and soft user-facing messages
    (`st.error`/`st.warning`, rendered as `stAlert` with a `kind`). A real
    Garmin 429/rate-limit surfaces as an `stAlert[kind=error]`, not as a
    Streamlit exception, so excluding alerts made the probe miss it.
    """
    errs = []
    exc = page.locator('[data-testid="stException"]')
    for i in range(exc.count()):
        txt = exc.nth(i).inner_text(timeout=2000)
        errs.append(txt[:500])
    # st.error / st.warning render as stAlert with a kind attribute
    alert = page.locator('[data-testid="stAlert"]')
    for i in range(alert.count()):
        try:
            kind = alert.nth(i).get_attribute("kind", timeout=1000) or ""
        except Exception:
            kind = ""
        if kind in ("error", "warning"):
            txt = alert.nth(i).inner_text(timeout=2000)
            errs.append(f"[{kind}] {txt[:500]}")
    return errs


def main() -> int:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    findings: dict = {"flows": {}, "errors_total": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        console_msgs: list[str] = []
        page.on("console", lambda msg: console_msgs.append(f"{msg.type}: {msg.text}") if msg.type in ("error", "warning") else None)

        print("→ loading", URL, flush=True)
        page.goto(URL, wait_until="networkidle", timeout=60000)
        wait_for_ready(page)

        # --- Flow 1: Dashboard / main view ---
        page.screenshot(path=str(SCREENSHOT_DIR / "01_dashboard.png"), full_page=True)
        title = page.title()
        body_text = page.locator("body").inner_text(timeout=10000)
        body_lower = body_text.lower()

        dashboard_checks = {
            "title_present": "ai trainer" in title.lower() or "ai trainer" in body_lower,
            "has_real_date_range": any(m in body_text for m in ("2026-06", "июн", "jun")),
            "has_metric_or_section": any(
                m in body_lower
                for m in ("readiness", "готовност", "activity", "активност", "sleep", "сон", "training", "трениров")
            ),
            "exception_rendered": page.locator('[data-testid="stException"]').count(),
        }
        findings["flows"]["dashboard_initial"] = {
            "title": title,
            "checks": dashboard_checks,
            "body_excerpt": body_text[:800],
        }
        print("  dashboard:", json.dumps(dashboard_checks, ensure_ascii=False), flush=True)

        # --- Flow 1b: connect Garmin via sidebar form with real .env creds ---
        email, password = load_env_creds()
        connect_result: dict = {"creds_available": bool(email and password)}
        if email and password:
            try:
                # expand the "Garmin Connect" details section in the sidebar
                details = page.locator('details').first
                try:
                    if details.get_attribute("open") is None:
                        details.locator("summary").click(timeout=3000)
                        time.sleep(0.5)
                except Exception:
                    pass

                # sidebar text/password inputs are keyed by aria-label
                email_input = page.get_by_label("Email Garmin", exact=False).first
                email_input.wait_for(timeout=8000)
                email_input.fill(email)
                pwd_input = page.get_by_label("Пароль Garmin", exact=False).first
                pwd_input.wait_for(timeout=8000)
                pwd_input.fill(password)

                # click the "Подключиться" button in the sidebar
                connect_btn = page.get_by_role("button", name="Подключиться").first
                connect_btn.click(timeout=8000)

                # sync may take a while against live Garmin; wait up to 120s
                wait_for_ready(page, 120000)
                time.sleep(3.0)
                errs = collect_errors(page)
                page.screenshot(path=str(SCREENSHOT_DIR / "02_after_connect.png"), full_page=True)
                after = page.locator("body").inner_text(timeout=10000)
                connect_result.update(
                    {
                        "exceptions_after": len(errs),
                        "errors_after": errs[:2],
                        "body_excerpt_after": after[:800],
                        "shows_real_activity_count": "95" in after,
                        "shows_real_metric": any(
                            m in after
                            for m in ("активност", "activity", "готовност", "readiness", "HRV", "сон", "sleep", "training", "трениров")
                        ),
                    }
                )
                print("  connect:", json.dumps({k: v for k, v in connect_result.items() if k != "body_excerpt_after"}, ensure_ascii=False), flush=True)
            except Exception as e:
                connect_result["error"] = f"{e!s}"[:300]
                page.screenshot(path=str(SCREENSHOT_DIR / "02_connect_failed.png"), full_page=True)
                print("  connect: FAILED", str(e)[:200], flush=True)
        findings["flows"]["garmin_connect"] = connect_result

        # --- Flow 2: navigation — click through sidebar pages if present ---
        nav_targets = ["Планирование", "Planning", "Тренировки", "Activities", "Коуч", "Coach", "Настройки", "Settings"]
        nav_results = {}
        for label in nav_targets:
            btn = page.get_by_role("button", name=label).first
            try:
                btn.wait_for(timeout=1500)
            except Exception:
                # try as link/radio
                btn = page.get_by_text(label, exact=False).first
                try:
                    btn.wait_for(timeout=1500)
                except Exception:
                    nav_results[label] = "not_found"
                    continue
            try:
                btn.click(timeout=3000)
                wait_for_ready(page, 30000)
                errs = collect_errors(page)
                time.sleep(1.0)
                page.screenshot(path=str(SCREENSHOT_DIR / f"nav_{label}.png"), full_page=True)
                nav_results[label] = {"clicked": True, "exceptions": len(errs), "errors": errs[:2]}
                print(f"  nav[{label}]: clicked, exceptions={len(errs)}", flush=True)
            except Exception as e:
                nav_results[label] = f"click_failed: {e!s}"[:200]
        findings["flows"]["navigation"] = nav_results

        # --- console errors ---
        findings["flows"]["console"] = console_msgs[:20]
        findings["errors_total"] = sum(
            v.get("exceptions", 0) for v in nav_results.values() if isinstance(v, dict)
        ) + dashboard_checks["exception_rendered"]

        browser.close()

    REPORT.write_text(json.dumps(findings, ensure_ascii=False, indent=2))
    print("\n=== REPORT ===", json.dumps(findings, ensure_ascii=False, indent=2), sep="\n", flush=True)
    print(f"\nreport: {REPORT}", flush=True)
    return 0 if findings["errors_total"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
