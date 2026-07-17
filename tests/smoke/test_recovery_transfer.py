"""M1 RED contract for RecoveryReplan v2 (Issue #209), expanded per pre-M2 review.

Pins, before `models/recovery_transfer.py` exists:
- stable machine-readable rejection codes (ALL failed guards per candidate);
- the D+1…D+3 window relative to the SOURCE session date, never earlier;
- cross-week transfers forbidden in v1 (`cross_week_boundary`);
- fail-closed v1: no bounded reduction, neighbours never modified;
- recovery spacing evaluated on the post-removal plan state;
- minimal-intervention ranking (empty day beats occupied) before nearest-date;
- the full atomic move proven via `day_changes` (source loses the id, target
  gains the new session, neighbours preserved, totals recomputed from sessions);
- content-derived identity reproducible by `ensure_session_identities`;
- (round 2) availability read from `constraint_summary`, EXACT reason sets,
  actual executed load in spacing, day DURATION ceiling shared with the
  scheduler, weekly duration conservation as evidence, exact code registry.
"""
from __future__ import annotations

import json
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


def _plan(day_specs, available_weekdays=None):
    """Minimal identity-stamped goal plan. Day 0 is _TODAY (Monday)."""
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
    if available_weekdays is not None:
        # Availability lives INSIDE constraint_summary in real plans (built by
        # apply_planning_constraints → summarize_availability), never top-level.
        plan["constraint_summary"]["available_day_indices"] = list(available_weekdays)
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


def _rank(plan, conflict, **kwargs):
    from models.recovery_transfer import rank_transfer_candidates

    return rank_transfer_candidates(plan, conflict, today=_TODAY, **kwargs)


def _variant(plan, conflict, **kwargs):
    from models.recovery_transfer import build_transfer_variant

    return build_transfer_variant(plan, conflict, today=_TODAY, **kwargs)


def _rows_by_offset(rows):
    return {int(row["offset"]): row for row in rows}


def _week(quality_today=True, d1=None, d2=None, d3=None, protected_days=(), tail=None, **plan_kwargs):
    specs = [
        {"sessions": [_session("bike", "quality", 80.0)] if quality_today else []},
        {"sessions": d1 or []},
        {"sessions": d2 or []},
        {"sessions": d3 or []},
        {"sessions": (tail or {}).get(4, [_session("run", "easy", 30.0)])},
        {"sessions": (tail or {}).get(5, [])},
        {"sessions": (tail or {}).get(6, [])},
    ]
    for offset in protected_days:
        specs[offset]["protected"] = True
    return _plan(specs, **plan_kwargs)


# ---------------------------------------------------------------------------
# Ranking: codes, availability, spacing, minimal intervention
# ---------------------------------------------------------------------------


def test_safe_d2_yields_atomic_transfer_with_lineage():
    """BDD 1 (re-scenario'd, review round 3): D+1 is protected, D+2 is a free
    safe day. D+1 must NOT carry a hard session here — a quality neighbour
    would legitimately fire `recovery_spacing` on D+2 (both `quality` and
    `long` are hard); the easy D+3 neighbour does not."""
    plan = _week(d1=[], d2=[], d3=[_session("swim", "easy", 25.0)], protected_days=(1,))
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
    assert variant.get("reduction") is None  # v1 is fail-closed, no reduction ever
    # in-week transfer conserves weekly duration BY CONSTRUCTION — evidence field
    assert variant["weekly_duration_delta_minutes"] == 0

    rows = _rows_by_offset(variant["candidates"])
    assert rows[1]["eligible"] is False
    assert sorted(rows[1]["rejected_reasons"]) == ["protected"]
    assert rows[2]["eligible"] is True and rows[2]["rejected_reasons"] == []
    assert all(row["rule_version"] == "recovery-transfer-v1" for row in variant["candidates"])


def test_truly_unavailable_day_is_rejected_with_code():
    """A day outside available_day_indices is `unavailable`, not merely
    protected: D+1 protected, D+2 unavailable (Wednesday excluded), D+3 clean.
    D+1 is protected-empty rather than hard so `unavailable` is isolated —
    a hard D+1 would add `recovery_spacing` to D+2's exact set."""
    plan = _week(
        d1=[],
        d2=[],
        d3=[],
        protected_days=(1,),
        available_weekdays=[0, 1, 3, 4, 5, 6],  # Wednesday (weekday 2) excluded
    )
    conflict = _conflict(plan)
    assert "available_day_indices" not in plan  # lives ONLY in constraint_summary

    rows = _rows_by_offset(_rank(plan, conflict))
    assert sorted(rows[2]["rejected_reasons"]) == ["unavailable"]
    assert rows[3]["eligible"] is True
    variant = _variant(plan, conflict)
    assert variant is not None and variant["target_date"] == (_TODAY + timedelta(days=3)).isoformat()


