"""Theme bootstrap: resolve initial dark-mode and persist the choice.

Stage 3 of theme consolidation. Two responsibilities:

1. ``resolve_initial_dark_mode`` — a pure preference cascade
   (stored > system > default) that is unit-testable.
2. ``render_theme_probe`` / ``persist_theme_choice`` — JS roundtrips via
   ``streamlit.components.v1.html``, which actually executes JS (unlike
   ``<script>`` tags emitted through ``st.markdown``, which Streamlit does
   not run). The probe feeds stored/system values back through a query param
   so Python can seed ``dark_mode`` on the next rerun.

The localStorage key is ``aitrainer_dark_mode`` (kept from the legacy
write-only implementation so existing client storage still maps cleanly).
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

# Query param used to carry the JS-resolved preference back into Python.
THEME_QUERY_PARAM = "aitrainer_dark"
LOCALSTORAGE_KEY = "aitrainer_dark_mode"


def resolve_initial_dark_mode(
    stored: Optional[str],
    system_prefers_dark: Optional[bool],
) -> bool:
    """Decide the initial dark-mode value from stored/system signals.

    Preference cascade:
    1. ``stored`` — an explicit user choice persisted across sessions
       ("true"/"false"). Corrupt values are treated as "no preference".
    2. ``system_prefers_dark`` — the OS ``prefers-color-scheme`` signal.
    3. default — light (``False``).
    """
    if stored is not None:
        normalized = stored.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        # corrupt value -> fall through to system/default
    if system_prefers_dark is not None:
        return bool(system_prefers_dark)
    return False


def render_theme_probe() -> None:
    """Emit a JS probe that resolves the initial theme once per session.

    Runs only when no query param has been set yet (avoids re-probing on
    every rerun). The JS reads localStorage, falls back to the OS
    ``prefers-color-scheme`` media query, and writes the result into the
    parent URL as a query param so Streamlit picks it up on rerun.
    """
    try:
        already = st.query_params.get(THEME_QUERY_PARAM)
    except Exception:
        already = None
    if already is not None:
        return  # already resolved this session

    try:
        from streamlit.components.v1 import html as components_html
    except Exception:
        return  # components not available; bootstrap stays default

    js = """
    <script>
    (function () {
        try {
            var stored = localStorage.getItem('%s');
            var dark;
            if (stored === 'true' || stored === 'false') {
                dark = stored === 'true';
            } else {
                dark = window.matchMedia &&
                       window.matchMedia('(prefers-color-scheme: dark)').matches;
            }
            var parent = window.parent;
            if (parent) {
                var url = new URL(parent.location.href);
                url.searchParams.set('%s', dark ? '1' : '0');
                parent.location.replace(url.toString());
            }
        } catch (e) { /* swallow; bootstrap stays default-light */ }
    })();
    </script>
    """ % (LOCALSTORAGE_KEY, THEME_QUERY_PARAM)

    components_html(js, height=0, width=0)


def consume_theme_query_param() -> Optional[bool]:
    """Read and clear the theme query param if present.

    Returns the resolved bool, or None if no param was set. Clearing it keeps
    the URL clean after the first paint.
    """
    try:
        raw = st.query_params.get(THEME_QUERY_PARAM)
    except Exception:
        return None
    if raw is None:
        return None
    # consume it so the URL stays clean
    try:
        del st.query_params[THEME_QUERY_PARAM]
    except Exception:
        pass
    return raw == "1"


def persist_theme_choice(dark_mode: bool) -> None:
    """Persist a manual toggle choice to localStorage via a JS roundtrip."""
    try:
        from streamlit.components.v1 import html as components_html
    except Exception:
        return

    value = "true" if dark_mode else "false"
    js = """
    <script>
    (function () {
        try { localStorage.setItem('%s', '%s'); } catch (e) {}
    })();
    </script>
    """ % (LOCALSTORAGE_KEY, value)
    components_html(js, height=0, width=0)


__all__ = [
    "LOCALSTORAGE_KEY",
    "THEME_QUERY_PARAM",
    "consume_theme_query_param",
    "persist_theme_choice",
    "render_theme_probe",
    "resolve_initial_dark_mode",
]
