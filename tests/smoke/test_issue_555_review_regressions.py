"""Review regressions exercise the actual prompt boundary, not only raw getters."""
from datetime import date, datetime, timezone

import pytest

from data.database import Database
from models.ai_tools import AITools
from models.coach_tool_presenter import format_tool_result
from services.wellness_ingest import normalize_intervals_wellness


def seed(db, day, fatigue=3):
    db.sync_wellness_batch([
        normalize_intervals_wellness({'id': day, 'fatigue': fatigue, 'sleepQuality': 4}).as_payload()
    ], provider='intervals', cursor_value=day, received_at=f'{day}T06:00:00Z')


class UTCHostClock(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = datetime(2026, 9, 9, 22, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


def test_snapshot_uses_one_date_on_utc_host(tmp_path, monkeypatch):
    from services import readiness_snapshot, subjective_wellness
    from config.settings import Settings
    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'Europe/Moscow')
    monkeypatch.setattr(readiness_snapshot, 'datetime', UTCHostClock)
    monkeypatch.setattr(subjective_wellness, 'datetime', UTCHostClock)
    db = Database(str(tmp_path / 'clock.db'))
    seed(db, '2026-09-09', 1)
    seed(db, '2026-09-10', 4)
    result = readiness_snapshot.build_readiness_snapshot(db)
    assert result['subjective_wellness']['date'] == result['as_of_date'] == '2026-09-09'


def test_today_historical_anchor_reaches_observations(tmp_path):
    from api.today_snapshot import build_today_decision_snapshot
    db = Database(str(tmp_path / 'history.db'))
    seed(db, '2026-09-08', 1)
    seed(db, '2026-09-09', 4)
    result = build_today_decision_snapshot(db, today=date(2026, 9, 8))
    assert result['date'] == result['subjective_wellness']['date'] == '2026-09-08'
    assert result['subjective_wellness']['status'] == 'current'


@pytest.mark.parametrize('measured', ['present', 'missing', 'error'])
def test_observations_reach_native_messages_and_synthesis(tmp_path, monkeypatch, measured):
    from models.ai_coach_runtime import run_native_tool_loop, build_chat_synthesis_prompt
    from tests.smoke.test_readiness_snapshot_contract import _seed_full_readiness

    db = Database(str(tmp_path / 'prompt.db'))
    day = date.today().isoformat()
    seed(db, day)
    if measured == 'present':
        _seed_full_readiness(db, day)
    if measured == 'error':
        def fail(*args):
            raise RuntimeError('synthetic measured-table failure')
        monkeypatch.setattr(db, 'get_sleep_data', fail)

    class Provider:
        received = ''
        def generate_with_tools(self, messages, schemas, **kwargs):
            for item in messages:
                if item['role'] == 'tool':
                    self.received = item['content']
                    return {'text': 'done', 'tool_calls': []}
            return {'text': '', 'tool_calls': [
                {'id': 'one', 'name': 'get_readiness_today', 'arguments': {}}
            ]}

    provider = Provider()
    _, results = run_native_tool_loop(provider, AITools(db), 'Самочувствие?', [], format_tool_result)
    synthesis = build_chat_synthesis_prompt([], 'Самочувствие?', results)
    for text in (provider.received, synthesis):
        assert 'sleepQuality' in text
        assert 'Плохое' in text
        assert day in text
        assert 'answered_current_keys' in text
        assert 'present' in text
        assert 'received_at' in text
    if measured == 'error':
        assert 'unavailable' in provider.received
        assert 'synthetic measured-table failure' in provider.received


def test_tool_uses_its_computed_for_date_on_utc_host(tmp_path, monkeypatch):
    from models import ai_tools
    from services import subjective_wellness
    class UTCHostDate(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 9)
    monkeypatch.setattr(ai_tools, 'date', UTCHostDate)
    monkeypatch.setattr(subjective_wellness, 'datetime', UTCHostClock)
    db = Database(str(tmp_path / 'tool-clock.db'))
    seed(db, '2026-09-09', 1)
    seed(db, '2026-09-10', 4)
    result = AITools(db).get_readiness_today()
    assert result['computed_for'] == result['subjective_wellness']['date'] == '2026-09-09'


def test_readiness_message_does_not_hide_observations(tmp_path):
    from services.subjective_wellness import build_subjective_wellness
    db = Database(str(tmp_path / 'message.db'))
    seed(db, '2026-09-09')
    block = build_subjective_wellness(db, as_of=date(2026, 9, 9))
    text = format_tool_result('get_readiness_today', {
        'computed_for': '2026-09-09', 'message': 'Недостаточно данных готовности',
        'subjective_wellness': block,
    })
    assert 'Недостаточно данных готовности' in text
    assert 'sleepQuality' in text and 'Плохое' in text
