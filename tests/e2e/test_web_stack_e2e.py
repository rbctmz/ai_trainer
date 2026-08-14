"""Сквозной smoke-сценарий основного web-стека (этап 1 E2E).

Один пользовательский маршрут подтверждает, что приложение запускается, работает
на изолированных демонстрационных данных и основные страницы открываются без
ошибок:

1. FastAPI поднимается с временной SQLite-базой и временным каталогом чатов,
   credentials Garmin/Intervals.icu очищены (реальные провайдеры не затрагиваются).
2. После готовности API вызывается ``POST /api/demo/seed``.
3. Next.js запускается с адресом тестового API (``API_BASE_URL``).
4. Playwright проходит маршрут «Обзор» → «Сегодня» → «План» через основное меню;
   зависание в загрузке и необработанные console/pageerror — падение теста.
5. Серверы останавливаются, временные данные удаляются; при падении снимок
   экрана, журнал консоли и логи серверов сохраняются в ``logs/e2e/<запуск>/``.

Запуск (одна команда)::

    python -m pytest -m e2e tests/e2e -q

Локальные требования: установлены зависимости ``web/node_modules`` и
``playwright install chromium``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"

TODAY_STATE_TITLES = (
    "План в силе",
    "Есть предложение",
    "Конфликт требует внимания",
    "Данных недостаточно",
    "Плана нет",
)


@pytest.fixture(scope="module")
def web_stack():
    raise NotImplementedError(
        "E2E-харнесс не реализован (RED-этап): запуск FastAPI + Next.js "
        "на изолированных демо-данных (см. docs: этап 1 E2E)"
    )
    yield  # pragma: no cover


def test_main_user_journey(web_stack) -> None:
    page = web_stack.page

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
