"""Issue #475 / spike #471: bike steady-state duration density must match step-zone math.

VALIDATED spike `spikes/issue-471-bike-tss-density-vs-zones/README.md` proved that steady
bike templates were planned around 50/64/32 TSS/h while their own power bands imply ~40/~45/
~22 TSS/h — the plan overshot the workout by 23-37%. The planner's duration estimator
(`workout_catalog._candidate_duration`) realizes `_TARGET_DENSITY[builder_key]`, a single map
shared across sports; for a fixed target TSS a mis-aimed density means the wrong ride length
and a stored `tss_per_hour` that the athlete can never actually hit at the prescribed zones.

Contract pinned here (all thresholds DERIVED from the materialized steps, none hardcoded):
  A) every bike steady-state builder carries a sport-scoped estimate —
     `_TARGET_DENSITY_BY_SPORT[("bike", key)]` — because the generic key is shared with
     Run/Swim/Walk defs (#475: do not overwrite other sports with unvalidated numbers);
  B) that scoped value equals the zone-implied density of the actually-materialized steps
     (same mid-of-band NP-free math as `evidence.py::implied_tss_for_steps`) within ±10%;
  C) a canonical 60-min materialization lands INSIDE the def's declared
     `[min_tss_per_hour, max_tss_per_hour]`.

Zone-implied density for a staged pattern is duration-invariant in the ideal case
(100·Σ share·frac²) so a multi-minute-duration probe averages bookend-floor noise.
"""
from __future__ import annotations

import pytest

import models.workout_catalog as _catalog_module
from models.workout_catalog import _candidate_duration, catalog_definitions, materialize_workout

pytestmark = pytest.mark.smoke

FTP = 160.0
PROBE_MINIMUMS = (45, 60, 90)

BIKE_STEADY_CASES = [
    ("recovery", "bike_recovery_spin"),
    ("endurance", "bike_aerobic_endurance"),
    ("progression", "bike_aerobic_progression"),
]


def _definition(template_key: str):
    match = next((d for d in catalog_definitions() if d.template_key == template_key), None)
    assert match is not None, f"no catalog definition {template_key}"
    return match


def _scoped(builder_key: str) -> float | None:
    """Look up the sport-scoped estimate; ``None`` = not implemented yet."""
    table = getattr(_catalog_module, "_TARGET_DENSITY_BY_SPORT", None)
    if not isinstance(table, dict):
        return None
    return table.get(("bike", builder_key))


def _feasible_target_tss(definition, minutes: int) -> float:
    """A target provably satisfying every bound (midpoint of declared density band)."""
    mid = (definition.min_tss_per_hour + definition.max_tss_per_hour) / 2.0 * minutes / 60.0
    return round(min(max(mid, definition.min_tss), definition.max_tss), 1)


def _zone_implied_density(definition, minutes: int) -> float | None:
    """TSS/h equivalent to the steps' power bands; mirrors `evidence.py`'s formula."""
    result = materialize_workout(
        definition,
        {"duration_minutes": minutes, "target_tss": _feasible_target_tss(definition, minutes)},
        {"ftp": FTP},
    )
    if result.get("materialization_status") != "materialized":
        return None
    total = 0.0
    for step in result["steps"]:
        target = step.get("target") or {}
        if str(target.get("type")) != "power":
            return None
        mid = (float(target["low"]) + float(target["high"])) / 2.0
        hours = float(step.get("duration_seconds") or 0) / 3600.0
        total += hours * 100.0 * (mid / FTP) ** 2
    return total * 60.0 / minutes if minutes > 0 else None


@pytest.mark.parametrize(
    "builder_key,template_key",
    BIKE_STEADY_CASES,
    ids=[t for _, t in BIKE_STEADY_CASES],
)
def test_scope_exists_and_matches_zones_within_10pct(builder_key, template_key):
    """A)+B): a sport-scoped estimate that reproduces the step-level math within ±10%."""
    definition = _definition(template_key)
    observations = [
        v for m in PROBE_MINIMUMS if (v := _zone_implied_density(definition, m)) is not None
    ]
    assert observations, f"{template_key}: no feasible probe materialized"
    reference = sum(observations) / len(observations)

    scoped = _scoped(builder_key)
    assert scoped is not None, (
        f"_TARGET_DENSITY_BY_SPORT[('bike', '{builder_key}')] missing — "
        "bike steady-state builders need a sport-scoped density estimate (#475)"
    )
    drift = (scoped - reference) / reference
    assert abs(drift) <= 0.10, (
        f"'bike/{builder_key}' density {scoped} deviates from zone-implied {reference:.1f} by {drift * 100:+.0f}%"
    )


@pytest.mark.parametrize("template_key", [t for _, t in BIKE_STEADY_CASES])
def test_zone_implied_inside_declared_bounds(template_key):
    """C): the canonical structure's implied density is legal inside its own bounds."""
    definition = _definition(template_key)
    observed = _zone_implied_density(definition, 60)
    assert observed is not None, f"{template_key}: canonical materialization failed"
    assert definition.min_tss_per_hour <= observed <= definition.max_tss_per_hour, (
        f"{template_key}: zone-implied {observed:.1f} outside declared "
        f"[{definition.min_tss_per_hour}, {definition.max_tss_per_hour}]"
    )


def test_estimator_uses_scoped_density():
    """The duration estimator honours `_TARGET_DENSITY_BY_SPORT` over the generic map."""
    definition = _definition("bike_aerobic_endurance")
    scoped = _scoped("endurance")
    assert scoped is not None, "sport-scoped table absent (RED until #475 is implemented)"
    target_tss = round(scoped * 90 / 60, 1)
    duration = _candidate_duration(definition, target_tss, estimated_duration_minutes=0)
    assert duration is not None, "estimator could not find a feasible duration with scoped density"
    realized = target_tss * 60.0 / duration
    assert abs(realized - scoped) / scoped <= 0.02, (
        f"estimator landed on {realized:.1f} TSS/h, far from scoped {scoped}"
    )
