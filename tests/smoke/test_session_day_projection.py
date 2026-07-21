"""Contract tests for the day-template primary-session projection (issue #232).

A day template's top-level scalars (`template_name`, `session_focus`,
`fatigue_cost`, `expected_recovery_hours`, `materialized_steps`, …) are a
projection of the day's primary session `sessions[0]` (issues #205/#206). The
initial builder projects the FULL primary; the transfer/near-term mutation
paths historically projected only a subset, leaving a day that had been
transferred or edited with stale catalog metadata from a previous primary — a
name/fatigue from one workout stitched onto another workout's focus/steps.

These tests pin that a transfer keeps the projection complete: the moved-onto
day mirrors its new primary in full, and a day emptied by the move carries no
catalog identity. A builder-parity test guards the projector's key list against
future drift. See docs/session_day_projection_execplan.md.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from api import planning_service as ps
from data.database import Database
from models.session_transfer import apply_session_transfer
from tests.smoke.test_api_planning import _seeded_db

# Top-level keys that must always equal the primary session's after projection.
_MIRRORED = ("template_name", "fatigue_cost", "expected_recovery_hours", "session_focus", "materialized_steps")
# Catalog-identity keys an emptied (off) day must not keep.
_CATALOG_IDENTITY = ("template_name", "fatigue_cost", "expected_recovery_hours", "stimulus", "materialized_steps")


def _active_plan(tmp_path) -> dict:
    db: Database = _seeded_db(tmp_path)
    event = (datetime.now() + timedelta(weeks=9)).strftime("%Y-%m-%d")
    ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=event,
        available_hours=12,
        available_days=["mon", "tue", "wed", "thu", "sat", "sun"],
        persist=True,
    )
    plan = ps.get_active_plan(db)
    assert plan and plan.get("session_templates")
    return deepcopy(plan)


def _single_session_training_day(templates) -> int | None:
    for index, tpl in enumerate(templates):
        sessions = tpl.get("sessions") or []
        if len(sessions) == 1 and sessions[0].get("template_name"):
            return index
    return None


def _other_training_day(templates, exclude: int) -> int | None:
    for index, tpl in enumerate(templates):
        if index != exclude and (tpl.get("sessions") or []):
            return index
    return None


def test_transfer_reprojects_full_primary_metadata_without_drift(tmp_path):
    plan = _active_plan(tmp_path)
    templates = plan["session_templates"]
    source_index = _single_session_training_day(templates)
    assert source_index is not None, "expected at least one one-session training day"
    target_index = _other_training_day(templates, exclude=source_index)
    assert target_index is not None, "expected a second training day to receive the transfer"

    moved_session_id = templates[source_index]["sessions"][0]["session_id"]
    target_date = str(templates[target_index]["date"])

    result = apply_session_transfer(plan, session_id=moved_session_id, target_date=target_date)["goal_plan"]
    source_tpl = result["session_templates"][source_index]
    target_tpl = result["session_templates"][target_index]

    # The source day is now empty; an off day carries no catalog identity.
    assert not (source_tpl.get("sessions") or [])
    for key in _CATALOG_IDENTITY:
        assert not source_tpl.get(key), f"emptied day kept stale {key!r}: {source_tpl.get(key)!r}"

    # The target day's top-level scalars mirror its new primary exactly — no
    # field lags behind on the previous primary.
    primary = target_tpl["sessions"][0]
    for key in _MIRRORED:
        assert target_tpl.get(key) == primary.get(key), f"top-level {key!r} drifted from sessions[0]"


def test_transfer_preserves_day_owned_fields(tmp_path):
    plan = _active_plan(tmp_path)
    templates = plan["session_templates"]
    source_index = _single_session_training_day(templates)
    assert source_index is not None
    target_index = _other_training_day(templates, exclude=source_index)
    assert target_index is not None

    before = {
        i: (templates[i].get("date"), templates[i].get("phase"))
        for i in (source_index, target_index)
    }
    moved_session_id = templates[source_index]["sessions"][0]["session_id"]
    target_date = str(templates[target_index]["date"])

    result = apply_session_transfer(plan, session_id=moved_session_id, target_date=target_date)["goal_plan"]
    for i in (source_index, target_index):
        tpl = result["session_templates"][i]
        assert (tpl.get("date"), tpl.get("phase")) == before[i], "transfer must not disturb day-owned fields"


def test_projector_matches_builder_projection(tmp_path):
    """Anti-drift guard: the canonical projector reproduces the initial
    builder's top-level projection for every primary-derived key. If a catalog
    key the builder propagates is missing from the projector's allow-list, this
    fails."""
    from models.training_planner import project_day_scalars

    plan = _active_plan(tmp_path)
    # Keys the top level owns independently of the primary-session projection:
    # day-level structure plus identity/lineage, which ensure_session_identities
    # (not this projector) stamps. The projector guards only catalog/presentation.
    day_owned = {
        "date", "week_index", "day_index", "phase", "allocated_parts", "sessions", "total_tss",
        "session_id", "session_material_fingerprint", "session_identity_rule_version",
        "replaces_session_id", "replaced_session_ids", "transfer_group_id",
        "constraint", "protected_by_constraint", "adjustment_note",
    }
    checked = 0
    for tpl in plan["session_templates"]:
        sessions = tpl.get("sessions") or []
        if not sessions:
            continue
        primary = sessions[0]
        probe = {"sessions": [deepcopy(primary)]}
        project_day_scalars(probe)
        for key in primary:
            if key in day_owned:
                continue
            assert probe.get(key) == tpl.get(key), (tpl.get("date"), key)
        checked += 1
    assert checked > 0, "expected at least one training day to compare"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
