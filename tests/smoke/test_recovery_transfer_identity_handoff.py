"""M5 RED contract for RecoveryReplan v2 (Issue #209): reconciliation and
feedback identity handoff after a confirmed `transfer_1_3d` (BDD 11), per the
M5 preflight checker comment on PR #210
(https://github.com/rbctmz/ai_trainer/pull/210#issuecomment-5010888978).

`models/plan_actual_reconciliation.py::build_reconciliation` and
`models/post_workout_feedback.py::build_feedback_prompts` both still treat
each `session_templates[i]` as ONE planned/feedback target, keyed by the
day-level `daily_plan[i]` scalar total and `template.get("session_id")`. That
shape predates #205/#206's nested `sessions[]` per-day model, where a
multi-session day's top-level `session_id` is a projection of the day's
aggregate material — NOT any individual session's own content-derived id
(`models/session_identity.py`: "the day's identity is a projection of its
primary session" holds only when `len(sessions) == 1`). After a confirmed
`transfer_1_3d` lands a session on an already-occupied day, or moves a brick,
the day-scalar row hides the independent sibling, can merge otherwise-
ambiguous same-sport evidence into one false match, and loses the moved
session's own content (composite `kind`/legs) for prompt building. These
tests pin the per-PARENT-SESSION contract required before Milestone 6, using
a pure synthetic confirm (`models/session_transfer.py::apply_session_transfer`,
the same primitive `api/planning_service.py::apply_recovery_replan_transfer`
confirms through) → reconciliation → feedback vertical. No provider or live
DB access; `Database` is only ever a local sqlite tmp file.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from data.database import Database
from models.plan_actual_reconciliation import build_reconciliation
from models.planning_checkpoints import build_planning_checkpoint
from models.post_workout_feedback import build_feedback_prompts
from models.session_transfer import apply_session_transfer
from tests.smoke.test_recovery_transfer import (
    _TODAY,
    _brick_session,
    _conflict,
    _plan,
    _session,
    _week,
)


pytestmark = pytest.mark.smoke


def _activity(activity_id: str, day_iso: str, sport: str, tss: float, duration: float = 60.0) -> dict:
    return {
        "activity_id": activity_id,
        "date": day_iso,
        "started_at_utc": f"{day_iso}T06:00:00Z",
        "sport": sport,
        "tss": tss,
        "duration_minutes": duration,
        "activity_name": activity_id,
    }


# ---------------------------------------------------------------------------
# 1. Parent-session truth on multi-session days (not day-scalar, not legs)
# ---------------------------------------------------------------------------


def test_reconciliation_emits_one_row_per_independent_session_not_one_row_per_day():
    """M5 preflight #1: a multi-session day must yield one planned row per
    PARENT session in `sessions[]`, each carrying its own session_id and TSS
    — not one row per day built from the aggregate `daily_plan` scalar and
    the day's projected (day-level) `session_id`."""
    plan = _plan([{"sessions": [_session("bike", "quality", 60.0), _session("swim", "easy", 20.0)]}])
    bike, swim = plan["session_templates"][0]["sessions"]
    assert bike["session_id"] and swim["session_id"] and bike["session_id"] != swim["session_id"]

    result = build_reconciliation(plan, [], as_of=_TODAY, weeks=1, base_checkpoint_id=1)

    rows_by_id = {row["session_id"]: row for row in result["rows"]}
    assert set(rows_by_id) == {bike["session_id"], swim["session_id"]}
    assert rows_by_id[bike["session_id"]]["tss"] == 60.0
    assert rows_by_id[swim["session_id"]]["tss"] == 20.0


def test_composite_brick_remains_one_parent_row_alongside_independent_sibling():
    """M5 preflight #1: a composite brick stays ONE parent target (never two
    leg rows) even on a day it shares with an independent sibling session."""
    plan = _plan([{"sessions": [_brick_session(45.0, 20.0), _session("swim", "easy", 15.0)]}])
    brick, swim = plan["session_templates"][0]["sessions"]

    result = build_reconciliation(plan, [], as_of=_TODAY, weeks=1, base_checkpoint_id=1)

    rows_by_id = {row["session_id"]: row for row in result["rows"]}
    assert set(rows_by_id) == {brick["session_id"], swim["session_id"]}
    assert rows_by_id[brick["session_id"]]["tss"] == 65.0
    assert rows_by_id[swim["session_id"]]["tss"] == 15.0


# ---------------------------------------------------------------------------
# 2/3. Transfer identity handoff + sibling preservation (no old-id
# resurrection, independent siblings tracked by their own id)
# ---------------------------------------------------------------------------


