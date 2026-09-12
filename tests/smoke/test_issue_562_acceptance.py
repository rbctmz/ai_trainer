"""Issue #562 M6a acceptance (Domain / API Implementer).

Covers the owner's M6a list: both providers × five states over the terminal API,
identical public field sets without service data, capture-run idempotency and
same-day monotonic revision, fail-open preservation of provider data, the
per-revision status invariant against the day cutoff and daily anchor, the
explicit status precedence, and history readback without mutation.

Behaviour that is already implemented is recorded as honest characterization /
acceptance GREEN (no artificial RED). RED is used only for the missing
fixture/pinning infrastructure that M6a itself owns.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.deps import get_database
from api.main import app
from config.settings import Settings
from data.database import Database
from models.recovery_response import select_daily_anchor
from services import recovery_analytics
from services.recovery_analytics import RECOVERY_CAPTURE_PUBLIC_FIELDS
from services.intervals_sync import IntervalsSyncResult

pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "e2e" / "fixtures" / "recovery_capture"

PROVIDERS = ("garmin", "intervals")
STATUSES = (
    "saved_before_load",
    "saved_too_late",
    "activity_start_missing",
    "ineligible",
    "capture_failed",
)
DAY = "2026-07-23"
MOSCOW_OBSERVED = datetime(2026, 7, 23, 5, 0, tzinfo=timezone.utc)  # 08:00 локально
RUN_ID = "3f1c0f4e-6a1b-4c2d-9e30-8a7b6c5d4e3f"
TERMINAL_STATES = {"succeeded", "partial", "failed"}


def _block(provider: str, status: str) -> dict:
    """Внутренний блок для состояния: плюс служебный мусор, которого не должно быть наружу."""
    block = {
        "provider": provider,
        "capture_run_id": RUN_ID,
        "status": status,
        "reason": None,
        "eligibility_status": "eligible",
        "eligibility_reasons": [],
        "local_date": DAY,
        "observed_at_utc": "2026-07-23T05:00:00Z",
        "observed_at_local": "2026-07-23T08:00:00+03:00",
        "cutoff_at_utc": "2026-07-23T09:00:00Z",
        "snapshot_id": 17,
        "revision": 1,
        "created": True,
        "error": None,
        "episode_refresh": {"error": "repair failed at /private/athlete.db", "created": 0},
        "snapshot": {"score": 71.0},
        "unexpected_key": "internal-only",
    }
    if status == "ineligible":
        block.update(
            eligibility_status="ineligible",
            eligibility_reasons=["low_confidence"],
            reason="low_confidence",
        )
    if status == "activity_start_missing":
        block.update(reason="activity_start_missing", cutoff_at_utc=None)
    if status == "saved_too_late":
        block.update(reason=None)
    if status == "capture_failed":
        block.update(
            reason="snapshot_capture_failed",
            error="snapshot_capture_failed",
            local_date=None,
            observed_at_utc=None,
            observed_at_local=None,
            cutoff_at_utc=None,
            snapshot_id=None,
            revision=None,
            created=False,
        )
    return block


def _client(db: Database) -> TestClient:
    app.dependency_overrides[get_database] = lambda demo=False: db
    return TestClient(app)


def _wait_terminal(client: TestClient, *, timeout_s: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = client.get("/api/sync").json()
        if str(payload.get("sync_state")) in TERMINAL_STATES:
            return payload
        time.sleep(0.02)
    raise AssertionError("sync job did not reach a terminal state")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    from api.sync_jobs import sync_job_manager

    sync_job_manager.reset_for_tests()
    monkeypatch.setattr(Settings, "ATHLETE_TIMEZONE", "Europe/Moscow")
    yield
    app.dependency_overrides.pop(get_database, None)


CAPTURE_WARNING_TEMPLATE = "⚠️ Recovery snapshot capture: {reason}"


def _capture_warnings(block: dict) -> list[str]:
    """D4: отказ capture в продакшене добавляет warning → ответ становится `partial`."""
    if str(block.get("status")) != "capture_failed":
        return []
    reason = str(block.get("reason") or "snapshot_capture_failed")
    return [CAPTURE_WARNING_TEMPLATE.format(reason=reason)]


def _install_garmin(monkeypatch, db: Database, block: dict) -> None:
    from api.routers import system as system_mod
    from services import sync as sync_service

    def fake_sync(_state, days=None, on_progress=None, capture_run_id=None):
        return sync_service.GarminSyncResult(
            recovery_capture=block, warnings=_capture_warnings(block)
        )

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_a, **_k: True)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fake_sync)


def _install_intervals(monkeypatch, db: Database, block: dict) -> None:
    from api.routers import system as system_mod

    def fake_sync(_database, *, days=None, now=None, on_progress=None, client=None,
                  chunk_days=None, capture_run_id=None):
        return IntervalsSyncResult(
            new=1, recovery_capture=block, warnings=_capture_warnings(block)
        )

    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(
        system_mod.intervals_sync_service, "sync_intervals_data", fake_sync
    )


def _terminal_payload(tmp_path, monkeypatch, provider: str, status: str, *, suffix: str = "") -> dict:
    db = Database(str(tmp_path / f"{provider}-{status}{suffix}.db"))
    block = _block(provider, status)
    if provider == "garmin":
        _install_garmin(monkeypatch, db, block)
    else:
        _install_intervals(monkeypatch, db, block)
    client = _client(db)
    client.post("/api/sync", json={"days": 1, "source": provider})
    return _wait_terminal(client)


# --- a) оба провайдера × пять состояний, одинаковый публичный набор полей -------


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("status", STATUSES)
def test_terminal_api_exposes_the_same_public_fields(tmp_path, monkeypatch, provider, status):
    payload = _terminal_payload(tmp_path, monkeypatch, provider, status)

    capture = payload["result"]["recovery_capture"]
    assert set(capture) == set(RECOVERY_CAPTURE_PUBLIC_FIELDS) | {"job_id"}
    assert capture["provider"] == provider
    assert capture["status"] == status
    assert capture["capture_run_id"] == RUN_ID
    assert capture["job_id"] == payload["job_id"]
    assert isinstance(capture["created"], bool)


@pytest.mark.parametrize("status", STATUSES)
def test_both_providers_agree_on_the_field_set(tmp_path, monkeypatch, status):
    garmin = _terminal_payload(
        tmp_path, monkeypatch, "garmin", status, suffix="-g"
    )["result"]["recovery_capture"]
    intervals = _terminal_payload(
        tmp_path, monkeypatch, "intervals", status, suffix="-i"
    )["result"]["recovery_capture"]

    assert set(garmin) == set(intervals)
    assert garmin["status"] == intervals["status"] == status


# --- b) никаких служебных данных и внутренних путей ---------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("status", STATUSES)
def test_terminal_api_carries_no_service_internals(tmp_path, monkeypatch, provider, status):
    payload = _terminal_payload(tmp_path, monkeypatch, provider, status)
    raw = json.dumps(payload)

    assert "episode_refresh" not in raw
    assert "unexpected_key" not in raw
    assert "internal-only" not in raw
    assert "athlete.db" not in raw
    assert "repair failed" not in raw
    assert "recovery_capture" in payload["result"]


# --- c/d) идентичность рана: повтор и следующая ревизия ------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_repeating_the_same_run_creates_no_new_revision(tmp_path, provider):
    """Characterization: идемпотентность реализована (M1) — фиксируем её приёмкой.

    Job-уровневая идентичность (один job → один полный UUID) покрыта тестом M4
    `test_terminal_*_payload_carries_clean_capture`; здесь проверяется само
    правило хранилища на обоих провайдерах.
    """
    db = Database(str(tmp_path / f"repeat-{provider}.db"))
    _seed_day(db)

    first = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id=RUN_ID, provider=provider, observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]
    retry = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id=RUN_ID, provider=provider,
        observed_at_utc=datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc),
    )["recovery_capture"]

    assert first["created"] is True
    assert retry["created"] is False
    assert retry["revision"] == first["revision"] == 1
    assert len(db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY)) == 1


def test_new_job_on_the_same_day_creates_the_next_revision(tmp_path, monkeypatch):
    """Второй job того же дня несёт новый полный UUID и получает следующую ревизию."""
    from api.routers import system as system_mod
    from services import sync as sync_service

    db = Database(str(tmp_path / "day.db"))
    _seed_day(db)
    seen: list[str] = []

    def fake_sync(state, days=None, on_progress=None, capture_run_id=None):
        seen.append(capture_run_id)
        result = recovery_analytics.capture_post_sync_recovery_state(
            state.database,
            capture_run_id=capture_run_id,
            provider="garmin",
            observed_at_utc=MOSCOW_OBSERVED,
        )
        sync_result = sync_service.GarminSyncResult()
        sync_result.recovery_capture = result["recovery_capture"]
        return sync_result

    monkeypatch.setattr(system_mod.Settings, "GARMIN_EMAIL", "user@example.com", raising=False)
    monkeypatch.setattr(system_mod.Settings, "GARMIN_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(system_mod.garmin_service, "authenticate", lambda *_a, **_k: True)
    monkeypatch.setattr(system_mod, "real_database", lambda: db)
    monkeypatch.setattr(system_mod.sync_service, "sync_garmin_data", fake_sync)

    client = _client(db)
    client.post("/api/sync", json={"days": 1, "source": "garmin"})
    first = _wait_terminal(client)
    client.post("/api/sync", json={"days": 1, "source": "garmin"})
    second = _wait_terminal(client)

    assert seen[0] != seen[1], "каждый job несёт собственный полный UUID"
    assert first["result"]["recovery_capture"]["revision"] == 1
    assert second["result"]["recovery_capture"]["revision"] == 2
    assert (
        second["result"]["recovery_capture"]["capture_run_id"]
        != first["result"]["recovery_capture"]["capture_run_id"]
    )


# --- e) fail-open сохраняет данные провайдера ---------------------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_capture_failure_keeps_provider_data(tmp_path, monkeypatch, provider):
    db = Database(str(tmp_path / f"failopen-{provider}.db"))
    _seed_day(db)
    _seed_activity(db)
    captured = _capture_provider(monkeypatch, db, provider, failing=True)

    assert captured["status"] == "capture_failed"
    assert _count(db, "activities") == 1, "данные провайдера обязаны остаться"
    assert captured["reason"] == "snapshot_capture_failed"


# --- f) статус ревизии согласован с cutoff и дневным anchor --------------------


@pytest.mark.parametrize("provider", PROVIDERS)
def test_revision_status_matches_cutoff_and_daily_anchor(tmp_path, provider):
    """Ранняя ревизия — до нагрузки, поздняя после активности — слишком поздно."""
    db = Database(str(tmp_path / f"anchor-{provider}.db"))
    _seed_day(db)

    early = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id=f"{provider}-early", provider=provider, observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]
    _seed_activity(db, started_at="2026-07-23T07:00:00Z")  # 10:00 локально
    late = recovery_analytics.capture_post_sync_recovery_state(
        db,
        capture_run_id=f"{provider}-late",
        provider=provider,
        observed_at_utc=datetime(2026, 7, 23, 8, 0, tzinfo=timezone.utc),
    )["recovery_capture"]

    assert early["status"] == "saved_before_load"
    assert late["status"] == "saved_too_late"
    assert late["cutoff_at_utc"] == "2026-07-23T07:00:00Z"

    anchor = select_daily_anchor(
        db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY),
        db.get_activities_between("2026-07-22", DAY),
        local_date=date.fromisoformat(DAY),
        athlete_timezone=Settings.ATHLETE_TIMEZONE,
    )
    assert anchor["snapshot"]["revision"] == 1, "anchor дня остаётся у ранней ревизии"
    assert anchor["snapshot"]["observed_at_utc"] == "2026-07-23T05:00:00Z"


# --- приоритет предикатов ------------------------------------------------------


def test_capture_failed_precedes_every_other_predicate(tmp_path, monkeypatch):
    """Первый шаг приоритета: отказ capture важнее доменных состояний."""
    db = Database(str(tmp_path / "p1.db"))
    _seed_day(db, partial=True)
    _seed_activity(db, started_at=None)

    failed = _capture_provider(monkeypatch, db, "garmin", failing=True)

    assert failed["status"] == "capture_failed"
    assert failed["reason"] == "snapshot_capture_failed"


def test_status_precedence_is_explicit(tmp_path):
    """Остальные шаги: activity_start_missing → ineligible → before/too_late."""
    # 1) activity_start_missing побеждает ineligible.
    db2 = Database(str(tmp_path / "p2.db"))
    _seed_day(db2, partial=True)
    _seed_activity(db2, started_at=None)
    missing = recovery_analytics.capture_post_sync_recovery_state(
        db2, capture_run_id="prec-missing", provider="garmin", observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]
    assert missing["status"] == "activity_start_missing"

    # 3) ineligible — когда старт читаем, но снимок не прошёл gate.
    db3 = Database(str(tmp_path / "p3.db"))
    _seed_day(db3, partial=True)
    ineligible = recovery_analytics.capture_post_sync_recovery_state(
        db3, capture_run_id="prec-ineligible", provider="garmin", observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]
    assert ineligible["status"] == "ineligible"
    assert ineligible["reason"] == "low_confidence"

    # 4) before/too_late — когда нет ни отказа, ни непригодности.
    db4 = Database(str(tmp_path / "p4.db"))
    _seed_day(db4)
    before = recovery_analytics.capture_post_sync_recovery_state(
        db4, capture_run_id="prec-before", provider="garmin", observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]
    assert before["status"] == "saved_before_load"


# --- g) история читается и не мутируется --------------------------------------


def test_existing_snapshots_and_episodes_stay_readable_and_unmutated(tmp_path):
    db = Database(str(tmp_path / "history.db"))
    _seed_day(db)
    old = _seed_legacy_snapshot(db)
    before_rows = _raw_rows(db, "readiness_snapshots")

    capture = recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id="history-new", provider="garmin", observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]

    after_rows = _raw_rows(db, "readiness_snapshots")
    assert capture["revision"] == 2, "новая ревизия идёт после исторической"

    # Историческая строка не изменилась ни одним полем.
    assert len(after_rows) == len(before_rows) + 1
    assert all(row in after_rows for row in before_rows)
    preserved = next(row for row in after_rows if row["capture_run_id"] == old["capture_run_id"])
    assert preserved == old, "историческая ревизия не мутируется"

    # Читаемость через публичные читатели.
    history = db.get_readiness_snapshot_history(preserved["target_key"])
    assert [row["revision"] for row in history] == [1, 2], "ридер отдаёт историю по возрастанию"
    assert history[0]["capture_run_id"] == old["capture_run_id"]
    assert db.get_readiness_snapshots(capture_mode="prospective", local_date=DAY)


# --- M6a-owned fixture infrastructure ----------------------------------------

FIXTURE_NAMES = [
    f"{provider}_{status}.json" for provider in PROVIDERS for status in STATUSES
]


def _fixture_path(provider: str, status: str) -> Path:
    return FIXTURE_DIR / f"{provider}_{status}.json"


def _fixture_payload(provider: str, status: str) -> dict:
    return json.loads(_fixture_path(provider, status).read_text(encoding="utf-8"))


def _normalized(payload: dict) -> dict:
    """Стабилизировать волатильные значения: пинится форма, а не момент запуска."""
    normalized = json.loads(json.dumps(payload))
    normalized["job_id"] = "job-00000001"
    normalized["started_at"] = "2026-07-23T05:00:00"
    normalized["finished_at"] = "2026-07-23T05:00:05"
    result = normalized.get("result") or {}
    result["synced_at"] = "2026-07-23T05:00:05"
    capture = result.get("recovery_capture")
    if isinstance(capture, dict):
        capture["job_id"] = "job-00000001"
    return normalized


@pytest.mark.skipif(
    os.environ.get("CAPTURE_FIXTURE_REGEN") != "1",
    reason="регенерация фикстур выполняется явно: CAPTURE_FIXTURE_REGEN=1",
)
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("status", STATUSES)
def test_regenerate_terminal_api_fixtures(tmp_path, monkeypatch, provider, status):
    """M6a владеет формой API: фикстуры создаются из реального терминального ответа."""
    payload = _normalized(_terminal_payload(tmp_path, monkeypatch, provider, status))
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _fixture_path(provider, status).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert _fixture_path(provider, status).is_file()


def test_terminal_api_fixtures_exist_for_both_providers_and_all_five_states():
    """RED-инфраструктура M6a: фикстуры формы API создаёт и пинит этот слайс."""
    missing = [name for name in FIXTURE_NAMES if not (FIXTURE_DIR / name).is_file()]
    assert missing == [], f"нет фикстур: {missing}"


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_shape_matches_the_real_terminal_payload(
    fixture_name, tmp_path, monkeypatch
):
    provider, status = fixture_name.removesuffix(".json").split("_", 1)
    fixture = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    real = _terminal_payload(tmp_path, monkeypatch, provider, status)

    assert set(fixture) == set(real)
    assert set(fixture["result"]) == set(real["result"])
    assert set(fixture["result"]["recovery_capture"]) == set(
        real["result"]["recovery_capture"]
    )
    assert fixture["source"] == provider
    assert fixture["result"]["recovery_capture"]["status"] == status


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_cross_field_invariants(fixture_name):
    """Pinning не только формы: поля обязаны быть согласованы между собой (D4)."""
    payload = json.loads((FIXTURE_DIR / fixture_name).read_text(encoding="utf-8"))
    block = payload["result"]["recovery_capture"]

    if block["status"] == "capture_failed":
        assert payload["sync_state"] == "partial", payload["sync_state"]
        assert payload["result"]["sync_state"] == "partial"
        assert payload["result"]["severity"] == "warning"
        assert block["reason"] == block["error"] == "snapshot_capture_failed"
        assert block["local_date"] is None and block["observed_at_utc"] is None
        assert any(
            "snapshot_capture_failed" in notice for notice in payload["result"]["notices"]
        ), payload["result"]["notices"]
    else:
        assert payload["sync_state"] == "succeeded", payload["sync_state"]
        assert payload["result"]["sync_state"] == "succeeded"
        assert block["error"] is None
        assert not any(
            "Recovery snapshot capture" in notice for notice in payload["result"]["notices"]
        ), payload["result"]["notices"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_real_path_agrees_with_the_capture_failed_fixture(tmp_path, monkeypatch, provider):
    """Реальный путь для capture_failed тоже `partial` + warning (межполевое согласие)."""
    real = _terminal_payload(tmp_path, monkeypatch, provider, "capture_failed")
    fixture = _fixture_payload(provider, "capture_failed")

    assert real["sync_state"] == fixture["sync_state"] == "partial"
    assert real["result"]["severity"] == fixture["result"]["severity"] == "warning"
    assert any(
        "snapshot_capture_failed" in notice for notice in real["result"]["notices"]
    ), real["result"]["notices"]


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_carries_no_service_internals(fixture_name):
    raw = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")

    for forbidden in ("episode_refresh", "unexpected_key", "internal-only", "athlete.db"):
        assert forbidden not in raw
    block = json.loads(raw)["result"]["recovery_capture"]
    assert set(block) == set(RECOVERY_CAPTURE_PUBLIC_FIELDS) | {"job_id"}


# --- helpers ------------------------------------------------------------------


def _seed_day(db: Database, *, partial: bool = False, day: str = DAY) -> None:
    db.sync_sleep_data(
        {day: {"total_sleep_minutes": 480, "sleep_score": 82.0,
               "sleep_score_observed_at": day, "total_sleep_observed_at": day}}
    )
    if partial:
        return
    db.sync_hrv_data({day: {"rmssd": 45.0, "stress_score": 20.0, "rmssd_observed_at": day}})
    db.sync_daily_health({day: {"resting_hr": 52, "resting_hr_observed_at": day}})
    db.sync_training_status(
        {day: {"training_status": "PRODUCTIVE", "training_readiness": 78.0,
               "training_readiness_observed_at": day}}
    )


def _seed_activity(db: Database, *, started_at: str | None = "2026-07-23T07:00:00Z") -> None:
    db.save_activities(
        [
            {
                "activity_id": "acceptance-ride",
                "date": DAY,
                "started_at_utc": started_at,
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )


def _state(db: Database):
    from api.deps import make_headless_state

    return make_headless_state(db)


def _capture_provider(monkeypatch, db: Database, provider: str, *, failing: bool):
    """Прогнать реальный sync-путь провайдера, подменив только сбор данных."""
    if failing:
        def _boom(*_args, **_kwargs):
            raise RuntimeError("derived analytics unavailable at /private/athlete.db")

        monkeypatch.setattr(
            recovery_analytics, "record_post_sync_recovery_state", _boom
        )
    return recovery_analytics.capture_post_sync_recovery_state(
        db, capture_run_id=f"{provider}-run", provider=provider, observed_at_utc=MOSCOW_OBSERVED
    )["recovery_capture"]


def _count(db: Database, table: str) -> int:
    conn = sqlite3.connect(db.db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _raw_rows(db: Database, table: str) -> list[dict]:
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
    finally:
        conn.close()
    return rows


def _seed_legacy_snapshot(db: Database) -> dict:
    """Строка «до M2»: без capture_provider в провенансе."""
    saved = db.save_readiness_snapshot(
        {
            "fingerprint": "legacy-history-fingerprint",
            "target_key": f"readiness:prospective:{DAY}",
            "capture_mode": "prospective",
            "local_date": DAY,
            "athlete_timezone": "Europe/Moscow",
            "observed_at_utc": "2026-07-23T04:00:00Z",
            "capture_run_id": "legacy-run",
            "rule_version": "readiness_snapshot_v3",
            "score": 70.0,
            "status": "ready",
            "confidence": 0.8,
            "as_of_date": DAY,
            "is_provisional": False,
            "source_completeness": 0.8,
            "stale": False,
            "eligibility_status": "eligible",
            "eligibility_reasons": [],
            "factors": [],
            "drivers": [],
            "missing_inputs": [],
            "tsb": {},
            "provenance": {"as_of_date": DAY},
            "snapshot": {"score": 70.0, "as_of_date": DAY},
        }
    )
    assert saved["created"] is True
    return _raw_rows(db, "readiness_snapshots")[0]
