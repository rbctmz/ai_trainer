"""Fail-closed contracts for the explicitly authorized live delivery probe."""
from __future__ import annotations

from datetime import date

import pytest


class _AcceptanceClient:
    def __init__(self, *, events=None, executable=True):
        self.events = {
            str(row["external_id"] or row["id"]): dict(row)
            for row in (events or [])
        }
        self.executable = executable
        self.list_calls = []
        self.upsert_calls = []
        self.delete_calls = []
        self._next_id = 9000

    def is_configured(self):
        return True

    def list_workout_events(self, oldest, newest):
        self.list_calls.append((oldest, newest))
        return [dict(row) for row in self.events.values()]

    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        result = []
        for row in rows:
            external_id = str(row["external_id"])
            previous = self.events.get(external_id)
            provider_id = previous["id"] if previous else self._next_id
            if previous is None:
                self._next_id += 1
            stored = {
                **row,
                "id": provider_id,
                "uid": previous["uid"] if previous else f"provider-{provider_id}",
                "workout_doc": (
                    {"steps": [{"duration": 600}]} if self.executable else None
                ),
            }
            self.events[external_id] = stored
            result.append(dict(stored))
        return result

    def delete_events(self, payloads):
        rows = [dict(row) for row in payloads]
        self.delete_calls.append(rows)
        deleted = 0
        for candidate in rows:
            for key, event in list(self.events.items()):
                if (
                    event.get("id") == candidate.get("id")
                    and event.get("external_id") == candidate.get("external_id")
                ):
                    self.events.pop(key)
                    deleted += 1
        return deleted


def _foreign_event() -> dict:
    return {
        "id": 42,
        "uid": "interval-coach-slot",
        "external_id": None,
        "category": "WORKOUT",
        "start_date_local": "2026-07-20T08:00:00",
        "type": "Run",
        "name": "IntervalCoach workout",
        "workout_doc": {"steps": [{"duration": 1200}]},
        "moving_time": 1200,
        "oauth_client_id": 173,
        "created_by_id": "athlete",
    }


def test_live_acceptance_requires_exact_confirmation_before_provider_read() -> None:
    from scripts.accept_intervals_delivery_live import run_live_acceptance

    client = _AcceptanceClient(events=[_foreign_event()])

    with pytest.raises(ValueError, match="confirmation"):
        run_live_acceptance(
            client,
            target_date=date(2026, 7, 20),
            today=date(2026, 7, 14),
            confirmation="yes",
        )

    assert client.list_calls == []
    assert client.upsert_calls == []
    assert client.delete_calls == []


def test_live_acceptance_upserts_twice_preserves_foreign_and_cleans_exact_probe() -> None:
    from scripts.accept_intervals_delivery_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        run_live_acceptance,
    )

    foreign = _foreign_event()
    client = _AcceptanceClient(events=[foreign])

    report = run_live_acceptance(
        client,
        target_date=date(2026, 7, 20),
        today=date(2026, 7, 14),
        confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
    )

    assert report["status"] == "success"
    assert report["same_provider_id"] is True
    assert report["parsed_steps"] is True
    assert report["foreign_unchanged"] is True
    assert report["cleanup_deleted"] == 1
    assert len(client.upsert_calls) == 2
    assert "uid" not in client.upsert_calls[0][0]
    assert client.upsert_calls[0][0]["external_id"].startswith(
        "ai_trainer:acceptance:"
    )
    assert client.delete_calls == [
        [
            {
                "id": report["provider_event_id"],
                "external_id": client.upsert_calls[0][0]["external_id"],
            }
        ]
    ]
    assert list(client.events.values()) == [foreign]


def test_live_acceptance_cleans_probe_when_provider_does_not_parse_steps() -> None:
    from scripts.accept_intervals_delivery_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        run_live_acceptance,
    )

    client = _AcceptanceClient(events=[_foreign_event()], executable=False)

    with pytest.raises(RuntimeError, match="parsed workout steps"):
        run_live_acceptance(
            client,
            target_date=date(2026, 7, 20),
            today=date(2026, 7, 14),
            confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
        )

    assert len(client.upsert_calls) == 2
    assert len(client.delete_calls) == 1
    assert list(client.events.values()) == [_foreign_event()]


def test_live_acceptance_refuses_residual_probe_without_mutation() -> None:
    from scripts.accept_intervals_delivery_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        acceptance_external_id,
        run_live_acceptance,
    )

    target = date(2026, 7, 20)
    residual = {
        "id": 77,
        "uid": "provider-generated-residual",
        "external_id": acceptance_external_id(target),
        "category": "WORKOUT",
        "start_date_local": "2026-07-20T21:00:00",
    }
    client = _AcceptanceClient(events=[_foreign_event(), residual])

    with pytest.raises(RuntimeError, match="residual acceptance event"):
        run_live_acceptance(
            client,
            target_date=target,
            today=date(2026, 7, 14),
            confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
        )

    assert client.upsert_calls == []
    assert client.delete_calls == []


def test_live_acceptance_rejects_non_future_date_before_provider_read() -> None:
    from scripts.accept_intervals_delivery_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        run_live_acceptance,
    )

    client = _AcceptanceClient()

    with pytest.raises(ValueError, match="future"):
        run_live_acceptance(
            client,
            target_date=date(2026, 7, 14),
            today=date(2026, 7, 14),
            confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
        )

    assert client.list_calls == []