def test_transfer_lands_on_occupied_day_and_new_id_is_tracked_independently_of_survivor():
    """M5 preflight #2/#3: after a confirmed transfer lands a session on a
    day that already carries an independent sibling, reconciliation must
    track BOTH parents by their own ids — the moved session under its NEW
    content-derived id, the untouched sibling under its unchanged id — and
    never resurrect the replaced (old) id anywhere."""
    plan = _week(d1=[], d2=[_session("swim", "easy", 25.0)], d3=[])
    conflict = _conflict(plan)
    old_id = conflict["session_id"]
    swim_id = plan["session_templates"][2]["sessions"][0]["session_id"]
    target_date = (_TODAY + timedelta(days=2)).isoformat()

    moved = apply_session_transfer(plan, session_id=old_id, target_date=target_date)
    new_id = moved["new_session_id"]
    moved_plan = moved["goal_plan"]

    activities = [
        _activity("bike-actual", target_date, "bike", 80.0),
        _activity("swim-actual", target_date, "swim", 25.0),
    ]
    result = build_reconciliation(
        moved_plan,
        activities,
        as_of=_TODAY + timedelta(days=3),
        weeks=1,
        base_checkpoint_id=2,
    )

    target_rows = [row for row in result["rows"] if row["date"] == target_date]
    assert {row["session_id"] for row in target_rows} == {new_id, swim_id}
    assert not any(row["session_id"] == old_id for row in result["rows"])

    new_row = next(row for row in target_rows if row["session_id"] == new_id)
    swim_row = next(row for row in target_rows if row["session_id"] == swim_id)
    assert new_row["match_status"] == "matched"
    assert new_row["actual_activity_ids"] == ["bike-actual"]
    assert swim_row["match_status"] == "matched"
    assert swim_row["actual_activity_ids"] == ["swim-actual"]


def test_two_independent_same_sport_sessions_each_fail_closed_on_ambiguous_match():
    """M5 preflight #3 (same-sport ambiguity): two independent same-sport
    sessions on one day, with two same-sport candidate activities and no
    unique way to tell them apart, must each report their own `ambiguous`
    status with zero claimed evidence — never silently merge both activities
    onto one day-level row."""
    plan = _plan([{"sessions": [_session("run", "easy", 20.0), _session("run", "recovery", 10.0)]}])
    easy, recovery = plan["session_templates"][0]["sessions"]
    day_iso = plan["session_templates"][0]["date"]
    activities = [
        _activity("run-a", day_iso, "run", 22.0),
        _activity("run-b", day_iso, "run", 11.0),
    ]

    result = build_reconciliation(plan, activities, as_of=_TODAY, weeks=1, base_checkpoint_id=3)

    rows_by_id = {row["session_id"]: row for row in result["rows"]}
    assert set(rows_by_id) == {easy["session_id"], recovery["session_id"]}
    assert rows_by_id[easy["session_id"]]["match_status"] == "ambiguous"
    assert rows_by_id[recovery["session_id"]]["match_status"] == "ambiguous"
    assert rows_by_id[easy["session_id"]]["actual_activity_ids"] == []
    assert rows_by_id[recovery["session_id"]]["actual_activity_ids"] == []


# ---------------------------------------------------------------------------
# 4. Authoritative provider external ids, including brick leg suffixes,
# after a transfer — never resolving via the replaced (old) parent id
# ---------------------------------------------------------------------------


