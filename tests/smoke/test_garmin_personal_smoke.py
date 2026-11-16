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
    # Даже ошибочно короткий явно выбранный ключ остаётся секретом.
    assert module._redact("abc def", ["abc"]) == "*** def"
    assert module._redact("long-abc-secret", ["abc", "long-abc-secret"]) == "***"


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


@pytest.mark.parametrize("padding", [0, 100, 130, 159, 200])
@pytest.mark.parametrize("phase", ["token", "json", "download", "sleep"])
def test_error_body_never_enters_public_diagnostics(monkeypatch, padding, phase):
    module = _load_module()
    secret = "DUMMY_CREDENTIAL_FOR_REVIEW_" + "z" * 64
    body = ("HEALTH_CANARY_87 " + "x" * padding + secret).encode()
    state = module.SmokeState(api_key=secret, base_url="http://unused.invalid", secrets=[secret])
    state.client = module.PersonalApiClient(secret, delay=0, retries=0, secrets=[secret])
    monkeypatch.setattr(module, "_send", lambda *args: module.HttpResponse(400, body))
    actions = {
        "token": lambda: module.obtain_token(api_key=secret, base_url=state.base_url,
                                              timeout=1, secrets=state.secrets),
        "json": lambda: state.client.get_json("/synthetic"),
        "download": lambda: state.client.get_bytes("/synthetic"),
        "sleep": lambda: module._probe_sleep_daily_fields(state),
    }

    def probe(_state):
        actions[phase]()
        return "PASS", "unexpected"

    monkeypatch.setattr(module, "_probes", lambda **kwargs: [(phase, probe)])
    result = module.run_smoke(state)
    assert result[0].status == "FAIL"
    for text in (module._format_text(result, state), module._format_json(result, state)):
        assert "HEALTH_CANARY" not in text
        assert secret[:12] not in text
        assert "HTTP 400" in text


def test_arbitrary_exception_payload_is_not_printed(monkeypatch):
    module = _load_module()
    state = module.SmokeState(api_key=API_KEY, base_url="http://unused.invalid", secrets=[API_KEY])

    def probe(_state):
        raise ValueError("HEALTH_CANARY_87 " + API_KEY)

    monkeypatch.setattr(module, "_probes", lambda **kwargs: [("synthetic", probe)])
    result = module.run_smoke(state)
    assert result[0].status == "FAIL"
    assert "ValueError" in result[0].detail
    assert "HEALTH_CANARY" not in module._format_json(result, state)
    assert API_KEY not in module._format_text(result, state)


def test_state_repr_hides_credentials():
    module = _load_module()
    state = module.SmokeState(api_key="DUMMY_API_KEY", base_url="https://example.invalid",
                              secrets=["DUMMY_API_KEY", "DUMMY_BEARER_TOKEN"])
    assert "DUMMY_API_KEY" not in repr(state)
    assert "DUMMY_BEARER_TOKEN" not in repr(state)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_unrelated_sleep_window_error_never_confirms_limit(status):
    module = _load_module()

    class Client:
        calls = 0

        def request(self, *args):
            self.calls += 1
            return module.HttpResponse(200 if self.calls == 1 else status, b"[]")

    state = module.SmokeState(api_key=API_KEY, base_url="https://unused.invalid")
    state.client = Client()
    result, detail = module._probe_sleep_window(state)
    assert result != "PASS", detail


@pytest.mark.parametrize("body", [b'{}', b'{"error":"invalid request"}'])
def test_generic_bad_request_does_not_confirm_sleep_limit(body):
    module = _load_module()

    class Client:
        calls = 0

        def request(self, *args):
            self.calls += 1
            return module.HttpResponse(200, b"[]") if self.calls == 1 else module.HttpResponse(400, body)

    state = module.SmokeState(api_key=API_KEY, base_url="https://unused.invalid")
    state.client = Client()
    assert module._probe_sleep_window(state)[0] == "WARN"


def test_sleep_cap_checks_adjacent_inclusive_windows():
    module = _load_module()
    windows = []

    class Client:
        def request(self, method, path, params):
            start = datetime.fromisoformat(params["startDate"]).date()
            end = datetime.fromisoformat(params["endDate"]).date()
            days = (end - start).days + 1
            windows.append((days, end))
            return module.HttpResponse(200, b"[]") if days <= 31 else module.HttpResponse(400, b'{"error":"range too large"}')

    state = module.SmokeState(api_key=API_KEY, base_url="https://unused.invalid")
    state.client = Client()
    assert module._probe_sleep_window(state)[0] == "PASS"
    assert [days for days, _ in windows] == [31, 32]
    assert windows[0][1] == windows[1][1]


def test_database_selection_uses_env_and_explicit_path(monkeypatch, tmp_path):
    module = _load_module()
    selected = tmp_path / "selected.sqlite"
    explicit = tmp_path / "explicit.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(selected))
    assert Path(module._parse_args([]).db) == selected
    assert Path(module._parse_args(["--db", str(explicit)]).db) == explicit
    monkeypatch.setenv("DATABASE_PATH", "")
    assert Path(module._parse_args(["--db", str(explicit)]).db) == explicit
    assert not selected.exists() and not explicit.exists()


def test_platform_database_default_does_not_use_checkout(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    selected = Path(module._parse_args([]).db)
    assert selected != module.REPO_ROOT / "ai_trainer.db"
    assert selected.is_relative_to(tmp_path)
    assert not selected.exists()


def test_skip_db_does_not_require_valid_database_selection(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("DATABASE_PATH", "")
    assert module._parse_args(["--skip-db"]).db is None


def test_namespace_read_is_query_only_and_preserves_database(tmp_path, monkeypatch):
    module = _load_module()
    db_path = _make_db(tmp_path / "fixture.sqlite", ["111"])
    before = db_path.read_bytes()
    queries = []
    connect = sqlite3.connect

    def traced(*args, **kwargs):
        assert "mode=ro" in args[0] and kwargs.get("uri")
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(module.sqlite3, "connect", traced)
    assert module._load_garmin_link_ids(db_path) == ["111"]
    assert any("query_only" in q.lower() for q in queries)
    assert db_path.read_bytes() == before


def test_http_200_with_other_activity_id_is_not_namespace_proof(tmp_path):
    module = _load_module()

    class Client:
        def request(self, *args):
            return module.HttpResponse(200, b'{"activityId":999}')

    state = module.SmokeState(api_key=API_KEY, base_url="https://unused.invalid",
                              db_path=_make_db(tmp_path / "fixture.sqlite", ["111"]))
    state.client = Client()
    assert module._probe_activity_namespace(state)[0] == "WARN"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_cross_origin_redirect_never_receives_credentials(method):
    module = _load_module()
    received = []

    class Destination(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):  # noqa: N802
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

    destination = ThreadingHTTPServer(("127.0.0.1", 0), Destination)

    class Source(Destination):
        def do_GET(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{destination.server_port}/target")
            self.end_headers()

        do_POST = do_GET

    source = ThreadingHTTPServer(("127.0.0.1", 0), Source)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (source, destination)]
    for thread in threads:
        thread.start()
    try:
        try:
            module._send(method, f"http://127.0.0.1:{source.server_port}/source",
                         {"Authorization": "Bearer DUMMY_ONLY"}, 2)
        except module.SmokeError:
            pass
        assert received == []
    finally:
        for server in (source, destination):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
