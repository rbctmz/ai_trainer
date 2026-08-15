"""Конфтест E2E-контура: харнесс web-стека (сценарий — test_web_stack_e2e.py).

Харнесс поднимает FastAPI и Next.js на изолированных временных данных и отдаёт
страницу Playwright. При любом падении setup (запуск API, demo-seed, прогрев,
Next.js, Chromium) диагностические материалы сохраняются в ``logs/e2e/<запуск>/``
ДО очистки временного каталога: текст ошибки, текущий этап запуска, api.log,
next.log, js-errors и снимок экрана, если браузер уже создан.

Тестовый хук ``E2E_FAIL_SETUP_AT=<этап>`` принудительно роняет setup на названном
этапе — используется регрессионной проверкой сохранения диагностики
(test_setup_failure_artifacts.py); в обычных прогонах переменная не задаётся.
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

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
ARTIFACTS_ROOT = REPO_ROOT / "logs" / "e2e"  # logs/ уже вне git

SETUP_STAGES = (
    "fastapi:запуск",
    "api:health",
    "api:demo-seed",
    "api:прогрев",
    "nextjs:запуск",
    "nextjs:готовность",
    "chromium",
    "browser",
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


def _stop_process_group(proc: subprocess.Popen | None) -> None:
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


def _new_artifacts_dir() -> Path:
    run_dir = ARTIFACTS_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _save_artifacts(
    run_dir: Path,
    *,
    error_text: str | None,
    stage: str,
    logs: tuple[Path, ...],
    page,
    js_errors: list[str],
) -> None:
    """Сохранить диагностические материалы; не должно маскировать исходное падение."""
    if error_text is not None:
        (run_dir / "error.txt").write_text(error_text, encoding="utf-8")
    (run_dir / "stage.txt").write_text(stage, encoding="utf-8")
    (run_dir / "js-errors.txt").write_text("\n".join(js_errors) or "<ошибок не собрано>", encoding="utf-8")
    for log in logs:
        if log.exists():
            shutil.copy2(log, run_dir / log.name)
    if page is not None:
        try:
            page.screenshot(path=str(run_dir / "screenshot.png"), full_page=True)
        except Exception as exc:  # noqa: BLE001
            (run_dir / "screenshot-error.txt").write_text(str(exc), encoding="utf-8")


def _maybe_fail_stage(stage: str) -> None:
    """Тестовый хук: принудительный сбой setup на названном этапе (см. модуль docstring)."""
    target = os.environ.get("E2E_FAIL_SETUP_AT")
    if target and target == stage:
        raise RuntimeError(f"принудительный сбой setup на этапе {stage!r} (регрессия сохранения диагностики)")


class WebStack:
    """Изолированный web-стек: FastAPI (temp SQLite) + Next.js + страница Playwright."""

    def __init__(self, api_base: str, web_base: str, tmp_dir: Path, api_log: Path, next_log: Path, page, js_errors: list[str]) -> None:
        self.api_base = api_base
        self.web_base = web_base
        self.tmp_dir = tmp_dir
        self.api_log = api_log
        self.next_log = next_log
        self.page = page
        self.js_errors = js_errors

    def capture_failure(self) -> None:
        """Артефакты падения сценария: снимок экрана, консоль, URL, логи серверов."""
        run_dir = _new_artifacts_dir()
        try:
            self.page.screenshot(path=str(run_dir / "screenshot.png"), full_page=True)
        except Exception as exc:  # noqa: BLE001
            (run_dir / "screenshot-error.txt").write_text(str(exc), encoding="utf-8")
        (run_dir / "url.txt").write_text(self.page.url, encoding="utf-8")
        _save_artifacts(
            run_dir,
            error_text=None,
            stage="сценарий",
            logs=(self.api_log, self.next_log),
            page=None,  # снимок уже сделан выше
            js_errors=self.js_errors,
        )


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
    page = None
    js_errors: list[str] = []
    stage = "init"

    try:
        # --- FastAPI: временные БД и чаты, credentials провайдеров очищены ---
        stage = "fastapi:запуск"
        _maybe_fail_stage(stage)
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

        stage = "api:health"
        _maybe_fail_stage(stage)
        _wait_until(
            f"{api_base}/api/health",
            lambda response: json.loads(response.read()).get("status") == "ok",
            timeout_s=90,
            proc=api_proc,
            log_path=api_log,
        )

        # --- Демо-данные в изолированную демо-базу ---
        stage = "api:demo-seed"
        _maybe_fail_stage(stage)
        request = urllib.request.Request(
            f"{api_base}/api/demo/seed", data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            assert response.status == 200, f"POST /api/demo/seed -> {response.status}"

        # --- Прогрев демо-пути одним последовательным запросом ---
        # POST /api/demo/seed наполняет ДЕМО-базу; страницы читают её при ?demo=1
        # (демо-флаг в localStorage). Прогрев также обходит холодный race
        # параллельных конструкций Database в lru_cache (api/deps.py; отдельная
        # issue) и даёт серверную проверку наличия данных до запуска браузера.
        stage = "api:прогрев"
        _maybe_fail_stage(stage)
        with urllib.request.urlopen(f"{api_base}/api/dashboard/summary?demo=1", timeout=60) as response:
            warmup = json.loads(response.read())
        assert warmup.get("has_data") is True, f"демо-данные не видны в API: {warmup}"

        # --- Next.js dev-сервер с адресом тестового API ---
        stage = "nextjs:запуск"
        _maybe_fail_stage(stage)
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

        stage = "nextjs:готовность"
        _maybe_fail_stage(stage)
        _wait_until(
            f"{web_base}/",
            lambda response: response.status < 500,
            timeout_s=180,
            proc=next_proc,
            log_path=next_log,
        )

        # --- Браузер: собираем необработанные console/pageerror ---
        stage = "chromium"
        _maybe_fail_stage(stage)
        from playwright.sync_api import sync_playwright

        playwright_driver = sync_playwright().start()
        try:
            browser = playwright_driver.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - понятная диагностика окружения
            raise RuntimeError(
                "Chromium для Playwright недоступен; выполните: python -m playwright install chromium"
            ) from exc

        stage = "browser"
        _maybe_fail_stage(stage)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        # Штатный демо-режим продукта: тумблер «Демо» пишет флаг в localStorage,
        # fetch-слой добавляет ?demo=1 — чтение идёт из изолированной демо-базы.
        context.add_init_script("window.localStorage.setItem('demo', '1');")
        page = context.new_page()
        page.on(
            "console",
            lambda message: js_errors.append(f"console[{message.type}]: {message.text}")
            if message.type == "error" and "favicon" not in message.text
            else None,
        )
        page.on("pageerror", lambda error: js_errors.append(f"pageerror: {error}"))
        yield WebStack(api_base, web_base, tmp_dir, api_log, next_log, page, js_errors)
    except Exception as exc:
        # Диагностика сбоя setup — до очистки временного каталога в finally.
        _save_artifacts(
            _new_artifacts_dir(),
            error_text=f"{type(exc).__name__}: {exc}",
            stage=stage,
            logs=(api_log, next_log),
            page=page,
            js_errors=js_errors,
        )
        raise
    finally:
        if browser is not None:
            browser.close()
        if playwright_driver is not None:
            playwright_driver.stop()
        _stop_process_group(next_proc)
        _stop_process_group(api_proc)
        shutil.rmtree(tmp_dir, ignore_errors=True)
