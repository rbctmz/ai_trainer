"""BDD/TDD contract for issue #172 plan-vs-actual reconciliation."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest

from data.database import Database
from models.plan_actual_reconciliation import (
    MATCH_RULE_VERSION,
    REBALANCE_RULE_VERSION,
    apply_weekly_rebalance_preview,
    build_reconciliation,
    build_weekly_rebalance_preview,
)
from models.session_identity import SESSION_ID_RULE_VERSION, ensure_session_identities


START = date(2026, 7, 6)


def _goal_plan(days: int = 21) -> dict:
    roles = [
        "recovery",
        "easy",
        "easy",
        "easy",
        "quality",
        "long",
        "recovery",
    ]
    sports = ["bike", "bike", "bike", "run", "swim", "bike", "bike"]
    daily_plan = []
    templates = []
    weekly_summary = []
    for index in range(days):
        current = START + timedelta(days=index)
        role = roles[index % 7]
        sport = sports[index % 7]
        tss = float([10, 20, 22, 25, 45, 60, 10][index % 7])
        parts = {"bike": 0.0, "run": 0.0, "swim": 0.0}
        parts[sport] = tss
        daily_plan.append((datetime.combine(current, datetime.min.time()), tss, parts))
        templates.append(
            {
                "date": current.isoformat(),
                "week_index": index // 7,
                "day_index": index % 7,
                "phase": "Build",
                "session_role": role,
                "session_focus": f"focus-{index}",
                "sport": sport,
                "sport_label": sport,
                "duration_minutes": int(tss * 2),
                "template_key": f"build:{role}:{sport}",
                "export_name": f"Session {index}",
                "description": f"Session {index} · {tss} TSS",
            }
        )
    for week_index in range((days + 6) // 7):
        week_days = daily_plan[week_index * 7 : week_index * 7 + 7]
        week_templates = templates[week_index * 7 : week_index * 7 + 7]
        weekly_summary.append(
            {
                "week_start": START + timedelta(days=week_index * 7),
                "phase": "Build",
                "weekly_tss": int(round(sum(item[1] for item in week_days))),
                "bike": round(sum(item[2]["bike"] for item in week_days), 1),
                "run": round(sum(item[2]["run"] for item in week_days), 1),
                "swim": round(sum(item[2]["swim"] for item in week_days), 1),
                "day_roles": [item["session_role"] for item in week_templates],
                "day_focuses": [item["session_focus"] for item in week_templates],
                "adjustment_note": "—",
            }
        )
    return {
        "goal_type": "triathlon",
        "distance": "olympic",
        "start_week": START,
        "daily_plan": daily_plan,
        "session_templates": templates,
        "weekly_summary": weekly_summary,
        "weekly_tss_plan": [row["weekly_tss"] for row in weekly_summary],
        "protected_dates": [],
        "constraint_summary": {},
        "near_term_edit_version": 0,
    }


def _activity(
    activity_id: str,
    day: str,
    sport: str,
    tss: float,
    duration: float = 60.0,
) -> dict:
    return {
        "activity_id": activity_id,
        "date": day,
        "started_at_utc": f"{day}T06:00:00Z",
        "sport": sport,
        "tss": tss,
        "duration_minutes": duration,
        "activity_name": activity_id,
    }


def _session_by_date(plan: dict, day: str) -> dict:
    return next(item for item in plan["session_templates"] if item.get("date") == day)


def test_session_identity_is_deterministic_and_replacement_safe() -> None:
    source = _goal_plan()

    preview = ensure_session_identities(source)
    confirmation = ensure_session_identities(source)

    assert preview["session_identity_rule_version"] == SESSION_ID_RULE_VERSION
    assert [row.get("session_id") for row in preview["session_templates"]] == [
        row.get("session_id") for row in confirmation["session_templates"]
    ]
    assert all(str(row["session_id"]).startswith("ats_") for row in preview["session_templates"])

    changed = deepcopy(preview)
    changed["daily_plan"][9] = (
        changed["daily_plan"][9][0],
        changed["daily_plan"][9][1] + 15.0,
        {**changed["daily_plan"][9][2], "run": changed["daily_plan"][9][1] + 15.0},
    )
    changed["session_templates"][9]["duration_minutes"] += 20
    replaced = ensure_session_identities(changed, previous_goal_plan=preview)

    assert replaced["session_templates"][8]["session_id"] == preview["session_templates"][8]["session_id"]
    assert replaced["session_templates"][9]["session_id"] != preview["session_templates"][9]["session_id"]
    assert replaced["session_templates"][9]["replaces_session_id"] == preview["session_templates"][9]["session_id"]

    embedded_edit = deepcopy(preview)
    embedded_edit["daily_plan"][10] = (
        embedded_edit["daily_plan"][10][0],
        embedded_edit["daily_plan"][10][1] - 10.0,
        {**embedded_edit["daily_plan"][10][2], "swim": embedded_edit["daily_plan"][10][1] - 10.0},
    )
    embedded_replacement = ensure_session_identities(embedded_edit)
    assert embedded_replacement["session_templates"][10]["session_id"] != preview["session_templates"][10]["session_id"]
    assert embedded_replacement["session_templates"][10]["replaces_session_id"] == preview["session_templates"][10]["session_id"]

    unchanged_after_replacement = ensure_session_identities(
        deepcopy(embedded_replacement),
        previous_goal_plan=embedded_replacement,
    )
    assert unchanged_after_replacement["session_templates"][10]["replaces_session_id"] == preview["session_templates"][10]["session_id"]


def test_reconciliation_uses_relative_lookback_and_preserves_full_actual_load() -> None:
    plan = ensure_session_identities(_goal_plan())
    activities = [
        _activity("ride-a", "2026-07-08", "cycling", 30.1, 50),
        _activity("ride-b", "2026-07-08", "bike", 34.1, 55),
        _activity("bike-on-run-day", "2026-07-09", "cycling", 31.0, 45),
        _activity("paired-ride", "2026-07-12", "cycling", 30.2, 60),
        _activity("swim-a", "2026-07-12", "open_water_swimming", 10.0, 25),
        _activity("swim-b", "2026-07-12", "swimming", 9.3, 20),
    ]

    result = build_reconciliation(
        plan,
        activities,
        as_of=date(2026, 7, 13),
        weeks=1,
        base_checkpoint_id=63,
    )

    assert result["rule_version"] == MATCH_RULE_VERSION
    assert result["window"] == {"start": "2026-07-07", "end": "2026-07-13", "weeks": 1}
    assert result["base_checkpoint_id"] == 63
    assert {row["date"] for row in result["rows"]} == {
        "2026-07-07",
        "2026-07-08",
        "2026-07-09",
        "2026-07-10",
        "2026-07-11",
        "2026-07-12",
        "2026-07-13",
    }

    july_8 = next(row for row in result["rows"] if row["date"] == "2026-07-08")
    assert july_8["match_status"] == "matched"
    assert july_8["match_method"] == "date_sport_heuristic"
    assert july_8["actual_total_tss"] == pytest.approx(64.2)
    assert july_8["actual_activity_ids"] == ["ride-a", "ride-b"]
    assert july_8["adherence"] == "major_deviation"

    july_9 = next(row for row in result["rows"] if row["date"] == "2026-07-09")
    assert july_9["match_status"] == "ambiguous"
    assert july_9["adherence"] == "unknown"
    assert july_9["actual_total_tss"] == 0
    assert [item["activity_id"] for item in july_9["candidate_activities"]] == ["bike-on-run-day"]

    july_12 = next(row for row in result["rows"] if row["date"] == "2026-07-12")
    assert july_12["actual_total_tss"] == pytest.approx(30.2)
    assert set(july_12["actual_activity_ids"]) == {"paired-ride"}
    assert {item["activity_id"] for item in result["unplanned_activities"]} >= {"swim-a", "swim-b"}
    assert result["metrics"]["total_actual_tss"] == pytest.approx(144.7)
    assert result["metrics"]["unplanned_tss"] == pytest.approx(50.3)


def test_ai_trainer_external_id_wins_while_foreign_provider_pair_is_only_evidence() -> None:
    plan = ensure_session_identities(_goal_plan())
    target = _session_by_date(plan, "2026-07-08")
    activities = [_activity("garmin-1", "2026-07-08", "cycling", 20.0)]
    provider_activities = [
        {
            "id": "icu-a1",
            "external_id": "garmin-1",
            "paired_event_id": "icu-e1",
            "start_date_local": "2026-07-08T09:00:00",
            "type": "Ride",
        }
    ]
    provider_events = [
        {
            "id": "icu-e1",
            "external_id": f"ai_trainer:{target['session_id']}",
            "category": "WORKOUT",
            "start_date_local": "2026-07-08T07:00:00",
            "type": "Ride",
        }
    ]

    stable = build_reconciliation(
        plan,
        activities,
        as_of=date(2026, 7, 13),
        weeks=1,
        base_checkpoint_id=63,
        provider_activities=provider_activities,
        provider_events=provider_events,
    )
    stable_row = next(row for row in stable["rows"] if row["date"] == "2026-07-08")
    assert stable_row["match_method"] == "ai_trainer_external_id"
    assert stable_row["confidence"] == 1.0

    provider_events[0]["external_id"] = None
    foreign = build_reconciliation(
        plan,
        activities,
        as_of=date(2026, 7, 13),
        weeks=1,
        base_checkpoint_id=63,
        provider_activities=provider_activities,
        provider_events=provider_events,
    )
    foreign_row = next(row for row in foreign["rows"] if row["date"] == "2026-07-08")
    assert foreign_row["match_method"] == "date_sport_heuristic"
    assert any("provider paired event" in evidence.lower() for evidence in foreign_row["evidence"])


def test_ai_trainer_brick_leg_external_ids_are_exact_parent_evidence() -> None:
    plan = ensure_session_identities(_goal_plan())
    target = _session_by_date(plan, "2026-07-08")
    target["kind"] = "composite"
    target["legs"] = [{"sport": "bike"}, {"sport": "run"}]
    activities = [
        _activity("bike-leg", "2026-07-08", "bike", 45.0),
        _activity("run-leg", "2026-07-08", "run", 20.0),
    ]
    provider_activities = [
        {"external_id": "bike-leg", "paired_event_id": "event-bike"},
        {"external_id": "run-leg", "paired_event_id": "event-run"},
    ]
    provider_events = [
        {
            "id": "event-bike",
            "external_id": f"ai_trainer:{target['session_id']}:leg:1",
        },
        {
            "id": "event-run",
            "external_id": f"ai_trainer:{target['session_id']}:leg:2",
        },
    ]

    result = build_reconciliation(
        plan,
        activities,
        as_of=date(2026, 7, 13),
        weeks=1,
        base_checkpoint_id=63,
        provider_activities=provider_activities,
        provider_events=provider_events,
    )

    row = next(item for item in result["rows"] if item["date"] == "2026-07-08")
    assert row["match_method"] == "ai_trainer_external_id"
    assert set(row["actual_activity_ids"]) == {"bike-leg", "run-leg"}


def test_user_match_reserves_activity_before_automatic_heuristics() -> None:
    raw = _goal_plan()
    raw["daily_plan"].append(deepcopy(raw["daily_plan"][2]))
    duplicate = deepcopy(raw["session_templates"][2])
    duplicate["session_focus"] = "explicit second session"
    duplicate["export_name"] = "Explicit second session"
    raw["session_templates"].append(duplicate)
    plan = ensure_session_identities(raw)
    first = plan["session_templates"][2]
    second = plan["session_templates"][-1]
    activity = _activity("reserved-ride", "2026-07-08", "bike", 34.0)
    ledger = [
        {
            "target_key": f"session:{second['session_id']}",
            "session_id": second["session_id"],
            "match_status": "matched",
            "match_method": "user_confirmed",
            "confidence": 1.0,
            "actual_activity_ids": ["reserved-ride"],
            "actual_snapshot": {"role": "easy"},
            "evidence": ["User selected the second session"],
        }
    ]

    result = build_reconciliation(
        plan,
        [activity],
        as_of=date(2026, 7, 13),
        weeks=1,
        base_checkpoint_id=63,
        ledger_rows=ledger,
    )

    first_row = next(row for row in result["rows"] if row["session_id"] == first["session_id"])
    second_row = next(row for row in result["rows"] if row["session_id"] == second["session_id"])
    assert first_row["match_status"] == "unmatched"
    assert second_row["match_method"] == "user_confirmed"
    assert second_row["actual_activity_ids"] == ["reserved-ride"]
    assert result["metrics"]["total_actual_tss"] == 34.0


def test_match_ledger_is_idempotent_and_corrections_append_revisions(tmp_path) -> None:
    db = Database(str(tmp_path / "ledger.db"))
    payload = {
        "fingerprint": "match-fingerprint-1",
        "target_key": "session:ats_123",
        "session_id": "ats_123",
        "base_checkpoint_id": 63,
        "session_date": "2026-07-08",
        "match_status": "matched",
        "match_method": "user_confirmed",
        "confidence": 1.0,
        "planned_snapshot": {"tss": 21.5, "sport": "bike", "role": "easy"},
        "actual_activity_ids": ["ride-a", "ride-b"],
        "actual_snapshot": {"tss": 64.2, "sport": "bike", "role": "easy"},
        "evidence": ["user selected both rides"],
        "rule_version": MATCH_RULE_VERSION,
    }

    first = db.save_plan_actual_match(payload)
    retry = db.save_plan_actual_match(payload)
    correction = db.save_plan_actual_match(
        {
            **payload,
            "fingerprint": "match-fingerprint-2",
            "actual_activity_ids": ["ride-a"],
            "actual_snapshot": {"tss": 30.1, "sport": "bike", "role": "easy"},
            "supersedes_match_id": first["id"],
        }
    )

    assert retry["id"] == first["id"]
    assert first["revision"] == 1
    assert correction["revision"] == 2
    latest = db.get_latest_plan_actual_matches(start_date="2026-07-07", end_date="2026-07-13")
    assert len(latest) == 1
    assert latest[0]["id"] == correction["id"]
    assert latest[0]["supersedes_match_id"] == first["id"]


def _eligible_reconciliation(*, actual_tss: float, ambiguous: int = 0) -> dict:
    return {
        "rule_version": MATCH_RULE_VERSION,
        "base_checkpoint_id": 63,
        "data_quality": {
            "planned_session_count": 5,
            "matched_count": 4,
            "ambiguous_count": ambiguous,
            "coverage": 0.8,
            "status": "sufficient" if not ambiguous else "data_gap",
            "reasons": [] if not ambiguous else ["ambiguous_matches"],
        },
        "metrics": {
            "planned_tss": 100.0,
            "matched_actual_tss": actual_tss,
            "unplanned_tss": 0.0,
            "total_actual_tss": actual_tss,
        },
        "rows": [],
        "unplanned_activities": [],
    }


def test_weekly_rebalance_changes_only_allowed_future_easy_sessions() -> None:
    plan = ensure_session_identities(_goal_plan())
    plan["protected_dates"] = ["2026-07-16"]
    plan["constraint_summary"] = {
        "near_term_edit": {
            "is_active": True,
            "edited_dates": ["2026-07-17"],
            "edited_day_count": 1,
            "horizon_days": 1,
        }
    }
    before = deepcopy(plan)

    preview = build_weekly_rebalance_preview(
        plan,
        _eligible_reconciliation(actual_tss=180.0),
        as_of=date(2026, 7, 13),
        protected_dates={"2026-07-16", "2026-07-17"},
    )

    assert preview["rule_version"] == REBALANCE_RULE_VERSION
    assert preview["status"] == "proposal"
    assert preview["reason"] == "over_plan_future_reduction"
    assert preview["reduction_budget_tss"] <= 40
    assert preview["reduction_budget_tss"] <= int(preview["future_window_tss"] * 0.15 // 5) * 5
    assert preview["future_tss_delta"] < 0
    assert preview["changes"]
    assert all(item["date"] > "2026-07-13" for item in preview["changes"])
    assert all(item["session_role"] == "easy" for item in preview["changes"])
    assert {item["date"] for item in preview["changes"]}.isdisjoint({"2026-07-16", "2026-07-17"})

    updated = apply_weekly_rebalance_preview(plan, preview)
    for index, (day, _total, _parts) in enumerate(before["daily_plan"]):
        day_text = day.date().isoformat()
        if day_text <= "2026-07-13" or day_text in {"2026-07-16", "2026-07-17"}:
            assert updated["daily_plan"][index] == before["daily_plan"][index]
            assert updated["session_templates"][index] == before["session_templates"][index]

    changed_dates = {item["date"] for item in preview["changes"]}
    for day_text in changed_dates:
        old = _session_by_date(before, day_text)
        new = _session_by_date(updated, day_text)
        assert new["session_id"] != old["session_id"]
        assert new["replaces_session_id"] == old["session_id"]
        assert f"Total TSS: {next(item['after_tss'] for item in preview['changes'] if item['date'] == day_text)}" in new["description"]


def test_weekly_rebalance_rounding_never_exceeds_per_session_capacity() -> None:
    plan = ensure_session_identities(_goal_plan())
    for index, total in zip((8, 9, 10), (34.1, 35.4, 36.7)):
        dt, _old_total, parts = plan["daily_plan"][index]
        sport = plan["session_templates"][index]["sport"]
        plan["daily_plan"][index] = (
            dt,
            total,
            {key: total if key == sport else 0.0 for key in parts},
        )
    plan = ensure_session_identities(plan)

    preview = build_weekly_rebalance_preview(
        plan,
        _eligible_reconciliation(actual_tss=200.0),
        as_of=date(2026, 7, 13),
    )

    assert preview["status"] == "proposal"
    for change in preview["changes"]:
        reduction = -float(change["delta_tss"])
        exact_capacity = min(float(change["before_tss"]) * 0.25, float(change["before_tss"]) - 5.0)
        assert reduction <= exact_capacity + 1e-9
        assert float(change["after_tss"]) >= 5.0
    assert -float(preview["future_tss_delta"]) <= float(preview["reduction_budget_tss"])


@pytest.mark.parametrize(
    ("reconciliation", "expected_reason"),
    [
        (_eligible_reconciliation(actual_tss=90.0), "no_change_under_plan"),
        (_eligible_reconciliation(actual_tss=108.0), "no_change_below_threshold"),
        (_eligible_reconciliation(actual_tss=180.0, ambiguous=1), "data_gap"),
    ],
)
def test_weekly_rebalance_never_catches_up_and_blocks_weak_evidence(
    reconciliation: dict,
    expected_reason: str,
) -> None:
    preview = build_weekly_rebalance_preview(
        ensure_session_identities(_goal_plan()),
        reconciliation,
        as_of=date(2026, 7, 13),
    )

    assert preview["status"] == "no_change"
    assert preview["reason"] == expected_reason
    assert preview["changes"] == []
    assert preview["future_tss_delta"] == 0
