"""Smoke: единый сигнал готовности models/readiness.py (issue #139, ExecPlan docs/readiness_today_execplan.md)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from models.readiness import (
    BASELINE_WINDOW_DAYS,
    FACTOR_WEIGHTS,
    INELIGIBLE_REASON_INVALID_OBSERVATION,
    LOAD_METRICS_WINDOW_DAYS,
    OBSERVATION_CONFIRMED_TODAY,
    OBSERVATION_INVALID,
    OBSERVATION_OUTDATED,
    OBSERVATION_UNVERIFIED,
    PRIMARY_RECOVERY_KEYS,
    compute_readiness_today,
)


pytestmark = pytest.mark.smoke

TODAY = date(2026, 7, 9)


def _daily_frame(column: str, values: dict[int, float]) -> pd.DataFrame:
    """Frame with `date` and one value column; keys are day offsets back from TODAY (0 = today)."""
    rows = [
        {"date": pd.Timestamp(TODAY - timedelta(days=offset)), column: value}
        for offset, value in sorted(values.items())
    ]
    return pd.DataFrame(rows)


def _history(column: str, value: float, days: int = 28, start_offset: int = 1) -> dict[int, float]:
    return {offset: value for offset in range(start_offset, start_offset + days)}


def _full_inputs(
    *,
    rmssd_today: float = 37.0,
    rmssd_base: float = 37.0,
    rhr_today: float = 55.0,
    rhr_base: float = 55.0,
    sleep_score: float = 80.0,
    garmin_readiness: float = 80.0,
) -> dict:
    hrv = _daily_frame("rmssd", {0: rmssd_today, **_history("rmssd", rmssd_base)})
    health = _daily_frame("resting_hr", {0: rhr_today, **_history("resting_hr", rhr_base)})
    sleep = _daily_frame("sleep_score", {0: sleep_score})
    training = _daily_frame("training_readiness", {0: garmin_readiness})
    activities = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": 40.0}
            for offset in range(1, 60)
        ]
    )
    return {
        "sleep_df": sleep,
        "hrv_df": hrv,
        "health_df": health,
        "training_df": training,
        "activities_df": activities,
    }


def test_all_good_inputs_give_ready_score_with_full_confidence():
    result = compute_readiness_today(**_full_inputs(), today=TODAY)

    assert result["status"] in {"ready", "strong"}
    assert result["score"] is not None and result["score"] >= 60
    assert result["confidence"] == 1.0
    assert {f["key"] for f in result["factors"]} == {
        "hrv",
        "resting_hr",
        "sleep",
        "training_readiness",
        "tsb",
    }
    assert result["as_of_date"] == TODAY.isoformat()
    assert result["tsb"]["window_days"] == LOAD_METRICS_WINDOW_DAYS


def test_green_garmin_does_not_mask_elevated_rhr_and_suppressed_hrv():
    """Ключевой инвариант issue #139: зелёный Garmin не маскирует недовосстановление."""
    good = compute_readiness_today(**_full_inputs(), today=TODAY)
    strained = compute_readiness_today(
        **_full_inputs(rhr_today=60.0, rmssd_today=31.0),  # RHR +5, HRV ≈ −16%
        today=TODAY,
    )

    assert strained["score"] < good["score"]
    driver_keys = [d["key"] for d in strained["drivers"]]
    assert "resting_hr" in driver_keys
    assert "hrv" in driver_keys
    rhr_driver = next(d for d in strained["drivers"] if d["key"] == "resting_hr")
    assert "55" in rhr_driver["evidence"] and "60" in rhr_driver["evidence"]


def test_baseline_excludes_today():
    """Сегодняшний выброс не должен растить базлайн, с которым сам же сравнивается (#126/#128)."""
    result = compute_readiness_today(
        **_full_inputs(rhr_today=70.0, rhr_base=55.0),
        today=TODAY,
    )

    rhr = next(f for f in result["factors"] if f["key"] == "resting_hr")
    assert rhr["baseline"] == pytest.approx(55.0, abs=0.1)
    assert rhr["deviation"] == pytest.approx(15.0, abs=0.1)
    assert rhr["score"] <= 20


