from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json
from api.planning_service import record_plan_actual_match
from api.today_snapshot import build_today_decision_story_from_sources
from api.readiness_snapshot import build_readiness_snapshot
from models.today_decision_story import compose_today_decision_story
from services.reconciliation import reconciliation_at
from services.session_projection import session_projection_at,session_projection_revision_heads,session_projection_from_reconciliation
from tests.smoke.test_daily_story_consistency import _database
from tests.smoke.test_issue_529_match_handoff import DAY,DAY_ISO,_activity
from tests.smoke.test_today_decision_story import _wellness
from tests.smoke.test_reconciliation_service_migration import _table_snapshots

root=Path('/private/tmp/ai-trainer-daily-fix-20261001')
results={}
with TemporaryDirectory(dir=root/'runtime',prefix='reviewer-delta-') as tmp:
    db,plan,checkpoint,ids=_database(Path(tmp))
    original_projections=[session_projection_at(db,session_id=sid,as_of=DAY_ISO) for sid in ids]
    db.save_activities([{**_activity(),'activity_id':'alternate-bike','duration_minutes':30,'tss':30}])
    record_plan_actual_match(db,base_checkpoint_id=checkpoint['id'],session_id=ids[0],activity_ids=[_activity()['activity_id']],actual_role='easy',action='confirm')
    frozen_heads=session_projection_revision_heads(db,ids)
    frozen=reconciliation_at(db,weeks=1,as_of=DAY_ISO,include_provider=False)
    frozen['_story_revision_heads']=frozen_heads
    original_run=session_projection_from_reconciliation(db,frozen,session_id=ids[1])
    record_plan_actual_match(db,base_checkpoint_id=checkpoint['id'],session_id=ids[0],activity_ids=['alternate-bike'],actual_role='easy',action='confirm')
    readiness=build_readiness_snapshot(db,as_of=DAY)
    kwargs=dict(db=db,as_of=DAY_ISO,session_id=None,session_ids=ids,readiness=readiness,
        subjective_wellness=_wellness(day=DAY_ISO),primary_action={'kind':'follow_plan','reason':'OK','enabled':True},
        expected_checkpoint_id=checkpoint['id'])
    before=_table_snapshots(db)
    guarded=build_today_decision_story_from_sources(reconciliation_snapshot=frozen,**kwargs)
    fresh=build_today_decision_story_from_sources(**kwargs)
    assert before==_table_snapshots(db)
    bike,run=guarded['fact']['sessions']
    assert guarded['next_action']['kind']=='inspect_evidence'
    assert bike['projection_status']=='data_gap' and bike['actual']['load_tss'] is None
    assert run['actual']['activity_ids']==original_run['fact']['actual_activity_ids']
    assert run['completion_status']==original_run['fact']['completion_status']
    assert run['evidence_revision']==original_run['evidence_revision']
    assert fresh['fact']['sessions'][0]['actual']['activity_ids']==['alternate-bike']
    results['G1']={'guarded_action':guarded['next_action']['kind'],'affected_bike':bike,
        'unaffected_run_retained':True,'fresh_current_bike':fresh['fact']['sessions'][0],
        'read_adapters_unchanged':True}
    for boundary in ['missing_identity','malformed_identity','mixed_checkpoint','malformed_checkpoint','malformed_actual_id','old_parent_anchor']:
        projections=deepcopy(original_projections)
        if boundary=='missing_identity':projections[1]['session_id']=None
        if boundary=='malformed_identity':projections[1]['session_id']=['bad']
        if boundary=='mixed_checkpoint':projections[1]['evidence_revision']['planning_checkpoint_id']+=1
        if boundary=='malformed_checkpoint':projections[1]['evidence_revision']['planning_checkpoint_id']={}
        if boundary=='malformed_actual_id':projections[1]['fact']['actual_activity_ids']=[{}]
        if boundary=='old_parent_anchor':projections[1]['evidence_revision']['as_of']='2026-08-30'
        story=compose_today_decision_story(as_of=DAY_ISO,session_projection=None,session_projections=projections,
            readiness=readiness,subjective_wellness=_wellness(day=DAY_ISO),primary_action={'kind':'follow_plan','reason':'OK'},rule_versions=None)
        assert story['next_action']['kind']=='inspect_evidence'
        assert story['fact']['actual']['load_tss'] is None
        assert story['fact']['sessions'][0]['actual']['activity_ids']==[_activity()['activity_id']]
        results[boundary]={'action':story['next_action']['kind'],'state':story['fact']['projection_status'],
            'total':story['fact']['actual']['load_tss'],'known_bike_retained':True}
    for bucket in ['confirmed_today','outdated','unverified','invalid','missing']:
        invalid=deepcopy(readiness)
        invalid['freshness'][bucket]=[{}]
        story=compose_today_decision_story(as_of=DAY_ISO,session_projection=None,readiness=invalid,
            subjective_wellness=_wellness(day=DAY_ISO),primary_action={'kind':'follow_plan','reason':'OK'},rule_versions=None)
        state=next(e['freshness'] for e in story['evidence'] if e['kind']=='readiness')
        assert state=='unknown'
        results['S1_'+bucket]=state
    (root/'evidence/reviewer-delta.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps({'G1':'gap with unaffected parent preserved','G2':'6 boundary cases review/null and known fact retained',
        'S1':'5 malformed buckets unknown, no exceptions','read_adapters_unchanged':True},ensure_ascii=False))