def test_transferred_brick_authoritative_external_id_uses_new_parent_leg_suffixes_and_ignores_stale_old_id():
    """M5 preflight #4: once a composite brick has been transferred, only
    `ai_trainer:<new_id>` / `:leg:N` pairs are authoritative evidence for the
    new parent; a stale pair still tagged with the REPLACED old id must never
    resolve against the new row, and the untouched sibling on the target day
    is tracked under its own unrelated id."""
    plan = _plan(
        [
            {"sessions": [_brick_session(45.0, 20.0)]},
            {"sessions": []},
            {"sessions": [_session("swim", "easy", 15.0)]},
        ]
    )
    old_id = plan["session_templates"][0]["sessions"][0]["session_id"]
    target_date = plan["session_templates"][2]["date"]
    swim_id = plan["session_templates"][2]["sessions"][0]["session_id"]

    moved = apply_session_transfer(plan, session_id=old_id, target_date=target_date)
    new_id = moved["new_session_id"]
    moved_plan = moved["goal_plan"]

    activities = [
        _activity("bike-leg", target_date, "bike", 45.0),
        _activity("run-leg", target_date, "run", 20.0),
        _activity("stale-leg", target_date, "bike", 45.0),
        _activity("swim-actual", target_date, "swim", 15.0),
    ]
    provider_activities = [
        {"external_id": "bike-leg", "paired_event_id": "ev-bike"},
        {"external_id": "run-leg", "paired_event_id": "ev-run"},
        {"external_id": "stale-leg", "paired_event_id": "ev-stale"},
    ]
    provider_events = [
        {"id": "ev-bike", "external_id": f"ai_trainer:{new_id}:leg:1"},
        {"id": "ev-run", "external_id": f"ai_trainer:{new_id}:leg:2"},
        {"id": "ev-stale", "external_id": f"ai_trainer:{old_id}:leg:1"},
    ]

    result = build_reconciliation(
        moved_plan,
        activities,
        as_of=_TODAY + timedelta(days=2),
        weeks=1,
        base_checkpoint_id=4,
        provider_activities=provider_activities,
        provider_events=provider_events,
    )

    rows_by_id = {row["session_id"]: row for row in result["rows"]}
    assert set(rows_by_id) == {new_id, swim_id}
    assert not any(row["session_id"] == old_id for row in result["rows"])
    brick_row = rows_by_id[new_id]
    assert brick_row["match_method"] == "ai_trainer_external_id"
    assert set(brick_row["actual_activity_ids"]) == {"bike-leg", "run-leg"}
    assert "stale-leg" not in brick_row["actual_activity_ids"]


# ---------------------------------------------------------------------------
# 5. Ledger isolation (regression guard: the ledger key is derived from the
# CURRENT row's own session_id, so a stale old-id match must stay isolated
# whatever shape the row-building takes)
# ---------------------------------------------------------------------------


def test_ledger_confirmed_match_for_old_session_is_not_inherited_by_new_session_after_transfer():
    """M5 preflight #5: a stale user-confirmed ledger row keyed
    `session:<old_id>` must never be picked up as evidence for the moved
    session's NEW identity. Kept green today (single-session-day transfer,
    no day-scalar interference) as an explicit regression guard for the
    parent-session-truth fix the rest of this file pins."""
    plan = _week(d1=[], d2=[], d3=[])
    conflict = _conflict(plan)
    old_id = conflict["session_id"]
    target_date = (_TODAY + timedelta(days=2)).isoformat()

    moved = apply_session_transfer(plan, session_id=old_id, target_date=target_date)
    new_id = moved["new_session_id"]
    moved_plan = moved["goal_plan"]

    stale_ledger = [
        {
            "target_key": f"session:{old_id}",
            "session_id": old_id,
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "actual_activity_ids": ["phantom-activity"],
            "actual_snapshot": {"role": "quality"},
            "evidence": ["stale user match from before the transfer"],
        }
    ]
    activities = [_activity("bike-real-actual", target_date, "bike", 80.0)]

    result = build_reconciliation(
        moved_plan,
        activities,
        as_of=_TODAY + timedelta(days=2),
        weeks=1,
        base_checkpoint_id=5,
        ledger_rows=stale_ledger,
    )

    new_row = next(row for row in result["rows"] if row["session_id"] == new_id)
    assert new_row["match_method"] != "user_confirmed"
    assert "phantom-activity" not in new_row["actual_activity_ids"]
    assert new_row["actual_activity_ids"] == ["bike-real-actual"]


# ---------------------------------------------------------------------------
# 6/7. Feedback handoff: prompt-layer composite metadata + submit/history
# targeting the new parent, fail-closed on the replaced (old) id (BDD 11)
# ---------------------------------------------------------------------------


def test_feedback_prompt_composite_metadata_is_not_lost_for_non_primary_session_on_multi_session_day():
    """M5 preflight #6/#7 (brick transfer, prompt layer): `build_feedback_prompts`
    looks up each row's template by `template.get("session_id")` — a
    DAY-level projection on a multi-session day, not any individual session's
    id. After a brick transfer lands the composite parent on a day with an
    independent sibling, its own `kind`/`parent_session_id` must not be lost
    just because the day's top-level id belongs to neither session."""
    plan = _plan(
        [
            {"sessions": [_brick_session(45.0, 20.0)]},
            {"sessions": []},
            {"sessions": [_session("swim", "easy", 15.0)]},
        ]
    )
    old_id = plan["session_templates"][0]["sessions"][0]["session_id"]
    target_date = plan["session_templates"][2]["date"]
    swim_id = plan["session_templates"][2]["sessions"][0]["session_id"]

    moved = apply_session_transfer(plan, session_id=old_id, target_date=target_date)
    new_id = moved["new_session_id"]
    moved_plan = moved["goal_plan"]

    rows = [
        {
            "session_id": new_id,
            "date": target_date,
            "name": "Brick",
            "role": "long",
            "sport": "brick",
            "match_status": "matched",
            "match_method": "ai_trainer_external_id",
            "confidence": 1.0,
            "actual_activity_ids": [],
            "actual_activities": [],
            "adherence": "unknown",
        },
        {
            "session_id": swim_id,
            "date": target_date,
            "name": "Swim easy",
            "role": "easy",
            "sport": "swim",
            "match_status": "matched",
            "match_method": "date_sport_heuristic",
            "confidence": 0.75,
            "actual_activity_ids": [],
            "actual_activities": [],
            "adherence": "unknown",
        },
    ]
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    prompts = build_feedback_prompts(
        rows,
        templates=moved_plan["session_templates"],
        latest_feedback_by_session={},
        prompt_events_by_session={},
        forecasts=[],
        now_utc=now,
        as_of=now.date().isoformat(),
    )

    by_id = {item["session_id"]: item for item in prompts["prompts"]}
    assert by_id[new_id]["kind"] == "composite"
    assert by_id[new_id]["parent_session_id"] == new_id


