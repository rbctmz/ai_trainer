"""Smoke coverage for utils/visualizations.py's TSB-zone chart migration
(issue #63).

create_banister_chart (the only one of the two migrated chart functions
with live callers -- see ui/pages/planning.py) used its own 4-way TSB split
(5/-10/-30) across four touchpoints that had to move in lockstep: per-point
marker colors, four background rects, and three boundary reference lines.
All four now derive from tsb_zone() and the shared _TSB_TONE_COLORS /
_TSB_TONE_BG_COLORS palettes, verified here by inspecting the built Plotly
figure's object graph rather than asserting on strings alone.

create_modern_dashboard_chart's TSB gauge was migrated too (same pattern),
but that function has zero callers anywhere in the app (confirmed by
repo-wide grep) and fails even on main before this change, for a reason
unrelated to TSB: its go.Indicator trace is incompatible with the xy
subplot type declared for that grid position. Out of scope to fix here --
not smoke-tested for that reason, since it cannot run at all regardless of
this change.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from models.banister import tsb_zone
from utils.visualizations import _TSB_TONE_BG_COLORS, _TSB_TONE_COLORS, Visualizations

_DATES = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(10)]
_TSB_VALUES = [-25.0, -20.1, -15.0, -10.1, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0]


def _build_chart():
    return Visualizations.create_banister_chart(
        _DATES, [40.0] * 10, [40.0] * 10, _TSB_VALUES
    )


def test_tsb_marker_colors_match_canonical_zone_at_every_point():
    fig = _build_chart()
    tsb_trace = next(t for t in fig.data if t.name == "TSB (Форма)")

    expected = [_TSB_TONE_COLORS[tsb_zone(tsb)["tone"]] for tsb in _TSB_VALUES]
    assert list(tsb_trace.marker.color) == expected


def test_background_rects_use_canonical_boundaries_and_matching_colors():
    fig = _build_chart()
    bands = {
        (round(shp.y0), round(shp.y1)): shp.fillcolor
        for shp in fig.layout.shapes
        if shp.y0 != shp.y1  # exclude the hline dashed-line shapes, which have y0==y1
    }
    assert bands == {
        (10, 30): _TSB_TONE_BG_COLORS["success"],
        (-10, 10): _TSB_TONE_BG_COLORS["neutral"],
        (-20, -10): _TSB_TONE_BG_COLORS["warning"],
        (-50, -20): _TSB_TONE_BG_COLORS["danger"],
    }


def test_boundary_reference_lines_sit_at_canonical_boundaries():
    fig = _build_chart()
    boundary_annotations = {
        round(ann.y): ann.text
        for ann in fig.layout.annotations
        if ann.y in (10, -10, -20)
    }
    assert boundary_annotations == {
        10: "🟢 Свежесть",
        -10: "🟡 Стабильная нагрузка",
        -20: "🟠 Накопленная усталость",
    }
