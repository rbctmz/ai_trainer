from pathlib import Path
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
import json, sqlite3, hashlib, uuid
from fastapi.testclient import TestClient
from data.database import Database
from models.planning_checkpoints import build_planning_checkpoint
from models.session_identity import ensure_session_identities
from models.workout_catalog import materialize_session_template
from models.ai_tools import AITools
from services.wellness_ingest import normalize_intervals_wellness
from api.main import app
from api.deps import get_database
from api.today_snapshot import build_today_decision_snapshot
from tests.smoke.test_reconciliation_service_migration import _table_snapshots
from tests.smoke.test_readiness_conflicts import _seed_dated_night
from utils.athlete_time import athlete_local_date
root = Path('/private/tmp/ai-trainer-daily-fix-20261001')
anchor = athlete_local_date()
day = anchor.isoformat()

def session(sport, load, minutes):
    result = dict(materialize_session_template(phase='Base', session_role='easy', sport=sport, target_tss=load, estimated_duration_minutes=minutes, goal_type='Триатлон', zone_snapshot={'ftp':250,'lthr':170,'css':120}))
    result.update(sport=sport,sport_label={'bike':'велосипед','run':'бег'}[sport],session_role='easy',session_focus='Audit '+sport,total_tss=load,duration_minutes=minutes,export_name='Audit '+sport)
    return result

def make_plan(sessions):
    parts={'bike':0.,'run':0.,'swim':0.}
    for s in sessions:
        if s.get('kind')=='composite':
            for leg in s['legs']:parts[leg['sport']]+=leg['target_tss']
        else:parts[s['sport']]+=s['total_tss']
    total=sum(parts.values())
    primary=sessions[0]
    return ensure_session_identities(dict(goal_type='Триатлон',distance='Олимпийка',start_week=anchor,events=[],weekly_tss_plan=[total],base_weekly_tss_plan=[total],phases=['Base'],
    daily_plan=[(datetime.combine(anchor,datetime.min.time()),total,parts)],session_templates=[dict(date=day,week_index=0,day_index=0,phase='Base',session_role='easy',session_focus='Audit day',sport=primary['sport'],sport_label=primary['sport_label'],duration_minutes=sum(s['duration_minutes'] for s in sessions),sessions=deepcopy(sessions))],
    weekly_summary=[dict(week_start=anchor,phase='Base',weekly_tss=total,**parts)],constraint_summary={},near_term_edit_version=0))

def activity(identity,sport,load,minutes,hour=9):
    return dict(activity_id=identity,date=day,started_at_utc=f'{day}T{hour:02}:00:00Z',sport=sport,tss=load,duration_minutes=minutes,activity_name='Synthetic '+identity)

