"""Frozen 30-case M4c feasibility experiment; synthetic SQLite only.

Run from repository root: python docs/reports/2026-10-21-planning-entry-load-m4c/experiment.py --output /tmp/m4c-experiment.json
Budget/fixtures/exit rules: spikes/issue-710-entry-dose/README.md, frozen before this run.
"""

from __future__ import annotations
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest  # noqa: E402
from api import planning_service as ps  # noqa: E402
from models.planning_build_confirmation import (
    BuildParameters,
    canonical_json,
    dependency_components,
)  # noqa: E402
from tests.smoke._planning_build_confirmation import pin_clock  # noqa: E402
from tests.smoke._planning_entry_dose import entry_request, exposure_db  # noqa: E402

AS_OF = date(2026, 10, 16)
CAPS = {
    s: {
        "source": "athlete_declared",
        "weekly_minutes": m,
        "weekly_sessions": 1,
        "max_session_minutes": m,
    }
    for s, m in (("bike", 60), ("run", 40), ("swim", 20))
}


def row(identity, ago, sport, minutes, tss=30, parent=None):
    return {
        "activity_id": identity,
        "date": (AS_OF - timedelta(days=ago)).isoformat(),
        "sport": sport,
        "duration_minutes": minutes,
        "tss": tss,
        "tss_method": {
            "bike": "power_tss_bike",
            "run": "hr_tss_run",
            "swim": "pace_tss_swim",
        }.get(sport, "synthetic_fixed"),
        "parent": parent,
    }


def steady():
    return [
        row(f"{s}-{ago}", ago, s, CAPS[s]["weekly_minutes"])
        for ago in (2, 9, 16, 23)
        for s in CAPS
    ]


def history(kind):
    rows = steady()
    limits = None
    coverage = "user_reported_complete"
    if kind == "run_only":
        rows = [r for r in rows if r["sport"] == "run"]
        limits = {s: CAPS[s] for s in ("bike", "swim")}
    elif kind == "mixed":
        rows = [
            row(f"mixed-{i}", ago, s, 40)
            for i, (ago, s) in enumerate(
                zip((2, 9, 16, 23), ("run", "bike", "bike", "swim"), strict=True)
            )
        ]
    elif kind.startswith("empty"):
        rows = []
        coverage = "unknown" if kind == "empty_unknown" else coverage
    elif kind == "sparse":
        rows = [row("one", 2, "run", 40)]
    elif kind == "missing_duration":
        rows[1]["duration_minutes"] = None
    elif kind == "partial":
        coverage = "partial"
    elif kind in {"multi", "partial_multi", "zero_tss_multi"}:
        rows = []
        for ago in (2, 9, 16, 23):
            parent = f"envelope-{ago}"
            rows.append(row(parent, ago, "multi_sport", 120, 90))
            sports = ("swim",) if kind == "partial_multi" else tuple(CAPS)
            rows.extend(
                row(
                    f"{s}-{ago}",
                    ago,
                    s,
                    CAPS[s]["weekly_minutes"],
                    0 if kind == "zero_tss_multi" else 30,
                    parent,
                )
                for s in sports
            )
    elif kind == "future":
        rows.append(row("future", -1, "run", 500))
    elif kind == "today":
        rows.append(row("today", 0, "run", 500))
    return rows, deepcopy(limits), coverage


