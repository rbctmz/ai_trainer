"""Explicit manual identity, replay and rollback acceptance (#720)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from data.database import Database
from services.activity_ingest import ingest_provider_activity, normalize_provider_activity
from services.activity_manual_links import manage_manual_link


def seed(path):
    db = Database(str(path))
    original = {"id": "i_original", "source": "UPLOAD", "external_id": None,
                "start_date": "2026-01-01T10:00:00Z", "start_date_local": "2026-01-01T13:00:00",
                "type": "Ride", "name": "Original", "elapsed_time": 4500,
                "distance": 31400, "tss": 41.4, "tss_method": "power_tss_bike"}
    garmin = {"activity_id": "123456", "date": "2026-01-01", "sport": "virtual_ride",
              "started_at_utc": "2026-01-01T10:00:00Z", "duration_minutes": 75,
              "distance_km": 31.4, "tss": 41.4, "tss_method": "power_tss_bike",
              "activity_name": "Garmin copy"}
    for source, row in [("intervals", original), ("garmin", garmin)]:
        ingest_provider_activity(db, normalize_provider_activity(row, source), primary_source="intervals")
    return db, original, garmin


def preview(path, **kwargs):
    return manage_manual_link(path, "i_original", "123456", **kwargs)


def apply(path, **kwargs):
    p = preview(path, unlink=kwargs.get("unlink", False))
    return preview(path, apply=True, expected_token=p["token"],
                   reason="Owner confirmed same FIT", confirm_stopped=True, **kwargs)


def state(path):
    with sqlite3.connect(path) as c:
        return list(c.iterdump())


def test_preview_does_not_initialize_old_schema_or_mutate(tmp_path):
    path = tmp_path / "db.sqlite"
    seed(path)
    with sqlite3.connect(path) as c:
        c.execute("DROP TABLE IF EXISTS activity_manual_links")
    before = state(path)
    p = preview(path)
    assert p["allowed"] and not p["linked"]
    assert p["before"]["count"] == 2 and p["after"]["count"] == 1
    assert p["after"]["tss"] == 41.4
    assert state(path) == before


@pytest.mark.parametrize("order", [("intervals", "garmin"), ("garmin", "intervals")])
@pytest.mark.parametrize("primary", ["intervals", "garmin"])
def test_apply_restart_and_replay_preserve_original_and_payloads(tmp_path, order, primary):
    path = tmp_path / "db.sqlite"
    db, original, garmin = seed(path)
    assert apply(path)["linked"]
    db = Database(str(path))
    for source in order:
        row = original if source == "intervals" else garmin
        ingest_provider_activity(db, normalize_provider_activity(row, source), primary_source=primary)
    assert db.get_activity("123456") is None
    assert db.get_activity("intervals_i_original")["activity_name"] == "Original"
    assert db.get_intervals_provider_activity_id("intervals_i_original") == "i_original"
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM activity_provider_links WHERE provider_payload IS NOT NULL").fetchone()[0] == 2
    assert apply(path)["linked"]


def test_stale_preview_and_missing_confirmation_leave_state_unchanged(tmp_path):
    path = tmp_path / "db.sqlite"
    seed(path)
    token = preview(path)["token"]
    with sqlite3.connect(path) as c:
        c.execute("UPDATE activities SET tss=42 WHERE activity_id='123456'")
    before = state(path)
    with pytest.raises(ValueError, match="stale"):
        preview(path, apply=True, expected_token=token, reason="same FIT", confirm_stopped=True)
    assert state(path) == before
    with pytest.raises(ValueError, match="confirm"):
        preview(path, apply=True, expected_token=preview(path)["token"], reason="same FIT")
    assert state(path) == before


def test_authored_references_block_but_target_notes_survive(tmp_path):
    path = tmp_path / "db.sqlite"
    db, _, _ = seed(path)
    db.add_activity_tag("123456", "keep")
    before = state(path)
    assert not preview(path)["allowed"]
    with pytest.raises(ValueError, match="block"):
        apply(path)
    assert state(path) == before
    db.remove_activity_tag("123456", "keep")
    db.save_activity_coach_notes("intervals_i_original", "Preserve original note")
    apply(path)
    assert db.get_activity_coach_notes("intervals_i_original") == "Preserve original note"


def test_returned_intervals_copy_uses_selected_original_and_rejects_second_claimant(tmp_path):
    path = tmp_path / "db.sqlite"
    db, original, _ = seed(path)
    apply(path)
    returned = {**original, "id": "i_returned", "source": "GARMIN_CONNECT",
                "external_id": "123456", "name": "Returned copy", "tss": 88}
    ingest_provider_activity(db, normalize_provider_activity(returned, "intervals"), primary_source="garmin")
    assert db.get_activity("intervals_i_original")["tss"] == 41.4
    assert db.get_intervals_provider_activity_id("intervals_i_original") == "i_original"
    before = state(path)
    with pytest.raises(ValueError, match="ambiguous"):
        ingest_provider_activity(db, normalize_provider_activity({**returned, "id": "i_extra"}, "intervals"))
    assert state(path) == before


def test_unlink_restores_current_payloads_and_reset_clears_decision(tmp_path):
    path = tmp_path / "db.sqlite"
    db, _, garmin = seed(path)
    apply(path)
    ingest_provider_activity(db, normalize_provider_activity({**garmin, "tss": 45}, "garmin"))
    assert not apply(path, unlink=True)["linked"]
    assert db.get_activity("123456")["tss"] == 45
    assert db.get_activity("intervals_i_original")["tss"] == 41.4
    assert not apply(path, unlink=True)["linked"]
    apply(path)
    db.clear_all_data()
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT COUNT(*) FROM activity_manual_links").fetchone()[0] == 0


def test_json_ledger_reference_blocks(tmp_path):
    path = tmp_path / "db.sqlite"
    seed(path)
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE example_ledger (snapshot_json TEXT)")
        c.execute("INSERT INTO example_ledger VALUES (?)", (json.dumps({"actual_activity_ids": ["123456"]}),))
    assert not preview(path)["allowed"]


@pytest.mark.parametrize("change", [
    {"sport": "running"}, {"duration_minutes": 80},
    {"started_at_utc": "2026-01-01T10:00:01Z"},
    {"started_at_utc": None}, {"duration_minutes": float("inf")},
])
def test_incompatible_pair_refuses_without_writes(tmp_path, change):
    path = tmp_path / "db.sqlite"
    db, _, garmin = seed(path)
    ingest_provider_activity(db, normalize_provider_activity({**garmin, **change}, "garmin"))
    before = state(path)
    assert not preview(path)["allowed"]
    with pytest.raises(ValueError, match="incompatible"):
        apply(path)
    assert state(path) == before


def test_failure_mid_projection_rolls_back_decision_and_cache_cleanup(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite"
    seed(path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO activity_intervals(activity_id,intervals_json) VALUES ('123456','[]')")
    before = state(path)
    original_project = Database._project_canonical
    calls = []
    def fail_second(self, cursor, cid, primary):
        original_project(self, cursor, cid, primary)
        calls.append(cid)
        if len(calls) == 2:
            raise RuntimeError("injected projection failure")
    monkeypatch.setattr(Database, "_project_canonical", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        apply(path)
    assert state(path) == before


def test_losing_caches_are_cleared_and_survivor_is_preserved(tmp_path):
    path = tmp_path / "db.sqlite"
    db, _, _ = seed(path)
    with sqlite3.connect(path) as c:
        for cid in ['123456', 'intervals_i_original']:
            c.execute("INSERT INTO activity_intervals(activity_id,intervals_json) VALUES (?, '[]')", (cid,))
            c.execute("INSERT INTO activity_power_curves(activity_id,curve_json) VALUES (?, '{}')", (cid,))
            c.execute("INSERT INTO bike_hr_quality_pairs(activity_id,date) VALUES (?, '2026-01-01')", (cid,))
    assert preview(path)["allowed"]
    apply(path)
    with sqlite3.connect(path) as c:
        for table in ['activity_intervals', 'activity_power_curves', 'bike_hr_quality_pairs']:
            assert c.execute(f'SELECT activity_id FROM {table}').fetchall() == [('intervals_i_original',)]
    assert len(db.get_bike_hr_pairs()) == 1


def test_unlink_preview_matches_returned_copy_projection(tmp_path, monkeypatch):
    from config.settings import Settings
    monkeypatch.setattr(Settings, "PRIMARY_ACTIVITY_SOURCE", "intervals")
    path = tmp_path / "db.sqlite"
    db, original, _ = seed(path)
    apply(path)
    returned = {**original, "id": "i_returned", "source": "GARMIN_CONNECT",
                "external_id": "123456", "tss": 50}
    ingest_provider_activity(db, normalize_provider_activity(returned, "intervals"))
    p = preview(path, unlink=True)
    assert p['after']['tss'] == 91.4
    result = apply(path, unlink=True)
    assert result['after'] == p['after']


def test_api_totals_count_one_activity_after_link(tmp_path):
    from api.routers.activities import list_activities
    path = tmp_path / "db.sqlite"
    db, _, _ = seed(path)
    assert list_activities(days=365, db=db)['count'] == 2
    apply(path)
    result = list_activities(days=365, db=db)
    assert result['count'] == 1
    assert result['items'][0]['activity_id'] == 'intervals_i_original'
    assert result['totals']['tss'] == 41.4


def test_cli_preview_and_apply_require_explicit_token(tmp_path, capsys):
    from scripts.link_activities import main
    path = tmp_path / 'db.sqlite'
    seed(path)
    args = ['--database', str(path), '--intervals-id', 'i_original', '--garmin-id', '123456']
    before = state(path)
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['mode'] == 'preview'
    assert state(path) == before
    assert main([*args, '--apply', '--confirm-stopped', '--reason', 'same FIT']) == 2
    assert 'token' in capsys.readouterr().err
    assert state(path) == before
    assert main([*args, '--apply', '--confirm-stopped', '--reason', 'same FIT', '--expected-token', result['token']]) == 0
    assert json.loads(capsys.readouterr().out)['after']['count'] == 1


@pytest.mark.parametrize('seconds,allowed', [(4499, True), (4501, True), (4498, False), (4502, False)])
def test_source_second_boundary_survives_minute_normalization(tmp_path, seconds, allowed):
    path = tmp_path / 'db.sqlite'
    db, original, _ = seed(path)
    ingest_provider_activity(db, normalize_provider_activity({**original, 'elapsed_time': seconds}, 'intervals'))
    assert preview(path)['allowed'] is allowed
