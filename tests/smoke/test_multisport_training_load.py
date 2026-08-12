"""Regression contracts for multisport envelope load de-duplication (#420)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from models.signals_engine import training_load_metrics


pytestmark = pytest.mark.smoke


def _metrics(frame: pd.DataFrame, *, as_of: date | None) -> dict[str, object]:
    return training_load_metrics(frame, as_of=as_of)


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_multisport_envelope_and_legs_count_load_once(as_of: date | None) -> None:
    legs = pd.DataFrame(
        [
            {"date": "2026-07-26", "sport": "swimming", "tss": 34.7},
            {"date": "2026-07-26", "sport": "cycling", "tss": 85.7},
            {"date": "2026-07-26", "sport": "running", "tss": 65.2},
        ]
    )
    envelope_and_legs = pd.concat(
        [
            pd.DataFrame(
                [
                    {
                        "date": "2026-07-26",
                        "sport": "multi_sport",
                        "tss": 68.7,
                    }
                ]
            ),
            legs,
        ],
        ignore_index=True,
    )

    assert _metrics(envelope_and_legs, as_of=as_of) == _metrics(legs, as_of=as_of)


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_standalone_multisport_activity_keeps_its_load(as_of: date | None) -> None:
    standalone = pd.DataFrame(
        [{"date": "2026-07-26", "sport": "multi_sport", "tss": 68.7}]
    )

    metrics = _metrics(standalone, as_of=as_of)

    assert float(metrics["ctl"]) > 0.0
    assert float(metrics["atl"]) > 0.0


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_unrelated_same_day_activity_does_not_hide_multisport_load(
    as_of: date | None,
) -> None:
    multisport_and_strength = pd.DataFrame(
        [
            {"date": "2026-07-26", "sport": "multi_sport", "tss": 68.7},
            {"date": "2026-07-26", "sport": "strength", "tss": 20.0},
        ]
    )
    expected_total = pd.DataFrame(
        [{"date": "2026-07-26", "sport": "strength", "tss": 88.7}]
    )

    assert _metrics(multisport_and_strength, as_of=as_of) == _metrics(
        expected_total, as_of=as_of
    )


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_partial_leg_without_tss_does_not_hide_multisport_load(
    as_of: date | None,
) -> None:
    partial_sync = pd.DataFrame(
        [
            {"date": "2026-07-26", "sport": "multi_sport", "tss": 68.7},
            {"date": "2026-07-26", "sport": "swimming", "tss": None},
        ]
    )
    envelope_only = partial_sync.iloc[[0]].copy()

    assert _metrics(partial_sync, as_of=as_of) == _metrics(
        envelope_only, as_of=as_of
    )