def test_empty_inputs_give_unknown():
    result = compute_readiness_today(None, None, None, None, None, today=TODAY)

    assert result["score"] is None
    assert result["status"] == "unknown"
    assert result["factors"] == []
    assert result["drivers"] == []
    assert result["confidence"] == 0.0


def test_heavy_recent_load_pushes_tsb_factor_down():
    inputs = _full_inputs()
    inputs["activities_df"] = pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": 150.0}
            for offset in range(1, 8)
        ]
    )
    result = compute_readiness_today(**inputs, today=TODAY)

    tsb = next(f for f in result["factors"] if f["key"] == "tsb")
    assert tsb["raw_value"] < -10
    assert tsb["score"] <= 55
    assert "TSB" in tsb["evidence"]


def test_tsb_decays_through_rest_days_until_today():
    inputs = _full_inputs()
    inputs["activities_df"] = pd.DataFrame(
        [{"date": pd.Timestamp(TODAY - timedelta(days=5)), "tss": 180.0}]
    )

    result = compute_readiness_today(**inputs, today=TODAY)

    tsb = next(f for f in result["factors"] if f["key"] == "tsb")
    assert tsb["as_of"] == TODAY.isoformat()
    assert result["tsb"]["as_of"] == TODAY.isoformat()
    # Без нулевых дней отдыха Banister остаётся на дате тренировки:
    # TSB около -19.7. Через 5 дней отдыха он должен заметно восстановиться.
    assert tsb["raw_value"] > -10
    assert tsb["score"] >= 70


def test_missing_garmin_readiness_renormalizes_weights():
    inputs = _full_inputs()
    inputs["training_df"] = None
    result = compute_readiness_today(**inputs, today=TODAY)

    keys = {f["key"] for f in result["factors"]}
    assert "training_readiness" not in keys
    assert result["confidence"] == pytest.approx(0.8)
    assert result["score"] is not None
    assert "training_readiness" in result["missing_inputs"]
    # веса присутствующих факторов в сумме дают 1 после перенормировки
    assert sum(f["weight"] for f in result["factors"]) == pytest.approx(1.0, abs=0.005)


def test_hrv_without_baseline_uses_absolute_bands():
    inputs = _full_inputs()
    inputs["hrv_df"] = _daily_frame("rmssd", {0: 52.0})  # только сегодня, истории нет
    result = compute_readiness_today(**inputs, today=TODAY)

    hrv = next(f for f in result["factors"] if f["key"] == "hrv")
    assert hrv["baseline"] is None
    assert hrv["score"] == 75


def test_stale_input_is_marked_but_used():
    inputs = _full_inputs()
    # HRV только за вчера — используется, но помечен как отставший
    inputs["hrv_df"] = _daily_frame("rmssd", {1: 37.0, **_history("rmssd", 37.0, start_offset=2)})
    result = compute_readiness_today(**inputs, today=TODAY)

    hrv = next(f for f in result["factors"] if f["key"] == "hrv")
    assert hrv["stale_input"] is True
    assert hrv["score"] is not None


def test_baseline_window_is_28_days():
    assert BASELINE_WINDOW_DAYS == 28


# ---------------------------------------------------------------------------
# Issue #557 M1: per-factor observation status and intervention eligibility.
# The provenance columns below are populated by ingest in M3; the model must
# classify a measurement as verified only when the observation date is known.
# ---------------------------------------------------------------------------


def _observations_frame(column: str, rows, observation_column: str) -> pd.DataFrame:
    """Frame with `date`, one value column and one provider observation column.

    `rows` is an iterable of (stored_offset, value, observed_offset | None); all
    offsets are days back from TODAY.
    """
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(TODAY - timedelta(days=stored)),
                column: value,
                observation_column: (
                    None
                    if observed is None
                    else (TODAY - timedelta(days=observed)).isoformat()
                ),
            }
            for stored, value, observed in rows
        ]
    )


def _history_rows(value: float, *, days: int = 28, start_offset: int = 1):
    return [(offset, value, None) for offset in range(start_offset, start_offset + days)]


def _activities() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": pd.Timestamp(TODAY - timedelta(days=offset)), "tss": 40.0}
            for offset in range(1, 60)
        ]
    )


