import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

root = Path('/private/tmp/ai-trainer-daily-fix-20261001')
ev = root / 'evidence'
work = Path('/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer')
manifest = json.loads((ev / 'acceptance-validation.json').read_text())
export = json.loads((ev / 'candidate-export.json').read_text())
hashes = {}
for name, digest in manifest['source_files'].items():
    current = hashlib.sha256((work / name).read_bytes()).hexdigest()
    candidate = hashlib.sha256((root / 'candidate' / name).read_bytes()).hexdigest()
    assert current == candidate == digest == export[name], name
    hashes[name] = current

expected = dict(ordinary='follow_plan', completed='follow_plan', two='follow_plan',
                **{'partial-brick': 'follow_plan'}, ambiguous='confirm_match',
                stale='inspect_evidence', conflicting='inspect_evidence')
cases = []
for case, action in expected.items():
    data = json.loads((ev / f'scenario-{case}.json').read_text())
    story = data['responses']['today']['body']['decision_story']
    assert story == data['coach_context']['story'], case
    assert story['next_action']['kind'] == action, case
    assert story['next_action']['changes_plan'] is False, case
    assert story['next_action']['clearance_claim'] is False, case
    assert data['read_adapters_unchanged'], case
    assert all(r['http_status'] == 200 for group in ['responses', 'projections', 'activity_cards'] for r in data[group].values()), case
    fact = story['fact']
    parents = fact.get('sessions', [fact])
    for parent in parents:
        canonical = data['projections'][parent['session_id']]['body']
        for key in ['plan', 'deviation', 'cause', 'evidence_revision']:
            assert parent[key] == canonical[key], (case, key)
        for key, projection_key in [('activity_ids', 'actual_activity_ids'), ('load_tss', 'load_tss'), ('legs', 'legs')]:
            assert parent['actual'][key] == canonical['fact'][projection_key], (case, key)
    for card in data['activity_cards'].values():
        canonical = card['body']['activity'].get('session_projection')
        if canonical:
            assert canonical == data['projections'][canonical['session_id']]['body'], case
    readiness = next(item for item in story['evidence'] if item['kind'] == 'readiness')['freshness']
    assert readiness == ('unknown' if case == 'stale' else 'current'), case
    if case == 'two':
        assert fact['session_id'] is None and len(parents) == 2
        assert [p['completion_status'] for p in parents] == ['complete', 'not_observed']
        assert parents[1]['actual']['activity_ids'] == [] and fact['actual']['load_tss'] == 45
    if case == 'partial-brick':
        assert 'sessions' not in fact
        assert len(fact['actual']['legs']) == 1 and fact['actual']['legs'][0]['sport'] == 'bike'
        assert fact['actual']['transition']['actual_minutes'] is None
    cases.append({'case': case, 'parents': len(parents), 'action': action,
                  'readiness': readiness, 'completion': [p['completion_status'] for p in parents],
                  'actual_tss': fact['actual']['load_tss']})

browser = json.loads((ev / 'real-browser-results.json').read_text())
states = browser['results']
counts = Counter(s['surface'] for s in states)
assert len(states) == 67
assert counts == {'today': 42, 'today-explanation': 14, 'planning': 7, 'activities': 4}, counts
assert all(not s['overflow'] for s in states)
for key in ['page_errors', 'api_errors', 'blocked_writes']:
    assert browser[key] == [], key
assert browser['processes_stopped'] is True
for case in expected:
    today = [s for s in states if s['case'] == case and s['surface'] == 'today']
    assert {(s['theme'], s['width']) for s in today} == {(theme, width) for theme in ['light', 'dark'] for width in [390, 978, 1280]}, case
    explanations = [s for s in states if s['case'] == case and s['surface'] == 'today-explanation']
    assert {(s['theme'], s['width']) for s in explanations} == {('light', 978), ('dark', 978)}, case
    for s in explanations:
        if case == 'two':
            assert 'Выполненная тренировка связана с планом' in s['text']
            assert 'Выполнение не найдено' in s['text']
        if case == 'ordinary':
            assert 'Неполные данные' not in s['text']
            assert 'Актуальность данных не подтверждена' not in s['text']

xml = ET.parse(ev / 'broad-confirmed.xml').getroot()
suites = list(xml.iter('testsuite'))
totals = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ['tests', 'failures', 'errors', 'skipped']}
assert totals == {'tests': 2991, 'failures': 0, 'errors': 0, 'skipped': 18}, totals
assert '2973 passed, 18 skipped, 46 deselected' in (ev / 'broad-confirmed.log').read_text()
assert 'All checks passed!' in (ev / 'ruff-final.log').read_text()
assert '85 passed' in (ev / 'focused-review-final.log').read_text()
out = {'hashes': hashes, 'cases': cases, 'browser_counts': dict(counts), 'suite_xml': totals,
       'verified': 'PASS', 'boundaries': 'Saved evidence read-back only; no new full review or product checks.'}
(ev / 'reviewer-final-readback.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps(out, ensure_ascii=False, indent=2))
