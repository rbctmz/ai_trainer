"""RED/GREEN contract for Issue #194: `reconciliation_at` ownership moves
from `api/planning_service.py` to `services/reconciliation.py`.

`services/recovery_analytics.py::refresh_recovery_episodes` imports
`api.planning_service.reconciliation_at` with a local (function-body)
import — a `services → api` layering inversion flagged on PR #187 (review
comment 🔵-2). The fix moves `reconciliation_at` and its two private
helpers (`_parse_as_of`, `_provider_reconciliation_evidence`) into a new
`services/reconciliation.py`, with `api.planning_service` keeping a
compatibility re-export (the SAME function object, not a copy) so every
existing caller keeps working unchanged.

These tests pin: the service returns payloads byte-equivalent to frozen
pre-refactor `main` baselines across five scenarios (no plan; local-only
with provider disabled; provider available; provider unavailable/data-gap;
ledger-confirmed nested multi-session identity); repeated reads never
mutate the database; provider access stays disabled when
`include_provider=False`; and `api.planning_service.reconciliation_at`
remains the exact same callable.

Before `services/reconciliation.py` exists, this file fails to collect
(`ModuleNotFoundError: No module named 'services.reconciliation'`) — that
is the intended RED state. No live Garmin/provider access; `Database` is
only ever a local sqlite tmp file, and every case here either omits the
provider entirely or injects a fake client.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import timedelta

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from tests.smoke.test_api_planning import _reconciliation_db
from tests.smoke.test_recovery_transfer import _TODAY, _conflict, _session, _week


pytestmark = pytest.mark.smoke


def _canonical(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


_PRE_REFACTOR_PAYLOAD_SHA256 = {
    # Captured from main@eeefc96 before reconciliation_at moved to services/.
    "no_plan": "e91c4897f1de495c9564da88f8a9fdeaba02f0439e7fb5c2f7aa1148833bd9dd",
    "local_disabled": "a7dc028bb5ea036eb9df29f7f25af6ac375cc5c4da99a1b4d80427e5b41d7449",
    "provider_available": "e73108c14b9b7931bed05dd3998e0f9302615dbe2f42563732337841d2d182b0",
    "provider_unavailable": "4ddcc6c4b46f1cddacf14a4212b9a8f29dc029da3165c90e02c4757b038f99a1",
    "nested_ledger": "ed5430b52b1999f8a83f7635164d6745daa05eef561a010e8c10c4b7497e6e4e",
}


def _assert_pre_refactor_payload(payload: dict, scenario: str) -> None:
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    assert digest == _PRE_REFACTOR_PAYLOAD_SHA256[scenario]


_MUTATION_TRACKED_TABLES = (
    "planning_checkpoints",
    "plan_actual_matches",
    "session_feedback",
    "coach_proposals",
    "recovery_episodes",
)


def _table_snapshots(db: Database) -> dict[str, object]:
    """Full row snapshots for every table `reconciliation_at` must not mutate."""
    conn = sqlite3.connect(db.db_path)
    try:
        snapshots: dict[str, object] = {}
        for table in _MUTATION_TRACKED_TABLES:
            try:
                cursor = conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')  # noqa: S608
            except sqlite3.OperationalError:
                snapshots[table] = None
                continue
            columns = tuple(item[0] for item in cursor.description or ())
            snapshots[table] = (columns, tuple(tuple(row) for row in cursor.fetchall()))
        return snapshots
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Old path (api.planning_service) and new path (services.reconciliation)
#    must be the exact same function object — not two copies.
# ---------------------------------------------------------------------------


def test_api_planning_service_reexports_the_same_function_object():
    from api.planning_service import reconciliation_at as old_path
    from services.reconciliation import reconciliation_at as new_path

    assert old_path is new_path


# ---------------------------------------------------------------------------
# 2. Byte-equivalence with pre-refactor main across five scenarios.
# ---------------------------------------------------------------------------


def test_byte_equivalent_when_no_plan_exists(tmp_path):
    from services.reconciliation import reconciliation_at

    db = Database(str(tmp_path / "no-plan.db"))

    result = reconciliation_at(db, weeks=1, as_of="2026-07-18", include_provider=False)

    assert result == {"has_plan": False, "rows": [], "unplanned_activities": []}
    _assert_pre_refactor_payload(result, "no_plan")


def test_byte_equivalent_local_only_provider_disabled(tmp_path, monkeypatch):
    from services.reconciliation import reconciliation_at
    from services import intervals_icu

    def _forbidden_get_client():
        raise AssertionError("provider must not be probed when include_provider=False")

    monkeypatch.setattr(intervals_icu, "get_client", _forbidden_get_client)

    db, _plan = _reconciliation_db(tmp_path)

    result = reconciliation_at(db, weeks=1, as_of="2026-07-13", include_provider=False)

    assert result["has_plan"] is True
    assert result["provider"] == {"status": "disabled"}
    assert result["rows"]
    _assert_pre_refactor_payload(result, "local_disabled")


class _FakeProviderClient:
    def __init__(self, activities=None, events=None, raise_error=None):
        self._activities = activities or []
        self._events = events or []
        self._raise_error = raise_error

    def is_configured(self) -> bool:
        return True

    def list_activities(self, oldest, newest):
        if self._raise_error is not None:
            raise self._raise_error
        return self._activities

    def list_workout_events(self, oldest, newest):
        if self._raise_error is not None:
            raise self._raise_error
        return self._events


def test_byte_equivalent_provider_available(tmp_path, monkeypatch):
    from services.reconciliation import reconciliation_at
    from services import intervals_icu

    fake_client = _FakeProviderClient(
        activities=[
            {
                "activity_id": "provider-act-1",
                "date": "2026-07-11",
                "sport": "cycling",
                "tss": 80.0,
            }
        ],
        events=[{"date": "2026-07-11", "sport": "cycling"}],
    )
    monkeypatch.setattr(intervals_icu, "get_client", lambda: fake_client)

    db, _plan = _reconciliation_db(tmp_path)

    result = reconciliation_at(db, weeks=1, as_of="2026-07-13", include_provider=True)

    assert result["provider"]["status"] == "available"
    assert result["provider"]["activity_count"] == 1
    _assert_pre_refactor_payload(result, "provider_available")


def test_byte_equivalent_provider_unavailable_data_gap(tmp_path, monkeypatch):
    from services.reconciliation import reconciliation_at
    from services import intervals_icu

    fake_client = _FakeProviderClient(raise_error=intervals_icu.IntervalsICUError("HTTP 500"))
    monkeypatch.setattr(intervals_icu, "get_client", lambda: fake_client)

    db, _plan = _reconciliation_db(tmp_path)

    result = reconciliation_at(db, weeks=1, as_of="2026-07-13", include_provider=True)

    assert result["provider"]["status"] == "unavailable"
    assert result["data_quality"]["status"] == "data_gap"
    assert "provider_unavailable" in result["data_quality"]["reasons"]
    _assert_pre_refactor_payload(result, "provider_unavailable")


def test_byte_equivalent_ledger_confirmed_nested_multi_session_identity(tmp_path):
    """Reuses the transfer + ledger-confirm fixtures from
    `tests/smoke/test_recovery_transfer_identity_handoff.py`'s M5 contract:
    a confirmed `transfer_1_3d` lands a session on an already-occupied day,
    the moved session's NEW id is then user-confirmed in the plan/actual
    ledger, and both parents (moved + untouched sibling) must reconcile
    independently under their own ids."""
    from api.planning_service import (
        apply_recovery_replan_transfer,
        record_plan_actual_match,
    )
    from services.reconciliation import reconciliation_at

    plan = _week(d1=[], d2=[_session("swim", "easy", 25.0)], d3=[])
    conflict = _conflict(plan)
    old_id = conflict["session_id"]
    target_date = (_TODAY + timedelta(days=2)).isoformat()

    db = Database(str(tmp_path / "nested-ledger.db"))
    base = db.save_planning_checkpoint(build_planning_checkpoint(plan))

    applied = apply_recovery_replan_transfer(
        db,
        base_checkpoint_id=base["id"],
        session_id=old_id,
        target_date=target_date,
    )
    new_id = applied["new_session_id"]
    new_checkpoint_id = applied["applied_checkpoint_id"]

    db.save_activities(
        [
            {
                "activity_id": "bike-moved-actual",
                "date": target_date,
                "started_at_utc": f"{target_date}T06:00:00Z",
                "sport": "bike",
                "tss": 80.0,
                "duration_minutes": 90,
            }
        ]
    )
    record_plan_actual_match(
        db,
        base_checkpoint_id=new_checkpoint_id,
        session_id=new_id,
        activity_ids=["bike-moved-actual"],
        actual_role="quality",
        action="confirm",
    )

    as_of = _TODAY + timedelta(days=3)
    result = reconciliation_at(db, weeks=1, as_of=as_of, include_provider=False)

    assert not any(row["session_id"] == old_id for row in result["rows"])
    new_row = next(row for row in result["rows"] if row["session_id"] == new_id)
    assert new_row["match_method"] == "user_confirmed"
    assert new_row["actual_activity_ids"] == ["bike-moved-actual"]
    _assert_pre_refactor_payload(result, "nested_ledger")
    assert base["id"] == 1  # sanity: fixture actually created the base checkpoint


# ---------------------------------------------------------------------------
# 3. Mutation-freedom: repeated reads never write checkpoints, ledger rows,
#    feedback, or recovery episodes.
# ---------------------------------------------------------------------------


def test_repeated_reads_are_mutation_free(tmp_path):
    from services.reconciliation import reconciliation_at

    db, _plan = _reconciliation_db(tmp_path)
    before = _table_snapshots(db)

    for _ in range(3):
        reconciliation_at(db, weeks=1, as_of="2026-07-13", include_provider=False)

    after = _table_snapshots(db)
    assert after == before


# ---------------------------------------------------------------------------
# 4. Provider gating: no provider probe at all when include_provider=False.
# ---------------------------------------------------------------------------


def test_include_provider_false_never_touches_the_provider_module(tmp_path, monkeypatch):
    from services.reconciliation import reconciliation_at
    from services import intervals_icu

    def _forbidden_get_client():
        raise AssertionError("provider must not be probed when include_provider=False")

    monkeypatch.setattr(intervals_icu, "get_client", _forbidden_get_client)

    db, _plan = _reconciliation_db(tmp_path)
    result = reconciliation_at(db, weeks=1, as_of="2026-07-13", include_provider=False)

    assert result["provider"] == {"status": "disabled"}


def test_reconciliation_honors_the_sixteen_week_reader_window(tmp_path, monkeypatch):
    """The bounded M3 reader must not silently lose weeks 13-16."""
    from services import reconciliation as service

    db = Database(str(tmp_path / "sixteen-week-window.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_week()))
    captured: dict[str, object] = {}

    def _capture(*_args, **kwargs):
        captured.update(kwargs)
        return {"rows": [], "unplanned_activities": [], "data_quality": {}}

    monkeypatch.setattr(service, "build_reconciliation", _capture)

    result = service.reconciliation_at(
        db,
        weeks=16,
        as_of=_TODAY,
        include_provider=False,
    )

    assert result["has_plan"] is True
    assert captured["weeks"] == 16

    captured.clear()
    monkeypatch.setattr(
        service,
        "_provider_reconciliation_evidence",
        lambda *_args, **_kwargs: ([], [], {"status": "not_configured"}),
    )

    service.reconciliation_at(
        db,
        weeks=16,
        as_of=_TODAY,
        include_provider=True,
    )

    assert captured["weeks"] == 12