def _factor(result: dict, key: str) -> dict:
    return next(f for f in result["factors"] if f["key"] == key)


def _verified_full_inputs() -> dict:
    """All four measurements confirmed for TODAY, TSB present."""
    return {
        "sleep_df": _daily_frame("sleep_score", {0: 80.0}),
        "hrv_df": _observations_frame(
            "rmssd", [(0, 37.0, 0), *_history_rows(37.0)], "rmssd_observed_at"
        ),
        "health_df": _observations_frame(
            "resting_hr", [(0, 55.0, 0), *_history_rows(55.0)], "resting_hr_observed_at"
        ),
        "training_df": _observations_frame(
            "training_readiness",
            [(0, 80.0, 0)],
            "training_readiness_observed_at",
        ),
        "activities_df": _activities(),
    }


def _mixed_inputs(*, rhr_observed: int | None) -> dict:
    """Yesterday's sleep/HRV, RHR observed today only when requested, TSB today."""
    return {
        "sleep_df": _daily_frame("sleep_score", {1: 80.0}),
        "hrv_df": _observations_frame(
            "rmssd", [(1, 37.0, 1), *_history_rows(37.0, start_offset=2)], "rmssd_observed_at"
        ),
        "health_df": _observations_frame(
            "resting_hr",
            [(0, 55.0, rhr_observed), *_history_rows(55.0)],
            "resting_hr_observed_at",
        ),
        "training_df": _observations_frame(
            "training_readiness",
            [(0, 80.0, None)],
            "training_readiness_observed_at",
        ),
        "activities_df": _activities(),
    }


def test_observation_status_classifies_factors_by_provenance():
    result = compute_readiness_today(**_mixed_inputs(rhr_observed=0), today=TODAY)

    hrv = _factor(result, "hrv")
    assert hrv["observation_status"] == OBSERVATION_OUTDATED
    assert hrv["age_days"] == 1
    assert hrv["intervention_eligible"] is False
    assert hrv["evidence_kind"] == "measurement"

    sleep = _factor(result, "sleep")
    assert sleep["observation_status"] == OBSERVATION_OUTDATED
    assert sleep["intervention_eligible"] is False

    rhr = _factor(result, "resting_hr")
    assert rhr["observation_status"] == OBSERVATION_CONFIRMED_TODAY
    assert rhr["age_days"] == 0
    assert rhr["observation_as_of"] == TODAY.isoformat()
    assert rhr["intervention_eligible"] is True

    training = _factor(result, "training_readiness")
    assert training["observation_status"] == OBSERVATION_UNVERIFIED
    assert training["intervention_eligible"] is False

    tsb = _factor(result, "tsb")
    assert tsb["observation_status"] == OBSERVATION_CONFIRMED_TODAY
    assert tsb["intervention_eligible"] is True
    assert tsb["evidence_kind"] == "derived_state"

    assert result["eligible_inputs"] == ["resting_hr", "tsb"]
    assert {item["key"] for item in result["ineligible_inputs"]} == {
        "hrv",
        "sleep",
        "training_readiness",
    }


def test_intervention_confidence_counts_eligible_factors_only():
    # Confirmed today RHR + current TSB: 2/5 = 0.4 (issue #557 AC3).
    with_rhr = compute_readiness_today(**_mixed_inputs(rhr_observed=0), today=TODAY)
    assert with_rhr["intervention_confidence"] == 0.4
    assert with_rhr["intervention_score"] is not None
    assert with_rhr["intervention_blocked_reason"] is None
    # Legacy presence-based confidence is frozen and still counts every factor.
    assert with_rhr["confidence"] == 1.0

    # RHR without an observation date: only TSB is eligible -> 1/5 = 0.2 and the
    # gate input is blocked because no primary measurement is confirmed today.
    without_rhr = compute_readiness_today(**_mixed_inputs(rhr_observed=None), today=TODAY)
    assert without_rhr["intervention_confidence"] == 0.2
    assert without_rhr["intervention_score"] is None
    assert (
        without_rhr["intervention_blocked_reason"]
        == "no_confirmed_today_primary_recovery_measurement"
    )
    assert without_rhr["confidence"] == 1.0


