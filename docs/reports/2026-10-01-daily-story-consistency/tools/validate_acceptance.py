import json,hashlib
from pathlib import Path
r=Path('/private/tmp/ai-trainer-daily-fix-20261001/evidence')
cases=['ordinary','completed','two','partial-brick','ambiguous','stale','conflicting']
expected={'ordinary':'follow_plan','completed':'follow_plan','two':'follow_plan','partial-brick':'follow_plan','ambiguous':'confirm_match','stale':'inspect_evidence','conflicting':'inspect_evidence'}
results=[]
for case in cases:
 d=json.loads((r/f'scenario-{case}.json').read_text());t=d['responses']['today']['body']['decision_story'];c=d['coach_context']['story'];f=t['fact']
 assert t==c,case
 assert t['next_action']['kind']==expected[case],case
 assert not t['next_action']['changes_plan'] and not t['next_action']['clearance_claim'],case
 assert d['read_adapters_unchanged'],case
 assert all(v['http_status']==200 for v in d['responses'].values()),case
 assert all(v['http_status']==200 for v in d['projections'].values()),case
 assert all(v['http_status']==200 for v in d['activity_cards'].values()),case
 readiness=next(e for e in t['evidence'] if e['kind']=='readiness')
 assert readiness['freshness']==('unknown' if case=='stale' else 'current'),case
 parents=f.get('sessions',[f])
 for p in parents:
  q=d['projections'][p['session_id']]['body']
  assert p['plan']==q['plan'] and p['cause']==q['cause'] and p['deviation']==q['deviation'],case
  assert p['evidence_revision']==q['evidence_revision'],case
  assert p['actual']['activity_ids']==q['fact']['actual_activity_ids'],case
  assert p['actual']['load_tss']==q['fact']['load_tss'],case
  assert p['actual']['legs']==q['fact']['legs'],case
 for card in d['activity_cards'].values():
  p=card['body']['activity'].get('session_projection')
  if p: assert p==d['projections'][p['session_id']]['body'],case
 if case=='two':
  assert f['session_id'] is None and len(parents)==2
  assert parents[0]['completion_status']=='complete' and parents[1]['completion_status']=='not_observed'
  assert parents[1]['actual']['activity_ids']==[] and f['actual']['load_tss']==45
 if case=='partial-brick':
  assert 'sessions' not in f and len(f['actual']['legs'])==1
  assert f['actual']['legs'][0]['sport']=='bike' and f['actual']['transition']['actual_minutes'] is None
 results.append({'case':case,'today_equals_coach':True,'canonical_parent_and_card_parity':True,'http_all_200':True,'read_adapters_unchanged':True,'action':t['next_action']['kind'],'readiness_freshness':readiness['freshness'],'parents':len(parents),'actual_load_tss':f['actual']['load_tss'],'changes_plan':False,'clearance_claim':False})
b=json.loads((r/'real-browser-results.json').read_text())
assert len(b['results'])==67
assert not any(x['overflow'] for x in b['results'])
assert b['page_errors']==[] and b['api_errors']==[] and b['blocked_writes']==[] and b['processes_stopped']
for x in b['results']:
 if x['surface']=='today-explanation':
  if x['case']=='two': assert 'Выполненная тренировка связана с планом' in x['text'] and 'Выполнение не найдено' in x['text']
  if x['case']=='ordinary': assert 'Неполные данные' not in x['text']
summary={'scenarios':results,'browser':{'states':67,'today':42,'explanation':14,'planning':7,'activity_detail':4,'themes':['light','dark'],'widths':[390,978,1280],'overflow':0,'page_errors':0,'api_errors':0,'blocked_writes':0,'processes_stopped':True},'source_files':{}}
w=Path('/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer')
for name in ['api/today_snapshot.py','api/routers/coach.py','models/today_decision_story.py','services/session_projection.py','web/lib/types.ts','tests/contracts/ts_contract.json','tests/smoke/test_daily_story_consistency.py','tests/smoke/test_today_decision_story.py']:
 summary['source_files'][name]=hashlib.sha256((w/name).read_bytes()).hexdigest()
 exported=json.loads((r/'candidate-export.json').read_text());assert summary['source_files'][name]==exported[name],name
(r/'acceptance-validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print('PASS: seven API variants, exact Today/Coach story parity, canonical parents/cards, 67 browser states, candidate source hashes')
