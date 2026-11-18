"""Fail-closed reads used at the authored workout write boundary."""

from datetime import date

import pytest

from services.intervals_icu import IntervalsICUClient, IntervalsICUError


@pytest.mark.parametrize("payload", [{}, [None], [{"name": "missing category"}]])
def test_preflight_distinguishes_bad_calendar_response_from_empty(monkeypatch, payload):
    monkeypatch.setattr(IntervalsICUClient, "_request_json", lambda *_args, **_kwargs: payload)
    client = IntervalsICUClient(api_key="")
    day = date(2026, 10, 17)
    assert client.list_workout_events(day, day) == []
    with pytest.raises(IntervalsICUError):
        client.list_workout_events(day, day, strict=True)


def test_strict_preflight_preserves_owned_identity_without_including_notes(monkeypatch):
    day = date(2026, 10, 17)

    def response(_client, method, path, **kwargs):
        assert method == "GET" and path == "/api/v1/athlete/0/events"
        assert kwargs["params"] == {"oldest": day.isoformat(), "newest": day.isoformat()}
        return [
            {"id": 13, "category": "NOTE", "name": "An unrelated note"},
            {"id": 14, "category": "WORKOUT", "external_id": "ai_trainer_swim:test", "type": "Swim"},
        ]

    monkeypatch.setattr(IntervalsICUClient, "_request_json", response)
    rows = IntervalsICUClient(api_key="").list_workout_events(day, day, strict=True)
    assert [row["id"] for row in rows] == [14]
    assert rows[0]["external_id"] == "ai_trainer_swim:test"


def test_read_back_one_created_event_by_id_with_mismatches_rejected(monkeypatch):
    provider = {"id": 14, "category": "WORKOUT", "type": "Swim", "workout_doc": {"steps": []}}

    def response(_client, method, path):
        assert method == "GET" and path == "/api/v1/athlete/0/events/14"
        return provider

    monkeypatch.setattr(IntervalsICUClient, "_request_json", response)
    client = IntervalsICUClient(api_key="")
    assert client.get_workout_event(14) == provider
    provider["id"] = 999
    with pytest.raises(IntervalsICUError):
        client.get_workout_event(14)
