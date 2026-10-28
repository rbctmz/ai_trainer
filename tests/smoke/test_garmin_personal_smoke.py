"""Контракт live-smoke для Garmin Personal API (scripts/garmin_personal_smoke.py).

Скрипт ходит в живой Garmin, поэтому проверяется на локальной HTTP-заглушке:
контракт token-эндпоинта (JWT строкой), классификация лимитов диапазонов дат,
сверка ``activityId`` с локальной БД (ADR-0008), маскирование секретов и коды
выхода. Живой прогон остаётся за владельцем ключа.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import threading
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, urlparse
import zipfile
import io

import pytest

pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "garmin_personal_smoke.py"
API_KEY = "test-key"


def _load_module():
    spec = importlib.util.spec_from_file_location("garmin_personal_smoke", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["garmin_personal_smoke"] = module
    spec.loader.exec_module(module)
    return module


def _jwt(*, seconds: int = 24 * 3600) -> str:
    def _segment(payload: dict) -> str:
        raw = json.dumps(payload).encode()
        return urlsafe_b64encode(raw).decode().rstrip("=")

    header = _segment({"alg": "none", "typ": "JWT"})
    body = _segment({"exp": (datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)).timestamp()})
    return f"{header}.{body}.signature"


class _StubHandler(BaseHTTPRequestHandler):
    """Мини-эмуляция Personal API: только те ответы, которые читает smoke."""

    db_activity_id = "999"

    def log_message(self, *args) -> None:  # noqa: A003 - глушим шум сервера
        return

    def _body(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, payload) -> None:
        self._body(status, json.dumps(payload).encode(), "application/json")

    def do_POST(self) -> None:  # noqa: N802 - имя метода HTTP
        if not self.path.endswith("/personal-api/personal-api-key/token"):
            self._json(404, {"error": "unknown token path"})
            return
        if self.headers.get("Authorization") != f"ApiKey {API_KEY}":
            self._json(401, {"error": "bad key"})
            return
        self._body(200, _jwt().encode(), "text/plain")

    def do_GET(self) -> None:  # noqa: N802 - имя метода HTTP
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        if path == "/userprofile-service/userprofile/settings":
            self._json(200, {"measurementSystem": "metric", "firstDayOfWeek": {"dayId": 1}})
        elif path == "/activitylist-service/activities/search/activities":
            self._json(
                200,
                [
                    {"activityId": 111, "activityTypeDTO": {"typeKey": "running"}},
                    {"activityId": 222, "activityTypeDTO": {"typeKey": "cycling"}},
                ],
            )
        elif path.startswith("/activity-service/activity/"):
            activity_id = path.rsplit("/", 1)[-1]
            if activity_id == "111":
                self._json(
                    200,
                    {
                        "activityId": 111,
                        "activityTypeDTO": {"typeKey": "running"},
                        "summaryDTO": {
                            "distance": 10000.0,
                            "duration": 3000.0,
                            "averageHR": 150,
                            "calories": 700,
                            "trainingEffect": 3.4,
                            "trainingStressScore": 55.0,
                        },
                    },
                )
            else:
                self._json(404, {"error": "not found"})
        elif path == "/usersummary-service/v2/dailysummaries":
            self._json(200, {"data": [{"calendarDate": "2026-10-01"}] * 3})
        elif path == "/sleep-service/sleep/dailySleep":
            # Живой Personal API отдаёт DTO в корне, без обёртки dailySleepDTO.
            self._json(
                200,
                {
                    "calendarDate": "2026-10-25",
                    "sleepTimeSeconds": 27000,
                    "deepSleepSeconds": 4000,
                    "lightSleepSeconds": 15000,
                    "remSleepSeconds": 6000,
                    "awakeSleepSeconds": 1800,
                    "sleepScores": {"overall": {"value": 80}},
                },
            )
        elif path == "/sleep-service/sleep/dailySleepSummariesByDate":
            start = datetime.fromisoformat(query["startDate"][0]).date()
            end = datetime.fromisoformat(query["endDate"][0]).date()
            if (end - start).days + 1 > 31:
                self._json(400, {"error": "range too large"})
            else:
                self._json(200, [{"calendarDate": "2026-10-01"}])
        elif path.startswith("/hrv-service/hrv/daily/"):
            self._json(200, {"userProfilePk": 1, "hrvSummaries": [{}, {}]})
        elif path == "/wellness-service/wellness/bodyBattery/reports/daily":
            self._json(200, [{"date": "2026-10-01"}, {"date": "2026-10-02"}])
        else:
            self._json(404, {"error": "unknown path"})


@pytest.fixture()
def stub_api() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _make_db(path: Path, garmin_ids: list[str]) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE activity_provider_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_activity_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_activity_id TEXT NOT NULL,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for external_id in garmin_ids:
            connection.execute(
                "INSERT INTO activity_provider_links "
                "(canonical_activity_id, provider, provider_activity_id) VALUES (?, 'garmin', ?)",
                (f"canonical_{external_id}", external_id),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def _state(module, base_url: str, db_path: Path):
    return module.SmokeState(
        api_key=API_KEY,
        base_url=base_url,
        timeout=5.0,
        delay=0.0,
        db_path=db_path,
        secrets=[API_KEY],
    )


def test_run_smoke_reaches_all_probes_against_stub(stub_api: str, tmp_path: Path):
    module = _load_module()
    db_path = _make_db(tmp_path / "db.sqlite", ["111", "222"])
    results = module.run_smoke(_state(module, stub_api, db_path), skip_fit=True)
    by_key = {result.key: result for result in results}

    assert [result.status for result in results].count("FAIL") == 0
    assert by_key["token"].status == "PASS"
    assert "24" in by_key["token"].detail or "23" in by_key["token"].detail
    assert by_key["activity_id_namespace"].status == "PASS"
    assert by_key["activity_summary"].status == "PASS"
    assert by_key["daily_summaries_90d"].status == "PASS"
    assert by_key["sleep_window_cap"].status == "PASS", by_key["sleep_window_cap"].detail
    assert by_key["sleep_daily_fields"].status == "PASS"
    assert "плоский DTO" in by_key["sleep_daily_fields"].detail
    assert by_key["fit_download"].status == "SKIP"


def test_namespace_warns_when_db_ids_do_not_match(stub_api: str, tmp_path: Path):
    module = _load_module()
    db_path = _make_db(tmp_path / "db.sqlite", ["999"])
    results = module.run_smoke(_state(module, stub_api, db_path), skip_fit=True)
    namespace = {result.key: result for result in results}["activity_id_namespace"]

    assert namespace.status == "WARN"
    assert "ADR-0008" in namespace.detail


def test_namespace_skips_without_local_database(stub_api: str, tmp_path: Path):
    module = _load_module()
    results = module.run_smoke(_state(module, stub_api, tmp_path / "missing.sqlite"), skip_fit=True)
    namespace = {result.key: result for result in results}["activity_id_namespace"]

    assert namespace.status == "SKIP"


def test_failed_token_marks_probe_fail_and_skips_dependents(stub_api: str, tmp_path: Path):
    module = _load_module()
    state = _state(module, stub_api, tmp_path / "db.sqlite")
    state.api_key = "wrong-key"
    results = module.run_smoke(state, skip_db=True, skip_fit=True)
    by_key = {result.key: result for result in results}

    assert by_key["token"].status == "FAIL"
    assert by_key["profile"].status == "SKIP"


def test_secrets_are_redacted_from_details():
    module = _load_module()
    assert module._redact("before SECRETVALUE after", ["SECRETVALUE"]) == "before *** after"
    # короткие строки не считаются секретом, иначе маскируется любой текст
    assert module._redact("abc def", ["abc"]) == "abc def"
    assert module._snippet(b"boom SECRETVALUE", ["SECRETVALUE"]) == "boom ***"


def test_jwt_expiration_is_parsed_from_payload():
    module = _load_module()
    expires_at = module._jwt_expires_at(_jwt(seconds=3600))
    remaining = (expires_at - datetime.now(tz=timezone.utc)).total_seconds()
    assert 3500 < remaining <= 3600


def test_non_jwt_token_response_is_rejected():
    module = _load_module()
    with pytest.raises(module.SmokeError):
        module._jwt_expires_at("not-a-jwt")


def test_api_key_resolution_prefers_explicit_then_env(monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "from-env")
    assert module.resolve_api_key("explicit") == "explicit"
    assert module.resolve_api_key(None) == "from-env"
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY")
    with pytest.raises(module.SmokeError):
        module.resolve_api_key(None)


def test_main_without_key_returns_config_error(monkeypatch: pytest.MonkeyPatch, capsys):
    module = _load_module()
    # .env репозитория может содержать настоящий ключ — тест не должен его читать.
    monkeypatch.setattr(module, "_load_dotenv", lambda: None)
    monkeypatch.delenv("GARMIN_PERSONAL_API_KEY", raising=False)
    assert module.main([]) == 2
    assert "ключ не найден" in capsys.readouterr().err


def test_zip_payload_without_fit_is_reported_as_warn(stub_api: str, tmp_path: Path, monkeypatch):
    module = _load_module()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "no fit here")
    state = _state(module, stub_api, _make_db(tmp_path / "db.sqlite", ["111"]))
    state.activity_id = 111
    module._probe_token(state)
    original = _StubHandler.do_GET

    def do_GET(self):  # noqa: N802 - подмена одного маршрута
        if self.path.startswith("/download-service/files/activity/"):
            payload = buffer.getvalue()
            self._body(200, payload, "application/zip")
            return
        original(self)

    monkeypatch.setattr(_StubHandler, "do_GET", do_GET)
    status, detail = module._probe_fit(state)
    assert status == "WARN"
    assert "нет .fit" in detail
