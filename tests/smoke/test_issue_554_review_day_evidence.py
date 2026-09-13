"""Issue #554 review: доказательство fail-closed сессии переживает проекцию дня.

Ревьюер отметил, что `failed_bounds` должен доходить до персистентной сессии
(исправлено в `materialize_session_template`). Здесь пинится вторая половина
контракта: шаблон дня — это то, что читают виды плана и правки, поэтому причина
fail-closed обязана переживать проекцию скаляров дня, а не оставаться только на
`sessions[0]`.

До правки `project_day_scalars` зеркалил лишь ключи из
`_SESSION_META_MIRROR_KEYS`, где `failed_bounds` отсутствовал: builder кладёт
доказательство на уровень дня, а проекция его снимала, и правка/перенос такого
дня теряли причину отказа.

Фикстура намеренно берёт шаблон, чья собственная прескрипция не проходит
объявленные границы (`tss_below_minimum` + `density_below_minimum`), а не
подкладывает поле руками.
"""
from __future__ import annotations

import pytest

from models.training_planner import project_day_scalars
from models.workout_catalog import materialize_session_template

pytestmark = pytest.mark.smoke

GOAL = "Триатлон"


def _fail_closed_session() -> dict:
    session = materialize_session_template(
        phase="Build",
        session_role="quality",
        sport="bike",
        target_tss=20.0,
        estimated_duration_minutes=30,
        goal_type=GOAL,
        zone_snapshot={"ftp": 160.0},
    )
    assert session["materialization_status"] == "infeasible", session["materialization_status"]
    assert session["failed_bounds"], session
    return session


def _day_template(session: dict) -> dict:
    return {
        "date": "2026-08-21",
        "phase": "Build",
        "sessions": [session],
        "total_tss": float(session.get("total_tss") or 0.0),
    }


def test_session_carries_its_own_fail_closed_evidence() -> None:
    session = _fail_closed_session()

    assert session["failed_bounds"] == ["tss_below_minimum", "density_below_minimum"]
    snapshot = dict(session["parameter_snapshot"])
    # Запрошенный бюджет и выведенная нагрузка различимы: причина отказа аудируема.
    assert float(snapshot["requested_tss"]) == 20.0
    assert float(snapshot["target_tss"]) < 20.0


def test_day_projection_keeps_fail_closed_evidence() -> None:
    session = _fail_closed_session()
    template = _day_template(session)

    project_day_scalars(template)

    assert template["failed_bounds"] == session["failed_bounds"], template.get("failed_bounds")
    assert template["materialization_status"] == session["materialization_status"]
    assert template["template_key"] == session["template_key"]
    assert template["duration_minutes"] == int(session["duration_minutes"])


def test_projection_drops_evidence_when_the_primary_session_has_none() -> None:
    """Обратная сторона контракта: без fail-closed доказательства день его не несёт."""
    session = _fail_closed_session()
    healthy = dict(session)
    healthy.pop("failed_bounds")
    healthy["materialization_status"] = "materialized"
    template = _day_template(healthy)
    template["failed_bounds"] = ["stale_evidence"]

    project_day_scalars(template)

    assert "failed_bounds" not in template, template.get("failed_bounds")
    assert template["materialization_status"] == "materialized"


def test_fail_closed_day_keeps_evidence_across_repeated_projection() -> None:
    """Правка дня пересобирает скаляры: доказательство обязано оставаться на месте."""
    session = _fail_closed_session()
    template = _day_template(session)
    expected = list(session["failed_bounds"])

    for _ in range(2):
        project_day_scalars(template)

    assert template["failed_bounds"] == expected
    assert template["date"] == "2026-08-21"
