"""M6 (Issue #205): A/B race forecast load feeds CTL/ATL and weekly accounting.

A race is a hard effort: the load model must anticipate it. But the athlete's
race is sacred — the race day stays protected, is never materialized as a
deliverable AI Trainer session, and the athlete's own provider event is never
overwritten. The forecast lives OUTSIDE the discipline budget chain
(budget == sessions == weekly buckets stays intact); it is an explicit
`race_forecast_loads` truth consumed by the Banister simulation and shown as
`race_forecast_tss` on the race week's summary row.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from models.training_planner import apply_race_event_overlays


pytestmark = pytest.mark.smoke


def _constant_plan(start: date, days: int, tss: float = 40.0):
    daily = [
        (
            datetime.combine(start + timedelta(days=offset), datetime.min.time()),
            tss,
            {"run": 0.0, "bike": tss, "swim": 0.0},
        )
        for offset in range(days)
    ]
    summaries = []
    for week_index in range((days + 6) // 7):
        day_count = min(7, days - week_index * 7)
        summaries.append(
            {
                "week_start": start + timedelta(days=week_index * 7),
                "phase": "Race Week",
                "weekly_tss": int(tss * day_count),
                "bike": tss * day_count,
                "run": 0.0,
                "swim": 0.0,
                "day_roles": ["easy"] * 7,
                "day_focuses": ["—"] * 7,
            }
        )
    return daily, summaries


def test_overlay_emits_bounded_race_forecast_for_a_and_b_only():
    start = date(2026, 9, 21)
    daily, summaries = _constant_plan(start, 21)
    events = [
        {"date": "2026-09-26", "priority": "C", "label": "Club", "confirmed": True},
        {"date": "2026-10-03", "priority": "B", "label": "Tune-up", "confirmed": True},
        {"date": "2026-10-10", "priority": "A", "label": "Main", "confirmed": True},
    ]

    adjusted, after_summaries, metadata = apply_race_event_overlays(
        daily, summaries, events, goal_type="Триатлон"
    )

    forecasts = {row["priority"]: row for row in metadata["race_forecast_loads"]}
    assert set(forecasts) == {"A", "B"}  # C stays train-through, no forecast
    assert forecasts["A"]["date"] == "2026-10-10"
    assert forecasts["B"]["date"] == "2026-10-03"
    assert forecasts["A"]["tss"] > forecasts["B"]["tss"] > 0
    assert forecasts["A"]["tss"] <= 300 and forecasts["B"]["tss"] <= 200
    assert forecasts["A"]["basis"]

    # the race day itself remains a protected zero-load day in the plan chain
    by_date = {dt.date().isoformat(): total for dt, total, _parts in adjusted}
    assert by_date["2026-10-10"] == 0.0
    assert by_date["2026-10-03"] == 0.0
    assert {"2026-10-03", "2026-10-10"} <= set(metadata["protected_dates"])

    # weekly accounting: the race week row carries the forecast explicitly,
    # without polluting the discipline buckets
    week_b, week_a = after_summaries[1], after_summaries[2]
    assert float(week_b.get("race_forecast_tss") or 0.0) == forecasts["B"]["tss"]
    assert float(week_a.get("race_forecast_tss") or 0.0) == forecasts["A"]["tss"]


def _built_plan(db):
    from api import planning_service as ps

    today = datetime.now().date()
    return ps.build_plan(
        db,
        goal_type="triathlon",
        distance="olympic",
        event_date=None,
        events=[
            {"date": (today + timedelta(days=13)).isoformat(), "priority": "B",
             "label": "B", "confirmed": True},
            {"date": (today + timedelta(weeks=12)).isoformat(), "priority": "A",
             "label": "A", "confirmed": True},
        ],
        planning_mode="event_goal",
        available_hours=10,
        available_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        persist=True,
    )


def test_forecast_load_reaches_ctl_atl_and_persists(tmp_path, monkeypatch):
    from api import planning_service as ps

    with_load = _built_plan(Database(str(tmp_path / "with.db")))
    with monkeypatch.context() as patched:
        import models.training_planner as tp

        patched.setattr(tp, "RACE_FORECAST_TSS_POLICY", {"A": 0.0, "B": 0.0}, raising=True)
        without_load = _built_plan(Database(str(tmp_path / "without.db")))

    # racing costs freshness: the simulated final TSB must be lower when the
    # A-race effort is anticipated than when races are modelled as zero days
    assert with_load["forecast"]["final_tsb"] < without_load["forecast"]["final_tsb"]

    # the forecast truth is persisted and survives the checkpoint round-trip
    db = Database(str(tmp_path / "roundtrip.db"))
    _built_plan(db)
    active = ps.get_active_plan(db)
    loads = list(active.get("race_forecast_loads") or [])
    assert {row["priority"] for row in loads} == {"A", "B"}
    assert all(float(row["tss"]) > 0 for row in loads)


def test_weekly_race_forecast_survives_checkpoint_and_weeks_payload(tmp_path):
    """M6 blocker 2: `race_forecast_tss` must survive the checkpoint weekly-row
    serialization and appear in the API `weeks` payload — WITHOUT inflating
    `weekly_tss` or the discipline buckets (the three-way anchor stays clean)."""
    from api import planning_service as ps

    db = Database(str(tmp_path / "weekly-field.db"))
    result = _built_plan(db)

    api_race_weeks = [
        w for w in result["weeks"] if float(w.get("race_forecast_tss") or 0.0) > 0
    ]
    assert api_race_weeks, "API weeks payload must carry race_forecast_tss"
    for week in api_race_weeks:
        buckets = float(week["bike"]) + float(week["run"]) + float(week["swim"])
        # the forecast is an explicit separate field: weekly_tss still equals
        # the discipline buckets (rounding tolerance), not buckets + race
        assert abs(float(week["weekly_tss"]) - buckets) <= 3.0, week

    active = ps.get_active_plan(db)
    restored_race_weeks = [
        row
        for row in active["weekly_summary"]
        if float(row.get("race_forecast_tss") or 0.0) > 0
    ]
    assert restored_race_weeks, "checkpoint round-trip must keep race_forecast_tss"
    total_restored = round(
        sum(float(r["race_forecast_tss"]) for r in restored_race_weeks), 1
    )
    total_loads = round(
        sum(float(r["tss"]) for r in active.get("race_forecast_loads") or []), 1
    )
    assert total_restored == pytest.approx(total_loads, abs=0.11)


def test_forecast_after_execution_adjustment_still_anticipates_races(tmp_path, monkeypatch):
    """M6 blocker 1: the apply_adjustment forecast must keep anticipating the
    races. RED while the adjustment-path `_forecast` ignores
    race_forecast_loads (both variants come out equal)."""
    from api import planning_service as ps
    from models.planning_execution import build_execution_reconciliation_rows

    def _adjusted_final_tsb(db_path, zero_policy: bool) -> float:
        db = Database(str(db_path))
        _built_plan(db)
        goal_plan = ps.get_active_plan(db)
        rows = build_execution_reconciliation_rows(goal_plan, weeks=1)
        for row in rows:
            if int(row.get("planned_total_tss", 0) or 0) > 0:
                row["outcome"] = "missed"
                break
        if zero_policy:
            import models.training_planner as tp

            with monkeypatch.context() as patched:
                patched.setattr(
                    tp, "RACE_FORECAST_TSS_POLICY", {"A": 0.0, "B": 0.0}, raising=True
                )
                result = ps.apply_adjustment(db, rows=rows, weeks=1, persist=False)
        else:
            result = ps.apply_adjustment(db, rows=rows, weeks=1, persist=False)
        return float(result["forecast"]["final_tsb"])

    with_races = _adjusted_final_tsb(tmp_path / "adj-with.db", zero_policy=False)
    without_races = _adjusted_final_tsb(tmp_path / "adj-without.db", zero_policy=True)
    assert with_races < without_races


def test_race_day_is_never_materialized_or_delivered(tmp_path):
    from api import planning_service as ps
    from models.intervals_workout_delivery import build_delivery_events

    db = Database(str(tmp_path / "race-day.db"))
    _built_plan(db)
    active = ps.get_active_plan(db)

    race_dates = [str(row["date"]) for row in active.get("race_forecast_loads") or []]
    assert race_dates
    templates_by_date = {t["date"]: t for t in active["session_templates"]}
    for race_date in race_dates:
        template = templates_by_date[race_date]
        assert (template.get("sessions") or []) == [], race_date
        events = build_delivery_events(active, [race_date])
        assert events == [], (race_date, events)