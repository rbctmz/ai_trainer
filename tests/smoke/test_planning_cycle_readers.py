"""Current selection is distinct from explicit historical facts (S2 M4)."""
from datetime import date

import pytest

from api import planning_service as ps
from models.ai_tools import AITools
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from services.planning_cycles import current_cycle_context
from services.session_projection import session_projection_at
from services.intervals_plan_delivery import deliver_active_plan
from tests.smoke._planning_cycle_regressions import TODAY, legacy_db, evidence_bytes
from tests.smoke.test_planning_cycle_writer_guards import close
from tests.planning_fixtures import append_history

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize('terminal', ['ended', 'closed'])
def test_coach_current_context_agrees_and_has_no_obsolete_work(tmp_path, monkeypatch, terminal):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY if terminal == 'closed' else date(2026, 9, 28))
    if terminal == 'closed':
        close(db)
    context = current_cycle_context(db)
    tools = AITools(db)
    before = evidence_bytes(db)
    result = tools.get_active_plan()
    assert result['cycle_context'] == context
    assert result['has_plan'] == (terminal == 'ended')
    assert result['current_week'] is None
    assert tools.get_upcoming_workouts()['workouts'] == []
    assert ps.get_active_plan(db) is None
    assert evidence_bytes(db) == before


@pytest.mark.parametrize('terminal', ['ended', 'closed', 'empty'])
def test_delivery_resolves_cycle_before_obtaining_provider(tmp_path, monkeypatch, terminal):
    from services import intervals_plan_delivery as delivery
    db = legacy_db(tmp_path, monkeypatch, payloads=[] if terminal == 'empty' else None)
    if terminal == 'closed':
        close(db)
    def forbidden():
        pytest.fail('provider obtained for inactive cycle')
    monkeypatch.setattr(delivery, 'get_client', forbidden)
    result = deliver_active_plan(db, days=7, today=TODAY, source='test')
    assert result['status'] == 'no_plan'


def test_unassigned_newer_checkpoint_is_not_current(tmp_path, monkeypatch):
    from tests.smoke._planning_cycle_regressions import plan
    from models.planning_checkpoints import build_planning_checkpoint
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    expected = ps.current_status(db)['cycle_context']['checkpoint_id']
    append_history(db, build_planning_checkpoint(plan(date(2026, 12, 1))))
    assert ps.current_status(db)['cycle_context']['checkpoint_id'] == expected
    assert ps.active_plan_overview(db)['cycle_context']['checkpoint_id'] == expected
    assert db.get_latest_planning_checkpoint()['id'] != expected


def test_historical_session_projection_survives_close_without_selection(tmp_path, monkeypatch):
    from models.session_identity import ensure_session_identities
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    plan = ensure_session_identities(restore_goal_plan_from_checkpoint(db.get_current_planning_checkpoint()))
    sid = plan['session_templates'][0]['session_id']
    before = session_projection_at(db, session_id=sid)
    close(db)
    frozen = evidence_bytes(db)
    after = session_projection_at(db, session_id=sid)
    assert after == before
    assert after['projection_status'] != 'not_found'
    assert evidence_bytes(db) == frozen


def test_today_and_planning_share_inactive_cycle_without_assignments(tmp_path, monkeypatch):
    from api.today_snapshot import build_today_decision_snapshot
    from api import today_snapshot
    db = legacy_db(tmp_path, monkeypatch)
    monkeypatch.setattr(today_snapshot, '_run_loop', lambda *_args, **_kwargs: {'readiness_conflicts': {'as_of': TODAY.isoformat()}})
    for terminal in ['ended', 'closed']:
        if terminal == 'closed':
            close(db)
        status = ps.current_status(db)
        snapshot = build_today_decision_snapshot(db, today=TODAY)
        assert snapshot['cycle_context'] == status['cycle_context']
        assert snapshot['has_plan'] == status['has_plan']
        assert snapshot['has_actionable_plan'] is False
        assert snapshot['session'] is None
        assert snapshot['pending_proposal'] is None


