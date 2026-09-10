"""Provider self-reports: synthetic lifecycle and public route, never live data."""
from datetime import date, datetime, timezone

from data.database import Database
from services.wellness_ingest import sync_intervals_wellness
from tests.smoke.test_m4_intervals_wellness import FakeIntervalsClient


def test_subjective_only_route_and_clear(tmp_path):
    from services.subjective_wellness import build_subjective_wellness

    db = Database(str(tmp_path / 'test.db'))
    client = FakeIntervalsClient(wellness=[{'id': '2026-09-09', 'sleepQuality': 4, 'fatigue': 1}])
    sync_intervals_wellness(db, client, now=datetime(2026, 9, 9), window_days=1)
    result = build_subjective_wellness(db, as_of=date(2026, 9, 9))
    assert result['status'] == 'current'
    values = {v['key']: v for v in result['items']}
    assert values['sleepQuality']['value'] == 4
    assert values['fatigue']['value'] == 1
    assert values['stress']['state'] == 'missing'
    client._wellness[0]['fatigue'] = None
    sync_intervals_wellness(db, client, now=datetime(2026, 9, 9), window_days=1)
    result = build_subjective_wellness(db, as_of=date(2026, 9, 9))
    assert next(v for v in result['items'] if v['key'] == 'fatigue')['state'] == 'missing'


def test_scales_and_invalid_values():
    from models.subjective_wellness import SCALES, normalize_subjective
    for key in SCALES:
        for value in (1, 2, 3, 4):
            assert normalize_subjective({key: value})['fields'][key] == {
                'state': 'present', 'value': value,
            }
        for value in (0, -1, 5, True, '2', 2.0, {}, float('nan')):
            assert normalize_subjective({key: value})['fields'][key] == {
                'state': 'invalid', 'value': None,
            }
    assert normalize_subjective({'updated': '2026-09-09T10:00:00'})['provider_updated_at'] is None


def test_retry_order_reset_and_restart(tmp_path):
    import sqlite3
    from services.wellness_ingest import normalize_intervals_wellness
    from services.subjective_wellness import build_subjective_wellness

    path = str(tmp_path / 'life.db')
    db = Database(path)
    def save(value, stamp, updated='2026-09-09T07:00:00Z'):
        payload = normalize_intervals_wellness({
            'id': '2026-09-09', 'fatigue': value, 'updated': updated,
        }).as_payload()
        return db.sync_wellness_batch([payload], provider='intervals',
            cursor_value='2026-09-09', received_at=stamp)
    assert save(2, '2026-09-09T08:00:00Z')['subjective_new'] == 1
    assert save(2, '2026-09-09T08:01:00Z')['subjective_updated'] == 0
    save(4, '2026-09-09T07:59:00Z')  # delayed transport response
    save(4, '2026-09-09T08:02:00Z', '2026-09-09T06:00:00Z')  # old upstream revision
    db = Database(path)
    assert db.get_subjective_wellness('2026-09-09')['observation']['fields']['fatigue']['value'] == 2
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM subjective_wellness').fetchone()[0] == 1
    stale = build_subjective_wellness(db, as_of=date(2026, 9, 10))
    assert stale['status'] == 'stale'
    assert stale['answered_current_keys'] == []
    assert build_subjective_wellness(db, as_of=date(2026, 9, 8))['status'] == 'missing'
    db.clear_all_data()
    assert db.get_subjective_wellness('2026-09-10') is None
    assert db.get_sync_cursor('intervals', 'wellness') is None


def test_readiness_and_coach_route_do_not_change_metrics(tmp_path):
    from services.readiness_snapshot import build_readiness_snapshot
    from models.ai_tools import AITools
    from tests.smoke.test_readiness_snapshot_contract import _seed_full_readiness

    db = Database(str(tmp_path / 'route.db'))
    _seed_full_readiness(db, '2026-09-09')
    before = build_readiness_snapshot(db, as_of=date(2026, 9, 9),
                                     observed_at_utc=datetime(2026, 9, 9, tzinfo=timezone.utc))
    client = FakeIntervalsClient(wellness=[{'id': '2026-09-09', 'sleepQuality': 4, 'stress': 4}])
    sync_intervals_wellness(db, client, now=datetime(2026, 9, 9), window_days=1)
    after = build_readiness_snapshot(db, as_of=date(2026, 9, 9),
                                    observed_at_utc=datetime(2026, 9, 9, tzinfo=timezone.utc))
    assert after.pop('subjective_wellness')['status'] == 'current'
    before.pop('subjective_wellness')
    assert before == after
    assert db.get_sleep_data(36500).iloc[0]['sleep_score'] == 82
    assert db.get_hrv_data(36500).iloc[0]['stress_score'] == 20
    tool = object.__new__(AITools)
    tool.db = db
    assert 'subjective_wellness' in tool.get_readiness_today()


