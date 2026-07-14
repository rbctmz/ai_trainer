#!/usr/bin/env python3
"""Run one reversible Intervals.icu delivery acceptance probe."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.intervals_workout_delivery import provider_event_is_executable  # noqa: E402


LIVE_ACCEPTANCE_CONFIRMATION = "CREATE-VERIFY-AND-DELETE-ONE-INTERVALS-EVENT"
_ACCEPTANCE_PREFIX = "ai_trainer:acceptance:"


def acceptance_external_id(target_date: date) -> str:
    return f"{_ACCEPTANCE_PREFIX}{target_date.isoformat()}"


def _acceptance_payload(target_date: date) -> dict[str, Any]:
    name = "AI Trainer acceptance · temporary · delete me"
    return {
        "external_id": acceptance_external_id(target_date),
        "start_date_local": datetime.combine(
            target_date,
            datetime.min.time(),
        ).replace(hour=21).strftime("%Y-%m-%dT%H:%M:%S"),
        "category": "WORKOUT",
        "name": name,
        "description": "\n".join(
            [
                name,
                "- Warmup 5m 50-60%",
                "- Easy 5m 60-70%",
            ]
        ),
        "type": "Ride",
        "icu_training_load": 5,
        "moving_time": 600,
    }


def _is_exact_probe(
    event: Mapping[str, Any],
    *,
    external_id: str,
) -> bool:
    return str(event.get("external_id") or "") == external_id


def _foreign_snapshot(
    events: Sequence[Mapping[str, Any]],
    *,
    external_id: str,
) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events):
        if _is_exact_probe(event, external_id=external_id):
            continue
        key = str(event.get("id") or event.get("uid") or f"row:{index}")
        snapshot[key] = dict(event)
    return snapshot


def _one_confirmed_probe(
    rows: Sequence[Mapping[str, Any]],
    *,
    external_id: str,
) -> dict[str, Any]:
    matches = [
        dict(row)
        for row in rows
        if str(row.get("external_id") or "") == external_id
    ]
    if len(matches) != 1 or matches[0].get("id") is None:
        raise RuntimeError("provider did not confirm exactly one acceptance event")
    return matches[0]


def run_live_acceptance(
    client: Any,
    *,
    target_date: date,
    confirmation: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Upsert one probe twice, verify it, and always delete only that probe."""
    if confirmation != LIVE_ACCEPTANCE_CONFIRMATION:
        raise ValueError("exact live-write confirmation is required")
    current = today or date.today()
    if target_date <= current:
        raise ValueError("acceptance target must be a future date")
    if target_date > current + timedelta(days=30):
        raise ValueError("acceptance target must be within 30 days")
    if not client.is_configured():
        raise ValueError("Intervals.icu client is not configured")

    external_id = acceptance_external_id(target_date)
    before = client.list_workout_events(target_date, target_date)
    if any(_is_exact_probe(row, external_id=external_id) for row in before):
        raise RuntimeError(
            "residual acceptance event exists; inspect it before any new mutation"
        )
    foreign_before = _foreign_snapshot(before, external_id=external_id)
    payload = _acceptance_payload(target_date)
    mutated = False
    report: dict[str, Any] = {
        "status": "pending",
        "target_date": target_date.isoformat(),
        "provider_event_id": None,
        "same_provider_id": False,
        "parsed_steps": False,
        "foreign_unchanged": False,
        "cleanup_deleted": 0,
    }

    try:
        mutated = True
        first = _one_confirmed_probe(
            client.upsert_events_by_external_id([payload]),
            external_id=external_id,
        )
        second = _one_confirmed_probe(
            client.upsert_events_by_external_id([payload]),
            external_id=external_id,
        )
        same_provider_id = first["id"] == second["id"]
        if not same_provider_id:
            raise RuntimeError("repeated upsert created a different provider event id")
        if not provider_event_is_executable(second):
            raise RuntimeError("provider response has no parsed workout steps")

        after = client.list_workout_events(target_date, target_date)
        listed = _one_confirmed_probe(
            after,
            external_id=external_id,
        )
        if listed["id"] != second["id"]:
            raise RuntimeError("bounded provider read returned a different event id")
        foreign_unchanged = (
            _foreign_snapshot(after, external_id=external_id)
            == foreign_before
        )
        if not foreign_unchanged:
            raise RuntimeError("foreign provider events changed during acceptance")

        report.update(
            status="success",
            provider_event_id=second["id"],
            same_provider_id=True,
            parsed_steps=True,
            foreign_unchanged=True,
        )
        return report
    finally:
        if mutated:
            current_rows = client.list_workout_events(target_date, target_date)
            exact = [
                row
                for row in current_rows
                if str(row.get("external_id") or "") == external_id
                and row.get("id") is not None
            ]
            cleanup_payload = [
                {"id": row["id"], "external_id": external_id}
                for row in exact
            ]
            deleted = client.delete_events(cleanup_payload) if cleanup_payload else 0
            report["cleanup_deleted"] = int(deleted or 0)
            remaining = client.list_workout_events(target_date, target_date)
            if any(
                _is_exact_probe(row, external_id=external_id)
                for row in remaining
            ):
                raise RuntimeError("acceptance cleanup did not remove the probe")
            if (
                _foreign_snapshot(remaining, external_id=external_id)
                != foreign_before
            ):
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