def test_feedback_submit_and_history_target_new_session_after_transfer_and_fail_closed_on_old_id(
    tmp_path,
) -> None:
    """BDD 11 vertical: a completed activity on the transferred date attaches
    to the NEW session identity through `submit_session_feedback`, and
    post-workout feedback cannot attach to the replaced (old) session — a
    confirm → reconciliation → feedback path exercised through the real
    `Database`/`apply_recovery_replan_transfer` primitive, no provider or
    live DB access."""
    from api.planning_service import apply_recovery_replan_transfer
    from api.session_feedback import feedback_history, submit_session_feedback

    plan = _week(d1=[], d2=[_session("swim", "easy", 25.0)], d3=[])
    conflict = _conflict(plan)
    old_id = conflict["session_id"]
    target_date = (_TODAY + timedelta(days=2)).isoformat()

    db = Database(str(tmp_path / "m5-feedback-handoff.db"))
    base = db.save_planning_checkpoint(build_planning_checkpoint(plan))

    applied = apply_recovery_replan_transfer(
        db,
        base_checkpoint_id=base["id"],
        session_id=old_id,
        target_date=target_date,
    )
    new_id = applied["new_session_id"]

    db.save_activities(
        [
            {
                "activity_id": "bike-moved-actual",
                "date": target_date,
                "started_at_utc": f"{target_date}T06:00:00Z",
                "sport": "bike",
                "duration_minutes": 90,
                "tss": 80.0,
            },
            {
                "activity_id": "swim-sibling-actual",
                "date": target_date,
                "started_at_utc": f"{target_date}T08:00:00Z",
                "sport": "swim",
                "duration_minutes": 40,
                "tss": 25.0,
            },
        ]
    )

    now = datetime.combine(
        date.fromisoformat(target_date), datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=20)

    saved = submit_session_feedback(
        db,
        {
            "session_id": new_id,
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 6,
            "quality_rating_1_5": 4,
            "client_submission_fingerprint": "fp-new-id",
        },
        now_utc=now,
    )
    assert saved["feedback"]["session_id"] == new_id

    history = feedback_history(db, new_id)
    assert history["current"] is not None
    assert history["current"]["session_id"] == new_id

    with pytest.raises(LookupError):
        submit_session_feedback(
            db,
            {
                "session_id": old_id,
                "completion_status": "completed",
                "completion_pct": 100,
                "session_rpe_1_10": 5,
                "quality_rating_1_5": 3,
                "client_submission_fingerprint": "fp-old-id",
            },
            now_utc=now,
        )


# ---------------------------------------------------------------------------
# 8. Legacy single-session-per-day compatibility (regression guard)
# ---------------------------------------------------------------------------


def test_legacy_single_session_per_day_reconciliation_is_unchanged():
    """M5 preflight #8: plans where every day carries zero or one session
    (the pre-#209 legacy shape) keep producing exactly one row per non-rest
    day, unaffected by the parent-session-truth fix this file pins for
    multi-session days."""
    plan = _week(d1=[_session("run", "easy", 20.0)], d2=[], d3=[_session("swim", "recovery", 15.0)])

    result = build_reconciliation(
        plan, [], as_of=_TODAY + timedelta(days=6), weeks=1, base_checkpoint_id=6
    )

    non_rest_days = [t for t in plan["session_templates"][:7] if t.get("sessions")]
    assert len(result["rows"]) == len(non_rest_days)
    for template in non_rest_days:
        session = template["sessions"][0]
        row = next(r for r in result["rows"] if r["session_id"] == session["session_id"])
        assert row["tss"] == float(session["total_tss"])
