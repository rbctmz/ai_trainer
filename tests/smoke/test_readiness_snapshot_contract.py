"""Smoke tests for the shared readiness snapshot API contract.

Contributor-safe: temp SQLite only, no Garmin credentials, no network.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import pytest

from data.database import Database
from utils.athlete_time import athlete_local_date


def _events(streaming_response) -> list[dict[str, Any]]:
    async def collect() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for raw in streaming_response.body_iterator:
            text = raw if isinstance(raw, str) else raw.decode()
            if text.startswith("data:"):
                out.append(json.loads(text[5:].strip()))
        return out

    return asyncio.run(collect())


def _seed_activity(db: Database, date_str: str | None = None) -> None:
    date_str = date_str or athlete_local_date().isoformat()
    db.save_activities(
        [
            {
                "activity_id": f"act-{date_str}",
                "date": date_str,
                "sport": "running",
                "duration_minutes": 35,
                "distance_km": 5.5,
                "tss": 32.0,
            }
        ]
    )


def _seed_full_readiness(db: Database, date_str: str | None = None) -> None:
    date_str = date_str or athlete_local_date().isoformat()
    db.sync_sleep_data(
        {
            date_str: {
                "total_sleep_minutes": 480,
                "sleep_score": 82.0,
                "sleep_efficiency": 94.0,
            }
        }
    )
    db.sync_hrv_data({date_str: {"rmssd": 45.0, "stress_score": 20.0, "recovery_score": 77.0}})
    db.sync_daily_health({date_str: {"resting_hr": 52, "steps": 8500}})
    db.sync_training_status(
        {
            date_str: {
                "training_status": "PRODUCTIVE",
                "training_readiness": 78.0,
                "recovery_time_hours": 14.0,
            }
        }
    )


def test_readiness_snapshot_empty_db_is_unknown_and_provisional(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    snapshot = build_readiness_snapshot(Database(str(tmp_path / "empty.db")))

    assert snapshot["score"] is None
    assert snapshot["status"] == "unknown"
    assert snapshot["computed_at"] is None
    assert snapshot["is_provisional"] is True
    assert snapshot["source_completeness"] == 0.0
    assert set(snapshot["missing_inputs"]) == {
        "sleep",
        "hrv",
        "resting_hr",
    }
    assert snapshot["stale"] is False
    assert snapshot["factors"] == []
    assert "Недостаточно" in snapshot["reason"]


def test_readiness_snapshot_full_data_is_complete_and_anchored(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "full.db"))
    _seed_full_readiness(db)

    snapshot = build_readiness_snapshot(db)

    assert snapshot["score"] is not None
    assert snapshot["status"] in {"limited", "ready", "strong"}
    assert snapshot["computed_at"] == athlete_local_date().isoformat()
    assert snapshot["is_provisional"] is False
    assert snapshot["source_completeness"] == 1.0
    assert snapshot["missing_inputs"] == []
    assert snapshot["stale"] is False
    assert {factor["key"] for factor in snapshot["factors"]} >= {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }


def test_readiness_snapshot_partial_data_lists_missing_inputs(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "partial.db"))
    today = athlete_local_date().isoformat()
    db.sync_sleep_data({today: {"total_sleep_minutes": 420, "sleep_score": 68.0}})
    db.sync_hrv_data({today: {"rmssd": 35.0, "stress_score": 30.0}})

    snapshot = build_readiness_snapshot(db)

    assert snapshot["score"] is not None
    assert snapshot["is_provisional"] is True
    assert snapshot["source_completeness"] == 0.67
    assert snapshot["missing_inputs"] == ["resting_hr"]
    assert "частичным" in snapshot["reason"]


def test_readiness_snapshot_stale_data_is_marked_stale(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "stale.db"))
    old = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    _seed_full_readiness(db, old)

    snapshot = build_readiness_snapshot(db, stale_after_days=2)

    assert snapshot["score"] is not None
    assert snapshot["computed_at"] == old
    assert snapshot["stale"] is True
    assert snapshot["status"] == "stale"
    assert snapshot["is_provisional"] is True
    assert "устар" in snapshot["reason"].lower()


def test_dashboard_summary_exposes_readiness_snapshot(tmp_path):
    from api.deps import make_headless_state
    from api.routers.dashboard import dashboard_summary

    db = Database(str(tmp_path / "dashboard.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    payload = dashboard_summary(db=db, state=make_headless_state(database=db))

    assert payload["has_data"] is True
    snapshot = payload["readiness_snapshot"]
    assert snapshot["score"] is not None
    assert snapshot["source_completeness"] == 1.0


def test_dashboard_summary_today_uses_canonical_readiness_snapshot(tmp_path):
    from api.deps import make_headless_state
    from api.routers.dashboard import dashboard_summary

    db = Database(str(tmp_path / "dashboard-aligned.db"))
    today = datetime.now()
    activities = []
    for offset in (0, 35, 45, 55, 65, 75):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        activities.append(
            {
                "activity_id": f"load-{offset}",
                "date": day,
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 80.0,
            }
        )
    db.save_activities(activities)
    _seed_full_readiness(db)

    payload = dashboard_summary(db=db, state=make_headless_state(database=db))
    snapshot = payload["readiness_snapshot"]
    today_payload = payload["summary"]["today"]

    assert today_payload["readiness"] == round(snapshot["score"])
    assert today_payload["ctl"] == round(snapshot["tsb"]["ctl"], 1)
    assert today_payload["tsb"] == round(snapshot["tsb"]["tsb"], 1)


def test_dashboard_widgets_use_canonical_readiness_load(tmp_path):
    from api.deps import make_headless_state
    from api.routers.dashboard import dashboard_widgets

    db = Database(str(tmp_path / "widgets-aligned.db"))
    today = datetime.now()
    activities = []
    for offset in (0, 35, 45, 55, 65, 75):
        day = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        activities.append(
            {
                "activity_id": f"widget-load-{offset}",
                "date": day,
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 25.0,
                "tss": 80.0,
            }
        )
    db.save_activities(activities)
    _seed_full_readiness(db)

    payload = dashboard_widgets(db=db, state=make_headless_state(database=db))
    snapshot = payload["readiness_snapshot"]
    ctl = float(snapshot["tsb"]["ctl"])
    tsb = float(snapshot["tsb"]["tsb"])

    assert payload["training_score"]["fitness"]["detail"] == f"CTL {int(ctl)}"
    assert payload["training_score"]["load_mgmt"]["detail"] == f"TSB {tsb:+.1f}"
    assert f"TSB {tsb:+.1f}" in payload["daily_outlook"]["text"]


def test_planning_status_exposes_readiness_snapshot(tmp_path):
    from api.routers.planning import planning_status

    db = Database(str(tmp_path / "planning.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    payload = planning_status(db=db)

    assert payload["metrics"]
    assert payload["readiness_snapshot"]["score"] is not None
    assert payload["readiness_snapshot"]["is_provisional"] is False


def test_coach_stream_meta_exposes_readiness_snapshot(tmp_path, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr(Settings, "CHATS_DIR", str(tmp_path / "chats"), raising=False)

    from api.routers import coach as coach_mod

    db = Database(str(tmp_path / "coach.db"))
    _seed_activity(db)
    _seed_full_readiness(db)

    req = coach_mod.ChatRequest(message="Как восстановление?", provider="mock")
    events = _events(coach_mod.coach_chat(req, db))

    assert events[0]["type"] == "meta"
    snapshot = events[0]["readiness_snapshot"]
    assert snapshot["score"] is not None
    assert snapshot["source_completeness"] == 1.0


# ---------------------------------------------------------------------------
# Issue #557 M2: additive freshness / intervention contract on the snapshot.
# Legacy keys (score, confidence, stale, source_completeness, is_provisional)
# keep their semantics; freshness and intervention_* are new channels.
# ---------------------------------------------------------------------------


def test_snapshot_without_provenance_reports_data_gap_and_keeps_legacy_verdict(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "freshness.db"))
    _seed_full_readiness(db)  # M3 provenance columns stay NULL in this fixture

    snapshot = build_readiness_snapshot(db)

    # Additive channel: a stored row proves nothing about *when* it was measured,
    # so no measurement is confirmed for today and the gate input is blocked.
    freshness = snapshot["freshness"]
    assert freshness["state"] == "data_gap"
    assert freshness["anchor"] == athlete_local_date().isoformat()
    assert freshness["confirmed_today"] == []
    assert set(freshness["unverified"]) == {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }
    assert freshness["outdated"] == []
    assert freshness["invalid"] == []
    assert freshness["missing"] == ["tsb"]
    assert freshness["intervention_eligible"] == []
    assert freshness["blocked_reason"] == "no_intervention_eligible_factors"
    # The stress reference factor is not a weighted input and never lands in a bucket.
    for bucket in ("confirmed_today", "outdated", "unverified", "invalid", "missing"):
        assert "stress" not in freshness[bucket]

    assert snapshot["eligible_inputs"] == []
    assert {item["key"] for item in snapshot["ineligible_inputs"]} == {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }
    assert snapshot["intervention_score"] is None
    assert snapshot["intervention_confidence"] == 0.0
    assert snapshot["intervention_blocked_reason"] == "no_intervention_eligible_factors"

    # Frozen legacy channel keeps its own (presence-based) verdict.
    assert snapshot["is_provisional"] is False
    assert snapshot["score"] is not None
    assert snapshot["confidence"] == 0.8
    assert snapshot["stale"] is False


def test_snapshot_confirms_sleep_only_with_payload_observation_date(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "sleep_provenance_snapshot.db"))
    today = athlete_local_date().isoformat()
    db.sync_sleep_data(
        {
            today: {
                "total_sleep_minutes": 480,
                "sleep_score": 82.0,
                "sleep_score_observed_at": today,
            }
        }
    )

    snapshot = build_readiness_snapshot(db)

    freshness = snapshot["freshness"]
    assert freshness["confirmed_today"] == ["sleep"]
    assert "sleep" not in freshness["unverified"]
    assert freshness["state"] == "provisional"  # HRV/RHR are still unconfirmed
    assert snapshot["eligible_inputs"] == ["sleep"]
    assert snapshot["intervention_confidence"] == 0.2
    assert snapshot["intervention_score"] == pytest.approx(82.0)
    assert snapshot["intervention_blocked_reason"] is None
    # Another-day payload date on the same row is outdated, never fresh.
    db.sync_sleep_data(
        {
            today: {
                "total_sleep_minutes": 480,
                "sleep_score": 82.0,
                "sleep_score_observed_at": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            }
        }
    )
    outdated = build_readiness_snapshot(db)
    assert outdated["freshness"]["confirmed_today"] == []
    assert outdated["freshness"]["outdated"] == ["sleep"]
    assert outdated["intervention_score"] is None


def test_snapshot_empty_db_reports_data_gap_freshness(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    snapshot = build_readiness_snapshot(Database(str(tmp_path / "empty_v2.db")))

    freshness = snapshot["freshness"]
    assert freshness["state"] == "data_gap"
    assert freshness["confirmed_today"] == []
    assert freshness["outdated"] == []
    assert freshness["unverified"] == []
    assert freshness["invalid"] == []
    assert set(freshness["missing"]) == {"sleep", "hrv", "resting_hr", "training_readiness", "tsb"}
    assert freshness["intervention_eligible"] == []
    assert freshness["blocked_reason"] == "no_intervention_eligible_factors"

    assert snapshot["intervention_score"] is None
    assert snapshot["intervention_confidence"] == 0.0
    assert snapshot["eligible_inputs"] == []
    assert snapshot["ineligible_inputs"] == []
    assert snapshot["intervention_blocked_reason"] == "no_intervention_eligible_factors"


def test_snapshot_stale_data_blocks_intervention_but_keeps_stale_flag(tmp_path):
    from api.readiness_snapshot import build_readiness_snapshot

    db = Database(str(tmp_path / "stale_v2.db"))
    old = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    _seed_full_readiness(db, old)

    snapshot = build_readiness_snapshot(db, stale_after_days=2)

    freshness = snapshot["freshness"]
    assert freshness["state"] == "data_gap"
    assert freshness["outdated"] == []
    assert set(freshness["unverified"]) == {
        "sleep",
        "hrv",
        "resting_hr",
        "training_readiness",
    }
    assert snapshot["intervention_score"] is None
    assert snapshot["intervention_confidence"] == 0.0
    assert snapshot["intervention_blocked_reason"] == "no_intervention_eligible_factors"
    # Frozen legacy verdict is untouched by the new channel.
    assert snapshot["stale"] is True
    assert snapshot["status"] == "stale"


def test_snapshot_keeps_invalid_observations_in_their_own_bucket(tmp_path, monkeypatch):
    from datetime import date

    from models.readiness import compute_readiness_today as real_compute

    from services import readiness_snapshot as snapshot_module

    def _with_future_rhr(sleep_df, hrv_df, health_df, training_df, activities_df, **kwargs):
        """Inject a provider observation dated tomorrow into the health frame."""
        if health_df is not None and not health_df.empty:
            anchor = kwargs.get("today") or date.today()
            health_df = health_df.assign(
                resting_hr_observed_at=(anchor + timedelta(days=1)).isoformat()
            )
        return real_compute(
            sleep_df, hrv_df, health_df, training_df, activities_df, **kwargs
        )

    monkeypatch.setattr(snapshot_module, "compute_readiness_today", _with_future_rhr)

    db = Database(str(tmp_path / "invalid_obs.db"))
    today = athlete_local_date().isoformat()
    db.sync_sleep_data(
        {
            today: {
                "total_sleep_minutes": 480,
                "sleep_score": 82.0,
                "sleep_score_observed_at": today,
            }
        }
    )
    db.sync_daily_health({today: {"resting_hr": 52}})

    snapshot = snapshot_module._build_measured_readiness_snapshot(db)

    freshness = snapshot["freshness"]
    assert freshness["invalid"] == ["resting_hr"]
    assert "resting_hr" not in freshness["unverified"]
    assert freshness["confirmed_today"] == ["sleep"]
    assert freshness["state"] == "provisional"
    assert "resting_hr" not in snapshot["eligible_inputs"]
    invalid = next(item for item in snapshot["ineligible_inputs"] if item["key"] == "resting_hr")
    assert invalid["observation_status"] == "invalid"
    assert invalid["reason"] == "observation_in_future"
