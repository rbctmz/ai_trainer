"""A read-only comparison through the card and the retained delivery binding."""

from contextlib import closing
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_database
from api.routers.activities import router
from data.swim_program_store import confirm_preview, create_preview
from models.activity_intervals import normalize_garmin_splits_payload, normalize_intervals_payload
from models.swim_series_fact import swim_observations
from services.swim_delivery import confirm_swim_delivery
from tests.smoke._swim_program_fixtures import changed_program
from tests.smoke.test_swim_delivery_calendar import _preview_delivery
from tests.smoke.test_swim_delivery_calendar import assignment as assignment
from tests.swim_delivery_fixtures import IntervalsSandbox


def _cached_activity(db, assigned, paired):
    db.save_activities([{
        "activity_id": "actual-swim",
        "date": assigned["date"],
        "sport": "lap_swimming",
        "duration_minutes": 25,
        "distance_km": 0.5,
        "tss": 22,
    }])
    cached = normalize_intervals_payload({
        "paired_event_id": paired,
        "icu_intervals": [{"distance": 500, "moving_time": 600, "elapsed_time": 650}],
    })
    cached["garmin_laps"] = normalize_garmin_splits_payload({
        "lapDTOs": [{"distance": 500, "duration": 700}],
    })["intervals"]
    db.save_activity_intervals("actual-swim", cached)
    return cached


def _card(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    with TestClient(app) as client:
        response = client.get("/api/activities/actual-swim")
    assert response.status_code == 200
    return response.json()["activity"]


def test_card_uses_exact_delivered_version_and_reports_fallback(assignment):
    db, assigned, checkpoint_id = assignment
    preview = _preview_delivery(assignment)
    delivery = confirm_swim_delivery(db, preview["preview_id"], client=IntervalsSandbox())
    assert delivery["status"] == "provider_verified"
    cached = _cached_activity(db, assigned, delivery["provider_event_id"])
    version = changed_program()
    version["workouts"][0]["steps"][0]["distance_meters"] = 600
    confirm_preview(db, create_preview(db, version, base_revision=1)["preview_id"])

    card = _card(db)
    fact = card["swim_series_fact"]
    assert (fact["assignment_id"], fact["program_revision"]) == (assigned["assignment_id"], 1)
    assert fact["source"] == "intervals" and fact["used_fallback"] is True
    assert fact["matched_swims"] == 1 < fact["planned_swims"]
    first = fact["steps"][0]
    assert first["planned_distance_meters"] == 500
    assert first["pace_seconds_per_100m"] == 120
    assert (first["active_seconds"], first["rest_seconds"], first["elapsed_seconds"]) == (600, None, 650)
    assert first["observation_indices"] == [0]
    assert card["tss"] == 22
    assert db.get_activity_intervals("actual-swim") == cached
    assert db.get_current_planning_checkpoint()["id"] == checkpoint_id


def test_card_requires_unique_verified_pairing(assignment):
    db, assigned, _ = assignment
    _cached_activity(db, assigned, 101)
    assert _card(db)["swim_series_fact"] is None
    preview = _preview_delivery(assignment)
    confirm_swim_delivery(db, preview["preview_id"], client=IntervalsSandbox())
    assert _card(db)["swim_series_fact"] is not None

    with closing(db._connect()) as conn:
        conn.execute("""
            INSERT INTO swim_delivery_previews
            (preview_id, assignment_id, expires_at, binding_json, binding_fingerprint, attempted, receipt_json)
            SELECT ?, ?, expires_at, binding_json, binding_fingerprint, 1, receipt_json
            FROM swim_delivery_previews WHERE preview_id=?
        """, (str(uuid4()), str(uuid4()), preview["preview_id"]))
        conn.commit()
    assert _card(db)["swim_series_fact"] is None


def test_garmin_clocks_do_not_reuse_generic_duration_or_subtract_elapsed():
    cache = normalize_garmin_splits_payload({"lapDTOs": [
        {"distance": 25, "duration": 31},
        {"distance": 25, "movingDuration": 30, "elapsedDuration": 35},
        {"distance": 0, "movingDuration": 0, "elapsedDuration": 50},
        {"distance": 0, "duration": 60},
    ]})
    rows = swim_observations(cache["intervals"], source="garmin")
    assert [(row.active_seconds, row.rest_seconds, row.elapsed_seconds) for row in rows] == [
        (None, None, None),
        (30, None, 35),
        (0, 50, 50),
        (None, None, None),
    ]
