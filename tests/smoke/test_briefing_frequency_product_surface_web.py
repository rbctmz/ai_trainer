"""Executable web contract for issue #235: briefing frequency rendering.

No JS test runner exists in this repo (see
tests/smoke/test_recovery_transfer_product_surface_web.py for the same
source-string-contract pattern), so this file exercises the `.ts`/`.tsx`
source directly rather than mounting components.

Pins: the `TodayResponse.briefing` type, a `putJSON` helper for the new
PUT /api/settings/briefing contract, and /today's compact-day rendering —
gated on `state === "silence"` so a quiet-gate `no_plan`/`conflict_*` day
(which can also satisfy the backend's conservative `is_quiet_day`) never
collapses into the "План в силе" compact line, plus a reload-free expand
control and a frequency toggle that PUTs the setting.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_today_response_type_carries_briefing_frequency_and_quiet_flag() -> None:
    source = _source("web/lib/types.ts")

    assert "TodayBriefing" in source
    assert '"daily" | "conflicts_only"' in source
    assert "is_quiet_day: boolean" in source
    assert "briefing: TodayBriefing" in source


def test_api_helper_exposes_a_put_json_function_for_settings() -> None:
    source = _source("web/lib/api.ts")

    assert "export async function putJSON" in source
    assert 'method: "PUT"' in source


def test_today_page_computes_compact_day_conservatively_off_existing_state() -> None:
    """Compact rendering must never leak into a non-`silence` state, even if
    the backend's conservative `is_quiet_day` also happens to be true for a
    `no_plan`/`data_gap` day (those still have their own things to say)."""
    source = _source("web/app/today/page.tsx")

    assert "briefing?.is_quiet_day" in source
    assert 'frequency === "conflicts_only"' in source
    assert 'state === "silence"' in source


def test_today_page_renders_compact_summary_line_with_reload_free_expand() -> None:
    source = _source("web/app/today/page.tsx")

    assert "План в силе" in source
    assert "Развернуть брифинг" in source
    assert "setExpanded(true)" in source
    assert "useState(false)" in source


def test_today_page_frequency_toggle_puts_the_setting_and_refreshes_without_reload() -> None:
    source = _source("web/app/today/page.tsx")

    assert "putJSON" in source
    assert "/api/settings/briefing" in source
    assert "toggleBriefingFrequency" in source
    assert "window.location.reload" not in source
