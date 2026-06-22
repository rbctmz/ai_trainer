"""Compatibility helpers for running the app across Streamlit minor versions."""
from __future__ import annotations

import inspect
from typing import Any

import streamlit as st

_STRETCH_WIDTH = "stretch"
_PATCHED_ATTR = "_ai_trainer_width_compat"


def _streamlit_version_tuple(streamlit_module: Any = st) -> tuple[int, ...]:
    """Parse installed Streamlit's major.minor as ints (best-effort)."""
    raw = getattr(streamlit_module, "__version__", "")
    parts: list[int] = []
    for piece in str(raw).split(".")[:2]:
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def _supports_width_argument(func: Any) -> bool:
    try:
        return "width" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _make_stretch_translator(original: Any) -> Any:
    """Wrap a Streamlit element so width='stretch' becomes use_container_width."""

    def wrapped(*args, **kwargs):
        if kwargs.get("width") == _STRETCH_WIDTH:
            kwargs.pop("width", None)
            kwargs.setdefault("use_container_width", True)
        return original(*args, **kwargs)

    setattr(wrapped, _PATCHED_ATTR, True)
    setattr(wrapped, "__name__", getattr(original, "__name__", "wrapped"))
    return wrapped


def _wrap_stretch_width(func_name: str, streamlit_module: Any) -> None:
    original = getattr(streamlit_module, func_name)
    if getattr(original, _PATCHED_ATTR, False):
        return
    if _supports_width_argument(original):
        return
    setattr(streamlit_module, func_name, _make_stretch_translator(original))


def _wrap_dataframe_stretch(streamlit_module: Any) -> None:
    """Force width='stretch' -> use_container_width for st.dataframe.

    The generic shim does not cover dataframe because it declares `width`,
    but the Arrow proto still rejects the string value in Streamlit 1.4x
    (the parameter exists yet only integer pixels are accepted). Guard by
    version so native string-width support is used once it lands (>=1.50).
    """
    version = _streamlit_version_tuple(streamlit_module)
    if not ((1, 40) <= version < (1, 50)):
        return
    original = getattr(streamlit_module, "dataframe")
    if getattr(original, _PATCHED_ATTR, False):
        return
    setattr(streamlit_module, "dataframe", _make_stretch_translator(original))


def apply_streamlit_width_compat(streamlit_module: Any = st) -> None:
    """Translate width='stretch' into container-width calls for affected runtimes."""
    for func_name in ("button", "dataframe", "plotly_chart"):
        _wrap_stretch_width(func_name, streamlit_module)
    _wrap_dataframe_stretch(streamlit_module)


__all__ = ["apply_streamlit_width_compat"]
