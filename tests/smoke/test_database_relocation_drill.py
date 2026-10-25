"""#624 M3: real CLI + fresh application processes, synthetic storage only.

This accepts existing M1/M2 behavior; no invented RED claim. Child environments
have no provider credentials, a disposable home and an explicit database path.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pytest

from scripts.sqlite_backup_restore import inspect_relocation_database


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'scripts/sqlite_backup_restore.py'
DAY = '2026-10-25'
OBSERVED = datetime(2026, 10, 25, 18, tzinfo=timezone.utc)
ORIGINAL = 'intervals_m3_original'
ADDED = 'intervals_m3_after_activation'
WAL_MARKER = 'M3 committed WAL decision survived relocation'


def _ingest_fixture_activity(db, row: dict, provider: str) -> None:
    from dataclasses import replace
    from data.data_processor import ActivityProcessor, resolve_athlete_tss_profile
    from services.activity_ingest import ingest_provider_activity, normalize_provider_activity

    candidate = normalize_provider_activity(row, provider)
    ftp, lthr, css = resolve_athlete_tss_profile(db)
    resolved = ActivityProcessor.resolve_tss(candidate.canonical, ftp=ftp, lthr=lthr,
                                              swim_threshold_pace_seconds_per_100m=css)
    ingest_provider_activity(db, replace(candidate, canonical={**candidate.canonical, **resolved}),
                             primary_source='intervals')


def _seed_domains(path: Path) -> dict:
    from data.database import Database
    from models.planning_checkpoints import build_planning_checkpoint
    from models.plan_actual_reconciliation import MATCH_RULE_VERSION, build_reconciliation
    from models.post_workout_feedback import FEEDBACK_RULE_VERSION
    from models.session_identity import ensure_session_identities
    from services.activity_manual_links import manage_manual_link
    from services.recovery_analytics import record_post_sync_recovery_state
    from tests.planning_fixtures import seed_checkpoint

    db = Database(str(path))
    intervals = {'id': 'm3_original', 'source': 'UPLOAD', 'external_id': None,
                 'start_date': DAY + 'T10:00:00Z', 'start_date_local': DAY + 'T13:00:00',
                 'type': 'Ride', 'name': 'M3 synthetic ride', 'elapsed_time': 4500,
                 'distance': 31400, 'icu_training_load': 41.4}
    garmin = {'activity_id': '624003', 'date': DAY, 'sport': 'virtual_ride',
              'started_at_utc': DAY + 'T10:00:00Z', 'duration_minutes': 75,
              'distance_km': 31.4, 'source_tss': 41.4}
    for provider, activity in [('intervals', intervals), ('garmin', garmin)]:
        _ingest_fixture_activity(db, activity, provider)
    preview = manage_manual_link(path, 'm3_original', '624003')
    linked = manage_manual_link(path, 'm3_original', '624003', apply=True,
                                expected_token=preview['token'], reason='Synthetic owner-confirmed FIT pair',
                                confirm_stopped=True)
    assert linked['linked']
    bike_tss = db.get_activity(ORIGINAL)['tss']
    plan = ensure_session_identities({
        'goal_type': 'triathlon', 'distance': 'olympic',
        'start_week': date(2026, 10, 19), 'weekly_tss_plan': [bike_tss], 'phases': ['Base'],
        'daily_plan': [(datetime(2026, 10, 25), bike_tss, {'bike': bike_tss, 'run': 0., 'swim': 0.})],
        'session_templates': [{'date': DAY, 'week_index': 0, 'day_index': 6, 'phase': 'Base',
                               'session_role': 'long', 'session_focus': 'Endurance', 'sport': 'bike',
                               'duration_minutes': 75, 'kind': 'single', 'template_key': 'bike_endurance',
                               'definition_snapshot': {'step_builder_key': 'endurance', 'catalog_version': 'workout_catalog_v1'}}],
        'weekly_summary': [], 'protected_dates': [], 'constraint_summary': {},
    })
    checkpoint = seed_checkpoint(db, build_planning_checkpoint(plan))
    reconciliation = build_reconciliation(plan, db.get_activities_between(DAY, DAY),
                                          as_of=date.fromisoformat(DAY), weeks=2,
                                          base_checkpoint_id=checkpoint['id'])
    row = reconciliation['rows'][0]
    assert row['actual_activity_ids'] == [ORIGINAL]
    match = db.save_plan_actual_match({
        'fingerprint': 'm3-match', 'target_key': row['target_key'], 'session_id': row['session_id'],
        'base_checkpoint_id': checkpoint['id'], 'session_date': DAY,
        'match_status': 'matched', 'match_method': 'user_confirmed', 'confidence': 1.,
        'planned_snapshot': row, 'actual_activity_ids': [ORIGINAL],
        'actual_snapshot': {'activities': row['actual_activities'], 'tss': bike_tss},
        'evidence': ['Synthetic confirmed match'], 'rule_version': MATCH_RULE_VERSION,
    })
    feedback = db.save_session_feedback({
        'fingerprint': 'm3-feedback', 'target_key': row['target_key'], 'session_id': row['session_id'],
        'match_revision_id': match['id'], 'match_snapshot': row, 'actual_activity_ids': [ORIGINAL],
        'completion_status': 'completed', 'completion_pct': 100., 'completion_pct_source': 'athlete_entered',
        'session_rpe_1_10': 4, 'quality_rating_1_5': 4, 'note': 'Synthetic easy ride',
        'source': 'user_web', 'session_end_at_utc': DAY + 'T11:15:00Z',
        'session_end_provenance': 'started_at_utc_plus_duration_minutes', 'status': 'active',
        'rule_version': FEEDBACK_RULE_VERSION, 'submitted_at': DAY + 'T12:00:00Z',
    })['feedback']
    db.sync_wellness_batch([{'date': DAY,
        'hrv': {'rmssd': 45., 'rmssd_source': 'intervals'},
        'sleep': {'total_sleep_minutes': 480, 'total_sleep_source': 'intervals',
                  'sleep_score': 82., 'sleep_score_source': 'intervals'},
        'health': {'resting_hr': 52, 'resting_hr_source': 'intervals'},
    }], provider='intervals', cursor_value=DAY, primary_source='intervals')
    readiness = record_post_sync_recovery_state(db, capture_run_id='m3-readiness',
                                                observed_at_utc=OBSERVED, capture_provider='intervals')['snapshot']
    decision = db.save_coach_decision('Moderate', 'Before committed WAL marker',
                                       date=DAY, decision_event_id='m3-coach')
    # Leave a committed update in WAL after all model-valid fixture writes.
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('UPDATE coach_decisions SET reason=? WHERE decision_event_id=?', (WAL_MARKER, 'm3-coach'))
        conn.commit()
        main, wal = path.read_bytes(), Path(str(path) + '-wal').read_bytes()
    path.write_bytes(main)
    Path(str(path) + '-wal').write_bytes(wal)
    assert WAL_MARKER.encode() in wal and WAL_MARKER.encode() not in main
    return {'session_id': row['session_id'], 'checkpoint_id': checkpoint['id'],
            'match_id': match['id'], 'feedback_id': feedback['id'], 'readiness_id': readiness['id'],
            'decision_id': decision['id']}


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    from config.settings import Settings
    monkeypatch.setattr(Settings, 'PRIMARY_ACTIVITY_SOURCE', 'intervals')
    monkeypatch.setattr(Settings, 'ATHLETE_TIMEZONE', 'Europe/Moscow')
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / '.git').mkdir()  # synthetic checkout marker: source allowed here
    source, target, rollback = legacy / 'ai_trainer.db', tmp_path / 'store/new.db', tmp_path / 'backups/original.db'
    metadata = _seed_domains(source)
    return tmp_path, source, target, rollback, metadata


def _environment(root: Path, database: Path | None) -> dict[str, str]:
    home, temporary, launch = [root / name for name in ('home', 'tmp', 'launch')]
    for path in (home, temporary, launch):
        path.mkdir(exist_ok=True)
    # Preserve the outer isolation audit hook only when running its owned harness.
    inherited = os.environ.get('PYTHONPATH', '') if os.environ.get('AI_TRAINER_TEST_ROOT') else ''
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'TMPDIR': str(temporary),
           'XDG_DATA_HOME': str(home / 'data'), 'LOCALAPPDATA': str(home / 'local'),
           'DEMO_DATABASE_PATH': str(root / 'demo.db'), 'CHATS_DIR': str(root / 'chats'),
           'DEFAULT_AI_PROVIDER': 'mock', 'PRIMARY_ACTIVITY_SOURCE': 'intervals',
           'ATHLETE_TIMEZONE': 'Europe/Moscow', 'PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION': 'python',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(ROOT) + (os.pathsep + inherited if inherited else ''),
           'M3_DRILL_ROOT': str(root)}
    if os.environ.get('AI_TRAINER_TEST_ROOT'):
        env['AI_TRAINER_TEST_ROOT'] = os.environ['AI_TRAINER_TEST_ROOT']
    if database is not None:
        env['DATABASE_PATH'] = str(database)
    return env


def _cli(root: Path, *args: str, expected: int = 0) -> dict:
    result = subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=root / 'legacy',
                            env=_environment(root, root / 'legacy/ai_trainer.db'),
                            text=True, capture_output=True, timeout=45)
    assert result.returncode == expected, result.stderr + result.stdout
    assert 'Traceback' not in result.stderr
    return json.loads(result.stdout)


def _guard_probe(root: Path) -> None:
    def audit(event, args):
        if event == 'sqlite3.connect':
            raw = str(args[0])
            if raw == ':memory:' or 'mode=memory' in raw:
                return
            path = unquote(urlsplit(raw).path) if raw.startswith('file:') else raw
            if not Path(path).resolve().is_relative_to(root):
                raise PermissionError('SQLite outside synthetic M3 root')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = Path(os.fsdecode(args[0])).name
            if name == '.env' or (name.startswith('.env.') and name != '.env.example'):
                raise PermissionError('M3 credential file access blocked')
        if event == 'socket.connect' and isinstance(args[1], tuple):
            raise PermissionError('M3 network access blocked')
    sys.addaudithook(audit)


def _application_probe(action: str, metadata: dict) -> None:
    """Only called in a fresh child after dotenv has been disabled."""
    _guard_probe(Path(os.environ['M3_DRILL_ROOT']).resolve())
    from api.deps import get_database
    from api.main import app
    from config.database_paths import DatabasePathError
    from config.settings import Settings
    from fastapi.testclient import TestClient
    from services.planning_cycles import current_plan_snapshot
    from services.readiness_snapshot import build_readiness_snapshot
    from services.reconciliation import reconciliation_at

    try:
        with TestClient(app) as client:
            db = get_database(demo=False)
            if action == 'append':
                _ingest_fixture_activity(db, {
                    'id': 'm3_after_activation', 'source': 'UPLOAD', 'type': 'Run',
                    'start_date': DAY + 'T14:00:00Z', 'start_date_local': DAY + 'T17:00:00',
                    'elapsed_time': 1200, 'distance': 3000, 'icu_training_load': 12.,
                }, 'intervals')
            if action == 'reset':
                db.clear_all_data()
            response = client.get('/api/planning/cycles/current')
            assert response.status_code == 200, response.text
            checkpoint = current_plan_snapshot(db)[1]
            feedback = db.get_latest_session_feedback(metadata['session_id'])
            match = db.get_latest_plan_actual_match_for_session(metadata['session_id'])
            readiness = db.get_readiness_snapshots(local_date=DAY)
            measured = build_readiness_snapshot(db, as_of=date.fromisoformat(DAY), observed_at_utc=OBSERVED)
            reconciliation = reconciliation_at(db, as_of=DAY, weeks=2, include_provider=False)
            with closing(db._connect()) as conn:
                manual = conn.execute('SELECT intervals_activity_id,garmin_activity_id,reason FROM activity_manual_links').fetchall()
                providers = conn.execute('SELECT provider,provider_activity_id,provider_payload FROM activity_provider_links ORDER BY provider').fetchall()
            payload = {'database': Settings.DATABASE_PATH, 'api_context': response.json(),
                       'activities': sorted(row['activity_id'] for row in db.get_activities_between(DAY, DAY)),
                       'checkpoint_id': checkpoint['id'] if checkpoint else None,
                       'match': match, 'feedback': feedback, 'readiness': readiness,
                       'measured': {'score': measured['score'], 'status': measured['status']},
                       'decisions': db.get_coach_decisions(days=36500),
                       'manual': manual, 'providers': providers,
                       'reconciliation': {'has_plan': reconciliation['has_plan'],
                                          'rows': reconciliation.get('rows', [])}}
            print(json.dumps(payload, default=str))
    except DatabasePathError as exc:
        print(json.dumps({'error': str(exc)}))
        raise SystemExit(2) from None


def _app(root: Path, database: Path | None, metadata: dict, *, action='read', expected=0, legacy_cwd=False) -> dict:
    bootstrap = ('import dotenv; dotenv.load_dotenv=lambda *a,**k:False; '
                 'import json,sys; from tests.smoke.test_database_relocation_drill import _application_probe; '
                 '_application_probe(sys.argv[1],json.loads(sys.argv[2]))')
    env = _environment(root, database)
    result = subprocess.run([sys.executable, '-c', bootstrap, action, json.dumps(metadata)],
                            cwd=root / ('legacy' if legacy_cwd else 'launch'), env=env,
                            text=True, capture_output=True, timeout=45)
    assert result.returncode == expected, result.stderr + result.stdout
    return json.loads(result.stdout.splitlines()[-1])


def _migrate(root, source, target, rollback, *, apply=False, expected=0):
    return _cli(root, 'migrate', '--source', source, '--target', target, '--rollback-output', rollback,
                *(['--apply', '--confirm-stopped'] if apply else []), expected=expected)


def _without_path(payload):
    return {key: value for key, value in payload.items() if key != 'database'}


def test_cli_restart_new_writes_fresh_rollback_and_reset(scenario):
    root, source, target, rollback, metadata = scenario
    baseline = inspect_relocation_database(source)
    planned = _migrate(root, source, target, rollback)
    assert planned['status'] == 'planned' and planned['configuration_changed'] is False
    assert not target.parent.exists() and not rollback.parent.exists()
    # Apply has no activation side effect: an unchanged explicit env still reads source.
    copied = _migrate(root, source, target, rollback, apply=True)
    assert copied['status'] == 'copied_not_activated' and copied['configuration_changed'] is False
    assert inspect_relocation_database(target) == inspect_relocation_database(rollback) == baseline
    before_activation = _app(root, source, metadata)
    after_activation = _app(root, target, metadata)
    assert before_activation['database'] == str(source)
    assert after_activation['database'] == str(target)
    assert _without_path(before_activation) == _without_path(after_activation)
    assert after_activation['activities'] == [ORIGINAL]
    assert after_activation['checkpoint_id'] == metadata['checkpoint_id']
    assert after_activation['match']['id'] == metadata['match_id']
    assert after_activation['feedback']['id'] == metadata['feedback_id']
    assert after_activation['readiness'][0]['id'] == metadata['readiness_id']
    assert after_activation['readiness'][0]['capture_run_id'] == 'm3-readiness'
    assert after_activation['readiness'][0]['provenance']['capture_provider'] == 'intervals'
    assert after_activation['decisions'][0]['id'] == metadata['decision_id']
    assert after_activation['decisions'][0]['reason'] == WAL_MARKER
    assert after_activation['manual'][0][:2] == ['m3_original', '624003']
    assert len(after_activation['providers']) == 2
    assert after_activation['measured']['score'] is not None
    assert after_activation['reconciliation']['has_plan']
    assert after_activation['reconciliation']['rows'][0]['actual_activity_ids'] == [ORIGINAL]
    assert _migrate(root, source, target, rollback, apply=True, expected=2)['reason'] == 'target_exists'

    new_state = _app(root, target, metadata, action='append')
    assert new_state['activities'] == sorted([ORIGINAL, ADDED])
    assert _app(root, target, metadata) == new_state  # another clean process, same explicit path
    assert inspect_relocation_database(source) == inspect_relocation_database(rollback) == baseline
    fresh_state = inspect_relocation_database(target)
    assert fresh_state != baseline  # legacy/source snapshot is now stale

    fresh, restored = root / 'backups/current.db', root / 'restored/active.db'
    _cli(root, 'backup', '--database', target, '--output', fresh, '--confirm-stopped')
    _cli(root, 'restore', '--database', restored, '--backup', fresh, '--confirm-stopped')
    assert inspect_relocation_database(restored) == fresh_state
    assert _without_path(_app(root, restored, metadata)) == _without_path(new_state)
    empty_state = _app(root, restored, metadata, action='reset')
    assert empty_state['activities'] == [] and empty_state['checkpoint_id'] is None
    assert empty_state['feedback'] is None and empty_state['readiness'] == []
    assert inspect_relocation_database(source) == inspect_relocation_database(rollback) == baseline
    assert inspect_relocation_database(target) == inspect_relocation_database(fresh) == fresh_state
    assert fresh.exists() and rollback.exists()  # reset owns only its active DB
    reset_state = inspect_relocation_database(restored)
    _cli(root, 'restore', '--database', restored, '--backup', fresh,
         '--rollback-output', root / 'backups/post-reset.db', '--confirm-stopped')
    assert inspect_relocation_database(root / 'backups/post-reset.db') == reset_state
    assert inspect_relocation_database(restored) == fresh_state
    assert _without_path(_app(root, restored, metadata)) == _without_path(new_state)


def test_default_startup_refuses_legacy_before_creating_fresh_store(scenario):
    root, source, _, _, metadata = scenario
    baseline = inspect_relocation_database(source)
    result = _app(root, None, metadata, expected=2, legacy_cwd=True)
    assert 'database_migration_required' in result['error']
    assert not list((root / 'home').rglob('ai_trainer.db'))
    assert inspect_relocation_database(source) == baseline


@pytest.mark.parametrize('failure', ['target_appeared', 'missing_confirmation', 'namespace_overlap', 'invalid_source'])
def test_cli_refusal_does_not_publish_or_switch(scenario, failure):
    root, source, target, rollback, metadata = scenario
    baseline = inspect_relocation_database(source)
    _migrate(root, source, target, rollback)
    reason = {'target_appeared': 'target_exists', 'missing_confirmation': 'stopped_confirmation_required',
              'namespace_overlap': 'endpoint_namespace_overlap', 'invalid_source': 'source_integrity_failed'}[failure]
    chosen_source = source
    chosen_rollback = rollback
    flags = ['--apply', '--confirm-stopped']
    if failure == 'target_appeared':
        target.parent.mkdir()
        target.write_bytes(b'competing file after preview')
    elif failure == 'missing_confirmation':
        flags = ['--apply']
    elif failure == 'namespace_overlap':
        chosen_rollback = Path(str(target) + '-wal')
    else:
        chosen_source = root / 'corrupt.db'
        chosen_source.write_bytes(b'invalid synthetic sqlite')
    response = _cli(root, 'migrate', '--source', chosen_source, '--target', target,
                    '--rollback-output', chosen_rollback, *flags, expected=2)
    assert response['status'] == 'blocked' and response['reason'] == reason
    assert response['configuration_changed'] is False
    assert not rollback.exists()
    if failure == 'target_appeared':
        assert target.read_bytes() == b'competing file after preview'
    else:
        assert not target.exists()
    assert inspect_relocation_database(source) == baseline
    assert _app(root, source, metadata)['database'] == str(source)
