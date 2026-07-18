"""RED/GREEN contract for Issue #195: targeted recovery-episode refresh.

`services/recovery_analytics.py::refresh_recovery_episodes` caps its lookback
window at 12 weeks ending "today" so an unattended post-sync refresh stays
cheap. That cap has a side effect: if the athlete confirms a match, corrects
feedback, or tombstones feedback for a planned session that happened more
than 12 weeks ago, the append-only source tables (`plan_actual_matches`,
`session_feedback`) record the change fine, but the derived `recovery_episodes`
projection never looks back far enough to notice — it silently goes stale.

This module pins the fix (option 2 from the issue): the ordinary post-sync
refresh stays bounded and untouched; match/feedback mutations additionally
pass the affected `session_id` through a new `target_session_ids` parameter
that resolves that one session's own date from the active plan and does a
small, bounded reconciliation probe anchored on that date (never "today",
never a full-history scan) to materialize just that session's episode.

See `docs/recovery_episode_refresh_execplan.md` for the full design and
Decision Log. All fixtures use real temporary SQLite files (`tmp_path`) and
frozen dates; no live Garmin/Intervals.icu access.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from services.recovery_analytics import (
    refresh_recovery_episodes,
    refresh_recovery_episodes_best_effort,
)


pytestmark = pytest.mark.smoke

AS_OF = date(2026, 7, 18)
OLD_DATE = AS_OF - timedelta(days=140)  # ~20 weeks back; well past the 12-week (84-day) horizon


def _old_session_plan(session_date: date, *, sport: str = "bike", tss: float = 60.0) -> dict:
    day_iso = session_date.isoformat()
    return {
        "goal_type": "triathlon",
        "distance": "olympic",
        "start_week": session_date,
        "weekly_tss_plan": [tss],
        "phases": ["Build"],
        "daily_plan": [
            (datetime.combine(session_date, datetime.min.time()), tss, {sport: tss})
        ],
        "session_templates": [
            {
                "date": day_iso,
                "week_index": 0,
                "day_index": 0,
                "phase": "Build",
                "session_role": "long",
                "session_focus": "Endurance",
                "sport": sport,
                "duration_minutes": 60,
                "kind": "single",
                "template_key": f"{sport}_endurance",
                "definition_snapshot": {
                    "step_builder_key": "endurance",
                    "catalog_version": "workout_catalog_v1",
                },
            }
        ],
        "weekly_summary": [],
        "constraint_summary": {},
        "near_term_edit_version": 0,
    }


def _snapshot(db: Database, day: date, score: float) -> None:
    day_iso = day.isoformat()
    canonical = {
        "score": score,
        "status": "ready",
        "computed_at": day_iso,
        "as_of_date": day_iso,
        "rule_version": "readiness_snapshot_v2",
        "confidence": 0.8,
        "stale": False,
        "is_provisional": False,
        "source_completeness": 0.8,
        "missing_inputs": [],
        "factors": [{"key": "hrv", "as_of": day_iso, "stale_input": False}],
        "drivers": [],
        "tsb": {"ctl": 20, "atl": 25, "tsb": -5, "as_of": day_iso},
        "input_provenance": {"as_of_date": day_iso},
    }
    db.save_readiness_snapshot(
        {
            "fingerprint": f"capture-{day_iso}-{score}",
            "target_key": f"readiness:prospective:{day_iso}",
            "capture_mode": "prospective",
            "local_date": day_iso,
            "athlete_timezone": "Europe/Moscow",
            "observed_at_utc": f"{day_iso}T05:00:00Z",
            "capture_run_id": f"run-{day_iso}",
            "rule_version": "readiness_snapshot_v2",
            "score": score,
            "status": "ready",
            "confidence": 0.8,
            "as_of_date": day_iso,
            "is_provisional": False,
            "source_completeness": 0.8,
            "stale": False,
            "eligibility_status": "eligible",
            "eligibility_reasons": [],
            "factors": canonical["factors"],
            "drivers": [],
            "missing_inputs": [],
            "tsb": canonical["tsb"],
            "provenance": canonical["input_provenance"],
            "snapshot": canonical,
        }
    )


def _build_old_matched_session(
    db: Database,
    *,
    session_date: date,
    activity_id: str,
    sport: str = "bike",
    with_snapshots: bool = True,
) -> tuple[dict, str]:
    """Plant one fully-evidenced matched session at an old date.

    Returns (checkpoint, session_id).
    """
    plan = _old_session_plan(session_date, sport=sport)
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    session_id = checkpoint["goal_plan_snapshot"]["session_templates"][0]["session_id"]
    db.save_activities(
        [
            {
                "activity_id": activity_id,
                "date": session_date.isoformat(),
                "started_at_utc": f"{session_date.isoformat()}T08:00:00Z",
                "sport": sport,
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )
    db.save_plan_actual_match(
        {
            "fingerprint": f"match-{activity_id}",
            "target_key": f"session:{session_id}",
            "session_id": session_id,
            "base_checkpoint_id": checkpoint["id"],
            "session_date": session_date.isoformat(),
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {"date": session_date.isoformat(), "sport": sport, "role": "long"},
            "actual_activity_ids": [activity_id],
            "actual_snapshot": {"tss": 60.0, "sport": sport, "role": "long"},
            "evidence": ["User explicitly confirmed activity match"],
            "rule_version": "plan_actual_match_v1",
        }
    )
    if with_snapshots:
        for offset, score in ((0, 70), (1, 62), (2, 68), (3, 71)):
            _snapshot(db, session_date + timedelta(days=offset), score)
    return checkpoint, session_id


def _spy(monkeypatch, module, name):
    """Wrap `module.name` to record every call's args/kwargs while still
    delegating to the real implementation, so behavior is unchanged."""
    calls: list[dict] = []
    original = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


# ---------------------------------------------------------------------------
# Gate 1: ordinary bounded post-sync refresh stays bounded and untouched.
# ---------------------------------------------------------------------------


def test_bounded_sync_refresh_ignores_old_session_and_probes_with_fixed_twelve_week_window(
    tmp_path, monkeypatch
):
    from services import reconciliation as reconciliation_service

    db = Database(str(tmp_path / "bounded.db"))
    _checkpoint, session_id = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="old-ride"
    )
    calls = _spy(monkeypatch, reconciliation_service, "reconciliation_at")

    result = refresh_recovery_episodes(db, as_of=AS_OF)

    assert result["scope"] == "bounded_sync"
    assert result["created"] == 0
    assert db.get_recovery_episodes(latest_only=True) == []
    assert len(calls) == 1
    assert calls[0]["kwargs"]["weeks"] == 12
    assert calls[0]["kwargs"]["as_of"] == AS_OF
    assert calls[0]["kwargs"]["include_provider"] is False

    retry = refresh_recovery_episodes(db, as_of=AS_OF)
    assert retry["created"] == 0
    assert retry["scope"] == "bounded_sync"


# ---------------------------------------------------------------------------
# Gate 2: targeted refresh materializes the old session via a small probe
# anchored on the session's own date, never on "today" and never 12 weeks.
# ---------------------------------------------------------------------------


def test_targeted_refresh_materializes_old_session_via_probe_anchored_on_session_date(
    tmp_path, monkeypatch
):
    from services import reconciliation as reconciliation_service

    db = Database(str(tmp_path / "targeted.db"))
    _checkpoint, session_id = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="old-ride"
    )
    calls = _spy(monkeypatch, reconciliation_service, "reconciliation_at")

    result = refresh_recovery_episodes(db, as_of=AS_OF, target_session_ids=[session_id])

    assert result["scope"] == "targeted"
    assert result["created"] == 1
    assert result["requested_session_ids"] == [session_id]
    assert result["processed"] == [
        {"session_id": session_id, "status": "created", "episode_id": result["processed"][0]["episode_id"]}
    ]
    assert result["not_found"] == []

    episodes = db.get_recovery_episodes(latest_only=True)
    assert len(episodes) == 1
    assert episodes[0]["session_id"] == session_id
    assert episodes[0]["status"] == "eligible"
    assert episodes[0]["outcome"]["readiness_deltas"] == {"d1": -8.0, "d2": -2.0, "d3": 1.0}

    assert len(calls) == 1
    assert calls[0]["kwargs"]["weeks"] == 1
    assert calls[0]["kwargs"]["as_of"] == OLD_DATE
    assert calls[0]["kwargs"]["include_provider"] is False

    retry = refresh_recovery_episodes(db, as_of=AS_OF, target_session_ids=[session_id])
    assert retry["created"] == 0
    assert retry["processed"][0]["status"] == "unchanged"
    assert len(db.get_recovery_episodes(latest_only=True)) == 1


# ---------------------------------------------------------------------------
# Gate 3: correction and tombstone of an old matched session each append
# exactly one new append-only episode revision; identical retry is a no-op.
# ---------------------------------------------------------------------------


def test_correction_and_tombstone_of_old_session_each_append_one_new_revision(tmp_path):
    from api.session_feedback import (
        correct_session_feedback,
        submit_session_feedback,
        tombstone_session_feedback,
    )

    db = Database(str(tmp_path / "revisions.db"))
    _checkpoint, session_id = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="old-ride"
    )
    now = datetime.combine(AS_OF, datetime.min.time(), tzinfo=timezone.utc)

    first = submit_session_feedback(
        db,
        {
            "session_id": session_id,
            "client_submission_fingerprint": "submit-1",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 6,
            "quality_rating_1_5": 4,
            "note": "Solid long ride",
        },
        now_utc=now,
    )
    episodes = db.get_recovery_episodes(latest_only=True)
    assert len(episodes) == 1
    assert episodes[0]["revision"] == 1
    assert episodes[0]["feedback_id"] == first["feedback"]["id"]

    no_op = refresh_recovery_episodes_best_effort(db, as_of=AS_OF, target_session_ids=[session_id])
    assert no_op["created"] == 0

    corrected = correct_session_feedback(
        db,
        first["feedback"]["id"],
        {
            "client_submission_fingerprint": "correct-1",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 9,
            "quality_rating_1_5": 2,
            "note": "Actually it was brutal",
        },
        now_utc=now + timedelta(minutes=5),
    )
    episodes = db.get_recovery_episodes(latest_only=True)
    assert len(episodes) == 1
    assert episodes[0]["revision"] == 2
    assert episodes[0]["feedback_id"] == corrected["feedback"]["id"]
    assert episodes[0]["feedback_id"] != first["feedback"]["id"]

    tombstoned = tombstone_session_feedback(
        db,
        corrected["feedback"]["id"],
        client_submission_fingerprint="tombstone-1",
        now_utc=now + timedelta(minutes=10),
    )
    episodes = db.get_recovery_episodes(latest_only=True)
    assert len(episodes) == 1
    assert episodes[0]["revision"] == 3
    assert episodes[0]["feedback_id"] == tombstoned["feedback"]["id"]

    history = db.get_recovery_episodes(latest_only=False)
    assert len(history) == 3


# ---------------------------------------------------------------------------
# Gate 4: targeted refresh materializes only the requested session_id;
# another old session in the same checkpoint stays byte-unchanged.
# ---------------------------------------------------------------------------


def test_targeted_refresh_leaves_sibling_old_session_byte_unchanged(tmp_path):
    db = Database(str(tmp_path / "sibling.db"))
    plan = _old_session_plan(OLD_DATE, sport="bike")
    other_date = OLD_DATE + timedelta(days=21)
    plan["daily_plan"].append(
        (datetime.combine(other_date, datetime.min.time()), 45.0, {"run": 45.0})
    )
    plan["session_templates"].append(
        {
            "date": other_date.isoformat(),
            "week_index": 3,
            "day_index": 0,
            "phase": "Build",
            "session_role": "easy",
            "session_focus": "Aerobic",
            "sport": "run",
            "duration_minutes": 45,
            "kind": "single",
            "template_key": "run_easy",
            "definition_snapshot": {
                "step_builder_key": "aerobic",
                "catalog_version": "workout_catalog_v1",
            },
        }
    )
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    templates = checkpoint["goal_plan_snapshot"]["session_templates"]
    session_a = next(item for item in templates if item["date"] == OLD_DATE.isoformat())["session_id"]
    session_b = next(item for item in templates if item["date"] == other_date.isoformat())["session_id"]

    for session_id, session_date, activity_id, sport in (
        (session_a, OLD_DATE, "ride-a", "bike"),
        (session_b, other_date, "run-b", "run"),
    ):
        db.save_activities(
            [
                {
                    "activity_id": activity_id,
                    "date": session_date.isoformat(),
                    "started_at_utc": f"{session_date.isoformat()}T08:00:00Z",
                    "sport": sport,
                    "duration_minutes": 45,
                    "tss": 45.0,
                }
            ]
        )
        db.save_plan_actual_match(
            {
                "fingerprint": f"match-{activity_id}",
                "target_key": f"session:{session_id}",
                "session_id": session_id,
                "base_checkpoint_id": checkpoint["id"],
                "session_date": session_date.isoformat(),
                "match_status": "matched",
                "match_method": "user_confirmed",
                "confidence": 1.0,
                "planned_snapshot": {"date": session_date.isoformat(), "sport": sport, "role": "easy"},
                "actual_activity_ids": [activity_id],
                "actual_snapshot": {"tss": 45.0, "sport": sport, "role": "easy"},
                "evidence": ["User explicitly confirmed activity match"],
                "rule_version": "plan_actual_match_v1",
            }
        )
        for offset, score in ((0, 70), (1, 62), (2, 68), (3, 71)):
            _snapshot(db, session_date + timedelta(days=offset), score)

    both = refresh_recovery_episodes(db, as_of=AS_OF, target_session_ids=[session_a, session_b])
    assert both["created"] == 2
    before = {row["session_id"]: row for row in db.get_recovery_episodes(latest_only=True)}
    assert set(before) == {session_a, session_b}

    # Feed session A new feedback (changes its evidence) and target only A.
    from api.session_feedback import submit_session_feedback

    submit_session_feedback(
        db,
        {
            "session_id": session_a,
            "client_submission_fingerprint": "submit-a-only",
            "completion_status": "completed",
            "completion_pct": 100,
            "session_rpe_1_10": 7,
            "quality_rating_1_5": 4,
            "note": "A only",
        },
        now_utc=datetime.combine(AS_OF, datetime.min.time(), tzinfo=timezone.utc),
    )

    after = {row["session_id"]: row for row in db.get_recovery_episodes(latest_only=True)}
    assert after[session_a]["revision"] == 2
    assert after[session_b] == before[session_b]


# ---------------------------------------------------------------------------
# Gate 5: duplicate target ids are deduplicated deterministically; multiple
# valid targets get stable ordering and one probe per distinct target date.
# ---------------------------------------------------------------------------


def test_duplicate_targets_dedup_with_stable_order_and_one_probe_per_distinct_date(
    tmp_path, monkeypatch
):
    from services import reconciliation as reconciliation_service

    db = Database(str(tmp_path / "dedup.db"))
    other_date = OLD_DATE + timedelta(days=21)
    _checkpoint_a, session_a = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="ride-a"
    )
    plan_b = _old_session_plan(other_date, sport="run")
    checkpoint_b = db.save_planning_checkpoint(build_planning_checkpoint(plan_b))
    session_b = checkpoint_b["goal_plan_snapshot"]["session_templates"][0]["session_id"]
    db.save_activities(
        [
            {
                "activity_id": "run-b",
                "date": other_date.isoformat(),
                "started_at_utc": f"{other_date.isoformat()}T08:00:00Z",
                "sport": "run",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )
    db.save_plan_actual_match(
        {
            "fingerprint": "match-run-b",
            "target_key": f"session:{session_b}",
            "session_id": session_b,
            "base_checkpoint_id": checkpoint_b["id"],
            "session_date": other_date.isoformat(),
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "planned_snapshot": {"date": other_date.isoformat(), "sport": "run", "role": "long"},
            "actual_activity_ids": ["run-b"],
            "actual_snapshot": {"tss": 60.0, "sport": "run", "role": "long"},
            "evidence": ["User explicitly confirmed activity match"],
            "rule_version": "plan_actual_match_v1",
        }
    )
    for offset, score in ((0, 70), (1, 62), (2, 68), (3, 71)):
        _snapshot(db, other_date + timedelta(days=offset), score)

    # NOTE: checkpoint_b is now the active checkpoint, so it does not carry
    # session_a's template. Use each session while its own checkpoint was
    # still active by targeting both in one call against a merged plan
    # instead: rebuild a single checkpoint carrying both templates so both
    # ids resolve against the one active checkpoint, matching how a real
    # multi-session active plan looks.
    merged_plan = _old_session_plan(OLD_DATE, sport="bike")
    merged_plan["daily_plan"].append(
        (datetime.combine(other_date, datetime.min.time()), 60.0, {"run": 60.0})
    )
    merged_plan["session_templates"].append(dict(plan_b["session_templates"][0]))
    merged_checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(merged_plan))
    merged_templates = merged_checkpoint["goal_plan_snapshot"]["session_templates"]
    merged_a = next(t for t in merged_templates if t["date"] == OLD_DATE.isoformat())["session_id"]
    merged_b = next(t for t in merged_templates if t["date"] == other_date.isoformat())["session_id"]
    assert merged_a == session_a  # content-derived identity is stable across checkpoints
    assert merged_b == session_b

    calls = _spy(monkeypatch, reconciliation_service, "reconciliation_at")
    result = refresh_recovery_episodes(
        db, as_of=AS_OF, target_session_ids=[session_a, session_a, session_b, session_a]
    )

    assert result["requested_session_ids"] == [session_a, session_b]
    assert [item["session_id"] for item in result["processed"]] == [session_a, session_b]
    assert result["created"] == 2
    assert len(calls) == 2  # one probe per distinct target date, not per requested id


# ---------------------------------------------------------------------------
# Gate 6: unknown / absent-from-active-checkpoint / future-dated targets
# fail closed with a machine-readable reason and never broaden the probe.
# ---------------------------------------------------------------------------


def test_unknown_absent_and_future_dated_targets_fail_closed(tmp_path, monkeypatch):
    from services import reconciliation as reconciliation_service

    db = Database(str(tmp_path / "fail-closed.db"))
    _stale_checkpoint, stale_session_id = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="stale-ride"
    )
    # Replan: save a new, unrelated active checkpoint that does not carry
    # the old session's template at all.
    replan = _old_session_plan(AS_OF - timedelta(days=1), sport="swim")
    db.save_planning_checkpoint(build_planning_checkpoint(replan))

    future_date = AS_OF + timedelta(days=5)
    future_plan = _old_session_plan(future_date, sport="run")
    # Becomes the new active checkpoint: its one session is present (so
    # identity resolution succeeds) but dated after as_of, exercising the
    # "target_date_after_as_of" reason distinct from "not found at all".
    future_checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(future_plan))
    future_session_id = future_checkpoint["goal_plan_snapshot"]["session_templates"][0]["session_id"]

    calls = _spy(monkeypatch, reconciliation_service, "reconciliation_at")
    result = refresh_recovery_episodes(
        db,
        as_of=AS_OF,
        target_session_ids=["totally-unknown-id", stale_session_id, future_session_id],
    )

    by_id = {item["session_id"]: item for item in result["processed"]}
    assert by_id["totally-unknown-id"]["status"] == "not_found"
    assert by_id["totally-unknown-id"]["reason"] == "session_not_found_in_active_checkpoint"
    assert by_id[future_session_id]["status"] == "not_found"
    assert by_id[future_session_id]["reason"] == "target_date_after_as_of"

    # stale_session_id belongs to a superseded (non-active) checkpoint, so it
    # is also absent from the currently active checkpoint's templates.
    assert by_id[stale_session_id]["status"] == "not_found"
    assert by_id[stale_session_id]["reason"] == "session_not_found_in_active_checkpoint"

    assert result["created"] == 0
    assert sorted(result["not_found"]) == sorted(
        ["totally-unknown-id", stale_session_id, future_session_id]
    )
    assert calls == []  # no probe attempted for any failed-closed target
    assert db.get_recovery_episodes(latest_only=True) == []


# ---------------------------------------------------------------------------
# Gate 7: provider access is impossible in both scopes.
# ---------------------------------------------------------------------------


def test_provider_access_impossible_in_both_scopes(tmp_path, monkeypatch):
    from services import intervals_icu

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("get_client must never be called when include_provider=False")

    monkeypatch.setattr(intervals_icu, "get_client", _raise_if_called)

    db = Database(str(tmp_path / "provider-gate.db"))
    _checkpoint, session_id = _build_old_matched_session(
        db, session_date=OLD_DATE, activity_id="old-ride"
    )

    bounded = refresh_recovery_episodes(db, as_of=AS_OF)
    assert bounded["scope"] == "bounded_sync"

    targeted = refresh_recovery_episodes(db, as_of=AS_OF, target_session_ids=[session_id])
    assert targeted["scope"] == "targeted"
    assert targeted["created"] == 1


# ---------------------------------------------------------------------------
# Gate 8 (match side): the production call site passes the exact affected
# session_id to refresh_recovery_episodes_best_effort as a target.
# ---------------------------------------------------------------------------


def test_record_plan_actual_match_call_site_targets_old_session(tmp_path, monkeypatch):
    from api import planning_service as ps
    from services import recovery_analytics

    db = Database(str(tmp_path / "match-call-site.db"))
    plan = _old_session_plan(OLD_DATE, sport="bike")
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    session_id = checkpoint["goal_plan_snapshot"]["session_templates"][0]["session_id"]
    db.save_activities(
        [
            {
                "activity_id": "old-confirm",
                "date": OLD_DATE.isoformat(),
                "started_at_utc": f"{OLD_DATE.isoformat()}T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )
    calls = []
    original = recovery_analytics.refresh_recovery_episodes_best_effort

    def spy(db_arg, **kwargs):
        calls.append(kwargs)
        return original(db_arg, **kwargs)

    monkeypatch.setattr(recovery_analytics, "refresh_recovery_episodes_best_effort", spy)

    saved = ps.record_plan_actual_match(
        db,
        base_checkpoint_id=checkpoint["id"],
        session_id=session_id,
        activity_ids=["old-confirm"],
        actual_role="long",
        action="confirm",
    )

    assert saved["match_method"] == "user_confirmed"
    assert len(calls) == 1
    assert calls[0]["target_session_ids"] == [session_id]

    episodes = db.get_recovery_episodes(latest_only=True)
    assert len(episodes) == 1
    assert episodes[0]["session_id"] == session_id


# ---------------------------------------------------------------------------
# Gate 9: admin resolve does not double-create an episode revision when its
# match and synthesized feedback are committed in one request.
# ---------------------------------------------------------------------------


def test_admin_resolve_of_old_session_creates_exactly_one_episode_revision(tmp_path):
    from api.session_feedback import resolve_prediction_via_feedback

    db = Database(str(tmp_path / "admin-resolve.db"))
    plan = _old_session_plan(OLD_DATE, sport="bike")
    checkpoint = db.save_planning_checkpoint(build_planning_checkpoint(plan))
    session_id = checkpoint["goal_plan_snapshot"]["session_templates"][0]["session_id"]
    prediction = db.save_session_quality_prediction(
        fingerprint="admin-forecast-old",
        target_key=f"{checkpoint['id']}:{OLD_DATE.isoformat()}:0:session_quality_v1",
        rule_version="session_quality_v1",
        target_date=OLD_DATE.isoformat(),
        plan_checkpoint_id=checkpoint["id"],
        plan_session_index=0,
        planned_session={
            "date": OLD_DATE.isoformat(),
            "index": 0,
            "role": "long",
            "sport": "bike",
            "tss": 60.0,
            "duration_minutes": 60,
        },
        forecast={"prediction_pct": 70, "prediction_band": "uncertain"},
        inputs={"readiness_source": "canonical_snapshot"},
        evidence=["pre-start"],
        created_at=f"{OLD_DATE.isoformat()}T06:00:00Z",
    )["prediction"]
    db.save_activities(
        [
            {
                "activity_id": "admin-ride",
                "date": OLD_DATE.isoformat(),
                "started_at_utc": f"{OLD_DATE.isoformat()}T08:00:00Z",
                "sport": "bike",
                "duration_minutes": 60,
                "tss": 60.0,
            }
        ]
    )

    result = resolve_prediction_via_feedback(
        db,
        prediction["id"],
        activity_ids=["admin-ride"],
        actual_role="long",
        quality_rating_1_5=5,
        note="admin resolve old session",
        submitted_at=f"{AS_OF.isoformat()}T09:00:00Z",
    )

    assert result["predictions"][0]["status"] == "scored"
    episodes = db.get_recovery_episodes(latest_only=False)
    assert len(episodes) == 1
    assert episodes[0]["session_id"] == session_id
    assert episodes[0]["revision"] == 1
