"""Deep per-flow acceptance probe: connect once, then drive each page.

Connects with real Garmin credentials, then visits Planning, Activities,
HRV, Sleep, and AI Coach in turn, capturing exceptions + characteristic
content that proves real data flows through each surface. The target URL can
be overridden via ACCEPTANCE_BASE_URL; otherwise the probe falls back to
http://localhost:${ACCEPTANCE_PORT:-8521}/.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit(
        "Playwright is not installed in this Python environment. "
        "Run `pip install -r requirements-dev.txt` and "
        "`python -m playwright install chromium`."
    ) from exc

REPORT = Path("logs/e2e_flows_report.json")
SCREENSHOT_DIR = Path("logs/e2e_screenshots")
AI_LOADING_MARKERS = (
    "Генерирую ответ",
    "Обрабатываю данные",
    "Analyzing your data",
    "Processing data",
)


def resolve_base_url() -> str:
    explicit_url = os.getenv("ACCEPTANCE_BASE_URL", "").strip()
    if explicit_url:
        return explicit_url.rstrip("/") + "/"
    port = os.getenv("ACCEPTANCE_PORT", "8521").strip() or "8521"
    return f"http://localhost:{port}/"


def load_env_creds() -> tuple[str, str]:
    env = Path(".env")
    if not env.exists():
        raise SystemExit("`.env` not found. Live acceptance requires GARMIN credentials.")
    data: dict[str, str] = {}
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip().strip('"').strip("'")
    try:
        return data["GARMIN_EMAIL"], data["GARMIN_PASSWORD"]
    except KeyError as exc:
        raise SystemExit("GARMIN_EMAIL/GARMIN_PASSWORD are required for live acceptance.") from exc


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


def extract_chat_message_count(text: str) -> int | None:
    match = re.search(r"Сообщений в чате:\s*(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def has_pending_ai_response(text: str) -> bool:
    return any(marker in text for marker in AI_LOADING_MARKERS)


def extract_ai_response_excerpt(body_text: str, user_input: str) -> str:
    marker = body_text.rfind(user_input)
    if marker == -1:
        return body_text[-600:]
    excerpt = body_text[marker + len(user_input):].strip()
    return excerpt[:600]


def wait_for_ai_response_completion(
    page,
    user_input: str,
    expected_min_message_count: int | None,
    timeout_ms: int = 120000,
) -> dict:
    deadline = time.time() + timeout_ms / 1000
    last_body = ""
    last_count = None

    while time.time() < deadline:
        wait_for_ready(page, 10000)
        body_text = page.locator("body").inner_text(timeout=10000)
        last_body = body_text
        current_count = extract_chat_message_count(body_text)
        if current_count is not None:
            last_count = current_count

        enough_messages = (
            expected_min_message_count is None
            or (last_count is not None and last_count >= expected_min_message_count)
        )
        if user_input in body_text and enough_messages and not has_pending_ai_response(body_text):
            return {
                "completed": True,
                "body_text": body_text,
                "message_count": last_count,
                "response_excerpt": extract_ai_response_excerpt(body_text, user_input),
            }
        time.sleep(1.0)

    return {
        "completed": False,
        "body_text": last_body,
        "message_count": last_count,
        "response_excerpt": extract_ai_response_excerpt(last_body, user_input) if last_body else "",
    }


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
    url = resolve_base_url()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 1200}).new_page()

        page.goto(url, wait_until="networkidle", timeout=60000)
        wait_for_ready(page)

        # --- connect: expand the Garmin Connect details if collapsed ---
        connect_result: dict = {"creds_available": True}
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
        try:
            sync_btn = page.get_by_role("button", name="Синхронизировать данные").first
            sync_btn.wait_for(timeout=10000)
            sync_btn.click(timeout=8000)
            wait_for_ready(page, 180000)
            time.sleep(3.0)
            connect_result["sync_status"] = "clicked"
        except Exception as sync_exc:
            connect_result["sync_status"] = "not_available"
            connect_result["sync_note"] = str(sync_exc)[:200]

        connect_errors = collect_errors(page)
        connect_result["exceptions"] = len(connect_errors)
        connect_result["errors"] = connect_errors[:2]
        findings["flows"]["connect"] = connect_result
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
            user_prompt = "Какая у меня сегодня готовность по данным Garmin?"
            body_before_ai = page.locator("body").inner_text(timeout=10000)
            ai_message_count_before = extract_chat_message_count(body_before_ai)
            # find a text area for chat input
            ta = page.get_by_label("сообщение", exact=False).first
            try:
                ta.wait_for(timeout=4000)
            except Exception:
                ta = page.locator('textarea').last
                ta.wait_for(timeout=4000)
            ta.fill(user_prompt)
            page.keyboard.press("Enter")
            ai_result = wait_for_ai_response_completion(
                page,
                user_prompt,
                expected_min_message_count=(
                    ai_message_count_before + 2
                    if ai_message_count_before is not None
                    else None
                ),
            )
            errs = collect_errors(page)
            coach["ai_exceptions"] = len(errs)
            coach["ai_errors"] = errs[:2]
            coach["ai_message_count_before"] = ai_message_count_before
            coach["ai_message_count_after"] = ai_result["message_count"]
            coach["ai_response_completed"] = ai_result["completed"]
            coach["ai_response_excerpt"] = ai_result["response_excerpt"]
            coach["ai_body_after"] = ai_result["body_text"][-1500:]
            page.screenshot(path=str(SCREENSHOT_DIR / "flows_07_coach_response.png"), full_page=True)
            findings["flows"]["Коуч"] = coach
            print(
                f"  Коуч AI response: completed={ai_result['completed']}, exceptions={len(errs)}",
                flush=True,
            )
        except Exception as e:
            findings["flows"]["ai_coach_interaction"] = {"error": f"{e!s}"[:200]}
            print("  AI coach interaction: skipped/failed", str(e)[:120], flush=True)

        browser.close()

    REPORT.write_text(json.dumps(findings, ensure_ascii=False, indent=2))
    print(f"\nreport: {REPORT}", flush=True)
    total_exc = sum(v.get("exceptions", 0) for v in findings["flows"].values() if isinstance(v, dict))
    ai_completed = bool(findings["flows"].get("Коуч", {}).get("ai_response_completed"))
    return 0 if total_exc == 0 and ai_completed else 1


if __name__ == "__main__":
    sys.exit(main())
