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
    """Both surfaces share one *athlete-local* date (issue #557 anchor review).

    The pinned instant is 2026-09-09T22:00Z, already 2026-09-10 in the
    athlete's Moscow calendar: the anchor must follow the athlete, so
    readiness and subjective wellness agree on 09-10, not on the UTC date.
    """
    from services import readiness_snapshot, subjective_wellness
    from config.settings import Settings
    from utils import athlete_time
    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'Europe/Moscow')
    monkeypatch.setattr(athlete_time, 'datetime', UTCHostClock)
    monkeypatch.setattr(readiness_snapshot, 'datetime', UTCHostClock)
    monkeypatch.setattr(subjective_wellness, 'datetime', UTCHostClock)
    db = Database(str(tmp_path / 'clock.db'))
    seed(db, '2026-09-09', 1)
    seed(db, '2026-09-10', 4)
    result = readiness_snapshot.build_readiness_snapshot(db)
    assert result['subjective_wellness']['date'] == result['as_of_date'] == '2026-09-10'


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


class PinnedAthleteInstant(datetime):
    """2026-09-13T22:00Z — already 2026-09-14 on the athlete's Moscow calendar."""

    @classmethod
    def now(cls, tz=None):
        instant = datetime(2026, 9, 13, 22, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


class HostDay(date):
    """Host process calendar pinned one day behind the athlete."""

    @classmethod
    def today(cls):
        return date(2026, 9, 13)


class PinnedLosAngelesInstant(datetime):
    """2026-09-14T02:00Z — still 2026-09-13 for the athlete in Los Angeles."""

    @classmethod
    def now(cls, tz=None):
        instant = datetime(2026, 9, 14, 2, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


def test_tool_anchor_matches_canonical_snapshot_on_athlete_day(tmp_path, monkeypatch):
    """The host says 09-13 while the athlete is already on 09-14 (#577).

    Both the canonical readiness snapshot and the coach tool must follow the
    athlete calendar, so ``computed_for`` is the same 09-14 date the rest of
    the product exposes.
    """
    from config.settings import Settings
    from services import readiness_snapshot, subjective_wellness
    from utils import athlete_time
    from models import ai_tools

    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'Europe/Moscow')
    monkeypatch.setattr(athlete_time, 'datetime', PinnedAthleteInstant)
    monkeypatch.setattr(ai_tools, 'date', HostDay)

    db = Database(str(tmp_path / 'athlete-anchor.db'))
    seed(db, '2026-09-13', 1)
    seed(db, '2026-09-14', 4)

    canonical = readiness_snapshot.build_readiness_snapshot(db)

    reader_dates = []
    original_reader = subjective_wellness.build_subjective_wellness

    def capture_reader(db, *, as_of=None):
        reader_dates.append(as_of)
        return original_reader(db, as_of=as_of)

    monkeypatch.setattr(subjective_wellness, 'build_subjective_wellness', capture_reader)

    result = AITools(db).get_readiness_today()

    assert canonical['as_of_date'] == '2026-09-14'
    assert result['computed_for'] == canonical['as_of_date']
    assert result['subjective_wellness']['date'] == result['computed_for']
    # Issue #555 one-date rule: the observation reader gets computed_for's date.
    assert reader_dates[-1].isoformat() == result['computed_for']


def test_constraint_relative_dates_use_athlete_calendar(monkeypatch):
    """«сегодня»/«завтра» resolve on the athlete calendar, not the host clock."""
    from config.settings import Settings
    from models import ai_tools
    from models.ai_tools import _normalize_constraint_date
    from utils import athlete_time

    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'Europe/Moscow')
    monkeypatch.setattr(athlete_time, 'datetime', PinnedAthleteInstant)
    monkeypatch.setattr(ai_tools, 'datetime', PinnedAthleteInstant)

    assert _normalize_constraint_date('сегодня') == '2026-09-14'
    assert _normalize_constraint_date('завтра') == '2026-09-15'
    assert _normalize_constraint_date('today') == '2026-09-14'
    assert _normalize_constraint_date('tomorrow') == '2026-09-15'


def test_absolute_constraint_date_does_not_require_athlete_timezone(monkeypatch):
    """An explicit ISO date has no timezone dependency (#577 review round 1)."""
    from config.settings import Settings
    from models.ai_tools import _normalize_constraint_date

    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'not/a-zone')

    assert _normalize_constraint_date('2026-10-01') == '2026-10-01'


def test_tool_excludes_readiness_rows_after_athlete_day(tmp_path, monkeypatch):
    """Tomorrow's measurements must not enter today's Coach snapshot."""
    from config.settings import Settings
    from services import readiness_snapshot
    from tests.smoke.test_readiness_snapshot_contract import _seed_full_readiness
    from utils import athlete_time

    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'America/Los_Angeles')
    monkeypatch.setattr(athlete_time, 'datetime', PinnedLosAngelesInstant)

    db = Database(str(tmp_path / 'future-readiness.db'))
    _seed_full_readiness(db, '2026-09-14')

    canonical = readiness_snapshot.build_readiness_snapshot(db)
    result = AITools(db).get_readiness_today()

    assert canonical['as_of_date'] == result['computed_for'] == '2026-09-13'
    assert canonical['score'] is None
    assert result['readiness']['score'] is None
    assert result['readiness']['as_of_date'] is None


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