def test_no_safe_date_reports_exact_codes_per_candidate():
    """BDD 2: hard collision on D+1, protected D+2, unavailable D+3 —
    no transfer, each candidate names its exact stable codes. D+2 sits next to
    the hard D+1, so its honest exact set carries `recovery_spacing` too."""
    plan = _week(
        d1=[_session("run", "quality", 60.0)],
        d2=[_session("swim", "easy", 20.0)],
        d3=[],
        protected_days=(2,),
        available_weekdays=[0, 1, 2, 4, 5, 6],  # Thursday (weekday 3) excluded
    )
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    rows = _rows_by_offset(_rank(plan, conflict))
    assert len(rows) == 3
    assert sorted(rows[1]["rejected_reasons"]) == ["hard_collision"]
    assert sorted(rows[2]["rejected_reasons"]) == ["protected", "recovery_spacing"]
    assert sorted(rows[3]["rejected_reasons"]) == ["unavailable"]
    for row in rows.values():
        assert row["eligible"] is False


def test_multi_guard_candidate_reports_all_codes_not_first():
    """A candidate violating several guards lists every failed code — and ONLY
    the failed codes: an exact set, so bogus extra reasons fail too."""
    two_hard_day = [_session("run", "quality", 60.0), _session("swim", "easy", 20.0)]
    plan = _week(d1=list(two_hard_day), d2=[], d3=[], protected_days=(1,))
    conflict = _conflict(plan)

    rows = _rows_by_offset(_rank(plan, conflict))
    assert sorted(rows[1]["rejected_reasons"]) == [
        "hard_collision",
        "occasion_limit",
        "protected",
    ]


def test_recovery_spacing_uses_post_removal_state():
    """A hard transfer may not land adjacent to another hard day — but the
    source day stops counting because the session is leaving it: D+1 (adjacent
    to today's vacated quality) is fine; D+2 (adjacent to a D+3 long) is not."""
    plan = _week(d1=[], d2=[], d3=[_session("bike", "long", 100.0)])
    conflict = _conflict(plan)

    rows = _rows_by_offset(_rank(plan, conflict))
    assert rows[1]["eligible"] is True, rows[1]
    assert sorted(rows[2]["rejected_reasons"]) == ["recovery_spacing"]
    variant = _variant(plan, conflict)
    assert variant is not None and variant["target_date"] == (_TODAY + timedelta(days=1)).isoformat()


@pytest.mark.parametrize(
    ("neighbour_role", "blocks"),
    [
        ("quality", True),
        ("long", True),
        ("easy", False),
        ("recovery", False),
    ],
)
def test_adjacent_role_spacing_matrix(neighbour_role, blocks):
    """Review round 3: BOTH hard roles block a hard transfer on the adjacent
    day with `recovery_spacing` — `quality` exactly like `long`; easy and
    recovery neighbours never do. Probe: neighbour role on D+1, candidate D+2."""
    plan = _week(d1=[_session("run", neighbour_role, 50.0)], d2=[], d3=[])
    conflict = _conflict(plan)

    rows = _rows_by_offset(_rank(plan, conflict))
    if blocks:
        assert rows[2]["eligible"] is False
        assert sorted(rows[2]["rejected_reasons"]) == ["recovery_spacing"]
        variant = _variant(plan, conflict)
        assert variant is not None
        assert variant["target_date"] == (_TODAY + timedelta(days=3)).isoformat()
    else:
        assert rows[2]["eligible"] is True
        assert rows[2]["rejected_reasons"] == []


def test_minimal_intervention_outranks_nearest_date():
    """An empty D+2 beats an occupied-but-eligible D+1: fewer existing
    occasions on the target day is ranked before nearness."""
    plan = _week(d1=[_session("swim", "recovery", 15.0)], d2=[], d3=[])
    conflict = _conflict(plan)

    rows = _rows_by_offset(_rank(plan, conflict))
    assert rows[1]["eligible"] is True and rows[2]["eligible"] is True
    variant = _variant(plan, conflict)
    assert variant is not None
    assert variant["target_date"] == (_TODAY + timedelta(days=2)).isoformat()


