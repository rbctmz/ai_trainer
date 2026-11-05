#!/usr/bin/env python3
"""Read-only live smoke для Garmin Connect Personal API.

Проверяет то, что нельзя установить по документации (см.
`docs/garmin_personal_api_study.md`, раздел 11):

1. ключ обменивается на bearer-токен, и срок жизни токена действительно ~24 ч;
2. ``activityId`` из Personal API совпадают с id в наших ``activity_provider_links``
   — иначе сломается дедупликация Garmin ↔ Intervals (ADR-0008, п.2);
3. какие поля сводки активности реально заполнены;
4. фактические лимиты диапазонов дат (28/31 день, «до 1 года»);
5. скачивается ли FIT и читается ли он ``fitparse``.

Скрипт только читает: не пишет в БД, не печатает ключ, токен и значения
health-метрик — только наличие полей, количества строк и несколько id.

Запуск::

    export GARMIN_PERSONAL_API_KEY=...   # или строка в .env
    python scripts/garmin_personal_smoke.py
    python scripts/garmin_personal_smoke.py --json
    python scripts/garmin_personal_smoke.py --activity-id 123456789 --skip-db

Коды выхода: 0 — нет FAIL, 1 — есть FAIL, 2 — конфигурация (нет ключа).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sqlite3
import sys
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

DEFAULT_BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
API_KEY_ENV_VAR = "GARMIN_PERSONAL_API_KEY"
BASE_URL_ENV_VAR = "GARMIN_PERSONAL_API_BASE_URL"
API_KEY_PAGE = "https://connect.garmin.com/app/settings/personalApiToken"
USER_AGENT = "ai-trainer-garmin-personal-smoke/1.0"
# download-service отдаёт ZIP только при таком Accept (проверено живьём, иначе HTTP 406).
DOWNLOAD_ACCEPT = "application/zip, application/x-zip-compressed, application/octet-stream"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_DELAY_SECONDS = 0.4
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Поля сводки активности, на которые опираются наши метрики и TSS-каскад.
SUMMARY_FIELDS = (
    "distance",
    "duration",
    "elapsedDuration",
    "averageHR",
    "maxHR",
    "calories",
    "trainingEffect",
    "trainingStressScore",
    "activityTrainingLoad",
    "normalizedPower",
    "vO2MaxValue",
)
SUMMARY_CORE_FIELDS = ("distance", "duration", "averageHR", "calories")
# Стадии сна: в Personal API они лежат в корне ответа, а наш код ждёт обёртку
# dailySleepDTO (как у garminconnect) — форму ответа проверяет sleep_daily_fields.
SLEEP_STAGE_FIELDS = (
    "sleepTimeSeconds",
    "deepSleepSeconds",
    "lightSleepSeconds",
    "remSleepSeconds",
    "awakeSleepSeconds",
)
# Поля FIT-потока, которые нам реально нужны для собственных расчётов.
FIT_INTERESTING_FIELDS = (
    "timestamp",
    "heart_rate",
    "power",
    "cadence",
    "enhanced_speed",
    "distance",
    "position_lat",
)


class SmokeError(RuntimeError):
    """Ошибка конфигурации или протокола, которую видит оператор."""


class SmokeSkipped(SmokeError):
    """Проверка невозможна в текущем окружении (нет БД, нет ключа и т.п.)."""


class SmokeHttpError(SmokeError):
    """Неуспешный HTTP-ответ на обязательный запрос."""

    def __init__(self, status: int, path: str, snippet: str = "") -> None:
        self.status = status
        self.path = path
        self.message = f"HTTP {status} {path}" + (f": {snippet}" if snippet else "")
        super().__init__(self.message)


@dataclass(frozen=True)
class ProbeResult:
    key: str
    status: str
    detail: str


@dataclass(frozen=True)
class TokenInfo:
    access_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


@dataclass
class SmokeState:
    """Всё, что пробы передают друг другу по цепочке."""

    api_key: str
    base_url: str
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    delay: float = DEFAULT_DELAY_SECONDS
    db_path: Path = REPO_ROOT / "ai_trainer.db"
    activity_id: int | None = None
    window_days: int = 60
    secrets: list[str] = field(default_factory=list)
    token: TokenInfo | None = None
    client: PersonalApiClient | None = None
    api_activity_ids: list[str] = field(default_factory=list)
    api_activity_types: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _local_date() -> date:
    return datetime.now().date()


def _iso(value: date) -> str:
    return value.isoformat()


def _redact(text: str, secrets: Sequence[str]) -> str:
    """Вырезать из диагностического текста ключ и токен."""
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    return text


def _snippet(body: bytes, secrets: Sequence[str], *, limit: int = 160) -> str:
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    text = " ".join(text.split())
    return _redact(text[:limit], secrets)


def _jwt_expires_at(token: str) -> datetime:
    """Достать ``exp`` из JWT без проверки подписи (подпись проверит сервер)."""
    parts = token.split(".")
    if len(parts) < 2:
        raise SmokeError(
            "token-эндпоинт вернул не JWT: ожидается голая строка токена, "
            "см. docs/garmin_personal_api_study.md §2"
        )
    encoded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        expires = float(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SmokeError("в ответе токена нет JWT-claim 'exp'") from exc
    return datetime.fromtimestamp(expires, tz=timezone.utc)


def _dig(payload: Any, *path: str) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _load_dotenv() -> None:
    """Подхватить repo-root ``.env``, не перекрывая уже заданные переменные."""
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv есть в requirements.txt
        return
    load_dotenv(env_path, override=False)


def resolve_api_key(explicit: str | None) -> str:
    """Найти ключ: аргумент → окружение → ``.env`` (уже загруженный)."""
    if explicit is not None:
        key = explicit.strip()
        if not key:
            raise SmokeError("--api-key передан пустым")
        return key
    key = (os.getenv(API_KEY_ENV_VAR) or "").strip()
    if key:
        return key
    raise SmokeError(
        f"ключ не найден: задайте {API_KEY_ENV_VAR} в окружении или .env.\n"
        f"Создать ключ (30/90/180/365 дней): {API_KEY_PAGE}"
    )


def _send(method: str, url: str, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    request = urlrequest.Request(url, method=method, headers=dict(headers))
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=int(response.status), body=response.read())
    except urlerror.HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        return HttpResponse(status=int(exc.code), body=body)
    except urlerror.URLError as exc:
        raise SmokeError(f"сетевая ошибка: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SmokeError(f"таймаут запроса ({timeout:.0f} с)") from exc


class PersonalApiClient:
    """Минимальный GET-клиент Personal API на stdlib (как ``services/intervals_icu.py``).

    Ретраи только на 429/5xx: публичных лимитов Garmin не документирует, поэтому
    запросы идут последовательно с паузой ``delay`` между вызовами.
    """

    def __init__(
        self,
        access_token: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        delay: float = DEFAULT_DELAY_SECONDS,
        retries: int = 2,
        secrets: Sequence[str] = (),
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.delay = max(0.0, delay)
        self.retries = max(0, retries)
        self._secrets = list(secrets)
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        }

    def _url(self, path: str, params: Mapping[str, Any] | None) -> str:
        url = f"{self.base_url}{path}"
        if not params:
            return url
        cleaned = {key: value for key, value in params.items() if value is not None}
        if not cleaned:
            return url
        return f"{url}?{urlparse.urlencode(cleaned)}"

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> HttpResponse:
        url = self._url(path, params)
        response = HttpResponse(status=0, body=b"")
        for attempt in range(self.retries + 1):
            if self.delay:
                time.sleep(self.delay)
            response = _send(method, url, self._headers, self.timeout)
            if response.status not in RETRY_STATUSES or attempt >= self.retries:
                return response
            time.sleep(float(2 ** attempt))
        return response

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        response = self.request("GET", path, params)
        if response.status != 200:
            raise SmokeHttpError(response.status, path, _snippet(response.body, self._secrets))
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SmokeError(f"ответ {path} не является JSON") from exc

    def get_bytes(self, path: str) -> bytes:
        # Проверено живьём: download-service отдаёт файл только при Accept, который
        # содержит application/x-zip-compressed (или */*); application/json и
        # application/octet-stream дают HTTP 406 NotAcceptableException.
        headers = dict(self._headers)
        headers["Accept"] = DOWNLOAD_ACCEPT
        if self.delay:
            time.sleep(self.delay)
        response = _send("GET", self._url(path, None), headers, self.timeout)
        if response.status != 200:
            raise SmokeHttpError(response.status, path, _snippet(response.body, self._secrets))
        return response.body


def obtain_token(
    *,
    api_key: str,
    base_url: str,
    timeout: float,
    secrets: Sequence[str],
) -> TokenInfo:
    """Обменять Personal API key на bearer-токен (тело ответа — голая JWT-строка)."""
    url = f"{base_url.rstrip('/')}{TOKEN_PATH}"
    headers = {
        "Accept": "*/*",
        "Authorization": f"ApiKey {api_key}",
        "User-Agent": USER_AGENT,
    }
    response = _send("POST", url, headers, timeout)
    if response.status != 200:
        raise SmokeHttpError(response.status, TOKEN_PATH, _snippet(response.body, secrets))
    token = response.body.decode("utf-8", errors="replace").strip()
    if not token:
        raise SmokeError("token-эндпоинт вернул пустое тело")
    return TokenInfo(access_token=token, expires_at=_jwt_expires_at(token))


def _load_garmin_link_ids(db_path: Path, *, limit: int = 500) -> list[str]:
    """Прочитать id Garmin-активностей из нашей БД, не мешая работающему приложению."""
    if not db_path.is_file():
        raise SmokeSkipped(f"БД не найдена: {db_path}")
    try:
        connection = sqlite3.connect(
            f"file:{urlparse.quote(str(db_path))}?mode=ro", uri=True, timeout=5.0
        )
    except sqlite3.Error as exc:
        raise SmokeSkipped(f"БД не открывается на чтение: {exc}") from exc
    try:
        rows = connection.execute(
            "SELECT provider_activity_id FROM activity_provider_links "
            "WHERE provider = 'garmin' AND provider_activity_id IS NOT NULL "
            "ORDER BY imported_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise SmokeSkipped(f"таблица activity_provider_links недоступна: {exc}") from exc
    finally:
        connection.close()
    ordered: list[str] = []
    for (value,) in rows:
        text = str(value).strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _require_client(state: SmokeState) -> PersonalApiClient:
    if state.client is None:
        raise SmokeSkipped("нет клиента: токен не получен (см. пробу token)")
    return state.client


def _probe_token(state: SmokeState) -> tuple[str, str]:
    token = obtain_token(
        api_key=state.api_key,
        base_url=state.base_url,
        timeout=state.timeout,
        secrets=state.secrets,
    )
    state.token = token
    state.secrets.append(token.access_token)
    state.client = PersonalApiClient(
        token.access_token,
        base_url=state.base_url,
        timeout=state.timeout,
        delay=state.delay,
        secrets=state.secrets,
    )
    remaining_hours = (token.expires_at - _now()).total_seconds() / 3600
    status = "PASS" if remaining_hours > 23 else "WARN"
    return status, f"токен получен, до истечения {remaining_hours:.1f} ч (ожидаем ~24 ч)"


def _probe_profile(state: SmokeState) -> tuple[str, str]:
    payload = _require_client(state).get_json("/userprofile-service/userprofile/settings")
    units = _dig(payload, "measurementSystem")
    if units is None:
        return "WARN", "профиль получен, но measurementSystem отсутствует"
    return "PASS", f"неявный скоуп аккаунта подтверждён (measurementSystem={units!r})"


def _activity_type_key(item: Any) -> str:
    """Тип активности: в поиске поле ``activityType``, в сводке — ``activityTypeDTO``."""
    for path in (("activityType", "typeKey"), ("activityTypeDTO", "typeKey")):
        value = _dig(item, *path)
        if value:
            return str(value)
    return "?"


def _probe_activities(state: SmokeState) -> tuple[str, str]:
    client = _require_client(state)
    start = _local_date() - timedelta(days=max(1, state.window_days))
    payload = client.get_json(
        "/activitylist-service/activities/search/activities",
        {"start": 0, "limit": 10, "startDate": _iso(start)},
    )
    items = payload if isinstance(payload, list) else []
    ids = [str(item["activityId"]) for item in items if item.get("activityId") is not None]
    state.api_activity_ids = ids
    state.api_activity_types = [_activity_type_key(item) for item in items[:5]]
    if not ids:
        raise SmokeSkipped(
            f"активностей за {state.window_days} дн. нет — сводку и FIT проверить нечем"
        )
    if state.activity_id is None:
        state.activity_id = int(ids[0])
    types = ", ".join(state.api_activity_types) or "—"
    return "PASS", f"{len(ids)} активностей за {state.window_days} дн.; первый id={ids[0]} ({types})"


def _probe_activity_namespace(state: SmokeState) -> tuple[str, str]:
    """Главная проверка: id Personal API должны совпадать с нашими Garmin-id."""
    client = _require_client(state)
    db_ids = _load_garmin_link_ids(state.db_path)
    if not db_ids:
        raise SmokeSkipped(
            f"в {state.db_path.name} нет provider='garmin' связей — сверять не с чем"
        )
    api_ids = set(state.api_activity_ids)
    overlap = api_ids & set(db_ids)
    direct: list[tuple[str, int]] = []
    for activity_id in db_ids[:3]:
        response = client.request("GET", f"/activity-service/activity/{activity_id}")
        direct.append((activity_id, response.status))
    readable = [activity_id for activity_id, status in direct if status == 200]
    summary = (
        f"garmin-связей в БД: {len(db_ids)}; пересечение с последними 10 из API: {len(overlap)}; "
        f"прямое чтение id из БД: "
        + ", ".join(f"{activity_id}→HTTP {status}" for activity_id, status in direct)
    )
    if readable or overlap:
        return "PASS", summary + " — namespace совпадает"
    return "WARN", (
        summary
        + " — ни один id из БД не читается. Возможен иной namespace: сверьте id вручную, "
        "дедупликация Garmin↔Intervals (ADR-0008) опирается на это равенство"
    )


def _probe_activity_summary(state: SmokeState) -> tuple[str, str]:
    if state.activity_id is None:
        raise SmokeSkipped("нет id активности для проверки сводки")
    client = _require_client(state)
    payload = client.get_json(f"/activity-service/activity/{state.activity_id}")
    summary = _dig(payload, "summaryDTO")
    if not isinstance(summary, dict):
        summary = payload if isinstance(payload, dict) else {}
    filled = [name for name in SUMMARY_FIELDS if summary.get(name) not in (None, "", [])]
    empty = [name for name in SUMMARY_FIELDS if name not in filled]
    empty_core = [name for name in SUMMARY_CORE_FIELDS if name in empty]
    kind = _dig(payload, "activityTypeDTO", "typeKey")
    detail = f"id={state.activity_id} ({kind}); заполнено {len(filled)}/{len(SUMMARY_FIELDS)}"
    if empty:
        detail += f"; пусто: {', '.join(empty)}"
    if empty_core:
        return "WARN", detail + " — не заполнены базовые поля"
    return "PASS", detail


def _probe_daily_summaries(state: SmokeState) -> tuple[str, str]:
    client = _require_client(state)
    end = _local_date()
    start = end - timedelta(days=89)
    response = client.request(
        "GET",
        "/usersummary-service/v2/dailysummaries",
        {"startDate": _iso(start), "endDate": _iso(end)},
    )
    if response.status != 200:
        return (
            "WARN",
            f"90-дневный диапазон отклонён (HTTP {response.status}) — "
            "bootstrap придётся чанковать; заявленный лимит «до 1 года» не подтверждён",
        )
    payload = response.json() or {}
    rows = payload.get("data") if isinstance(payload, dict) else None
    count = len(rows) if isinstance(rows, list) else 0
    return "PASS", f"90 дней одним запросом: {count} дневных сводок"


def _probe_sleep_window(state: SmokeState) -> tuple[str, str]:
    client = _require_client(state)
    outcomes: list[tuple[int, int, int | None]] = []
    for days in (31, 40):
        end = _local_date()
        start = end - timedelta(days=days - 1)
        response = client.request(
            "GET",
            "/sleep-service/sleep/dailySleepSummariesByDate",
            {"startDate": _iso(start), "endDate": _iso(end)},
        )
        count = None
        if response.status == 200:
            payload = response.json()
            count = len(payload) if isinstance(payload, list) else 0
        outcomes.append((days, response.status, count))
    detail = "; ".join(
        f"{days} дн → HTTP {status}" + (f", {count} дней" if count is not None else "")
        for days, status, count in outcomes
    )
    ok31 = outcomes[0][1] == 200
    rejected40 = outcomes[1][1] != 200
    if ok31 and rejected40:
        return "PASS", detail + " — заявленный лимит 31 день подтверждён"
    if ok31:
        return "WARN", detail + " — лимит не enforced, можно брать окно шире"
    return "FAIL", detail


def _probe_sleep_daily_fields(state: SmokeState) -> tuple[str, str]:
    """Проверить форму ответа сна: нужные стадии и вложенность DTO."""
    client = _require_client(state)
    for offset in (1, 2, 3):
        day = _local_date() - timedelta(days=offset)
        response = client.request("GET", "/sleep-service/sleep/dailySleep", {"date": _iso(day)})
        if response.status != 200:
            raise SmokeHttpError(
                response.status,
                "/sleep-service/sleep/dailySleep",
                _snippet(response.body, state.secrets),
            )
        payload = response.json() or {}
        if not isinstance(payload, dict) or not payload:
            continue
        envelope = payload.get("dailySleepDTO")
        flat = envelope if isinstance(envelope, dict) and envelope else payload
        present = [name for name in SLEEP_STAGE_FIELDS if flat.get(name) is not None]
        if not present:
            continue
        shape = "обёртка dailySleepDTO" if flat is not payload else "плоский DTO в корне"
        has_score = isinstance(flat.get("sleepScores", payload.get("sleepScores")), dict)
        detail = (
            f"{day}: форма — {shape}; стадии {len(present)}/{len(SLEEP_STAGE_FIELDS)}"
            f" ({', '.join(present)}); sleepScores={'есть' if has_score else 'нет'}"
        )
        if flat is payload:
            detail += " — адаптеру нужно обернуть в dailySleepDTO"
        return "PASS", detail
    raise SmokeSkipped("нет данных сна за последние 1–3 дня — форму ответа не проверить")


def _probe_hrv(state: SmokeState) -> tuple[str, str]:
    client = _require_client(state)
    end = _local_date()
    start = end - timedelta(days=13)
    payload = client.get_json(f"/hrv-service/hrv/daily/{_iso(start)}/{_iso(end)}")
    summaries = _dig(payload, "hrvSummaries")
    count = len(summaries) if isinstance(summaries, list) else 0
    if count == 0:
        return "WARN", "эндпоинт ответил, но за 14 дней нет HRV-сводок"
    return "PASS", f"HRV за 14 дней: {count} дневных наблюдений"


def _probe_body_battery(state: SmokeState) -> tuple[str, str]:
    client = _require_client(state)
    end = _local_date()
    start = end - timedelta(days=30)
    payload = client.get_json(
        "/wellness-service/wellness/bodyBattery/reports/daily",
        {"startDate": _iso(start), "endDate": _iso(end)},
    )
    rows = payload if isinstance(payload, list) else []
    if not rows:
        return "WARN", "эндпоинт ответил, но за 31 день нет Body Battery"
    return "PASS", f"Body Battery за 31 день: {len(rows)} дневных отчётов"


def _probe_fit(state: SmokeState) -> tuple[str, str]:
    if state.activity_id is None:
        raise SmokeSkipped("нет id активности для скачивания FIT")
    client = _require_client(state)
    body = client.get_bytes(f"/download-service/files/activity/{state.activity_id}")
    buffer = io.BytesIO(body)
    if not zipfile.is_zipfile(buffer):
        return "WARN", f"ответ не ZIP ({len(body)} байт) — проверить формат вручную"
    with zipfile.ZipFile(buffer) as archive:
        names = archive.namelist()
        fits = [name for name in names if name.lower().endswith(".fit")]
        if not fits:
            return "WARN", f"в ZIP нет .fit-файла: {names}"
        payload = archive.read(fits[0])
    detail = f"ZIP: файлов {len(names)}, {fits[0]} — {len(payload)} байт"
    try:
        from fitparse import FitFile
    except ImportError:  # pragma: no cover - fitparse есть в requirements.txt
        raise SmokeSkipped(detail + "; fitparse не установлен")
    records = 0
    fields: set[str] = set()
    for message in FitFile(io.BytesIO(payload)).get_messages("record"):
        records += 1
        if records <= 5000:
            fields.update(
                fit_field.name for fit_field in message if fit_field.value is not None
            )
    found = [name for name in FIT_INTERESTING_FIELDS if name in fields]
    if records == 0:
        return "WARN", detail + "; в FIT нет record-сообщений"
    return "PASS", detail + f"; записей {records}, поля: {', '.join(found) or '—'}"


Probe = tuple[str, Callable[[SmokeState], tuple[str, str]]]


def _probes(*, skip_db: bool, skip_fit: bool) -> list[Probe]:
    probes: list[Probe] = [
        ("token", _probe_token),
        ("profile", _probe_profile),
        ("activities", _probe_activities),
    ]
    if skip_db:
        probes.append(("activity_id_namespace", _skip_probe("--skip-db")))
    else:
        probes.append(("activity_id_namespace", _probe_activity_namespace))
    probes.extend(
        [
            ("activity_summary", _probe_activity_summary),
            ("daily_summaries_90d", _probe_daily_summaries),
            ("sleep_window_cap", _probe_sleep_window),
            ("sleep_daily_fields", _probe_sleep_daily_fields),
            ("hrv_14d", _probe_hrv),
            ("body_battery_31d", _probe_body_battery),
        ]
    )
    if skip_fit:
        probes.append(("fit_download", _skip_probe("--skip-fit")))
    else:
        probes.append(("fit_download", _probe_fit))
    return probes


def _skip_probe(reason: str) -> Callable[[SmokeState], tuple[str, str]]:
    def _probe(_state: SmokeState) -> tuple[str, str]:
        raise SmokeSkipped(f"пропущено: {reason}")

    return _probe


def run_smoke(state: SmokeState, *, skip_db: bool = False, skip_fit: bool = False) -> list[ProbeResult]:
    """Выполнить пробы по порядку, изолируя падение одной от остальных."""
    results: list[ProbeResult] = []
    for key, probe in _probes(skip_db=skip_db, skip_fit=skip_fit):
        try:
            status, detail = probe(state)
        except SmokeSkipped as exc:
            results.append(ProbeResult(key, "SKIP", str(exc)))
        except SmokeHttpError as exc:
            results.append(ProbeResult(key, "FAIL", exc.message))
        except SmokeError as exc:
            results.append(ProbeResult(key, "FAIL", str(exc)))
        except Exception as exc:  # smoke не должен падать стеком на одной пробе
            results.append(ProbeResult(key, "FAIL", f"{type(exc).__name__}: {exc}"))
        else:
            results.append(ProbeResult(key, status, _redact(detail, state.secrets)))
    return results


def _format_text(results: Sequence[ProbeResult], state: SmokeState) -> str:
    counts = Counter(result.status for result in results)
    lines = [
        f"Garmin Personal API smoke — {_now().replace(microsecond=0).isoformat()}",
        f"base_url: {state.base_url}",
        f"БД: {state.db_path}",
        "",
    ]
    width = max(len(result.key) for result in results) if results else 10
    for result in results:
        lines.append(f"[{result.status:<4}] {result.key:<{width}}  {result.detail}")
    lines.extend(
        [
            "",
            f"Итог: {counts['PASS']} PASS, {counts['WARN']} WARN, "
            f"{counts['SKIP']} SKIP, {counts['FAIL']} FAIL",
        ]
    )
    if counts["FAIL"]:
        lines.append("Есть FAIL — результат не подтверждает пригодность Personal API.")
    elif counts["WARN"]:
        lines.append("FAIL нет; WARN требуют ручного вывода (см. docs/garmin_personal_api_study.md §11).")
    return "\n".join(lines)


def _format_json(results: Sequence[ProbeResult], state: SmokeState) -> str:
    counts = Counter(result.status for result in results)
    return json.dumps(
        {
            "generated_at": _now().replace(microsecond=0).isoformat(),
            "base_url": state.base_url,
            "database": str(state.db_path),
            "activity_id": state.activity_id,
            "ok": counts["FAIL"] == 0,
            "summary": {status: counts[status] for status in ("PASS", "WARN", "SKIP", "FAIL")},
            "results": [
                {"key": result.key, "status": result.status, "detail": result.detail}
                for result in results
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only live smoke для Garmin Connect Personal API.",
        epilog=f"Ключ создаётся вручную: {API_KEY_PAGE}",
    )
    parser.add_argument("--api-key", help="ключ (лучше через %s или .env)" % API_KEY_ENV_VAR)
    parser.add_argument(
        "--base-url",
        default=os.getenv(BASE_URL_ENV_VAR, DEFAULT_BASE_URL),
        help=f"по умолчанию {DEFAULT_BASE_URL}",
    )
    parser.add_argument("--db", default=str(REPO_ROOT / "ai_trainer.db"), help="SQLite кэш")
    parser.add_argument("--activity-id", type=int, help="проверить конкретную активность")
    parser.add_argument(
        "--days", type=int, default=60, help="окно поиска активностей, дней (по умолчанию 60)"
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="таймаут запроса, с"
    )
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="пауза между запросами, с"
    )
    parser.add_argument("--skip-db", action="store_true", help="не сверять id с локальной БД")
    parser.add_argument("--skip-fit", action="store_true", help="не скачивать FIT")
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    _load_dotenv()
    args = _parse_args(argv)
    try:
        api_key = resolve_api_key(args.api_key)
    except SmokeError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 2
    if args.api_key is not None:
        print(
            "предупреждение: ключ в --api-key виден в истории shell и списке процессов; "
            f"используйте {API_KEY_ENV_VAR}",
            file=sys.stderr,
        )
    state = SmokeState(
        api_key=api_key,
        base_url=str(args.base_url).rstrip("/"),
        timeout=max(1.0, float(args.timeout)),
        delay=max(0.0, float(args.delay)),
        db_path=Path(args.db).expanduser().resolve(),
        activity_id=args.activity_id,
        window_days=max(1, int(args.days)),
        secrets=[api_key],
    )
    results = run_smoke(state, skip_db=bool(args.skip_db), skip_fit=bool(args.skip_fit))
    print(_format_json(results, state) if args.json else _format_text(results, state))
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
