"""Executable web contract for Issue #557 M5: the readiness freshness surface.

The browser only renders server-owned values: `freshness`, per-factor
observation dates and the intervention verdict arrive from `/api/today`, and the
page must not recompute them. No JS test runner exists in this repo (see
`tests/smoke/test_recovery_transfer_product_surface_web.py`), so this file pins
the `.tsx` source contract directly.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


# ------------------------------------------------------------------- contract


def test_types_expose_the_freshness_and_provenance_contract() -> None:
    source = _source("web/lib/types.ts")

    assert "export type ReadinessObservationStatus" in source
    for status in ("confirmed_today", "outdated", "unverified", "invalid", "missing"):
        assert f'"{status}"' in source
    assert "export type ReadinessFreshnessState" in source
    assert "export interface ReadinessFreshness" in source
    assert "export interface ReadinessIneligibleInput" in source
    assert "export interface TodayReadinessDriver" in source

    # Per-factor provenance fields the UI renders as dates.
    for field in (
        "observation_as_of",
        "observation_status",
        "age_days",
        "intervention_eligible",
        "evidence_kind",
    ):
        assert field in source

    # Today's readiness carries the server-owned verdict and inputs.
    for field in (
        "freshness?: ReadinessFreshness | null",
        "intervention_score?: number | null",
        "intervention_confidence?: number",
        "eligible_inputs?: string[]",
        "ineligible_inputs?: ReadinessIneligibleInput[]",
        "intervention_blocked_reason?: string | null",
    ):
        assert field in source


# ------------------------------------------------------------------ rendering


def test_today_renders_dated_observation_labels_from_server_status() -> None:
    source = _source("web/app/today/page.tsx")

    assert "observationDateLabel" in source
    for label in (
        "сегодня",
        "вчера",
        "дн. назад",
        "некорректная дата измерения",
        "дата измерения неизвестна",
    ):
        assert label in source
    # The label is chosen by the server-provided observation_status, not inferred
    # from a date string comparison.
    assert "driver.observation_status" in source
    assert "driver.observation_as_of" in source
    assert "driver.age_days" in source


def test_today_surfaces_the_freshness_verdict_and_blocked_reason() -> None:
    source = _source("web/app/today/page.tsx")

    assert "readiness.freshness" in source
    assert 'readiness.freshness.state === "data_gap"' in source
    assert "readiness.freshness.blocked_reason" in source
    assert "freshnessSummary(readiness.freshness)" in source
    for bucket in ("confirmed_today", "outdated", "unverified", "invalid", "missing"):
        assert f"freshness.{bucket}" in source
    assert "no_confirmed_today_primary_recovery_measurement" in source
    assert "no_intervention_eligible_factors" in source
    # A descriptive score that is not backed by fresh measurements is labelled.
    assert "предварительно" in source


def test_today_does_not_recompute_readiness_business_rules() -> None:
    """The page may only map server values to labels."""
    source = _source("web/app/today/page.tsx")

    # No threshold arithmetic on the intervention channel or its inputs.
    for forbidden in (
        "readiness.intervention_score >",
        "readiness.intervention_score <",
        "intervention_confidence >",
        "intervention_confidence <",
        "eligible_inputs.includes(",
    ):
        assert forbidden not in source
    # Coverage is labelled honestly instead of being presented as freshness.
    assert "покрытие факторов" in source
    assert "описательная уверенность" in source
