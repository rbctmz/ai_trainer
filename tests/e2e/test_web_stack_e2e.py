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

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
ARTIFACTS_ROOT = REPO_ROOT / "logs" / "e2e"  # logs/ уже вне git

TODAY_STATE_TITLES = (
    "План в силе",
    "Есть предложение",
    "Конфликт требует внимания",
    "Данных недостаточно",
    "Плана нет",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _tail(path: Path, lines: int = 20) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "<лог недоступен>"
    return "\n".join(content[-lines:])


def _wait_until(url: str, accept, timeout_s: float, proc: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"процесс завершился досрочно (код {proc.returncode}); лог:\n{_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if accept(response):
                    return
        except urllib.error.HTTPError as exc:  # редиректы/4xx считаем ответом сервера
            if accept(exc):
                return
            last_error = exc
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"таймаут готовности {url} за {timeout_s:.0f}с: {last_error!r}")


def _stop_process_group(proc: subprocess.Popen | None, log_path: Path) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
        return
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass


class WebStack:
    """Изолированный web-стек: FastAPI (temp SQLite) + Next.js + страница Playwright."""

    def __init__(self, api_base: str, web_base: str, tmp_dir: Path, api_log: Path, next_log: Path, page) -> None:
        self.api_base = api_base
        self.web_base = web_base
        self.tmp_dir = tmp_dir
        self.api_log = api_log
        self.next_log = next_log
        self.page = page
        self.js_errors: list[str] = []

    def capture_failure(self) -> None:
        """Сохранить артефакты падения: снимок экрана, консоль, логи серверов."""
        run_dir = ARTIFACTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(run_dir / "screenshot.png"), full_page=True)
        except Exception as exc:  # noqa: BLE001 - артефакты не должны маскировать падение
            (run_dir / "screenshot-error.txt").write_text(str(exc), encoding="utf-8")
        (run_dir / "js-errors.txt").write_text(
            "\n".join(self.js_errors) or "<ошибок не собрано>", encoding="utf-8"
        )
        (run_dir / "url.txt").write_text(self.page.url, encoding="utf-8")
        for log in (self.api_log, self.next_log):
            if log.exists():
                shutil.copy2(log, run_dir / log.name)


@pytest.fixture(scope="module")
def web_stack():
    tmp_dir = Path(tempfile.mkdtemp(prefix="ai-trainer-e2e-"))
    api_port = _free_port()
    web_port = _free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    web_base = f"http://127.0.0.1:{web_port}"
    api_log = tmp_dir / "api.log"
    next_log = tmp_dir / "next.log"
    api_proc: subprocess.Popen | None = None
    next_proc: subprocess.Popen | None = None
    playwright_driver = None
    browser = None
    try:
        # --- FastAPI: временные БД и чаты, credentials провайдеров очищены ---
        api_env = {
            **os.environ,
            "DATABASE_PATH": str(tmp_dir / "e2e.db"),
            "DEMO_DATABASE_PATH": str(tmp_dir / "demo.db"),
            "CHATS_DIR": str(tmp_dir / "chats"),
            "GARMIN_EMAIL": "",
            "GARMIN_PASSWORD": "",
            "INTERVALS_ICU_API_KEY": "",
            "PYTHONUNBUFFERED": "1",
        }
        with api_log.open("wb") as log_handle:
            api_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                cwd=REPO_ROOT,
                env=api_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _wait_until(
            f"{api_base}/api/health",
            lambda response: json.loads(response.read()).get("status") == "ok",
            timeout_s=90,
            proc=api_proc,
            log_path=api_log,
        )

        # --- Демо-данные в изолированную БД ---
        request = urllib.request.Request(
            f"{api_base}/api/demo/seed", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            assert response.status == 200, f"POST /api/demo/seed -> {response.status}"

        # --- Прогрев демо-пути одним последовательным запросом ---
        # POST /api/demo/seed наполняет ДЕМО-базу; страницы читают её при ?demo=1
        # (демо-флаг в localStorage). Прогрев также обходит холодный race
        # параллельных конструкций Database в lru_cache (api/deps.py) и даёт
        # серверную проверку наличия данных до запуска браузера.
        with urllib.request.urlopen(f"{api_base}/api/dashboard/summary?demo=1", timeout=60) as response:
            warmup = json.loads(response.read())
        assert warmup.get("has_data") is True, f"демо-данные не видны в API: {warmup}"

        # --- Next.js dev-сервер с адресом тестового API ---
        next_env = {
            **os.environ,
            "API_BASE_URL": api_base,
            "NEXT_TELEMETRY_DISABLED": "1",
        }
        with next_log.open("wb") as log_handle:
            next_proc = subprocess.Popen(
                ["npm", "run", "dev", "--", "-p", str(web_port)],
                cwd=WEB_DIR,
                env=next_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                shell=False,
            )
        _wait_until(
            f"{web_base}/",
            lambda response: response.status < 500,
            timeout_s=180,
            proc=next_proc,
            log_path=next_log,
        )

        # --- Браузер: собираем необработанные console/pageerror ---
        from playwright.sync_api import sync_playwright

        playwright_driver = sync_playwright().start()
        try:
            browser = playwright_driver.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - понятная диагностика окружения
            raise RuntimeError(
                "Chromium для Playwright недоступен; выполните: python -m playwright install chromium"
            ) from exc
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        # Штатный демо-режим продукта: тумблер «Демо» пишет флаг в localStorage,
        # fetch-слой добавляет ?demo=1 — чтение идёт из изолированной демо-базы.
        context.add_init_script("window.localStorage.setItem('demo', '1');")
        page = context.new_page()
        stack = WebStack(api_base, web_base, tmp_dir, api_log, next_log, page)
        page.on(
            "console",
            lambda message: stack.js_errors.append(f"console[{message.type}]: {message.text}")
            if message.type == "error" and "favicon" not in message.text
            else None,
        )
        page.on("pageerror", lambda error: stack.js_errors.append(f"pageerror: {error}"))
        yield stack
    finally:
        if browser is not None:
            browser.close()
        if playwright_driver is not None:
            playwright_driver.stop()
        _stop_process_group(next_proc, next_log)
        _stop_process_group(api_proc, api_log)
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