def test_intervention_score_uses_renormalized_eligible_weights():
    mixed = compute_readiness_today(**_mixed_inputs(rhr_observed=0), today=TODAY)
    eligible = [f for f in mixed["factors"] if f["intervention_eligible"]]
    total_weight = sum(FACTOR_WEIGHTS[f["key"]] for f in eligible)
    expected = round(
        sum(f["score"] * FACTOR_WEIGHTS[f["key"]] / total_weight for f in eligible), 1
    )
    assert mixed["intervention_score"] == pytest.approx(expected)
    # Ineligible factors still shape the descriptive score, so the two differ.
    assert mixed["intervention_score"] != mixed["score"]

    verified = compute_readiness_today(**_verified_full_inputs(), today=TODAY)
    assert verified["intervention_confidence"] == verified["confidence"] == 1.0
    assert verified["intervention_score"] == verified["score"]
    assert verified["intervention_blocked_reason"] is None


def test_intervention_requires_a_primary_recovery_measurement():
    assert PRIMARY_RECOVERY_KEYS == ("sleep", "hrv", "resting_hr")
    result = compute_readiness_today(**_mixed_inputs(rhr_observed=None), today=TODAY)
    eligible_keys = {f["key"] for f in result["factors"] if f["intervention_eligible"]}
    assert eligible_keys == {"tsb"}
    assert not (eligible_keys & set(PRIMARY_RECOVERY_KEYS))
    assert result["intervention_score"] is None


def test_repeated_observation_is_dated_by_its_observation_not_the_query_date():
    """Re-ingesting one observation under today's query date must not make it fresh."""
    duplicated = _observations_frame(
        "rmssd",
        [(0, 37.0, 1), (1, 37.0, 1), *_history_rows(37.0, start_offset=2)],
        "rmssd_observed_at",
    )
    result = compute_readiness_today(
        **{**_verified_full_inputs(), "hrv_df": duplicated}, today=TODAY
    )

    hrv = _factor(result, "hrv")
    # Provenance: the observation is yesterday, so the factor is not eligible.
    assert hrv["observation_as_of"] == (TODAY - timedelta(days=1)).isoformat()
    assert hrv["age_days"] == 1
    assert hrv["observation_status"] == OBSERVATION_OUTDATED
    assert hrv["intervention_eligible"] is False
    # Frozen legacy channel: selection and as_of still follow the stored date.
    assert hrv["as_of"] == TODAY.isoformat()
    assert hrv["stale_input"] is False


def test_future_observation_is_not_intervention_eligible():
    """A measurement dated after the anchor cannot prove today's state (AC2)."""
    inputs = _mixed_inputs(rhr_observed=-1)  # observation dated tomorrow
    result = compute_readiness_today(**inputs, today=TODAY)

    rhr = _factor(result, "resting_hr")
    assert rhr["age_days"] == -1
    assert rhr["observation_status"] == OBSERVATION_INVALID
    assert rhr["intervention_eligible"] is False
    assert result["eligible_inputs"] == ["tsb"]
    assert result["intervention_confidence"] == 0.2
    assert result["intervention_score"] is None
    assert (
        result["intervention_blocked_reason"]
        == "no_confirmed_today_primary_recovery_measurement"
    )
    invalid = next(item for item in result["ineligible_inputs"] if item["key"] == "resting_hr")
    assert invalid["reason"] == INELIGIBLE_REASON_INVALID_OBSERVATION


