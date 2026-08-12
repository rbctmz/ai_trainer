"""Regression contracts for multisport envelope load de-duplication (#420)."""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd
import pytest

from models.signals_engine import training_load_metrics
from data.database import Database


pytestmark = pytest.mark.smoke
ENVELOPE_ID = "garmin-multisport-1"


def _row(
    activity_id: str,
    sport: str,
    tss: float | None,
    *,
    parent_id: str | None = None,
) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "provider_external_id": parent_id,
        "date": "2026-07-26",
        "sport": sport,
        "tss": tss,
    }


def _metrics(frame: pd.DataFrame, *, as_of: date | None) -> dict[str, object]:
    return training_load_metrics(frame, as_of=as_of)


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_multisport_envelope_and_legs_count_load_once(as_of: date | None) -> None:
    legs = pd.DataFrame(
        [
            _row("swim-leg", "swimming", 34.7, parent_id=ENVELOPE_ID),
            _row("transition-leg", "transition", 1.6, parent_id=ENVELOPE_ID),
            _row("bike-leg", "cycling", 85.7, parent_id=ENVELOPE_ID),
            _row("run-leg", "running", 65.2, parent_id=ENVELOPE_ID),
        ]
    )
    envelope_and_legs = pd.concat(
        [
            pd.DataFrame(
                [
                    _row(ENVELOPE_ID, "multi_sport", 68.7)
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
        [_row(ENVELOPE_ID, "multi_sport", 68.7)]
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
            _row(ENVELOPE_ID, "multi_sport", 68.7),
            _row("strength-1", "strength", 20.0),
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
            _row(ENVELOPE_ID, "multi_sport", 68.7),
            _row("swim-leg", "swimming", None, parent_id=ENVELOPE_ID),
        ]
    )
    envelope_only = partial_sync.iloc[[0]].copy()

    assert _metrics(partial_sync, as_of=as_of) == _metrics(
        envelope_only, as_of=as_of
    )


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_zero_tss_legs_do_not_hide_multisport_load(as_of: date | None) -> None:
    zero_load_legs = pd.DataFrame(
        [
            _row(ENVELOPE_ID, "multi_sport", 68.7),
            _row("swim-leg", "swimming", 0.0, parent_id=ENVELOPE_ID),
            _row("bike-leg", "cycling", 0.0, parent_id=ENVELOPE_ID),
            _row("run-leg", "running", 0.0, parent_id=ENVELOPE_ID),
        ]
    )
    envelope_only = zero_load_legs.iloc[[0]].copy()

    assert _metrics(zero_load_legs, as_of=as_of) == _metrics(
        envelope_only, as_of=as_of
    )


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_positive_partial_leg_does_not_double_count_multisport_load(
    as_of: date | None,
) -> None:
    partial_sync = pd.DataFrame(
        [
            _row(ENVELOPE_ID, "multi_sport", 68.7),
            _row("swim-leg", "swimming", 34.7, parent_id=ENVELOPE_ID),
        ]
    )
    envelope_only = partial_sync.iloc[[0]].copy()

    assert _metrics(partial_sync, as_of=as_of) == _metrics(
        envelope_only, as_of=as_of
    )


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_unlinked_same_day_run_keeps_its_load(as_of: date | None) -> None:
    envelope_and_run = pd.DataFrame(
        [
            _row(ENVELOPE_ID, "multi_sport", 68.7),
            _row("evening-run", "running", 20.0),
        ]
    )
    expected_total = pd.DataFrame(
        [{"date": "2026-07-26", "sport": "running", "tss": 88.7}]
    )

    assert _metrics(envelope_and_run, as_of=as_of) == _metrics(
        expected_total, as_of=as_of
    )


def test_database_exposes_intervals_external_activity_lineage(tmp_path) -> None:
    db = Database(str(tmp_path / "multisport.db"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "INSERT INTO activities (activity_id, date, sport, tss) VALUES (?, ?, ?, ?)",
        ("swim-leg", "2026-07-26", "swimming", 34.7),
    )
    conn.execute(
        """
        INSERT INTO activity_provider_links (
            canonical_activity_id, provider, provider_activity_id,
            external_provider, external_id, match_status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("swim-leg", "intervals", "intervals-swim", "garmin", ENVELOPE_ID, "ambiguous"),
    )
    conn.commit()
    conn.close()

    activities = db.get_activities(days=36500)

    assert activities.iloc[0]["provider_external_id"] == ENVELOPE_ID


@pytest.mark.parametrize("as_of", [None, date(2026, 7, 26)])
def test_canonical_envelope_self_reference_keeps_its_load(
    tmp_path, as_of: date | None
) -> None:
    db = Database(str(tmp_path / f"self-reference-{as_of}.db"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "INSERT INTO activities (activity_id, date, sport, tss) VALUES (?, ?, ?, ?)",
        (ENVELOPE_ID, "2026-07-26", "multi_sport", 68.7),
    )
    conn.execute(
        """
        INSERT INTO activity_provider_links (
            canonical_activity_id, provider, provider_activity_id,
            external_provider, external_id, match_status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ENVELOPE_ID, "intervals", "intervals-envelope", "garmin", ENVELOPE_ID, "matched"),
    )
    conn.commit()
    conn.close()

    metrics = _metrics(db.get_activities(days=36500), as_of=as_of)

    assert float(metrics["ctl"]) > 0.0
    assert float(metrics["atl"]) > 0.0
