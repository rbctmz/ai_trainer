"""RED contract for Issue #231: coach context is anchored to today.

Two independent defects reproduced here:
1. `training_load_metrics` (and thus `assemble_signals` and the coach's
   `get_performance_metrics`) calls Banister directly on activity dates only —
   the EWMA freezes at the last workout, so on a rest morning TSB is
   yesterday's value while the canonical readiness snapshot (`_tsb_metrics`,
   which feeds the sidebar) anchors zero-TSS days through today. Second
   instance of bug #139.
2. The coach has no tool for the canonical readiness snapshot nor for pending
   recovery-loop proposals, so chat cannot help contradicting the agent
   contour on adjacent pages.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest


pytestmark = pytest.mark.smoke


def _activities_through(last_offset_days: int, *, anchor: date) -> pd.DataFrame:
    """A month of daily easy TSS ending `last_offset_days` before the anchor."""
    rows = []
    for day_back in range(last_offset_days, last_offset_days + 28):
        rows.append(
            {"date": pd.Timestamp(anchor - timedelta(days=day_back)), "tss": 60.0}
        )
    return pd.DataFrame(rows)


def test_load_metrics_anchor_matches_canonical_readiness_tsb():
    """The coach load path must agree with the sidebar: with activities only
    through `anchor-3`, `training_load_metrics(df, as_of=anchor)` yields the
    same CTL/ATL/TSB as the canonical `_tsb_metrics(df, anchor)`."""
    from models.readiness import _tsb_metrics
    from models.signals_engine import training_load_metrics

    anchor = date(2026, 7, 20)
    df = _activities_through(3, anchor=anchor)  # last activity 3 rest days ago

    canonical = _tsb_metrics(df, anchor)
    assert canonical is not None

    anchored = training_load_metrics(df, as_of=anchor)
    assert round(float(anchored["tsb"]), 1) == canonical["tsb"]
    assert round(float(anchored["ctl"]), 1) == canonical["ctl"]
    assert round(float(anchored["atl"]), 1) == canonical["atl"]

    # And the anchored TSB must differ from the frozen (no-anchor) value —
    # rest days decay ATL, so today's TSB is higher than at the last workout.
    frozen = training_load_metrics(df)
    assert round(float(anchored["tsb"]), 1) != round(float(frozen["tsb"]), 1)


def test_get_performance_metrics_reports_split_dates(tmp_path):
    """The tool must not present the last activity date as 'today': it splits
    `data_through` (last activity) from `computed_for` (the anchor), so the
    model cannot narrate from a stale 'today'."""
    from data.database import Database
    from models.ai_tools import AITools

    tools = AITools(Database(str(tmp_path / "coach.db")))
    result = tools.get_performance_metrics()
    # empty DB path still must not crash; on data it exposes both dates
    assert "computed_for" in result
    assert "data_through" in result


def test_readiness_today_and_pending_proposal_tools_exist():
    """The coach needs the canonical snapshot and the contour's pending
    proposals as first-class tools, wired into the single schema registry so
    the native path (#190) picks them up automatically."""
    from data.database import Database
    from models.ai_tools import AITools
    import tempfile

    tools = AITools(Database(tempfile.mktemp(suffix=".db")))
    names = {schema["name"] for schema in tools.get_tool_schemas()}
    assert "get_readiness_today" in names
    assert "get_pending_proposals" in names
    assert set(names) == set(tools.tools.keys())  # registry bijection holds

    readiness = tools.execute_tool("get_readiness_today")
    assert readiness.get("success") is True
    proposals = tools.execute_tool("get_pending_proposals")
    assert proposals.get("success") is True