def measure(plan, entry):
    leaves = []
    first = defaultdict(float)
    start = date.fromisoformat(entry["scope"]["start_date"])
    for day in plan["session_templates"]:
        d = date.fromisoformat(day["date"][:10])
        for session in day.get("sessions", []):
            for leaf in (
                session.get("legs", [])
                if session.get("kind") == "composite"
                else [session]
            ):
                s = leaf["sport"]
                minutes = float(leaf["duration_minutes"])
                leaves.append((d, s, minutes))
                if start <= d < start + timedelta(days=7):
                    first[s] += minutes
                cap = entry["limits"][s]
                factor = 1.1 ** max(0, (d - start).days // 7 - 1)
                assert minutes <= cap["max_session_minutes"] * factor + 1e-7
    for offset in range(-6, 56):
        d = start + timedelta(days=offset)
        factor = 1.1 ** max(0, offset // 7 - 1)
        for s, cap in entry["limits"].items():
            bucket = [
                m
                for day, sport, m in leaves
                if sport == s and d <= day <= d + timedelta(days=6)
            ]
            assert sum(bucket) <= cap["weekly_minutes"] * factor + 1e-7
            assert len(bucket) <= cap["weekly_sessions"]
    assert set(first) == set(CAPS), "supported result must have all targeted sports"
    return dict(first)


def run(root, kind, start, monkeypatch):
    db = exposure_db(root, ["running"] * 4)
    recent, limits, coverage = history(kind)
    if kind == "nonfinite_limit":
        limits = deepcopy(CAPS)
        limits["bike"]["weekly_minutes"] = float("inf")
    with db._connect() as conn:
        conn.execute("DELETE FROM activities WHERE activity_id LIKE 'recent-%'")
        for item in recent:
            conn.execute(
                "INSERT INTO activities(activity_id,date,sport,duration_minutes,tss,tss_method) VALUES(?,?,?,?,?,?)",
                tuple(
                    item[k]
                    for k in (
                        "activity_id",
                        "date",
                        "sport",
                        "duration_minutes",
                        "tss",
                        "tss_method",
                    )
                ),
            )
            if item["parent"]:
                conn.execute(
                    "INSERT INTO activity_provider_links(canonical_activity_id,provider,provider_activity_id,external_provider,external_id) VALUES(?,'intervals',?,'garmin',?)",
                    (item["activity_id"], item["activity_id"], item["parent"]),
                )
    raw = entry_request(db, limits=limits)
    raw.update(start_date=start, start_week="2026-10-26")
    if coverage != "user_reported_complete":
        raw["history_coverage"]["status"] = coverage
    before = perf_counter()
    try:
        snapshot = ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
        if kind in {"duplicate", "conflict", "nonfinite_duration"}:
            sources = snapshot.sources()
            cols = sources["activities"]["columns"]
            idx = next(
                i
                for i, r in enumerate(sources["activities"]["data"])
                if r[cols.index("activity_id")] == "run-2"
            )
            item = deepcopy(sources["activities"]["data"][idx])
            evidence = next(
                r
                for r in sources["entry_inputs"]["rows"]
                if r["activity_id"] == "run-2"
            )
            evidence = deepcopy(evidence)
            if kind != "duplicate":
                item[cols.index("duration_minutes")] = evidence["duration_minutes"] = (
                    80 if kind == "conflict" else float("inf")
                )
            sources["activities"]["data"].append(item)
            sources["entry_inputs"]["rows"].append(evidence)
            context = snapshot.context()
            encoded = canonical_json(sources)
            context["components"] = dependency_components(encoded)
            snapshot = replace(
                snapshot, sources_json=encoded, context_json=canonical_json(context)
            )
        result = ps._calculate_plan_build(snapshot)
        response = json.loads(result.response_json)
        plan = json.loads(result.checkpoint_json)["goal_plan_snapshot"]
        if kind == "edit":
            shown = ps.prepare_plan_build(
                db, parameters=BuildParameters.from_mapping(raw), origin="planning_ui"
            )
            ps.confirm_plan_build(
                db, preview_id=shown["confirmation"]["preview_id"], origin="planning_ui"
            )
            from services.planning_cycles import current_cycle_context

            c = current_cycle_context(db)
            raw.update(
                action="edit_current",
                base_cycle_id=c["cycle_id"],
                base_cycle_revision=c["cycle_revision"],
                base_selection_revision=c["selection_revision"],
                base_checkpoint_id=c["checkpoint_id"],
                replace_current_cycle=False,
            )
            raw.pop("history_coverage")
            raw.pop("initial_dose_limits", None)
            result = ps._calculate_plan_build(
                ps._capture_plan_build_inputs(db, BuildParameters.from_mapping(raw))
            )
            response = json.loads(result.response_json)
            plan = json.loads(result.checkpoint_json)["goal_plan_snapshot"]
        entry = response["entry_load"]
        assert entry["scope"]["start_date"] == start
        assert response["build_readiness"]["training_suitability"] == "not_assessed"
        first = measure(plan, entry) if entry["can_publish"] else None
        if kind in {
            "steady",
            "run_only",
            "multi",
            "duplicate",
            "zero_tss_multi",
            "future",
            "today",
            "edit",
        }:
            assert entry["status"] == "supported", entry["blockers"]
            assert response["build_readiness"]["status"] == "ready", response[
                "build_readiness"
            ]["blockers"]
        if kind in {
            "mixed",
            "empty_complete",
            "empty_unknown",
            "sparse",
            "missing_duration",
            "partial",
            "partial_multi",
            "conflict",
        }:
            assert not entry["can_publish"], "false publishable result"
        expected_counts = {s: 4 for s in CAPS}
        if kind == "run_only":
            expected_counts = {"bike": 0, "run": 4, "swim": 0}
        if kind in {
            "steady",
            "run_only",
            "multi",
            "duplicate",
            "zero_tss_multi",
            "future",
            "today",
        }:
            assert {
                s: p["session_count"] for s, p in entry["profile"]["sports"].items()
            } == expected_counts
        if first:
            assert all(first[s] <= CAPS[s]["weekly_minutes"] for s in CAPS)
        return {
            "case": kind,
            "start": start,
            "status": entry["status"],
            "first_week_minutes": first,
            "limits": entry["limits"],
            "blocker_codes": sorted({b["code"] for b in entry["blockers"]}),
            "total_tss": response["totals"]["total_tss"],
            "elapsed_seconds": round(perf_counter() - before, 4),
        }
    except ValueError as exc:
        if kind not in {"nonfinite_limit", "nonfinite_duration"}:
            raise
        return {
            "case": kind,
            "start": start,
            "status": "invalid_input",
            "error": type(exc).__name__,
            "elapsed_seconds": round(perf_counter() - before, 4),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    kinds = (
        "run_only",
        "mixed",
        "steady",
        "empty_complete",
        "empty_unknown",
        "sparse",
        "missing_duration",
        "partial",
        "multi",
        "partial_multi",
        "duplicate",
        "conflict",
    )
    cases = [(k, s) for s in ("2026-10-26", "2026-10-28") for k in kinds] + [
        (k, "2026-10-28")
        for k in (
            "future",
            "today",
            "zero_tss_multi",
            "nonfinite_duration",
            "nonfinite_limit",
            "edit",
        )
    ]
    started = perf_counter()
    results = []
    with (
        pytest.MonkeyPatch.context() as monkeypatch,
        TemporaryDirectory(prefix="entry-m4c-") as temporary,
    ):
        pin_clock(monkeypatch)
        for index, (kind, start) in enumerate(cases):
            assert perf_counter() - started < 900, "15-minute budget exhausted"
            root = Path(temporary) / str(index)
            root.mkdir()
            results.append(run(root, kind, start, monkeypatch))
    assert len(results) == 30
    output = {
        "protocol": "frozen-m4c-30-v1",
        "as_of": AS_OF.isoformat(),
        "cases": results,
        "counts": dict(Counter(r["status"] for r in results)),
        "elapsed_seconds": round(perf_counter() - started, 4),
        "invariant_violations": 0,
        "claim": "technical feasibility only; training suitability not assessed",
    }
    Path(args.output).write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in output.items() if k != "cases"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
