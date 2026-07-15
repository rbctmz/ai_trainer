from __future__ import annotations

from datetime import date

import pytest


pytestmark = pytest.mark.smoke


class _CatalogAcceptanceClient:
    def __init__(self, *, executable: bool = True) -> None:
        self.executable = executable
        self.events: dict[str, dict] = {}
        self.upsert_calls: list[list[dict]] = []
        self.delete_calls: list[list[dict]] = []
        self.next_id = 900

    def is_configured(self) -> bool:
        return True

    def list_workout_events(self, _oldest, _newest):
        return [dict(row) for row in self.events.values()]

    def upsert_events_by_external_id(self, payloads):
        rows = [dict(row) for row in payloads]
        self.upsert_calls.append(rows)
        confirmed = []
        for row in rows:
            external_id = str(row["external_id"])
            previous = self.events.get(external_id)
            provider_id = previous["id"] if previous else self.next_id
            if previous is None:
                self.next_id += 1
            step_count = sum(
                line.startswith("- ")
                for line in str(row.get("description") or "").splitlines()
            )
            target = (
                {"power": {"start": 150, "end": 160, "units": "W"}}
                if row.get("type") == "Ride"
                else {"hr": {"start": 145, "end": 160, "units": "bpm"}}
            )
            stored = {
                **row,
                "id": provider_id,
                "uid": f"provider-{provider_id}",
                "workout_doc": (
                    {"steps": [dict(target) for _ in range(step_count)]}
                    if self.executable
                    else None
                ),
            }
            self.events[external_id] = stored
            confirmed.append(dict(stored))
        return confirmed

    def delete_events(self, payloads):
        rows = [dict(row) for row in payloads]
        self.delete_calls.append(rows)
        deleted = 0
        for candidate in rows:
            external_id = str(candidate.get("external_id") or "")
            stored = self.events.get(external_id)
            if stored and stored["id"] == candidate.get("id"):
                del self.events[external_id]
                deleted += 1
        return deleted


def test_v2_live_acceptance_upserts_two_typed_probes_and_cleans_them() -> None:
    from scripts.accept_workout_catalog_v2_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        run_live_acceptance,
    )

    client = _CatalogAcceptanceClient()
    report = run_live_acceptance(
        client,
        target_date=date(2026, 7, 30),
        today=date(2026, 7, 15),
        confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
    )

    assert report["status"] == "success"
    assert report["same_provider_ids"] is True
    assert report["parsed_step_counts"] == {"bike": 7, "run": 7}
    assert report["target_types"] == {"bike": "power", "run": "heart_rate"}
    assert report["foreign_unchanged"] is True
    assert report["cleanup_deleted"] == 2
    assert len(client.upsert_calls) == 2
    assert len(client.upsert_calls[0]) == 2
    assert all("uid" not in row for row in client.upsert_calls[0])
    assert len(client.delete_calls) == 1
    assert client.events == {}


def test_v2_live_acceptance_cleans_both_probes_when_parser_evidence_is_missing() -> None:
    from scripts.accept_workout_catalog_v2_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        run_live_acceptance,
    )

    client = _CatalogAcceptanceClient(executable=False)

    with pytest.raises(RuntimeError, match="parsed workout steps"):
        run_live_acceptance(
            client,
            target_date=date(2026, 7, 30),
            today=date(2026, 7, 15),
            confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
        )

    assert len(client.upsert_calls) == 2
    assert len(client.delete_calls) == 1
    assert len(client.delete_calls[0]) == 2
    assert client.events == {}


def test_v2_live_acceptance_refuses_residue_before_any_write() -> None:
    from scripts.accept_workout_catalog_v2_live import (
        LIVE_ACCEPTANCE_CONFIRMATION,
        acceptance_external_id,
        run_live_acceptance,
    )

    client = _CatalogAcceptanceClient()
    external_id = acceptance_external_id(date(2026, 7, 30), "bike")
    client.events[external_id] = {
        "id": 77,
        "external_id": external_id,
        "category": "WORKOUT",
        "start_date_local": "2026-07-30T20:00:00",
    }

    with pytest.raises(RuntimeError, match="residual acceptance event"):
        run_live_acceptance(
            client,
            target_date=date(2026, 7, 30),
            today=date(2026, 7, 15),
            confirmation=LIVE_ACCEPTANCE_CONFIRMATION,
        )

    assert client.upsert_calls == []
    assert client.delete_calls == []

