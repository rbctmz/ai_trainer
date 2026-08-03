"""BDD gates for UI beta v2 M4 (#268): dev-tools discoverability + trust/accessibility.

Covers: dev-only badge/menu gated by the build-time flag (with README docs),
adherence not calling today's unmatched planned session «Пропущено», keyboard-
accessible InfoTip, and user-facing microcopy without stray English labels.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from models.adherence_ribbon import build_adherence_ribbon


pytestmark = pytest.mark.smoke
REPO_ROOT = Path(__file__).resolve().parents[2]
NAV = REPO_ROOT / "web/components/Nav.tsx"
TOOLTIP = REPO_ROOT / "web/components/ui/Tooltip.tsx"
BUILDER = REPO_ROOT / "web/components/planning/PlanBuilder.tsx"
ADHERENCE_LIB = REPO_ROOT / "web/lib/adherence.ts"
TYPES = REPO_ROOT / "web/lib/types.ts"
README = REPO_ROOT / "README.md"


def _row(day: str):
    return {
        "index": 0,
        "session_id": f"s_{day}",
        "date": day,
        "sport": "run",
        "role": "quality",
        "tss": 60.0,
        "match_status": "unmatched",
        "adherence": None,
        "actual_total_tss": 0.0,
    }


def _snapshot(rows, as_of: date):
    return {
        "has_plan": True,
        "as_of": as_of.isoformat(),
        "window": {
            "start": (as_of - timedelta(days=6)).isoformat(),
            "end": as_of.isoformat(),
            "weeks": 1,
        },
        "rows": rows,
        "unplanned_activities": [],
        "data_quality": {"status": "ok", "reasons": []},
        "rule_version": "plan_actual_match_v1",
    }


def test_today_unmatched_planned_session_is_pending_not_missed():
    as_of = date(2026, 8, 9)
    ribbon = build_adherence_ribbon(
        _snapshot([_row("2026-08-09")], as_of),
        as_of=as_of,
        weeks=1,
    )

    day = next(item for item in ribbon["days"] if item["date"] == "2026-08-09")
    assert day["status"] == "pending"
    assert ribbon["weeks"][0]["adherence"]["missed"] == 0


def test_same_row_is_missed_after_day_boundary():
    as_of = date(2026, 8, 16)  # воскресенье; неделя понедельник-привязана
    ribbon = build_adherence_ribbon(
        _snapshot([_row("2026-08-15")], as_of),
        as_of=as_of,
        weeks=1,
    )

    day = next(item for item in ribbon["days"] if item["date"] == "2026-08-15")
    assert day["status"] == "missed"
    assert ribbon["weeks"][0]["adherence"]["missed"] == 1


def test_dev_tools_badge_is_gated_and_documented():
    nav = NAV.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert "showDevTools" in nav
    assert 'href="/decisions"' in nav
    assert 'href="/recovery"' in nav
    assert "NEXT_PUBLIC_SHOW_DEV_TOOLS=true" in readme


def test_tooltip_is_keyboard_accessible():
    source = TOOLTIP.read_text(encoding="utf-8")

    assert 'type="button"' in source
    assert "aria-expanded" in source
    assert "aria-label" in source
    assert "Escape" in source
    assert "focus-visible:ring" in source


def test_microcopy_has_no_stray_english_labels():
    builder = BUILDER.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    adherence = ADHERENCE_LIB.read_text(encoding="utf-8")

    assert "Weekly Target" not in builder
    assert "Недельная цель" in builder
    assert '"pending"' in types
    assert "pending" in adherence
