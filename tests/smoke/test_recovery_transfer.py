"""M1 RED contract for RecoveryReplan v2 (Issue #209).

Pre-registers the deterministic candidate ranking and transfer safety guards
from the issue's BDD list before `models/recovery_transfer.py` exists. The
transfer unit is a session (`session_id`); a brick is one composite session, so
atomic brick transfer is structural. Every candidate date reports ALL failed
guards; no safe date → no transfer variant, downgrade/keep remain.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from models.session_identity import ensure_session_identities


pytestmark = pytest.mark.smoke

_TODAY = date(2026, 8, 3)  # Monday


def _session(sport: str, role: str, tss: float, **extra):
    body = {
        "sport": sport,
        "sport_label": sport,
        "session_role": role,
        "session_focus": f"{role} {sport}",
        "duration_minutes": max(30, int(tss * 1.2)),
        "total_tss": float(tss),
        "template_key": f"build:{role}:{sport}",
        "export_name": f"{role} {sport}",
        "materialized_steps": [
            {"index": 0, "name": "Warm-up", "intensity": "easy",
             "duration_seconds": 600, "tss": round(tss * 0.2, 1),
             "target": {"type": "power", "unit": "watts", "low": 90, "high": 110}},
            {"index": 1, "name": "Work", "intensity": "work",
             "duration_seconds": 1800, "tss": round(tss * 0.6, 1),
             "target": {"type": "power", "unit": "watts", "low": 150, "high": 165}},
            {"index": 2, "name": "Cool-down", "intensity": "easy",
             "duration_seconds": 600, "tss": round(tss * 0.2, 1),
             "target": {"type": "power", "unit": "watts", "low": 80, "high": 100}},
        ],
    }
    body.update(extra)
    return body


def _brick_session(bike_tss: float, run_tss: float):
    return {
        "sport": "brick",
        "sport_label": "вело → бег",
        "session_role": "long",
        "session_focus": "Brick",
        "duration_minutes": 120,
        "total_tss": float(bike_tss + run_tss),
        "template_key": "build:long:brick",
        "export_name": "Brick",
        "kind": "composite",
        "transition_minutes": 5,
        "legs": [
            {"leg_index": 1, "sport": "bike", "target_tss": bike_tss,
             "materialized_steps": [{"index": 0, "name": "Ride", "intensity": "steady",
                                     "duration_seconds": 4800, "tss": bike_tss,
                                     "target": {"type": "power", "unit": "watts", "low": 140, "high": 160}}]},
            {"leg_index": 2, "sport": "run", "target_tss": run_tss,
             "materialized_steps": [{"index": 0, "name": "Run", "intensity": "steady",
                                     "duration_seconds": 1800, "tss": run_tss,
                                     "target": {"type": "pace", "unit": "sec_per_km", "fast": 300, "slow": 330}}]},
        ],
    }


def _plan(day_specs):
    """Build a minimal, identity-stamped goal plan from per-day session specs.

    Each spec: {"sessions": [...], "protected": bool}. Day 0 is _TODAY.
    """
    daily_plan = []
    templates = []
    protected: list[str] = []
    roles = []
    for offset, spec in enumerate(day_specs):
        day = _TODAY + timedelta(days=offset)
        sessions = [dict(s) for s in spec.get("sessions") or []]
        parts = {"run": 0.0, "bike": 0.0, "swim": 0.0}
        for s in sessions:
            if str(s.get("kind")) == "composite":
                for leg in s["legs"]:
                    parts[leg["sport"]] = round(parts[leg["sport"]] + float(leg["target_tss"]), 1)
            else:
                parts[s["sport"]] = round(parts[s["sport"]] + float(s["total_tss"]), 1)
        total = round(sum(parts.values()), 1)
        primary = sessions[0] if sessions else {}
        role = str(primary.get("session_role") or ("off" if total <= 0 else "easy"))
        roles.append(role)
        daily_plan.append((datetime.combine(day, datetime.min.time()), total, parts))
        template = {
            "date": day.isoformat(),
            "week_index": offset // 7,
            "day_index": offset % 7,
            "phase": "Build",
            "session_role": role,
            "session_focus": str(primary.get("session_focus") or "—"),
            "sport": str(primary.get("sport") or "off"),
            "sport_label": str(primary.get("sport_label") or "off"),
            "duration_minutes": int(primary.get("duration_minutes") or 0),
            "sessions": sessions,
        }
        for key in ("kind", "legs", "transition_minutes", "materialized_steps"):
            if key in primary:
                template[key] = primary[key]
        templates.append(template)
        if spec.get("protected"):
            protected.append(day.isoformat())

    weeks = (len(day_specs) + 6) // 7
    weekly_summary = []
    for w in range(weeks):
        week_roles = (roles[w * 7 : w * 7 + 7] + ["off"] * 7)[:7]
        weekly_summary.append(
            {
                "week_start": _TODAY + timedelta(days=w * 7),
                "phase": "Build",
                "weekly_tss": int(sum(t for _d, t, _p in daily_plan[w * 7 : w * 7 + 7])),
                "bike": 0.0,
                "run": 0.0,
                "swim": 0.0,
                "day_roles": week_roles,
                "day_focuses": ["—"] * 7,
            }
        )
    plan = {
        "goal_type": "Триатлон",
        "distance": "Олимпийка",
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "protected_dates": protected,
        "constraint_summary": {},
    }
    return ensure_session_identities(plan)


def _conflict(plan, day_offset: int = 0):
    template = plan["session_templates"][day_offset]
    session = (template.get("sessions") or [{}])[0]
    return {
        "date": template["date"],
        "severity": "high",
        "session_id": str(session.get("session_id") or ""),
        "session": {"role": session.get("session_role"), "tss": session.get("total_tss")},
    }


def _rank(plan, conflict):
    from models.recovery_transfer import rank_transfer_candidates

    return rank_transfer_candidates(plan, conflict, today=_TODAY)


def _variant(plan, conflict):
    from models.recovery_transfer import build_transfer_variant

    return build_transfer_variant(plan, conflict, today=_TODAY)


def _week(quality_today=True, d1=None, d2=None, d3=None, protected_days=()):
    specs = [
        {"sessions": [_session("bike", "quality", 80.0)] if quality_today else []},
        {"sessions": d1 or []},
        {"sessions": d2 or []},
        {"sessions": d3 or []},
        {"sessions": [_session("run", "easy", 30.0)]},
        {"sessions": [_session("bike", "long", 100.0)]},
        {"sessions": []},
    ]
    for offset in protected_days:
        specs[offset]["protected"] = True
    return _plan(specs)


def test_safe_d2_yields_atomic_transfer_with_lineage():
    """BDD 1: D+1 collides with quality, D+2 is a free safe day."""
    plan = _week(d1=[_session("run", "quality", 60.0)], d2=[], d3=[_session("swim", "easy", 25.0)])
    conflict = _conflict(plan)
    old_id = conflict["session_id"]
    assert old_id

    variant = _variant(plan, conflict)
    assert variant is not None
    assert variant["kind"] == "transfer_1_3d"
    assert variant["target_date"] == (_TODAY + timedelta(days=2)).isoformat()

    new_session = variant["new_session"]
    assert new_session["sport"] == "bike"
    assert new_session["session_role"] == "quality"
    assert float(new_session["total_tss"]) == 80.0
    assert new_session["materialized_steps"], "the stimulus steps travel with the session"
    assert new_session["replaces_session_id"] == old_id
    assert new_session.get("transfer_group_id")
    assert new_session.get("session_id") != old_id
    assert variant.get("reduction") is None

    rows = {row["offset"]: row for row in variant["candidates"]}
    assert rows[1]["eligible"] is False and rows[1]["rejected_reasons"]
    assert rows[2]["eligible"] is True and rows[2]["rejected_reasons"] == []
    assert all(row["rule_version"] == "recovery-transfer-v1" for row in variant["candidates"])


def test_no_safe_date_reports_every_reason_per_candidate():
    """BDD 2: quality collision on D+1, protected D+2, protected D+3 —
    no transfer, three visible rejections."""
    plan = _week(
        d1=[_session("run", "quality", 60.0)],
        d2=[_session("swim", "easy", 20.0)],
        d3=[],
        protected_days=(2, 3),
    )
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    rows = _rank(plan, conflict)
    assert len(rows) == 3
    for row in rows:
        assert row["eligible"] is False
        assert row["rejected_reasons"], row


def test_brick_transfers_only_as_whole_composite():
    """BDD 3: the parent and both ordered legs move together."""
    specs = [
        {"sessions": [_brick_session(60.0, 30.0)]},
        {"sessions": [_session("run", "quality", 60.0)]},
        {"sessions": []},
        {"sessions": [_session("swim", "easy", 25.0)]},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
    ]
    plan = _plan(specs)
    conflict = _conflict(plan)

    variant = _variant(plan, conflict)
    assert variant is not None
    new_session = variant["new_session"]
    assert str(new_session.get("kind")) == "composite"
    legs = new_session.get("legs") or []
    assert [leg["sport"] for leg in legs] == ["bike", "run"]
    assert [int(leg["leg_index"]) for leg in legs] == [1, 2]
    assert float(new_session["total_tss"]) == 90.0


def test_two_occasion_target_day_is_rejected_not_tripled():
    """BDD 4: a two-session day may not become a three-session day."""
    two = [_session("swim", "recovery", 15.0), _session("run", "easy", 25.0)]
    plan = _week(d1=list(two), d2=list(two), d3=list(two))
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    for row in _rank(plan, conflict):
        assert row["eligible"] is False
        assert any("occasion" in reason or "сесси" in reason for reason in row["rejected_reasons"]), row


def test_oversized_stimulus_offers_only_named_bounded_reduction():
    """BDD 5: if the full stimulus exceeds the target day's honest capacity,
    only an explicit named reduction may be offered; weekly TSS never grows."""
    specs = [
        {"sessions": [_session("bike", "quality", 200.0)]},
        {"sessions": [_session("bike", "easy", 100.0)]},
        {"sessions": [_session("run", "easy", 90.0)]},
        {"sessions": [_session("swim", "easy", 80.0)]},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
    ]
    plan = _plan(specs)
    conflict = _conflict(plan)

    variant = _variant(plan, conflict)
    if variant is None:
        rows = _rank(plan, conflict)
        assert all(not row["eligible"] and row["rejected_reasons"] for row in rows)
    else:
        reduction = variant.get("reduction")
        assert reduction is not None and reduction.get("reason")
        assert float(variant["new_session"]["total_tss"]) < 200.0
        assert float(variant["weekly_tss_delta"]) <= 0.0


def test_protected_race_and_post_race_days_are_never_targets():
    """BDD 6: race microcycle / post-race recovery cannot be overwritten."""
    plan = _week(d1=[], d2=[], d3=[], protected_days=(1, 2, 3))
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    for row in _rank(plan, conflict):
        assert row["eligible"] is False
        assert any("protect" in reason or "защищ" in reason for reason in row["rejected_reasons"]), row


def test_ranking_and_variant_are_byte_deterministic():
    """BDD 12: identical inputs → identical candidates and variant."""
    plan = _week(d1=[_session("run", "quality", 60.0)], d2=[], d3=[])
    conflict = _conflict(plan)

    assert _rank(plan, conflict) == _rank(plan, conflict)
    assert _variant(plan, conflict) == _variant(plan, conflict)