def test_two_occasion_target_day_is_rejected_not_tripled():
    """BDD 4: a two-session day may not become a three-session day."""
    two = [_session("swim", "recovery", 15.0), _session("run", "easy", 25.0)]
    plan = _week(d1=list(two), d2=list(two), d3=list(two))
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    for row in _rank(plan, conflict):
        assert row["eligible"] is False
        assert sorted(row["rejected_reasons"]) == ["occasion_limit"], row


def test_oversized_stimulus_fails_closed_with_ceiling_code():
    """BDD 5 (v1 semantics): no bounded reduction exists in v1 — an oversized
    stimulus rejects the candidate with `day_tss_ceiling`; neighbours are never
    modified; weekly TSS can never grow because nothing else changes. The
    conflict's duration is kept short so the DURATION guard stays silent and
    the exact-set check proves TSS is the only firing code."""
    specs = [
        {"sessions": [_session("bike", "quality", 200.0, duration_minutes=90)]},
        {"sessions": [_session("bike", "easy", 100.0)]},
        {"sessions": [_session("run", "easy", 90.0)]},
        {"sessions": [_session("swim", "easy", 80.0)]},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
    ]
    plan = _plan(specs)
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    rows = _rows_by_offset(_rank(plan, conflict))
    for row in rows.values():
        assert row["eligible"] is False
        assert sorted(row["rejected_reasons"]) == ["day_tss_ceiling"], row


def test_rejection_code_registry_is_exact():
    """Review round 2: the registry is a tested contract. `weekly_hours_ceiling`
    is REMOVED — unreachable in v1 because the cross-week ban makes every
    in-week transfer conserve weekly duration by construction; the duration
    guard that IS reachable is the day-level `day_duration_ceiling`."""
    from models.recovery_transfer import REJECTION_REASON_CODES

    assert REJECTION_REASON_CODES == {
        "unavailable",
        "protected",
        "hard_collision",
        "recovery_spacing",
        "occasion_limit",
        "day_tss_ceiling",
        "day_duration_ceiling",
        "cross_week_boundary",
    }


def test_day_duration_policy_lives_with_scheduler_policies():
    """`MAX_DAY_DURATION_MINUTES` is a scheduler-owned policy next to
    `MAX_DAY_TSS_POLICY` — RecoveryTransfer must not grow a parallel model."""
    from models.session_scheduler import MAX_DAY_DURATION_MINUTES, MAX_DAY_TSS_POLICY

    assert int(MAX_DAY_DURATION_MINUTES) == 240
    assert float(MAX_DAY_TSS_POLICY) == 220.0


def test_day_duration_ceiling_rejects_when_tss_fits():
    """Review round 2: the TSS ceiling does not replace a duration bound. A
    target day whose summed persisted duration would exceed the policy rejects
    with exactly `day_duration_ceiling` even though its TSS total fits.
    Duration comes from persisted sessions: independents sum their
    `duration_minutes`; a composite brick counts the parent duration
    (transition included)."""
    from models.session_scheduler import MAX_DAY_DURATION_MINUTES

    filler = _session(
        "bike", "easy", 60.0, duration_minutes=int(MAX_DAY_DURATION_MINUTES) - 40
    )
    plan = _week(d1=[filler], d2=[], d3=[])
    conflict = _conflict(plan)  # quality bike 80 TSS → 96 persisted minutes

    rows = _rows_by_offset(_rank(plan, conflict))
    assert rows[1]["eligible"] is False
    assert sorted(rows[1]["rejected_reasons"]) == ["day_duration_ceiling"]
    assert rows[2]["eligible"] is True
    variant = _variant(plan, conflict)
    assert variant is not None
    assert variant["target_date"] == (_TODAY + timedelta(days=2)).isoformat()
    assert variant["weekly_duration_delta_minutes"] == 0


def test_unplanned_actual_hard_load_blocks_adjacent_candidate():
    """Review round 2: spacing must respect ACTUAL executed load, not only the
    plan. The ranker consumes `actual_hard_dates` (ISO dates the loop extracts
    from its already-loaded reconciliation snapshot — the ranker itself never
    reads DB or provider). Adjacency policy is fixed at ±1 calendar day. The
    post-removal rule applies to the PLANNED session only: the source day's
    planned conflict stops counting because it leaves, but a real workout
    already executed there still blocks the neighbouring candidate."""
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)

    baseline = _rows_by_offset(_rank(plan, conflict))
    assert baseline[1]["eligible"] is True  # planned-only view: D+1 is fine

    actual = [_TODAY.isoformat()]  # unplanned hard group ride done this morning
    rows = _rows_by_offset(_rank(plan, conflict, actual_hard_dates=actual))
    assert rows[1]["eligible"] is False
    assert sorted(rows[1]["rejected_reasons"]) == ["recovery_spacing"]
    assert rows[2]["eligible"] is True  # ±1 adjacency only — D+2 unaffected
    variant = _variant(plan, conflict, actual_hard_dates=actual)
    assert variant is not None
    assert variant["target_date"] == (_TODAY + timedelta(days=2)).isoformat()