def test_legacy_selection_uses_stored_date_and_provenance_is_a_separate_channel():
    """Baselines captured from main 72f69b4 for the same provenance fixtures."""
    # Fixture A: the newer observation sits on the older stored row. Main selects
    # the latest *stored* row (80 -> score 40); provenance must not switch rows.
    fixture_a = _observations_frame(
        "resting_hr", [(1, 50.0, 0), (0, 80.0, 1)], "resting_hr_observed_at"
    )
    result_a = compute_readiness_today(
        sleep_df=None,
        hrv_df=None,
        health_df=fixture_a,
        training_df=None,
        activities_df=None,
        today=TODAY,
        max_value_age_days=None,
    )
    rhr_a = _factor(result_a, "resting_hr")
    assert rhr_a["raw_value"] == 80.0
    assert rhr_a["score"] == 40.0
    assert rhr_a["as_of"] == TODAY.isoformat()
    assert rhr_a["stale_input"] is False
    # ... while its own observation is yesterday: descriptive only, not eligible.
    assert rhr_a["observation_as_of"] == (TODAY - timedelta(days=1)).isoformat()
    assert rhr_a["observation_status"] == OBSERVATION_OUTDATED
    assert rhr_a["intervention_eligible"] is False

    # Fixture B: stored today, observed yesterday. Legacy stays today/not-stale,
    # provenance reports yesterday/stale (this is what readiness_snapshot reads).
    fixture_b = _observations_frame(
        "resting_hr", [(0, 55.0, 1), *_history_rows(55.0)], "resting_hr_observed_at"
    )
    result_b = compute_readiness_today(
        sleep_df=None,
        hrv_df=None,
        health_df=fixture_b,
        training_df=None,
        activities_df=None,
        today=TODAY,
        max_value_age_days=None,
    )
    rhr_b = _factor(result_b, "resting_hr")
    assert rhr_b["raw_value"] == 55.0
    assert rhr_b["score"] == 85.0
    assert rhr_b["baseline"] == 55.0
    assert rhr_b["as_of"] == TODAY.isoformat()
    assert rhr_b["stale_input"] is False
    assert rhr_b["observation_as_of"] == (TODAY - timedelta(days=1)).isoformat()
    assert rhr_b["age_days"] == 1
    assert rhr_b["observation_status"] == OBSERVATION_OUTDATED
    assert rhr_b["intervention_eligible"] is False


def test_unverified_measurement_stays_descriptive_but_not_intervention():
    legacy = compute_readiness_today(**_full_inputs(), today=TODAY)
    rhr = _factor(legacy, "resting_hr")

    assert rhr["observation_status"] == OBSERVATION_UNVERIFIED
    assert rhr["intervention_eligible"] is False
    # Frozen legacy behaviour: the value is still used and not marked stale.
    assert rhr["score"] is not None
    assert rhr["stale_input"] is False
    assert any(item["key"] == "resting_hr" for item in legacy["ineligible_inputs"])


def test_drivers_carry_provenance_fields():
    result = compute_readiness_today(**_mixed_inputs(rhr_observed=0), today=TODAY)
    assert result["drivers"]
    for driver in result["drivers"]:
        assert "as_of" in driver
        assert "observation_as_of" in driver
        assert "age_days" in driver
        assert driver["observation_status"] in {
            OBSERVATION_CONFIRMED_TODAY,
            OBSERVATION_OUTDATED,
            OBSERVATION_UNVERIFIED,
        }
        assert isinstance(driver["intervention_eligible"], bool)
        assert driver["evidence_kind"] in {"measurement", "derived_state"}
        assert driver["source"]


def test_legacy_aggregates_are_frozen_and_new_keys_are_additive():
    """Baseline captured from main 72f69b4 before M1 (no provenance columns)."""
    result = compute_readiness_today(**_full_inputs(), today=TODAY)

    assert result["score"] == 76.5
    assert result["status"] == "strong"
    assert result["confidence"] == 1.0
    assert result["as_of_date"] == TODAY.isoformat()
    assert {f["key"]: f["score"] for f in result["factors"]} == {
        "hrv": 70.0,
        "resting_hr": 85.0,
        "sleep": 80.0,
        "training_readiness": 80.0,
        "tsb": 70.0,
    }

    # Sleep rows carry their payload date, so they stay intervention-eligible
    # without a provenance column; RHR/HRV/training readiness do not.
    assert result["eligible_inputs"] == ["sleep", "tsb"]
    assert result["intervention_confidence"] == 0.4
    assert result["intervention_score"] == pytest.approx(75.7)


def test_empty_inputs_block_intervention_without_eligibility():
    result = compute_readiness_today(
        sleep_df=None,
        hrv_df=None,
        health_df=None,
        training_df=None,
        activities_df=None,
        today=TODAY,
    )
    assert result["score"] is None
    assert result["intervention_score"] is None
    assert result["intervention_confidence"] == 0.0
    assert result["intervention_blocked_reason"] == "no_intervention_eligible_factors"
    assert result["eligible_inputs"] == []
