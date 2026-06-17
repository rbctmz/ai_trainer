from __future__ import annotations

from types import SimpleNamespace

import pytest

from utils.streamlit_compat import apply_streamlit_width_compat


pytestmark = pytest.mark.smoke


def test_apply_streamlit_width_compat_translates_stretch_to_container_width():
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def make_stub(name: str):
        def stub(*args, **kwargs):
            calls.append((name, args, dict(kwargs)))
            return name

        return stub

    fake_streamlit = SimpleNamespace(
        button=make_stub("button"),
        dataframe=make_stub("dataframe"),
        plotly_chart=make_stub("plotly_chart"),
    )

    apply_streamlit_width_compat(fake_streamlit)

    assert fake_streamlit.button("CTA", width="stretch") == "button"
    assert fake_streamlit.dataframe("rows", width="stretch", height=200) == "dataframe"
    assert fake_streamlit.plotly_chart("fig", width="stretch") == "plotly_chart"

    assert calls == [
        ("button", ("CTA",), {"use_container_width": True}),
        ("dataframe", ("rows",), {"use_container_width": True, "height": 200}),
        ("plotly_chart", ("fig",), {"use_container_width": True}),
    ]


def test_apply_streamlit_width_compat_preserves_non_stretch_width_values():
    calls: list[dict[str, object]] = []

    def dataframe_stub(*args, **kwargs):
        calls.append(dict(kwargs))
        return "dataframe"

    fake_streamlit = SimpleNamespace(
        button=lambda *args, **kwargs: None,
        dataframe=dataframe_stub,
        plotly_chart=lambda *args, **kwargs: None,
    )

    apply_streamlit_width_compat(fake_streamlit)
    fake_streamlit.dataframe("rows", width=640, hide_index=True)

    assert calls == [{"width": 640, "hide_index": True}]