def test_protected_race_and_post_race_days_are_never_targets():
    """BDD 6: race microcycle / post-race recovery cannot be overwritten."""
    plan = _week(d1=[], d2=[], d3=[], protected_days=(1, 2, 3))
    conflict = _conflict(plan)

    assert _variant(plan, conflict) is None
    for row in _rank(plan, conflict):
        assert row["eligible"] is False
        assert sorted(row["rejected_reasons"]) == ["protected"], row


# ---------------------------------------------------------------------------
# Window and week-boundary semantics
# ---------------------------------------------------------------------------


def test_window_is_relative_to_source_session_date():
    """A future-dated conflict transfers forward from ITS OWN date: conflict on
    D+1 (Tuesday) → candidates are Wed/Thu/Fri, never today, never backwards."""
    plan = _week(
        quality_today=False,
        d1=[_session("bike", "quality", 80.0)],
        d2=[],
        d3=[],
    )
    conflict = _conflict(plan, day_offset=1)

    rows = _rank(plan, conflict)
    expected = [(_TODAY + timedelta(days=offset)).isoformat() for offset in (2, 3, 4)]
    assert [row["date"] for row in rows] == expected
    assert all(row["date"] > conflict["date"] for row in rows)


def test_cross_week_transfer_is_forbidden_in_v1():
    """Weekly budget is the #206 anchor invariant: candidates beyond the source
    week are rejected with `cross_week_boundary`. A Sunday conflict therefore
    has no candidates at all — downgrade/keep remain."""
    specs = [{"sessions": []} for _ in range(14)]
    specs[6] = {"sessions": [_session("bike", "quality", 80.0)]}  # Sunday
    plan = _plan(specs)
    conflict = _conflict(plan, day_offset=6)

    assert _variant(plan, conflict) is None
    for row in _rank(plan, conflict):
        assert row["eligible"] is False
        assert sorted(row["rejected_reasons"]) == ["cross_week_boundary"], row

    # Friday conflict: Sat/Sun stay in-week, Monday is rejected
    specs2 = [{"sessions": []} for _ in range(14)]
    specs2[4] = {"sessions": [_session("bike", "quality", 80.0)]}  # Friday
    plan2 = _plan(specs2)
    rows2 = _rows_by_offset(_rank(plan2, _conflict(plan2, day_offset=4)))
    assert rows2[1]["eligible"] is True
    assert rows2[2]["eligible"] is True
    assert sorted(rows2[3]["rejected_reasons"]) == ["cross_week_boundary"]


# ---------------------------------------------------------------------------
# Full atomic move, identity, brick
# ---------------------------------------------------------------------------


def test_day_changes_prove_full_atomic_move_with_neighbours_preserved():
    """The variant must prove the move end to end via day_changes: the source
    day loses the old id (neighbours intact), the target day gains the new
    session (neighbours intact), and totals are recomputed from sessions."""
    neighbour = _session("swim", "recovery", 15.0)
    plan = _week(d1=[], d2=[dict(neighbour)], d3=[])
    # make today's plan carry a second, unrelated session next to the conflict
    plan["session_templates"][0]["sessions"].append(
        dict(_session("swim", "easy", 20.0))
    )
    plan = ensure_session_identities(plan)
    conflict = _conflict(plan)
    old_id = conflict["session_id"]

    variant = _variant(plan, conflict)
    assert variant is not None
    changes = {row["date"]: row for row in variant["day_changes"]}
    source = changes[conflict["date"]]
    target = changes[variant["target_date"]]

    before_ids = {s["session_id"] for s in source["before_sessions"]}
    after_ids = {s["session_id"] for s in source["after_sessions"]}
    assert old_id in before_ids and old_id not in after_ids
    # the unrelated same-day swim survives untouched
    assert len(source["after_sessions"]) == len(source["before_sessions"]) - 1

    target_before_ids = {s["session_id"] for s in target["before_sessions"]}
    target_after_ids = {s["session_id"] for s in target["after_sessions"]}
    assert target_before_ids <= target_after_ids
    new_ids = target_after_ids - target_before_ids
    assert new_ids == {variant["new_session"]["session_id"]}

    # totals recomputed from the resulting sessions, not asserted from a field
    def _day_total(sessions):
        total = 0.0
        for s in sessions:
            if str(s.get("kind")) == "composite":
                total += sum(float(leg["target_tss"]) for leg in s.get("legs") or [])
            else:
                total += float(s.get("total_tss") or 0.0)
        return round(total, 1)

    assert _day_total(source["after_sessions"]) == round(
        _day_total(source["before_sessions"]) - 80.0, 1
    )
    assert _day_total(target["after_sessions"]) == round(
        _day_total(target["before_sessions"]) + 80.0, 1
    )


