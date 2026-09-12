"""Browser contract/UX acceptance for the recovery-capture readback (issue #562 M6b).

Это **не** provider E2E: продуктовые переключатели и инъекции провайдеров не
добавляются. Сценарий перехватывает три маршрута и проверяет, что пользователь
видит честный readback вердикта capture:

- ``/api/sync/providers`` — выбранный провайдер «настроен», поэтому кнопка активна;
- ``POST /api/sync`` — состояние ``running`` (как в реальном запуске job'а);
- ``GET /api/sync`` — первый ответ ``running``, затем соответствующая terminal-фикстура,
  поэтому тест обязан реально пройти polling-путь, а не завершиться после POST.

JSON-фикстуры созданы и запинены M6a (``tests/e2e/fixtures/recovery_capture/``);
их форма здесь не меняется.

Evidence: на каждый кейс сохраняется видимый текст строки синхронизации и снимок
экрана в каталог ``E2E_CAPTURE_EVIDENCE_DIR`` (по умолчанию
``logs/e2e-recovery-capture/<timestamp>``) — материалы для evidence bundle M6c.

Запуск::

    python -m pytest -m e2e tests/e2e/test_recovery_capture_readback.py -q
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "e2e" / "fixtures" / "recovery_capture"

PROVIDERS = ("garmin", "intervals")
STATUSES = (
    "saved_before_load",
    "saved_too_late",
    "activity_start_missing",
    "ineligible",
    "capture_failed",
)

PROVIDER_LABELS = {"garmin": "Garmin Connect", "intervals": "Intervals.icu"}

# Человеко-читаемые тексты статусов (совпадают с картой в SyncControl).
STATUS_TEXTS = {
    "saved_before_load": "снимок готовности сохранён до нагрузки",
    "saved_too_late": "снимок готовности сохранён после начала активности",
    "activity_start_missing": "нет данных о времени старта активности",
    "ineligible": "снимок сохранён, но не пригоден для оценки перед нагрузкой",
    "capture_failed": "снимок готовности не сохранён",
}

# Проблемные состояния обязаны показывать безопасную причину. Текст причины —
# человеко-читаемый маппинг кода либо честный fallback, но не сам код.
PROBLEM_STATUSES = {
    "saved_too_late",
    "activity_start_missing",
    "ineligible",
    "capture_failed",
}
REASON_TEXTS = {
    "saved_too_late": ("причина не уточнена",),
    "activity_start_missing": ("нет времени старта активности", "причина не уточнена"),
    "ineligible": ("недостаточно уверенности в данных", "причина не уточнена"),
    "capture_failed": ("сбой при сохранении снимка", "причина не уточнена"),
}

# Машинные коды и идентификаторы, которых пользователь видеть не должен.
FORBIDDEN_IN_UI = (
    "capture_run_id",
    "job_id",
    "snapshot_id",
    "episode_refresh",
    "saved_before_load",
    "saved_too_late",
    "activity_start_missing",
    "ineligible",
    "capture_failed",
    "low_confidence",
    "stale_snapshot",
    "stale_factor",
    "missing_score",
    "missing_as_of",
    "future_factor",
    "invalid_timezone",
    "snapshot_capture_failed",
    "activity_lookup_failed",
    "unparsable_observed_at",
    "3f1c0f4e-6a1b-4c2d-9e30-8a7b6c5d4e3f",
    "athlete.db",
    "undefined",
    "null",
)


def _fixture(provider: str, status: str) -> dict:
    return json.loads((FIXTURES / f"{provider}_{status}.json").read_text(encoding="utf-8"))


def _providers_payload(provider: str) -> dict:
    def entry(source: str) -> dict:
        configured = source == provider
        return {
            "source": source,
            "label": PROVIDER_LABELS[source],
            "description": "",
            "configured": configured,
            "connection": {"configured": configured} if configured else None,
        }

    return {
        "recommended_source": provider,
        "providers": [entry("garmin"), entry("intervals")],
    }


def _running_payload(terminal: dict, provider: str) -> dict:
    return {
        "job_id": terminal["job_id"],
        "source": provider,
        "sync_state": "running",
        "status": "running",
        "started_at": terminal.get("started_at"),
        "finished_at": None,
        "days": terminal.get("days"),
        "progress": {
            "percent": 10,
            "message": f"Синхронизация {PROVIDER_LABELS[provider]} запущена",
            "step_text": None,
            "stats_message": None,
        },
        "result": None,
        "error": None,
        "reused": False,
    }


PROVIDERS_URL = re.compile(r"/api/sync/providers")
JOB_URL = re.compile(r"/api/sync($|\?)")


def _install_routes(page, provider: str, status: str) -> dict:
    """Перехват providers/POST/GET: polling обязан дойти до terminal-фикстуры."""
    terminal = _fixture(provider, status)
    running = _running_payload(terminal, provider)
    calls = {"providers": 0, "post": 0, "get": 0}

    def providers_handler(route) -> None:
        calls["providers"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_providers_payload(provider)),
        )

    def job_handler(route) -> None:
        if route.request.method == "POST":
            calls["post"] += 1
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(running)
            )
            return
        calls["get"] += 1
        payload = running if calls["get"] == 1 else terminal
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(payload)
        )

    page.route(JOB_URL, job_handler)
    page.route(PROVIDERS_URL, providers_handler)
    return calls


_EVIDENCE_DIR: Path | None = None


def _evidence_dir() -> Path:
    """Один каталог на прогон: все кейсы складывают evidence вместе."""
    global _EVIDENCE_DIR
    if _EVIDENCE_DIR is not None:
        return _EVIDENCE_DIR
    configured = os.environ.get("E2E_CAPTURE_EVIDENCE_DIR")
    if configured:
        directory = Path(configured)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = ROOT / "logs" / "e2e-recovery-capture" / stamp
    directory.mkdir(parents=True, exist_ok=True)
    _EVIDENCE_DIR = directory
    return directory


def _sync_message(page):
    """Строка синхронизации: подробный <p> или компактный <span> (sm:inline)."""
    return page.locator("p, span").filter(has_text="Снимок готовности").first


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("status", STATUSES)
def test_recovery_capture_readback_is_visible_and_honest(web_stack, provider, status) -> None:
    page = web_stack.page
    calls = _install_routes(page, provider, status)
    terminal = _fixture(provider, status)
    capture = terminal["result"]["recovery_capture"]

    errors_before = len(web_stack.js_errors)
    try:
        page.goto(f"{web_stack.web_base}/dashboard", wait_until="domcontentloaded")
        # Провайдер выбран и настроен — значит перехват /api/sync/providers сработал.
        source_select = page.get_by_label("Источник синхронизации")
        source_select.wait_for(state="visible", timeout=60_000)
        expect(source_select).to_have_value(provider, timeout=60_000)
        button = page.get_by_title(f"Синхронизировать с {PROVIDER_LABELS[provider]}")
        button.wait_for(state="visible", timeout=60_000)
        expect(button).to_be_enabled(timeout=60_000)
        button.click()

        message = _sync_message(page)
        message.wait_for(state="visible", timeout=60_000)
        text = message.inner_text().strip()

        # Polling-путь пройден: POST один, GET минимум дважды (running → terminal).
        assert calls["providers"] >= 1, calls
        assert calls["post"] == 1, calls
        assert calls["get"] >= 2, f"polling не дошёл до terminal: {calls}"

        # Человеко-читаемый статус.
        assert STATUS_TEXTS[status] in text, text

        # D4: отказ capture делает терминальный ответ частичным — UI обязан это показать.
        if status == "capture_failed":
            assert "частично" in text, text
            assert terminal["sync_state"] == terminal["result"]["sync_state"] == "partial"

        # Время: локальное атлета, либо честный fallback при null.
        if capture["observed_at_local"]:
            assert "23.07" in text and "08:00" in text, text
            assert "время не определено" not in text, text
        else:
            assert "время не определено" in text, text

        # Причина для проблемных состояний — человеко-читаемая, не код.
        if status in PROBLEM_STATUSES:
            assert any(phrase in text for phrase in REASON_TEXTS[status]), text
        else:
            assert "причина не уточнена" not in text, text

        # Идентификаторы, машинные коды, сырой error и пути в UI не попадают.
        for forbidden in FORBIDDEN_IN_UI:
            assert forbidden not in text, f"в UI утекло: {forbidden}\n{text}"

        new_errors = web_stack.js_errors[errors_before:]
        assert new_errors == [], new_errors

        evidence = _evidence_dir()
        (evidence / f"{provider}_{status}.txt").write_text(text + "\n", encoding="utf-8")
        page.screenshot(path=str(evidence / f"{provider}_{status}.png"), full_page=False)
    finally:
        page.unroute(JOB_URL)
        page.unroute(PROVIDERS_URL)