def test_history_remains_browsable_with_no_restore_after_close(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    context = current_cycle_context(db)
    close(db)
    history = ps.planning_history(db)
    assert history['has_history'] is True
    assert history['cycle_context']['state'] == 'no_current'
    assert history['items'][0]['cycle_id'] == context['cycle_id']
    assert history['items'][0]['can_restore'] is False


def test_legacy_cache_cannot_reactivate_closed_plan(tmp_path, monkeypatch):
    from api.deps import make_headless_state
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    state = make_headless_state(db)
    state.refresh_planning_checkpoint_cache()
    assert state.resolved_goal_plan_context is not None
    close(db)
    assert state.resolved_goal_plan_context is None
    assert state.latest_planning_checkpoint is None
    assert state.goal_plan is None
    assert state.planning_checkpoint_history


def test_coach_presenter_does_not_call_ended_period_completed(tmp_path, monkeypatch):
    from models.coach_tool_presenter import format_tool_result
    db = legacy_db(tmp_path, monkeypatch)
    rendered = format_tool_result('get_active_plan', AITools(db).get_active_plan())
    assert 'Период закончился' in rendered
    assert 'План завершён' not in rendered
    assert 'исход: не указан' in rendered


def test_partial_final_week_is_historical_after_actual_end(tmp_path, monkeypatch):
    db = legacy_db(tmp_path, monkeypatch, start=date(2026, 10, 12), days=4)
    payload = ps.week_by_week_plan(db)
    assert payload['weeks']
    assert all(not row['is_current'] and row['state'] == 'past' and row['remaining_tss'] is None for row in payload['weeks'])
    assert all(day['state'] == 'past' for week in payload['weeks'] for day in week['days'])


def test_direct_legacy_goal_cache_observes_external_close(tmp_path, monkeypatch):
    from api.deps import make_headless_state
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    state = make_headless_state(db)
    state.refresh_planning_checkpoint_cache()
    assert state.goal_plan is not None
    close(db)
    assert state.goal_plan is None


def test_ambiguous_legacy_session_needs_explicit_checkpoint(tmp_path, monkeypatch):
    from models.planning_checkpoints import build_planning_checkpoint
    from models.session_identity import ensure_session_identities
    from tests.smoke._planning_cycle_regressions import plan, client_for
    from tests.planning_fixtures import seed_checkpoint
    db = legacy_db(tmp_path, monkeypatch, start=TODAY)
    first = db.get_current_planning_checkpoint()
    sid = ensure_session_identities(restore_goal_plan_from_checkpoint(first))['session_templates'][0]['session_id']
    close(db)
    seed_checkpoint(db, build_planning_checkpoint(plan(TODAY)))
    close(db)
    with client_for(db) as client:
        missing = client.get(f'/api/planning/session-projection/{sid}')
        explicit = client.get(f'/api/planning/session-projection/{sid}?checkpoint_id={first["id"]}')
    assert missing.status_code == 404
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()['evidence_revision']['planning_checkpoint_id'] == first['id']
    assert db.get_current_planning_checkpoint() is None


def test_explicit_history_keeps_inherited_match_revision_when_id_is_ambiguous(tmp_path):
    from copy import deepcopy
    from data.database import Database
    from models.planning_checkpoints import build_planning_checkpoint
    from models.session_identity import ensure_session_identities
    from tests.planning_fixtures import seed_checkpoint
    from tests.smoke.test_issue_529_match_handoff import DAY_ISO, _activity, _confirmed_ledger, _plan, _session
    original = _plan(_session('bike', 'quality', 60.0))
    predecessor = original['session_templates'][0]['sessions'][0]['session_id']
    changed = deepcopy(original)
    changed['daily_plan'][0] = (changed['daily_plan'][0][0], 45.0, {'bike':45.0, 'run':0.0, 'swim':0.0})
    changed['session_templates'][0]['sessions'][0].update(total_tss=45.0, duration_minutes=45)
    changed['session_templates'][0]['duration_minutes'] = 45
    changed['weekly_summary'][0].update(weekly_tss=45, bike=45.0)
    changed['weekly_tss_plan'] = [45]
    replacement = ensure_session_identities(changed, previous_goal_plan=original)
    sid = replacement['session_templates'][0]['sessions'][0]['session_id']
    db = Database(str(tmp_path / 'revision.db'))
    first = seed_checkpoint(db, build_planning_checkpoint(original))
    db.save_activities([_activity()])
    confirmed = db.save_plan_actual_match({**_confirmed_ledger(predecessor), 'base_checkpoint_id':first['id']})
    chosen = seed_checkpoint(db, build_planning_checkpoint(replacement))
    close(db)
    append_history(db, build_planning_checkpoint(replacement))
    before = evidence_bytes(db)
    result = session_projection_at(db, session_id=sid, as_of=DAY_ISO, checkpoint_id=chosen['id'])
    assert result['projection_status'] == 'matched'
    assert result['evidence_revision']['planning_checkpoint_id'] == chosen['id']
    assert result['evidence_revision']['match_revision_id'] == confirmed['id']
    assert evidence_bytes(db) == before