def test_partial_invalid_clear_and_atomic_failure(tmp_path):
    import sqlite3
    import pytest
    from services.subjective_wellness import build_subjective_wellness
    db = Database(str(tmp_path / 'atomic.db'))
    client = FakeIntervalsClient(wellness=[{'id': '2026-09-09', 'fatigue': 2, 'stress': 99}])
    sync_intervals_wellness(db, client, now=datetime(2026, 9, 9), window_days=1)
    result = build_subjective_wellness(db, as_of=date(2026, 9, 9))
    assert next(i for i in result['items'] if i['key'] == 'stress')['state'] == 'invalid'
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("CREATE TRIGGER reject_subjective BEFORE INSERT ON subjective_wellness "
                     "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    client._wellness[0] = {'id': '2026-09-10', 'fatigue': 1, 'hrv': 45}
    with pytest.raises(sqlite3.IntegrityError):
        sync_intervals_wellness(db, client, now=datetime(2026, 9, 10), window_days=1)
    assert db.get_sync_cursor('intervals', 'wellness') == '2026-09-09'
    assert db.get_hrv_data(36500).empty


def test_api_and_tool_agree_on_subjective_only_day(tmp_path):
    from fastapi.testclient import TestClient
    from api.main import app
    from api.deps import get_database
    from models.ai_tools import AITools
    from services.subjective_wellness import build_subjective_wellness

    db = Database(str(tmp_path / 'api.db'))
    day = date.today()
    client = FakeIntervalsClient(wellness=[{
        'id': day.isoformat(), 'sleepQuality': 4, 'soreness': 1, 'fatigue': 2,
        'stress': 3, 'mood': 2, 'motivation': 3, 'injury': 1, 'hydration': 2,
    }])
    sync_intervals_wellness(db, client, now=datetime.combine(day, datetime.min.time()), window_days=1)
    expected = build_subjective_wellness(db, as_of=day)
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_database] = lambda: db
    try:
        with TestClient(app) as http:
            dashboard = http.get('/api/dashboard/summary')
            today = http.get('/api/today')
        assert dashboard.status_code == today.status_code == 200
        assert dashboard.json()['readiness_snapshot']['subjective_wellness'] == expected
        assert today.json()['subjective_wellness'] == expected
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
    tool = object.__new__(AITools)
    tool.db = db
    assert tool.get_readiness_today()['subjective_wellness'] == expected
    assert len(expected['answered_current_keys']) == 8
    assert expected['provider_updated_at'] is None


def test_missing_today_does_not_resurrect_yesterday_and_local_date(tmp_path, monkeypatch):
    from services.subjective_wellness import build_subjective_wellness
    from services.wellness_ingest import normalize_intervals_wellness
    from config.settings import Settings
    db = Database(str(tmp_path / 'dates.db'))
    for day, values in [('2026-09-08', {'fatigue': 1}), ('2026-09-09', {})]:
        db.sync_wellness_batch([normalize_intervals_wellness({'id': day, **values}).as_payload()],
            provider='intervals', cursor_value=day, received_at='2026-09-09T21:30:00Z')
    # UTC retrieval is already next local day; provider id is never shifted.
    assert db.get_subjective_wellness('2026-09-09')['date'] == '2026-09-09'
    assert build_subjective_wellness(db, as_of=date(2026, 9, 9))['status'] == 'missing'
    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'not/a-zone')
    assert build_subjective_wellness(db)['status'] == 'unavailable'


def test_old_rating_stays_old_after_new_activity(tmp_path):
    from services.readiness_snapshot import build_readiness_snapshot
    from tests.smoke.test_readiness_snapshot_contract import _seed_activity
    db = Database(str(tmp_path / 'old.db'))
    client = FakeIntervalsClient(wellness=[{'id': '2026-09-08', 'fatigue': 1}])
    sync_intervals_wellness(db, client, now=datetime(2026, 9, 8), window_days=1)
    _seed_activity(db, '2026-09-09')
    result = build_readiness_snapshot(db, as_of=date(2026, 9, 9))['subjective_wellness']
    assert result['status'] == 'stale'
    assert result['date'] == '2026-09-08'
    assert result['age_days'] == 1
