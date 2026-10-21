"""M4b evidence matrix: synthetic rows, frozen dates, no medical dose oracle."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pandas as pd
import pytest

from api.planning_entry_contract import EntryExposureProfile, EntryLoadAssessment
from models.activity_lineage import authoritative_training_load_activities
from models.planning_entry_load import build_entry_exposure_profile, derive_entry_limits, normalize_entry_inputs

AS_OF = date(2026, 10, 21)
COVERAGE = {"status": "user_reported_complete", "start_date": "2026-09-23", "end_date_exclusive": "2026-10-21"}
SCOPE = {"start_date": "2026-10-28", "end_date": "2026-11-10"}


def row(identity, ago=2, sport="running", minutes=40, tss=30, parent=None, method="hr_tss_run"):
    return {"activity_id": identity, "date": (AS_OF - timedelta(days=ago)).isoformat(),
            "sport": sport, "duration_minutes": minutes, "tss": tss,
            "provider_external_id": parent, "tss_method": method}


def profile(rows, coverage=COVERAGE, zone="Europe/Moscow"):
    return build_entry_exposure_profile(rows, as_of=AS_OF, timezone=zone, coverage=coverage)


def steady(sport="run", minutes=40):
    return [row(f"{sport}-{ago}", ago=ago, sport=sport, minutes=minutes) for ago in (2, 9, 16, 23)]


def limits(p, declared=None, sports=("run",)):
    return derive_entry_limits(p, declared, cycle_scope=SCOPE, target_sports=sports)


def declared(minutes=60):
    return {"source": "athlete_declared", "weekly_minutes": minutes,
            "weekly_sessions": 2, "max_session_minutes": minutes / 2}


def test_changed_sport_at_equal_aggregate_load_changes_only_its_physical_profile():
    running = profile(steady())
    mixed_rows = steady()
    for item, sport in zip(mixed_rows, ("run", "bike", "swim", "bike"), strict=True):
        item["sport"] = sport
    mixed = profile(mixed_rows)
    assert {s: e["session_count"] for s, e in running["sports"].items()} == {"bike": 0, "run": 4, "swim": 0}
    assert {s: e["session_count"] for s, e in mixed["sports"].items()} == {"bike": 2, "run": 1, "swim": 1}
    assert limits(running)["limits"]["run"]["weekly_minutes"] == 40
    assert limits(mixed)["status"] == "needs_baseline"


@pytest.mark.parametrize("coverage,expected", [(None, None), ({"status": "unknown"}, None),
    ({**COVERAGE, "status": "partial"}, None), (COVERAGE, 0)])
def test_empty_covered_zero_is_not_unknown_history(coverage, expected):
    result = profile([], coverage)
    assert result["sports"]["bike"]["total_minutes"] == expected
    assert result["sports"]["bike"]["session_count"] == 0
    assert limits(result, sports=("bike",))["status"] == "needs_baseline"
    assert all(b["total_minutes"] == expected for b in result["sports"]["bike"]["bins"])


@pytest.mark.parametrize("duration", [None, 0, -1, float("nan"), float("inf"), -float("inf"), True, "40", 10**400])
def test_invalid_duration_keeps_observed_session_but_cannot_authorize_dose(duration):
    items = steady()
    items[0]["duration_minutes"] = duration
    result = profile(items)
    run = result["sports"]["run"]
    assert run["session_count"] == 4
    assert run["eligible_duration_session_count"] == 3
    assert run["observed_minutes"] == 120
    assert run["total_minutes"] is None
    assert limits(result)["status"] == "needs_baseline"
    assert "duration_missing_or_invalid" in {q["code"] for q in result["quality_limits"]}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("tss", [None, 0, float("nan"), float("inf"), -1])
def test_duration_evidence_does_not_depend_on_tss_availability(tss):
    result = profile([dict(r, tss=tss) for r in steady()])
    assert result["sports"]["run"]["observed_minutes"] == 160
    assert limits(result)["limits"]["run"]["weekly_minutes"] == 40
    assert result["sports"]["run"]["tss"]["total"] == (0 if tss == 0 else None)


def test_four_bins_include_covered_zeros_and_do_not_use_active_week_average():
    result = profile([row("one", ago=2, minutes=120), row("older", ago=9, minutes=120)])
    assert [b["observed_minutes"] for b in result["sports"]["run"]["bins"]] == [0, 0, 120, 120]
    # Median session count is floor(0.5), not an invented positive frequency.
    assert limits(result)["status"] == "needs_baseline"


def test_old_context_and_gap_do_not_raise_recent_reference():
    result = profile([row("old", ago=35, minutes=300)])
    run = result["sports"]["run"]
    assert run["session_count"] == 0 and run["context"]["session_count"] == 1
    assert run["days_since_last"] == 35 and run["context"]["observed_minutes"] == 300
    assert limits(result)["status"] == "needs_baseline"
    gap = profile([row(f"gap-{ago}", ago=ago) for ago in (9, 16, 23, 28)])
    assert limits(gap)["status"] == "needs_baseline"


@pytest.mark.parametrize("ago,expected", [(0, 0), (-1, 0), (28, 1), (29, 0), (84, 0), (85, 0)])
def test_reference_date_boundaries_are_half_open(ago, expected):
    result = profile([row("boundary", ago=ago)])
    assert result["sports"]["run"]["session_count"] == expected
    assert result["sports"]["run"]["context"]["session_count"] == int(1 <= ago <= 84)


def test_timezone_applies_to_timestamp_before_completed_day_cutoff():
    item = row("clock")
    item["date"] = "2026-10-20T22:30:00Z"
    assert profile([item], zone="Europe/Moscow")["sports"]["run"]["session_count"] == 0
    assert profile([item], zone="Europe/London")["sports"]["run"]["session_count"] == 1


def test_invalid_date_and_unknown_sport_are_explicit_quality_gaps():
    result = profile([*steady(), dict(row("bad-date"), date="bad"), row("bad-sport", sport="mystery")])
    assert limits(result)["status"] == "needs_baseline"
    assert {q["code"] for q in result["quality_limits"]} >= {"activity_date_invalid", "activity_sport_unknown"}


@pytest.mark.parametrize("sport,key", [("cycling", "bike"), ("virtual_ride", "bike"),
    ("Плавание", "swim"), ("open_water_swimming", "swim"), ("trail_running", "run"), ("бег", "run")])
def test_existing_sport_aliases_are_reused(sport, key):
    assert profile([row("alias", sport=sport)])["sports"][key]["session_count"] == 1


def test_identical_duplicate_is_counted_once_conflict_never_uses_row_order():
    items = steady()
    assert profile(items + [deepcopy(items[0])]) == profile(items)
    conflicting = items + [dict(items[0], duration_minutes=400)]
    result = profile(conflicting)
    assert result == profile(list(reversed(conflicting)))
    assert result["sports"]["run"]["session_count"] == 3
    assert limits(result)["status"] == "needs_baseline"


def multisport(tss=0):
    return [row("envelope", sport="multi_sport", minutes=150, tss=100),
            row("swim-leg", sport="swim", minutes=20, tss=tss, parent="envelope"),
            row("bike-leg", sport="bike", minutes=80, tss=tss, parent="envelope"),
            row("run-leg", sport="run", minutes=40, tss=tss, parent="envelope")]


@pytest.mark.parametrize("tss", [0, None, 30])
def test_complete_multisport_counts_physical_legs_even_with_zero_tss(tss):
    items = multisport(tss)
    before = deepcopy(items)
    result = profile(items)
    assert {s: e["observed_minutes"] for s, e in result["sports"].items()} == {"bike": 80, "run": 40, "swim": 20}
    assert all(e["reference_complete"] for e in result["sports"].values())
    assert "multisport_remainder_unknown" not in {q["code"] for q in result["quality_limits"]}
    assert items == before
    # Existing global-load authority still uses envelope for zero/missing TSS.
    authoritative = authoritative_training_load_activities(pd.DataFrame(items))
    assert set(authoritative.activity_id) == ({"envelope"} if tss in (0, None) else {"swim-leg", "bike-leg", "run-leg"})


def test_partial_multisport_keeps_known_stage_but_unknown_remainder():
    result = profile(multisport()[:2])
    assert result["sports"]["swim"]["observed_minutes"] == 20
    assert result["sports"]["bike"]["observed_minutes"] == 0
    assert all(not e["reference_complete"] for e in result["sports"].values())
    assert "multisport_remainder_unknown" in {q["code"] for q in result["quality_limits"]}
    assert limits(result, sports=("bike", "run", "swim"))["status"] == "needs_baseline"


def test_same_day_proximity_does_not_link_independent_activities():
    items = multisport()
    items[1]["provider_external_id"] = None
    result = profile(items)
    assert "multisport_remainder_unknown" in {q["code"] for q in result["quality_limits"]}
    assert result["sports"]["swim"]["session_count"] == 1


def test_reference_limits_declarations_and_final_validation_are_distinct():
    before = steady()
    p = profile(before)
    assert p == profile(list(reversed(before)))
    assessment = limits(p)
    EntryExposureProfile.model_validate(p)
    EntryLoadAssessment.model_validate(assessment)
    assert assessment["limits"]["run"]["source"] == "observed_reference"
    assert assessment["limits"]["run"]["weekly_minutes"] == 40
    assert assessment["limits"]["run"]["weekly_sessions"] == 1
    assert assessment["limits"]["run"]["max_session_minutes"] == 40
    assert assessment["scope"] == SCOPE  # Wednesday anchor, not rounded Monday.
    assert assessment["status"] == "unassessed" and assessment["can_publish"] is False
    assert assessment["warnings"][0]["code"] == "final_prescription_unassessed"
    supplied = limits(profile([], None), {"run": declared()}, sports=("run",))
    assert supplied["limits"]["run"]["source"] == "athlete_declared"
    assert supplied["profile"]["completeness"]["status"] == "unknown"
    assert supplied["limits"]["run"]["source_window"] is None
    assert supplied["can_publish"] is False
    # A supplied lower ceiling binds; a higher ceiling does not inflate history.
    for minutes in (20, 400):
        value = limits(p, {"run": declared(minutes)})["limits"]["run"]
        assert value["weekly_minutes"] == min(40, minutes)
        assert value["declared_ceiling"] == declared(minutes)


@pytest.mark.parametrize("field,value", [("weekly_minutes", 0), ("weekly_minutes", float("inf")),
    ("max_session_minutes", 1000), ("weekly_sessions", 1.5), ("weekly_sessions", True),
    ("weekly_minutes", "60"), ("source", "observed_reference")])
def test_declared_limit_validation_is_shared_and_never_invents_values(field, value):
    raw = dict(declared(), **{field: value})
    with pytest.raises(ValueError):
        normalize_entry_inputs(None, {"run": raw})


@pytest.mark.parametrize("coverage", [{"status": "complete"}, {"status": "partial"},
    {**COVERAGE, "start_date": "2026-10-20"}, {**COVERAGE, "end_date_exclusive": "2026-10-20"},
    {**COVERAGE, "start_date": "2026-10-22"}])
def test_invalid_or_short_complete_claim_cannot_authorize_reference(coverage):
    with pytest.raises(ValueError):
        profile(steady(), coverage)


def test_python_profile_and_limits_match_extracted_typescript_contract():
    from pathlib import Path
    from tests.contracts.conformance import validate
    artifact = json.loads((Path(__file__).resolve().parents[1] / "contracts" / "ts_contract.json").read_text())
    assessment = limits(profile(steady()))
    assert validate(assessment, artifact["types"]["EntryLoadAssessment"], artifact["types"]) == []
    assert validate(profile([], None), artifact["types"]["EntryExposureProfile"], artifact["types"]) == []
    assert validate(limits(profile([], None), {"run": declared()}),
                    artifact["types"]["EntryLoadAssessment"], artifact["types"]) == []


@pytest.mark.parametrize("sport", ["multisport", "multi-sport", "multi sport"])
def test_standalone_multisport_is_not_a_single_sport_permission(sport):
    result = profile([*steady(), row("envelope-only", sport=sport, minutes=200)])
    assert result["sports"]["run"]["observed_minutes"] == 160
    assert limits(result)["status"] == "needs_baseline"


def test_tss_methods_and_coverage_are_reported_without_inventing_measured_load():
    items = steady()
    items[0]["tss_method"] = "unknown_source"
    items[1]["tss"] = None
    summary = profile(items)["sports"]["run"]["tss"]
    assert summary["provenance"] == "mixed" and summary["coverage"] == "partial"
    assert summary["total"] == 90 and summary["unknown_session_count"] == 1
    assert limits(profile(items))["limits"]["run"]["weekly_minutes"] == 40


def test_feasible_history_and_declared_other_sports_have_resolved_sourced_limits():
    history = [*steady("run"), *steady("bike", 60), *steady("swim", 20)]
    resolved = limits(profile(history), sports=("bike", "run", "swim"))
    assert resolved["blockers"] == []
    assert {s: cap["weekly_minutes"] for s, cap in resolved["limits"].items()} == {"bike": 60, "run": 40, "swim": 20}
    partial = limits(profile(steady("run")), {"bike": declared(120), "swim": declared(60)},
                     sports=("bike", "run", "swim"))
    assert partial["blockers"] == []
    assert {s: cap["source"] for s, cap in partial["limits"].items()} == {
        "bike": "athlete_declared", "run": "observed_reference", "swim": "athlete_declared"}
    assert partial["can_publish"] is False and resolved["can_publish"] is False


def test_zero_tss_multisport_legs_can_supply_observed_reference_over_four_bins():
    history = []
    for ago in (2, 9, 16, 23):
        for item in multisport(0):
            item["date"] = (AS_OF - timedelta(days=ago)).isoformat()
            item["activity_id"] += f"-{ago}"
            if item["provider_external_id"]:
                item["provider_external_id"] += f"-{ago}"
            history.append(item)
    assessment = limits(profile(history), sports=("bike", "run", "swim"))
    assert assessment["blockers"] == []
    assert {s: cap["weekly_minutes"] for s, cap in assessment["limits"].items()} == {"bike": 80, "run": 40, "swim": 20}
    assert all(e["tss"]["total"] == 0 for e in assessment["profile"]["sports"].values())


def test_profile_contains_no_raw_provider_metadata_or_nonfinite_values():
    item = dict(row("public-id"), provider_token="synthetic-hidden", description="private fixture text", tss=float("inf"))
    result = profile([item])
    text = json.dumps(result, allow_nan=False)
    assert "synthetic-hidden" not in text and "private fixture text" not in text
    assert "provider_token" not in text


@pytest.mark.parametrize("ago", [0, -1])
def test_partial_today_or_future_leg_cannot_complete_observed_multisport_group(ago):
    items = [*steady(), *multisport()]
    items[-3]["date"] = (AS_OF - timedelta(days=ago)).isoformat()
    result = profile(items)
    assert "multisport_remainder_unknown" in {q["code"] for q in result["quality_limits"]}
    assert limits(result)["status"] == "needs_baseline"
