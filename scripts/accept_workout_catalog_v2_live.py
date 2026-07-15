#!/usr/bin/env python3
"""Create, verify, and delete isolated Workout Catalog v2 provider probes."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.intervals_workout_delivery import (  # noqa: E402
    build_intervals_workout_description,
    provider_event_is_executable,
)
from models.workout_catalog import (  # noqa: E402
    catalog_definitions,
    materialize_workout,
)


LIVE_ACCEPTANCE_CONFIRMATION = "CREATE-VERIFY-DELETE-WORKOUT-CATALOG-V2-PROBES"
_ACCEPTANCE_PREFIX = "ai_trainer:acceptance:catalog-v2:"


def acceptance_external_id(target_date: date, sport: str) -> str:
    return f"{_ACCEPTANCE_PREFIX}{target_date.isoformat()}:{sport}"


def _definition(template_key: str):
    return next(
        definition
        for definition in catalog_definitions()
        if definition.template_key == template_key
    )


def _probe_payloads(target_date: date) -> list[dict[str, Any]]:
    bike = materialize_workout(
        _definition("bike_threshold_intervals"),
        {"duration_minutes": 60, "target_tss": 80.0},
        {"ftp": 200},
    )
    run = materialize_workout(
        _definition("run_tempo_threshold"),
        {"duration_minutes": 60, "target_tss": 70.0},
        {"lthr": 165},
    )
    probes = (
        ("bike", "Ride", bike, 20, "AI Trainer v2 bike acceptance"),
        ("run", "Run", run, 21, "AI Trainer v2 run acceptance"),
    )
    payloads: list[dict[str, Any]] = []
    for sport, provider_type, materialized, hour, name in probes:
        steps = list(materialized["steps"])
        payloads.append(
            {
                "external_id": acceptance_external_id(target_date, sport),
                "start_date_local": datetime.combine(
                    target_date,
                    datetime.min.time(),
                ).replace(hour=hour).strftime("%Y-%m-%dT%H:%M:%S"),
                "category": "WORKOUT",
                "name": f"{name} · temporary · delete me",
                "description": build_intervals_workout_description(
                    steps,
                    title=name,
                ),
                "type": provider_type,
                "icu_training_load": int(
                    round(float(materialized["parameter_snapshot"]["target_tss"]))
                ),
                "moving_time": sum(
                    int(step["duration_seconds"])
                    for step in steps
                ),
            }
        )
    return payloads


def _foreign_snapshot(
    events: Sequence[Mapping[str, Any]],
    acceptance_ids: set[str],
) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events):
        if str(event.get("external_id") or "") in acceptance_ids:
            continue
        key = str(event.get("id") or event.get("uid") or f"row:{index}")
        snapshot[key] = dict(event)
    return snapshot


def _confirmed_map(
    rows: Sequence[Mapping[str, Any]],
    acceptance_ids: set[str],
) -> dict[str, dict[str, Any]]:
    confirmed: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        external_id = str(row.get("external_id") or "")
        if external_id not in acceptance_ids:
            continue
        if external_id in confirmed or row.get("id") is None:
            raise RuntimeError("provider did not confirm each acceptance event exactly once")
        confirmed[external_id] = row
    if set(confirmed) != acceptance_ids:
        raise RuntimeError("provider did not confirm each acceptance event exactly once")
    return confirmed


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_key(item, key) for item in value)
    return False


def _key_paths(value: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths.update(_key_paths(item, path))
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for item in value:
            paths.update(_key_paths(item, prefix))
    return paths


def _parsed_evidence(
    confirmed: Mapping[str, Mapping[str, Any]],
    target_date: date,
) -> tuple[dict[str, int], dict[str, str]]:
    counts: dict[str, int] = {}
    target_types: dict[str, str] = {}
    expected = {"bike": ("power", "power"), "run": ("hr", "heart_rate")}
    for sport, (provider_key, target_type) in expected.items():
        external_id = acceptance_external_id(target_date, sport)
        event = confirmed[external_id]
        if not provider_event_is_executable(event):
            raise RuntimeError("provider response has no parsed workout steps")
        workout_doc = event.get("workout_doc")
        steps = list(workout_doc.get("steps") or [])
        if len(steps) != 7:
            raise RuntimeError("provider parsed an unexpected workout step count")
        if not _contains_key(steps, provider_key):
            raise RuntimeError(
                f"provider did not parse expected {sport} target type; "
                f"sanitized key paths={sorted(_key_paths(steps))}"
            )
        counts[sport] = len(steps)
        target_types[sport] = target_type
    return counts, target_types


def run_live_acceptance(
    client: Any,
    *,
    target_date: date,
    confirmation: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Upsert both probes twice, verify parsing, and delete only those probes."""
    if confirmation != LIVE_ACCEPTANCE_CONFIRMATION:
        raise ValueError("exact live-write confirmation is required")
    current = today or date.today()
    if target_date <= current:
        raise ValueError("acceptance target must be a future date")
    if target_date > current + timedelta(days=30):
        raise ValueError("acceptance target must be within 30 days")
    if not client.is_configured():
        raise ValueError("Intervals.icu client is not configured")

    payloads = _probe_payloads(target_date)
    acceptance_ids = {str(row["external_id"]) for row in payloads}
    before = client.list_workout_events(target_date, target_date)
    if any(
        str(row.get("external_id") or "") in acceptance_ids
        for row in before
    ):
        raise RuntimeError(
            "residual acceptance event exists; inspect it before any new mutation"
        )
    foreign_before = _foreign_snapshot(before, acceptance_ids)
    mutated = False
    report: dict[str, Any] = {
        "status": "pending",
        "target_date": target_date.isoformat(),
        "provider_event_ids": {},
        "same_provider_ids": False,
        "parsed_step_counts": {},
        "target_types": {},
        "foreign_unchanged": False,
        "cleanup_deleted": 0,
    }

    try:
        mutated = True
        first = _confirmed_map(
            client.upsert_events_by_external_id(payloads),
            acceptance_ids,
        )
        second = _confirmed_map(
            client.upsert_events_by_external_id(payloads),
            acceptance_ids,
        )
        first_ids = {key: row["id"] for key, row in first.items()}
        second_ids = {key: row["id"] for key, row in second.items()}
        if first_ids != second_ids:
            raise RuntimeError("repeated upsert changed provider event identities")
        parsed_counts, target_types = _parsed_evidence(second, target_date)

        after = client.list_workout_events(target_date, target_date)
        listed = _confirmed_map(after, acceptance_ids)
        if {key: row["id"] for key, row in listed.items()} != second_ids:
            raise RuntimeError("bounded provider read returned different event identities")
        foreign_unchanged = _foreign_snapshot(after, acceptance_ids) == foreign_before
        if not foreign_unchanged:
            raise RuntimeError("foreign provider events changed during acceptance")

        report.update(
            status="success",
            provider_event_ids={
                sport: second[acceptance_external_id(target_date, sport)]["id"]
                for sport in ("bike", "run")
            },
            same_provider_ids=True,
            parsed_step_counts=parsed_counts,
            target_types=target_types,
            foreign_unchanged=True,
        )
        return report
    finally:
        if mutated:
            current_rows = client.list_workout_events(target_date, target_date)
            exact = [
                row
                for row in current_rows
                if str(row.get("external_id") or "") in acceptance_ids
                and row.get("id") is not None
            ]
            cleanup_payload = [
                {"id": row["id"], "external_id": row["external_id"]}
                for row in exact
            ]
            deleted = client.delete_events(cleanup_payload) if cleanup_payload else 0
            report["cleanup_deleted"] = int(deleted or 0)
            remaining = client.list_workout_events(target_date, target_date)
            if any(
                str(row.get("external_id") or "") in acceptance_ids
                for row in remaining
            ):
                raise RuntimeError("acceptance cleanup did not remove both probes")
            if _foreign_snapshot(remaining, acceptance_ids) != foreign_before:
                raise RuntimeError("foreign provider events changed during cleanup")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--confirm-live-write",
        required=True,
        help=f"must equal: {LIVE_ACCEPTANCE_CONFIRMATION}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    from services.intervals_icu import get_client

    args = _parse_args(argv)
    report = run_live_acceptance(
        get_client(),
        target_date=args.date,
        confirmation=args.confirm_live_write,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
