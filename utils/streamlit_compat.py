"""Compatibility helpers for running the app across Streamlit minor versions."""
from __future__ import annotations

import inspect
from typing import Any

import streamlit as st

_STRETCH_WIDTH = "stretch"
_PATCHED_ATTR = "_ai_trainer_width_compat"


def _supports_width_argument(func: Any) -> bool:
    try:
        return "width" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _wrap_stretch_width(func_name: str, streamlit_module: Any) -> None:
    original = getattr(streamlit_module, func_name)
    if getattr(original, _PATCHED_ATTR, False):
        return
    if _supports_width_argument(original):
        return

    def wrapped(*args, **kwargs):
        if kwargs.get("width") == _STRETCH_WIDTH:
            kwargs.pop("width", None)
            kwargs.setdefault("use_container_width", True)
        return original(*args, **kwargs)

    setattr(wrapped, _PATCHED_ATTR, True)
    setattr(wrapped, "__name__", getattr(original, "__name__", func_name))
    setattr(streamlit_module, func_name, wrapped)


def apply_streamlit_width_compat(streamlit_module: Any = st) -> None:
    """Translate width='stretch' into container-width calls for older runtimes."""
    for func_name in ("button", "dataframe", "plotly_chart"):
        _wrap_stretch_width(func_name, streamlit_module)


__all__ = ["apply_streamlit_width_compat"]
