"""Сквозной smoke-сценарий основного web-стека (этап 1 E2E).

Один пользовательский маршрут подтверждает, что приложение запускается, работает
на изолированных демонстрационных данных и основные страницы открываются без
ошибок: «Обзор» → «Сегодня» → «План» через основное меню. Зависание в загрузке и
необработанные console/pageerror — падение теста.

Харнесс (запуск FastAPI/Next.js на временных данных, артефакты падений) —
в ``tests/e2e/conftest.py``.

Запуск (одна команда)::

    python -m pytest -m e2e tests/e2e -q

Локальные требования: установлены зависимости ``web/node_modules`` и
``playwright install chromium``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

TODAY_STATE_TITLES = (
    "План в силе",
    "Есть предложение",
    "Конфликт требует внимания",
    "Данных недостаточно",
    "Плана нет",
)


def test_main_user_journey(web_stack) -> None:
    page = web_stack.page

    try:
        # --- «Обзор»: заголовок, данные загружены, не зависли в skeleton/error ---
        page.goto(f"{web_stack.web_base}/dashboard", wait_until="domcontentloaded")
        page.locator("h1", has_text="Обзор").wait_for(state="visible", timeout=60_000)
        date_chip = page.locator("header span").first
        date_chip.wait_for(state="visible", timeout=60_000)
        assert date_chip.inner_text().strip(), "данные дашборда не загрузились (нет summary.today.date)"
        assert page.get_by_text("Не удалось загрузить данные").count() == 0, (
            "дашборд показывает ошибку загрузки данных"
        )

        # --- Навигация по основному меню: «Сегодня» ---
        page.get_by_role("link", name="Сегодня").click()
        page.wait_for_url("**/today", timeout=60_000)
        today_h1 = page.locator("h1").first
        today_h1.wait_for(state="visible", timeout=60_000)
        assert today_h1.inner_text().strip() in TODAY_STATE_TITLES, (
            f"«Сегодня» в неожиданном состоянии: {today_h1.inner_text()!r}"
        )

        # --- Навигация по основному меню: «План» ---
        page.get_by_role("link", name="План").click()
        page.wait_for_url("**/planning", timeout=60_000)
        page.locator("h1", has_text="Планирование").wait_for(state="visible", timeout=60_000)

        # --- Необработанные ошибки страницы/консоли — падение ---
        assert not web_stack.js_errors, "Ошибки браузера во время сценария:\n" + "\n".join(
            web_stack.js_errors
        )
    except Exception:
        web_stack.capture_failure()
        raise
