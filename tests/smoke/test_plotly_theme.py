"""Smoke tests for the extracted Plotly theme helpers.

P1-theme-consolidation: these helpers moved out of the legacy ``ui/theme.py``
into ``ui/plotly_theme.py`` so the Material theme engine can be removed while
the chart color contract survives. The contract is the exact palette values.
"""
from __future__ import annotations

import pytest

from ui.plotly_theme import apply_plotly_theme, create_dark_table_html, get_plotly_theme


pytestmark = pytest.mark.smoke


def test_dark_plotly_theme_contract() -> None:
    theme = get_plotly_theme(True)
    assert theme["template"] == "plotly_dark"
    assert theme["paper_bgcolor"] == "#101411"  # cockpit --ic-bg
    assert theme["plot_bgcolor"] == "#19221D"   # cockpit --ic-surface
    assert theme["font_color"] == "#F4F0E7"     # cockpit --ic-ink
    assert theme["gridcolor"] == "rgba(244,240,231,0.12)"  # cockpit --ic-hairline


def test_light_plotly_theme_contract() -> None:
    theme = get_plotly_theme(False)
    assert theme["template"] == "plotly_white"
    assert theme["paper_bgcolor"] == "#FFFDF7"  # cockpit --ic-surface (light)
    assert theme["plot_bgcolor"] == "#FFFDF7"
    assert theme["font_color"] == "#18251F"     # cockpit --ic-ink (light)
    assert theme["gridcolor"] == "rgba(24,37,31,0.12)"  # cockpit --ic-hairline (light)


def test_apply_plotly_theme_writes_dark_palette_onto_figure() -> None:
    class _FakeFig:
        def __init__(self) -> None:
            self.calls: list[tuple[tuple, dict]] = []

        def update_layout(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return self

    fig = _FakeFig()
    result = apply_plotly_theme(fig, dark_mode=True)

    assert result is fig
    assert fig.calls, "apply_plotly_theme must call fig.update_layout"
    kwargs = fig.calls[0][1]
    assert kwargs["template"] == "plotly_dark"
    assert kwargs["paper_bgcolor"] == "#101411"
    assert kwargs["font"] == dict(color="#F4F0E7")


def test_create_dark_table_html_contains_dark_palette_and_headers() -> None:
    import pandas as pd

    df = pd.DataFrame({"col_a": [1, 2], "col_b": ["x", "y"]})
    html = create_dark_table_html(df)

    assert "#1E1E1E" in html  # dark surface
    assert "#F5F5F5" in html  # dark text
    assert "col_a" in html and "col_b" in html
    assert "<table" in html and "</table>" in html
