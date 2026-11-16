"""Owned SQLite lifecycle and immutable author/version identity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest
from data.database import Database
from data.swim_program_store import SwimProgramError, create_preview, confirm_preview, get_version, list_programs
from tests.smoke._swim_program_fixtures import PROGRAM_ID, example_program, changed_program

pytestmark = pytest.mark.smoke
NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def db_at(tmp_path):
    return Database(str(tmp_path / "swim.sqlite"))


def test_preview_confirm_restart_and_lost_response_replay(tmp_path):
    db = db_at(tmp_path)
    first = create_preview(db, example_program(), base_revision=0, now=NOW)
    assert list_programs(db) == []
    saved = confirm_preview(db, first["preview_id"], now=NOW)
    assert saved["revision"] == 1 and saved["document"]["source_text"] == example_program()["source_text"]
    assert confirm_preview(db, first["preview_id"], now=NOW) == saved
    other = create_preview(db, changed_program(), base_revision=1, now=NOW)
    second = confirm_preview(db, other["preview_id"], now=NOW)
    assert second["revision"] == 2 and second["document"]["title"] != saved["document"]["title"]
    reopened = Database(db.db_path)
    assert get_version(reopened, PROGRAM_ID, revision=1) == saved
    assert get_version(reopened, PROGRAM_ID) == second
    assert confirm_preview(reopened, first["preview_id"], now=NOW+timedelta(days=10)) == saved
    assert len(list_programs(reopened)) == 1
    # Rollback is another reviewed append, not deletion of revision2.
    rollback = create_preview(reopened, saved["document"], base_revision=2, now=NOW)
    restored = confirm_preview(reopened, rollback["preview_id"], now=NOW)
    assert restored["revision"] == 3 and restored["document"] == saved["document"]
    assert get_version(reopened, PROGRAM_ID, revision=2) == second


def test_concurrent_confirm_one_wins_and_other_is_stale(tmp_path):
    db = db_at(tmp_path)
    previews = [create_preview(db, doc, base_revision=0, now=NOW) for doc in (example_program(), changed_program())]
    def commit(preview):
        try:
            return confirm_preview(db, preview["preview_id"], now=NOW)["revision"]
        except SwimProgramError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, previews))
    assert sorted(map(str, results)) == ["1", "swim_program_stale"]
    assert len(list_programs(db)) == 1


def test_expiry_boundary_pruning_and_unknown_identity(tmp_path):
    db = db_at(tmp_path)
    preview = create_preview(db, example_program(), base_revision=0, now=NOW)
    with pytest.raises(SwimProgramError, match="swim_program_preview_expired"):
        confirm_preview(db, preview["preview_id"], now=NOW+timedelta(hours=24))
    assert list_programs(db) == []
    create_preview(db, changed_program(), base_revision=0, now=NOW+timedelta(hours=25))
    with pytest.raises(SwimProgramError, match="swim_program_not_found"):
        confirm_preview(db, preview["preview_id"], now=NOW+timedelta(hours=25))


def test_partial_failure_rolls_back_version_and_receipt(tmp_path):
    db = db_at(tmp_path)
    preview = create_preview(db, example_program(), base_revision=0, now=NOW)
    conn = db._connect()
    try:
        conn.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE ON swim_program_previews BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SwimProgramError):
        confirm_preview(db, preview["preview_id"], now=NOW)
    assert list_programs(db) == []
    conn = db._connect()
    try:
        conn.execute("DROP TRIGGER fail_receipt")
        conn.commit()
    finally:
        conn.close()
    assert confirm_preview(db, preview["preview_id"], now=NOW)["revision"] == 1


@pytest.mark.parametrize("table", ["swim_program_previews", "swim_program_versions"])
def test_corrupt_retained_bytes_fail_closed(tmp_path, table):
    db = db_at(tmp_path)
    preview = create_preview(db, example_program(), base_revision=0, now=NOW)
    if table.endswith("versions"):
        confirm_preview(db, preview["preview_id"], now=NOW)
    conn = db._connect()
    try:
        conn.execute(f"UPDATE {table} SET document_json=?", (json.dumps({"PRIVATE_CANARY": "secret"}),))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SwimProgramError, match="swim_program_corrupt"):
        if table.endswith("versions"):
            get_version(db, PROGRAM_ID)
        else:
            confirm_preview(db, preview["preview_id"], now=NOW)


def test_reset_and_backup_api_restore_own_all_state(tmp_path):
    db = db_at(tmp_path)
    preview = create_preview(db, example_program(), base_revision=0, now=NOW)
    saved = confirm_preview(db, preview["preview_id"], now=NOW)
    snapshot = tmp_path / "snapshot.sqlite"
    conn = db._connect()
    target = sqlite3.connect(snapshot)
    try:
        conn.backup(target)
    finally:
        target.close()
        conn.close()
    restored = Database(str(snapshot))
    assert get_version(restored, PROGRAM_ID) == saved
    assert confirm_preview(restored, preview["preview_id"], now=NOW) == saved
    db.clear_all_data()
    assert list_programs(db) == []
    conn = db._connect()
    try:
        assert conn.execute("SELECT count(*) FROM swim_program_previews").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM swim_program_versions").fetchone()[0] == 0
    finally:
        conn.close()
    assert get_version(restored, PROGRAM_ID) == saved


def test_additive_initialization_preserves_existing_data(tmp_path):
    db = db_at(tmp_path)
    db.set_user_setting('swim-test-canary', 'retained')
    conn = db._connect()
    try:
        conn.execute('DROP TABLE swim_program_previews')
        conn.execute('DROP TABLE swim_program_versions')
        conn.commit()
    finally:
        conn.close()
    reopened = Database(db.db_path)
    assert reopened.get_user_setting('swim-test-canary') == 'retained'
    assert list_programs(reopened) == []
    draft = create_preview(reopened, example_program(), base_revision=0, now=NOW)
    assert confirm_preview(reopened, draft['preview_id'], now=NOW)['revision'] == 1


@pytest.mark.parametrize('column,value', [
    ('fingerprint', 'invalid'), ('summary_json', '{}'), ('created_at', 'invalid'),
])
def test_corrupt_current_metadata_never_falls_back_to_earlier_version(tmp_path, column, value):
    db = db_at(tmp_path)
    for base, doc in enumerate((example_program(), changed_program())):
        draft = create_preview(db, doc, base_revision=base, now=NOW)
        confirm_preview(db, draft['preview_id'], now=NOW)
    conn = db._connect()
    try:
        conn.execute(f'UPDATE swim_program_versions SET {column}=? WHERE revision=2', (value,))
        conn.commit()
    finally:
        conn.close()
    for read in (lambda: get_version(db, PROGRAM_ID), lambda: list_programs(db),
                 lambda: create_preview(db, example_program(), base_revision=2, now=NOW)):
        with pytest.raises(SwimProgramError, match='swim_program_corrupt'):
            read()
    assert get_version(db, PROGRAM_ID, revision=1)['revision'] == 1


def test_broken_applied_receipt_is_corruption_not_missing_program(tmp_path):
    db = db_at(tmp_path)
    draft = create_preview(db, example_program(), base_revision=0, now=NOW)
    confirm_preview(db, draft['preview_id'], now=NOW)
    conn = db._connect()
    try:
        conn.execute('DELETE FROM swim_program_versions')
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SwimProgramError, match='swim_program_corrupt') as error:
        confirm_preview(db, draft['preview_id'], now=NOW)
    assert error.value.status == 503


def test_snapshot_contains_committed_version_and_replay_does_not_snapshot(tmp_path, monkeypatch):
    from config.settings import Settings
    from services import snapshot_runtime as runtime
    from services.swim_programs import confirm
    db = db_at(tmp_path)
    monkeypatch.setattr(Settings, 'AUTO_BACKUP_ENABLED', True)
    monkeypatch.setattr(Settings, 'BACKUP_DIR', str(tmp_path / 'backups'))
    monkeypatch.setattr(Settings, 'DATABASE_PATH', db.db_path)
    monkeypatch.setattr(Settings, 'ACCEPTANCE_MODE', False)
    runtime.reset_for_tests()
    calls = []
    def check(*args):
        calls.append(get_version(Database(db.db_path), PROGRAM_ID))
        return runtime.empty_status('degraded', 'backup_io_error')
    monkeypatch.setattr(runtime, 'check_snapshot', check)
    draft = create_preview(db, example_program(), base_revision=0)
    assert not calls
    saved = confirm(db, draft['preview_id'])
    assert calls == [saved]  # Separate connection sees committed bytes before snapshot.
    assert confirm(db, draft['preview_id']) == saved
    assert calls == [saved]
    assert runtime.backup_status(db)['state'] == 'degraded'
    with pytest.raises(SwimProgramError, match='swim_program_not_found'):
        confirm(db, 'missing')
    assert calls == [saved]
    runtime.reset_for_tests()