all_results=[]
for scenario in ['ordinary','completed','two','partial-brick','ambiguous','stale','conflicting']:
    folder=root/'runtime'/('scenario-'+scenario+'-'+uuid.uuid4().hex[:8])
    folder.mkdir(exist_ok=True)
    db=Database(str(folder/'audit.db'))
    bike=session('bike',40,40)
    run=session('run',30,30)
    if scenario=='two':sessions=[bike,run]
    elif scenario=='partial-brick':
        legs=[]
        for i,s in enumerate([bike,run],1):
            legs.append(dict(leg_index=i,sport=s['sport'],target_tss=s['total_tss'],duration_minutes=s['duration_minutes'],materialized_steps=s['materialized_steps'],definition_snapshot=s.get('definition_snapshot'),materialization_status=s.get('materialization_status')))
        sessions=[dict(sport='brick',sport_label='велосипед → бег',session_role='easy',session_focus='Audit brick',kind='composite',total_tss=70,duration_minutes=75,transition_minutes=5,legs=legs)]
    else:sessions=[bike]
    plan=make_plan(sessions)
    checkpoint=db.save_planning_checkpoint(build_planning_checkpoint(plan))
    _seed_dated_night(db, (anchor-timedelta(days=3)).isoformat() if scenario=='stale' else day)
    injury=2 if scenario=='conflicting' else 1
    wellness_day=(anchor-timedelta(days=3)).isoformat() if scenario=='stale' else day
    wellness=normalize_intervals_wellness({'id':wellness_day,'injury':injury,'fatigue':1,'sleepQuality':2}).as_payload()
    db.sync_wellness_batch([wellness],provider='intervals',cursor_value=wellness_day,received_at=wellness_day+'T07:00:00Z')
    acts=[]
    if scenario in ['completed','two','partial-brick']:acts=[activity('audit-bike-'+scenario,'bike',44,45)]
    if scenario=='ambiguous':acts=[activity('audit-bike-a','bike',44,45),activity('audit-bike-b','bike',40,40,17)]
    if acts:db.save_activities(acts)
    # Apply normal startup normalization before taking any comparable snapshots.
    db=Database(str(folder/'audit.db'))
    if scenario=='partial-brick':
        from api.planning_service import record_plan_actual_match
        sid=plan['session_templates'][0]['sessions'][0]['session_id']
        record_plan_actual_match(db,base_checkpoint_id=checkpoint['id'],session_id=sid,activity_ids=[acts[0]['activity_id']],actual_role='easy',action='confirm')
    app.dependency_overrides[get_database]=lambda db=db:db
    with TestClient(app) as client:
        responses={}
        for key,path in [('today','/api/today'),('planning','/api/planning/reconciliation?include_provider=false&as_of='+day),('overview','/api/planning/overview')]:
            response=client.get(path)
            responses[key]={'http_status':response.status_code,'body':response.json()}
        projections={}
        rows=[r for r in responses['planning']['body'].get('rows',[]) if r.get('date')==day]
        for row in rows:
            sid=row['session_id']
            response=client.get('/api/planning/session-projection/'+sid+'?as_of='+day)
            projections[sid]={'http_status':response.status_code,'body':response.json()}
        cards={}
        for act in acts:
            response=client.get('/api/activities/'+act['activity_id'])
            cards[act['activity_id']]={'http_status':response.status_code,'body':response.json()}
    app.dependency_overrides.clear()
    from api.routers import coach as coach_router
    ai_tools=AITools(db)
    with patch.object(coach_router,'AITools',return_value=ai_tools):
        lazy_response=coach_router.coach_chat(coach_router.ChatRequest(message='Какой факт тренировки сегодня?',provider='mock'),db=db,demo=True)
    coach_context=ai_tools.today_decision_context
    before=_table_snapshots(db)
    metrics=ai_tools.get_performance_metrics()
    readiness=ai_tools.get_readiness_today()
    unchanged=before==_table_snapshots(db)
    today=responses['today']['body']
    result={'scenario':scenario,'anchor':day,'checkpoint_id':checkpoint['id'],'database_path':str(folder/'audit.db'),'responses':responses,'projections':projections,'activity_cards':cards,'coach_metrics':metrics,'coach_readiness':readiness,'coach_context':coach_context,'read_adapters_unchanged':unchanged}
    file=root/'evidence'/('scenario-'+scenario+'.json')
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    summary={'scenario':scenario,'api_statuses':{k:v['http_status'] for k,v in responses.items()},'state':today.get('state'),'action':today.get('decision_story',{}).get('next_action',{}).get('kind'),'story_session_id':today.get('decision_story',{}).get('fact',{}).get('session_id'),'story_status':today.get('decision_story',{}).get('fact',{}).get('projection_status'),'story_actual':today.get('decision_story',{}).get('fact',{}).get('actual'),'readiness_freshness':(today.get('readiness')or{}).get('freshness'),'rows':[{k:r.get(k) for k in ['session_id','sport','match_status','actual_activity_ids','actual_total_tss']} for r in rows],'coach_adapter_unchanged':unchanged}
    all_results.append(summary)
    print(json.dumps(summary,ensure_ascii=False,default=str),flush=True)
(root/'evidence/six-scenarios-summary.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2,default=str))
