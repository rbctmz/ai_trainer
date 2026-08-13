"""Shared read projections for linked multisport activity rows."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


_ENVELOPE_SPORTS = {"multi_sport", "multisport"}
_LEG_SPORTS = {
    "swim": "swim",
    "swimming": "swim",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "pool_swimming": "swim",
    "bike": "bike",
    "biking": "bike",
    "cycling": "bike",
    "indoor_cycling": "bike",
    "ride": "bike",
    "virtual_ride": "bike",
    "run": "run",
    "running": "run",
    "trailrun": "run",
    "trail_running": "run",
    "jogging": "run",
}


@dataclass(frozen=True)
class MultisportActivityGroup:
    """One multisport envelope and its explicitly linked provider stages."""

    envelope_id: str
    stage_ids: tuple[str, ...]
    complete: bool


def _text_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column].fillna("").astype(str).str.strip()


def _sport_keys(frame: pd.DataFrame) -> pd.Series:
    return (
        _text_series(frame, "sport")
        .str.lower()
        .str.replace(r"[\s-]+", "_", regex=True)
    )


def identify_multisport_groups(
    frame: pd.DataFrame | None,
) -> tuple[MultisportActivityGroup, ...]:
    """Return deterministic envelope/stage groups proven by provider lineage.

    Same-day or same-sport proximity is deliberately insufficient: a stage is
    grouped only when its ``provider_external_id`` equals a multisport envelope
    activity id.  Partial groups are returned so presentation can show received
    stages while retaining the envelope as the authoritative aggregate.
    """
    required = {"activity_id", "provider_external_id", "sport", "tss"}
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return ()
    if not required.issubset(frame.columns):
        return ()

    activity_ids = _text_series(frame, "activity_id")
    parent_ids = _text_series(frame, "provider_external_id")
    sport_keys = _sport_keys(frame)
    envelopes = sport_keys.isin(_ENVELOPE_SPORTS) & activity_ids.ne("")
    envelope_ids = set(activity_ids[envelopes])
    linked = parent_ids.isin(envelope_ids) & ~envelopes
    if not linked.any():
        return ()

    tss_values = pd.to_numeric(frame["tss"], errors="coerce")
    normalized_legs = sport_keys.map(_LEG_SPORTS)
    order = pd.DataFrame(
        {
            "activity_id": activity_ids,
            "parent_id": parent_ids,
            "leg_sport": normalized_legs,
            "usable_tss": tss_values.gt(0.0),
            "source_order": range(len(frame)),
            "started_at": pd.to_datetime(
                frame.get("started_at_utc", pd.Series(index=frame.index, dtype=object)),
                errors="coerce",
                utc=True,
            ),
        },
        index=frame.index,
    ).loc[linked]
    order = order.sort_values(
        ["parent_id", "started_at", "source_order"],
        kind="stable",
        na_position="last",
    )

    groups: list[MultisportActivityGroup] = []
    for envelope_id in activity_ids[envelopes]:
        stages = order.loc[order["parent_id"] == envelope_id]
        if stages.empty:
            continue
        positive_legs = set(
            stages.loc[stages["usable_tss"], "leg_sport"].dropna().tolist()
        )
        groups.append(
            MultisportActivityGroup(
                envelope_id=envelope_id,
                stage_ids=tuple(stages["activity_id"].tolist()),
                complete={"swim", "bike", "run"}.issubset(positive_legs),
            )
        )
    return tuple(groups)


def authoritative_training_load_activities(
    frame: pd.DataFrame | None,
) -> pd.DataFrame:
    """Choose envelope or linked stages once for each multisport group."""
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    groups = identify_multisport_groups(frame)
    if not groups:
        return frame

    activity_ids = _text_series(frame, "activity_id")
    excluded: set[str] = set()
    for group in groups:
        if group.complete:
            excluded.add(group.envelope_id)
        else:
            excluded.update(group.stage_ids)
    return frame.loc[~activity_ids.isin(excluded)]
