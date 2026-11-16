"""Immutable identity, replay, failure and reset/restore boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import uuid4
import pytest
from data.database import Database
from data import swim_exercise_store as store
from models.swim_exercise import SwimExerciseDocument, exercise_fingerprint
from services import swim_exercises as service
from data.swim_program_store import create_preview,confirm_preview,get_version as get_program
from tests.smoke._swim_program_fixtures import example_program,PROGRAM_ID
from tests.smoke.test_swim_exercise import definition, EXERCISE_ID

pytestmark=pytest.mark.smoke


def save(db,raw=None,base=0,key=None):
    doc=SwimExerciseDocument.model_validate(raw or definition())
    return store.confirm(db,doc,base_revision=base,request_id=str(key or uuid4()),fingerprint=exercise_fingerprint(doc))


def test_history_replay_search_and_saved_program_snapshot(tmp_path):
    db=Database(str(tmp_path/'catalog.sqlite'));key=str(uuid4());first=save(db,key=key)
    resolved=service.resolve(db,exercise_id=EXERCISE_ID,revision=1,node_id='one.drill',distance_meters=50,instructions='Left arm')
    assert resolved['exercise']==first
    program=example_program();program['workouts'][0]['steps'][1]=resolved['step']
    draft=create_preview(db,program,base_revision=0);saved=confirm_preview(db,draft['preview_id'])
    raw=definition();raw['instructions']='Explicit revised instruction'
    second=save(db,raw,base=1)
    reopened=Database(db.db_path)
    assert store.get_version(reopened,EXERCISE_ID,revision=1)==first
    assert store.get_version(reopened,EXERCISE_ID)==second
    assert save(reopened,key=key)==first
    assert get_program(reopened,PROGRAM_ID)==saved
    assert service.resolve(reopened,exercise_id=EXERCISE_ID,revision=1,node_id='x',distance_meters=25)['exercise']==first
    assert len(store.list_exercises(db,query='EXAMPLE ALIAS'))==1
    raw['id']=str(uuid4());raw['variant']='Another variant';save(db,raw)
    assert len(store.list_exercises(db,query='Synthetic'))==2
    with pytest.raises(store.SwimExerciseError,match='request_conflict'): save(db,raw,key=key)
    rollback=save(db,first['document'],base=2)
    assert rollback['revision']==3 and rollback['document']==first['document']


def test_concurrent_base_and_mismatched_fingerprint(tmp_path):
    db=Database(str(tmp_path/'race.sqlite'))
    def attempt(_):
        try:return save(db)['revision']
        except store.SwimExerciseError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(attempt,range(2)))
    assert sorted(map(str,out))==['1','swim_exercise_stale']
    with pytest.raises(store.SwimExerciseError,match='fingerprint_mismatch'):
        store.confirm(db,SwimExerciseDocument.model_validate(definition()),base_revision=1,request_id=str(uuid4()),fingerprint='0'*64)


def test_restore_reset_and_insert_failure(tmp_path):
    db=Database(str(tmp_path/'source.sqlite'));key=str(uuid4());first=save(db,key=key)
    with db._connect() as c:c.execute("CREATE TRIGGER fail_exercise BEFORE INSERT ON swim_exercise_versions BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    with pytest.raises(store.SwimExerciseError):save(db,base=1)
    assert store.get_version(db,EXERCISE_ID)==first
    with db._connect() as c:c.execute('DROP TRIGGER fail_exercise')
    second=save(db,base=1)
    conn=db._connect();target=sqlite3.connect(tmp_path/'restored.sqlite')
    try:conn.backup(target)
    finally:target.close();conn.close()
    restored=Database(str(tmp_path/'restored.sqlite'))
    assert store.get_version(restored,EXERCISE_ID)==second
    assert save(restored,key=key)==first
    db.clear_all_data();assert store.list_exercises(db)==[]
    with db._connect() as c:assert c.execute('SELECT COUNT(*) FROM swim_exercise_versions').fetchone()[0]==0
    assert store.get_version(restored,EXERCISE_ID)==second


@pytest.mark.parametrize('column,value',[('document_json','PRIVATE_CANARY'),('fingerprint','bad'),('created_at','invalid'),('base_revision',0)])
def test_corrupt_head_fail_closed_without_fallback(tmp_path,column,value):
    db=Database(str(tmp_path/'corrupt.sqlite'));first=save(db);save(db,base=1)
    with db._connect() as c:c.execute(f'UPDATE swim_exercise_versions SET {column}=? WHERE revision=2',(value,))
    for read in (lambda:store.get_version(db,EXERCISE_ID),lambda:store.list_exercises(db),lambda:save(db,base=2)):
        with pytest.raises(store.SwimExerciseError,match='corrupt'):read()
    assert store.get_version(db,EXERCISE_ID,revision=1)==first


def test_snapshot_after_commit_once_on_replay(tmp_path,monkeypatch):
    from config.settings import Settings
    from services import snapshot_runtime as runtime
    db=Database(str(tmp_path/'snap.sqlite'));key=str(uuid4());raw=definition();doc=SwimExerciseDocument.model_validate(raw)
    monkeypatch.setattr(Settings,'AUTO_BACKUP_ENABLED',True);monkeypatch.setattr(Settings,'BACKUP_DIR',str(tmp_path/'backups'))
    monkeypatch.setattr(Settings,'DATABASE_PATH',db.db_path);monkeypatch.setattr(Settings,'ACCEPTANCE_MODE',False)
    runtime.reset_for_tests();seen=[]
    def check(*args):
        seen.append(store.get_version(Database(db.db_path),EXERCISE_ID));return runtime.empty_status('degraded','backup_io_error')
    monkeypatch.setattr(runtime,'check_snapshot',check)
    args=dict(base_revision=0,request_id=key,fingerprint=exercise_fingerprint(doc))
    try:
        saved=service.confirm(db,doc,**args);assert seen==[saved]
        assert service.confirm(db,doc,**args)==saved and seen==[saved]
        assert runtime.backup_status(db)['state']=='degraded'
    finally:runtime.reset_for_tests()
