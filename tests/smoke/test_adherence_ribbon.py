"""M1 RED contract for the adherence ribbon (Issue #228).

Pins, before `models/adherence_ribbon.py` and the API router exist:
- the ribbon is a PURE derivation over the reconciliation snapshot: no DB
  reads, no provider calls, input never mutated, byte-deterministic;
- day status matrix: worst honest label wins among matched rows
  (major_deviation > substituted > exact), `missed` only for planned TSS>0
  sessions, `unplanned` for unplanned-only days, `rest` otherwise;
- weekly aggregates: adherence buckets (+missed), planned vs actual TSS over
  matched rows, unplanned TSS, missed KEY sessions via the scheduler's shared
  hard-role set — never a duplicated role list;
- API: weeks clamped to [1, 8], has_plan=false passes through as an empty
  ribbon, and the render path NEVER touches the live provider
  (include_provider=False pinned by a tripwire).
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from data.database import Database


pytestmark = pytest.mark.smoke

_AS_OF = date(2026, 8, 9)  # Sunday; weeks=1 covers Mon 08-03 .. Sun 08-09


def _row(
    day: str,
    sport: str,
    role: str,
    tss: float,
    *,
    match_status: str = "matched",
    adherence: str | None = None,
    actual: float = 0.0,
):
    # FLAT shape, mirroring the REAL build_reconciliation row (verified against
    # a live /api/planning/reconciliation payload): planned fields live at the
    # top level, not under a nested "planned" dict.
    return {
        "index": 0,
        "session_id": f"s_{day}_{sport}_{role}",
        "date": day,
        "sport": sport,
        "role": role,
        "tss": float(tss),
        "match_status": match_status,
        "adherence": adherence,
        "actual_total_tss": float(actual),
    }


def _snapshot(rows, unplanned=(), *, weeks: int = 1, has_plan: bool = True):
    start = date(2026, 8, 3 - (weeks - 1) * 7)
    return {
        "has_plan": has_plan,
        "as_of": _AS_OF.isoformat(),
        "window": {
            "start": start.isoformat(),
            "end": _AS_OF.isoformat(),
            "weeks": weeks,
        },
        "rows": list(rows),
        "unplanned_activities": list(unplanned),
        "data_quality": {"status": "ok", "reasons": []},
        "rule_version": "plan_actual_match_v1",
    }


def _build(snapshot, *, weeks: int = 1):
    from models.adherence_ribbon import build_adherence_ribbon

    return build_adherence_ribbon(snapshot, as_of=_AS_OF, weeks=weeks)


def _days_by_date(ribbon):
    return {day["date"]: day for day in ribbon["days"]}


def _reference_week_rows():
    return [
        _row("2026-08-03", "bike", "quality", 80.0, adherence="exact", actual=85.0),
        _row("2026-08-04", "run", "easy", 30.0, adherence="substituted", actual=40.0),
        _row("2026-08-05", "swim", "easy", 25.0, adherence="major_deviation", actual=70.0),
        _row("2026-08-06", "run", "long", 90.0, match_status="unmatched"),
        # planned rest marker: zero-TSS row may exist and must NOT become missed
        _row("2026-08-08", "bike", "recovery", 0.0, match_status="unmatched"),
    ]


def _reference_unplanned():
    return [
        {"date": "2026-08-07", "activity_id": "a1", "sport": "bike", "tss": 45.0},
    ]


def test_day_status_matrix_and_week_aggregates():
    """BDD 1-3: statuses per day, weekly buckets, TSS sums reconcile."""
    ribbon = _build(_snapshot(_reference_week_rows(), _reference_unplanned()))
    days = _days_by_date(ribbon)

    assert ribbon["has_plan"] is True
    assert [day["date"] for day in ribbon["days"]] == [
        f"2026-08-0{n}" for n in range(3, 10)
    ]
    assert days["2026-08-03"]["status"] == "exact"
    assert days["2026-08-04"]["status"] == "substituted"
    assert days["2026-08-05"]["status"] == "major_deviation"
    assert days["2026-08-06"]["status"] == "missed"
    assert days["2026-08-07"]["status"] == "unplanned"
    assert days["2026-08-08"]["status"] == "rest"  # zero-TSS planned row is rest
    assert days["2026-08-09"]["status"] == "rest"

    assert days["2026-08-03"]["planned_tss"] == 80.0
    assert days["2026-08-03"]["actual_tss"] == 85.0
    assert days["2026-08-07"]["planned_tss"] == 0.0
    assert days["2026-08-07"]["actual_tss"] == 45.0

    assert len(ribbon["weeks"]) == 1
    week = ribbon["weeks"][0]
    assert week["week_start"] == "2026-08-03"
    assert week["planned_sessions"] == 4  # zero-TSS rest row does not count
    assert week["matched_sessions"] == 3
    assert week["adherence"] == {
        "exact": 1,
        "substituted": 1,
        "major_deviation": 1,
        "missed": 1,
        "unknown": 0,
    }
    assert week["planned_tss"] == pytest.approx(225.0)  # 80+30+25+90
    assert week["actual_tss"] == pytest.approx(195.0)  # matched rows only
    assert week["unplanned_tss"] == pytest.approx(45.0)
    assert week["missed_key_sessions"] == [
        {"date": "2026-08-06", "sport": "run", "role": "long"}
    ]


def test_matched_but_unclassified_day_is_unknown_not_unplanned():
    """Live vocabulary: a matched row can carry adherence='unknown' (e.g.
    actual_role is missing, classification could not run). Such a day is
    'unknown' — hiding a real match behind 'unplanned' or 'rest' would lie;
    but any CLASSIFIED label on the same day still outranks it."""
    rows = [_row("2026-08-04", "run", "quality", 25.0, adherence="unknown", actual=16.0)]
    unplanned = [{"date": "2026-08-04", "activity_id": "a2", "sport": "bike", "tss": 30.0}]
    ribbon = _build(_snapshot(rows, unplanned))
    day = _days_by_date(ribbon)["2026-08-04"]
    assert day["status"] == "unknown"
    assert day["actual_tss"] == pytest.approx(46.0)  # matched 16 + unplanned 30
    week = ribbon["weeks"][0]
    assert week["adherence"]["unknown"] == 1
    assert week["matched_sessions"] == 1

    mixed = [
        _row("2026-08-04", "run", "quality", 25.0, adherence="unknown", actual=16.0),
        _row("2026-08-04", "bike", "easy", 40.0, adherence="exact", actual=42.0),
    ]
    ribbon = _build(_snapshot(mixed))
    assert _days_by_date(ribbon)["2026-08-04"]["status"] == "exact"


def test_worst_honest_label_wins_within_a_day():
    rows = [
        _row("2026-08-04", "bike", "easy", 40.0, adherence="exact", actual=42.0),
        _row("2026-08-04", "run", "quality", 50.0, adherence="major_deviation", actual=15.0),
    ]
    ribbon = _build(_snapshot(rows))
    assert _days_by_date(ribbon)["2026-08-04"]["status"] == "major_deviation"


def test_missed_key_sessions_use_shared_hard_role_set():
    """A missed easy session is missed, but NOT a missed KEY session; quality
    and long both are — the set comes from models.session_scheduler."""
    from models.session_scheduler import HARD_SESSION_ROLES

    assert {"quality", "long"} == set(HARD_SESSION_ROLES)
    rows = [
        _row("2026-08-03", "bike", "quality", 60.0, match_status="unmatched"),
        _row("2026-08-04", "run", "long", 90.0, match_status="unmatched"),
        _row("2026-08-05", "swim", "easy", 20.0, match_status="unmatched"),
    ]
    week = _build(_snapshot(rows))["weeks"][0]
    assert week["adherence"]["missed"] == 3
    assert [(item["date"], item["role"]) for item in week["missed_key_sessions"]] == [
        ("2026-08-03", "quality"),
        ("2026-08-04", "long"),
    ]


def test_ribbon_is_pure_deterministic_and_does_not_mutate_input():
    snapshot = _snapshot(_reference_week_rows(), _reference_unplanned())
    before = json.dumps(snapshot, sort_keys=True)
    first = _build(snapshot)
    second = _build(snapshot)
    assert first == second
    assert json.dumps(snapshot, sort_keys=True) == before


def test_no_plan_passes_through_as_empty_ribbon():
    ribbon = _build({"has_plan": False, "rows": [], "unplanned_activities": []})
    assert ribbon["has_plan"] is False
    assert ribbon["weeks"] == []
    assert ribbon["days"] == []


def test_api_clamps_weeks_and_never_touches_the_provider(tmp_path, monkeypatch):
    """BDD 4-6 (API side): weeks clamp [1, 8]; empty DB → has_plan=false, not
    a 500; the render path is pinned to include_provider=False — any attempt
    to build a live provider client trips the tripwire."""
    import services.intervals_icu as intervals_icu

    def _tripwire(*_args, **_kwargs):
        raise AssertionError("adherence ribbon must not touch the live provider")

    monkeypatch.setattr(intervals_icu, "get_client", _tripwire)

    from api.routers.adherence import get_adherence

    db = Database(str(tmp_path / "adherence.db"))
    payload = get_adherence(db=db, weeks=99)
    assert payload["has_plan"] is False
    assert payload["weeks_requested"] == 8  # clamped ceiling
    payload = get_adherence(db=db, weeks=0)
    assert payload["weeks_requested"] == 1  # clamped floor


def test_api_returns_full_ribbon_schema_with_real_plan_and_activities(tmp_path):
    """Issue #242: the only router-level test previously used an empty DB
    (has_plan=false short-circuits before the day/week aggregation runs).
    With an active checkpoint the full ribbon shape must pass through the
    router unchanged."""
    from api.routers.adherence import get_adherence
    from tests.smoke.test_api_planning import _reconciliation_db

    db, _plan = _reconciliation_db(tmp_path)

    payload = get_adherence(db=db, weeks=1)

    assert payload["has_plan"] is True
    assert payload["weeks_requested"] == 1
    assert isinstance(payload["days"], list) and payload["days"]
    assert isinstance(payload["weeks"], list) and payload["weeks"]
    assert "status" in payload["days"][0]
    assert "planned_tss" in payload["days"][0]
    week = payload["weeks"][0]
    assert set(week["adherence"].keys()) == {"exact", "substituted", "major_deviation", "missed", "unknown"}


def test_web_surfaces_consume_api_statuses_and_never_rederive():
    """M3 source contract: the «План vs факт» ribbon and the /today strip consume
    the API payload (statuses arrive READY from models/adherence_ribbon.py); the
    web never re-derives adherence itself. The ribbon is ONE shared component
    (web/components/AdherenceRibbon.tsx) rendered both by the /adherence route
    (deep-link, out of top nav since #253) and the «План vs факт» tab inside
    /planning (folded in #255)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    ribbon = (root / "web" / "components" / "AdherenceRibbon.tsx").read_text(encoding="utf-8")
    assert "/api/adherence?weeks=4" in ribbon
    assert "classify" not in ribbon  # no client-side re-derivation

    # status labels live in ONE shared module consumed by both surfaces
    meta = (root / "web" / "lib" / "adherence.ts").read_text(encoding="utf-8")
    for status in ("exact", "substituted", "major_deviation", "missed", "unplanned", "rest"):
        assert status in meta, status
    assert 'from "@/lib/adherence"' in ribbon

    # the shared ribbon is consumed by BOTH the /adherence route and the /planning tab
    adherence_page = (root / "web" / "app" / "adherence" / "page.tsx").read_text(encoding="utf-8")
    assert "<AdherenceRibbon" in adherence_page
    planning_page = (root / "web" / "app" / "planning" / "page.tsx").read_text(encoding="utf-8")
    assert "<AdherenceRibbon" in planning_page

    strip = (root / "web" / "components" / "today" / "AdherenceStrip.tsx").read_text(
        encoding="utf-8"
    )
    assert "/api/adherence?weeks=1" in strip
    assert 'href="/adherence"' in strip

    # Top nav collapsed to 4 primary in #253: adherence is no longer a nav item
    # (reachability is via the /today AdherenceStrip above, asserted just prior).

    today_page = (root / "web" / "app" / "today" / "page.tsx").read_text(encoding="utf-8")
    assert "AdherenceStrip" in today_page