def test_new_identity_is_reproducible_by_ensure_session_identities():
    """The new session's id must be the content-derived id that
    ensure_session_identities itself would stamp on the target date — re-running
    identity over the resulting plan changes nothing."""
    from models.session_transfer import apply_session_transfer

    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)

    result = apply_session_transfer(
        plan,
        session_id=conflict["session_id"],
        target_date=(_TODAY + timedelta(days=1)).isoformat(),
    )
    moved_plan = result["goal_plan"]
    restamped = ensure_session_identities(moved_plan)
    assert restamped["session_templates"] == moved_plan["session_templates"]

    target_sessions = moved_plan["session_templates"][1]["sessions"]
    assert len(target_sessions) == 1
    assert target_sessions[0]["replaces_session_id"] == conflict["session_id"]
    assert target_sessions[0]["session_id"] != conflict["session_id"]


def test_brick_transfers_whole_with_consistent_group_and_leg_ids():
    """BDD 3 + review: the composite parent moves atomically; on the target the
    legs' leg_id/group identity follow the NEW parent id, bike→run order kept,
    an existing independent session on the target day survives. D+2/D+3 are
    protected so the occupied D+1 is the only eligible target — otherwise
    minimal-intervention ranking would prefer an empty day and the surviving-
    neighbour claim would probe nothing."""
    specs = [
        {"sessions": [_brick_session(60.0, 30.0)]},
        {"sessions": [_session("swim", "recovery", 15.0)]},
        {"sessions": [], "protected": True},
        {"sessions": [], "protected": True},
        {"sessions": []},
        {"sessions": []},
        {"sessions": []},
    ]
    plan = _plan(specs)
    conflict = _conflict(plan)
    old_parent_id = conflict["session_id"]

    variant = _variant(plan, conflict)
    assert variant is not None
    new_session = variant["new_session"]
    assert str(new_session.get("kind")) == "composite"
    new_parent_id = str(new_session["session_id"])
    assert new_parent_id and new_parent_id != old_parent_id
    legs = new_session.get("legs") or []
    assert [leg["sport"] for leg in legs] == ["bike", "run"]
    assert [int(leg["leg_index"]) for leg in legs] == [1, 2]
    assert [leg["leg_id"] for leg in legs] == [f"{new_parent_id}:1", f"{new_parent_id}:2"]
    assert float(new_session["total_tss"]) == 90.0
    assert variant["weekly_duration_delta_minutes"] == 0

    changes = {row["date"]: row for row in variant["day_changes"]}
    target = changes[variant["target_date"]]
    surviving = [s for s in target["after_sessions"] if s.get("sport") == "swim"]
    assert len(surviving) == 1  # the independent neighbour is untouched

    # review round 2: the downstream leaf projection must regroup the legs
    # under the NEW parent id — delivery/Today read group_id from here
    from models.training_planner import iter_leaf_sessions

    leaves = iter_leaf_sessions({"sessions": target["after_sessions"]})
    brick_leaves = [leaf for leaf in leaves if leaf.get("kind") == "brick_leg"]
    assert [leaf["group_id"] for leaf in brick_leaves] == [new_parent_id, new_parent_id]
    assert [leaf["session_id"] for leaf in brick_leaves] == [
        f"{new_parent_id}:1",
        f"{new_parent_id}:2",
    ]


def test_ranking_and_variant_are_byte_deterministic_and_pure():
    """BDD 12: identical inputs → identical candidates and variant; and the
    ranker/builder never mutate the input plan (whole-plan deep snapshot)."""
    plan = _week(d1=[_session("run", "quality", 60.0)], d2=[], d3=[])
    conflict = _conflict(plan)
    snapshot = json.dumps(plan, sort_keys=True, default=str)

    assert _rank(plan, conflict) == _rank(plan, conflict)
    assert _variant(plan, conflict) == _variant(plan, conflict)
    assert json.dumps(plan, sort_keys=True, default=str) == snapshot