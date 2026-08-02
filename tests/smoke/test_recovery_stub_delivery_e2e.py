"""Энд-до-энд доказательство для #318: реальная форма recovery-stub (как
checkpoint 74 от 2026-07-30) через production-точку входа safe_deliver_active_plan.

Контекст: исходная причинная цепочка #318 («детектор не ловит stub») опровергнута —
planned_session_requires_repair(real_stub) == True (template_key 'manual:' ловится).
Dict-skip в build_delivery_events тоже не продуктовый: restore_goal_plan_from_checkpoint
конвертирует daily_plan dict→tuple через _restore_daily_plan.

Этот тест фиксирует фактическое поведение production-пути на текущем HEAD:
stub-сессия (manual:base:easy:run, без materialized_steps) доходит до fail-closed
guard (require_executable_planned_session, f13f842) → safe_deliver_active_plan
возвращает failed/retryable, provider client НИЧЕГО не получает (upsert_calls == []).
Targetless event не эмитируется. Это regression-lock: если guard когда-либо
снимут/обойдут, тест поймёт, что появилась доставка fallback HR-zone токенов.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint


pytestmark = pytest.mark.smoke


class _FakeClient:
    """Двойник IntervalsICUClient — duck-typed, без сети."""

    def __init__(self, configured: bool = True):
        self.configured = configured
        self.list_calls: list = []
        self.upsert_calls: list = []
        self.delete_calls: list = []

    def is_configured(self) -> bool:
        return self.configured

    def list_workout_events(self, oldest, newest):
        self.list_calls.append((oldest, newest))
        return []

    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        return [{**row, "id": index + 100, "uid": f"provider-{index}"} for index, row in enumerate(rows)]

    def delete_events(self, payloads):
        rows = [dict(row) for row in payloads]
        self.delete_calls.append(rows)
        return len(rows)


def _stub_plan() -> dict[str, Any]:
    """План с recovery-stub сессией 07-30 в реальной форме ckpt 74:
    template_key='manual:base:easy:run', нет materialized_steps, есть lineage."""
    return {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": [
            (datetime(2026, 7, 30), 30.0, {"run": 30.0, "bike": 0.0, "swim": 0.0}),
        ],
        "session_templates": [
            {
                "date": "2026-07-30",
                "sport": "run",
                "sport_label": "бег",
                "session_role": "easy",
                "session_focus": "Легкая • бег",
                "duration_minutes": 35,
                "kind": "single",
                "template_key": "manual:base:easy:run",
                "export_name": "Триатлон Олимпийка — Легкая • бег",
                "session_id": "ats_db4b0586e42f57f36b45071d",
                "session_material_fingerprint": "db4b0586e42f57f36b45071d57f98e39140bad42",
                "session_identity_rule_version": "session_identity_v1",
                "replaces_session_id": "ats_c47964eecb58fd58f2f21163",
                "phase": "Base",
                # materialized_steps ОТСУТСТВУЮТ — облезлый stub
            },
        ],
        "weekly_tss_plan": [30],
        "phases": ["Base"],
        "weekly_summary": [],
        "constraint_summary": {},
    }


def test_recovery_stub_delivery_fails_closed_no_targetless_event(tmp_path) -> None:
    """Production-доставка stub-сессии 07-30: fail-closed, provider ничего не получает."""
    from services.intervals_plan_delivery import safe_deliver_active_plan

    db = Database(str(tmp_path / "stub_delivery.db"))
    db.save_planning_checkpoint(build_planning_checkpoint(_stub_plan()))
    client = _FakeClient()

    result = safe_deliver_active_plan(
        db,
        dates=["2026-07-30"],
        source="recovery_approve",
        client=client,
    )

    # fail-closed: статус failed, retryable, ничего не_upsertнулось
    assert result["status"] == "failed", result
    assert result.get("retryable") is True
    assert result.get("failed_count") == 1
    # ключевое: provider client не получил ни одного event — targetless не ушёл
    assert client.upsert_calls == [], f"unexpected upsert: {client.upsert_calls}"
    # причина зафиксирована в ошибке
    assert "not executable" in str(result.get("error", "")), result.get("error")
