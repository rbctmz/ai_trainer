"""Synthetic cloud/local facts stay separate; browser never starts a transfer."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.e2e.test_backup_status_ui import payload as local_payload

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def payload(state, warning=None):
    verified = state in {'ready', 'stale', 'degraded'}
    return {'state': state, 'reason_code': 'cloud_network_failed' if state == 'degraded' else None,
            'last_attempt_at': '2026-11-15T10:00:00Z' if verified else None,
            'last_verified_at': '2026-11-15T09:00:00Z' if verified else None,
            'last_covered_check_at': '2026-11-15T08:00:00Z' if verified else None,
            'last_drill_at': '2026-11-14T08:00:00Z' if verified else None,
            'drill_warning': warning}


@pytest.mark.parametrize('state,warning,expected', [
    ('disabled', None, 'Облачные резервные копии выключены.'),
    ('unknown', 'cloud_drill_due', 'Состояние облачной копии неизвестно.'),
    ('ready', None, 'Облачная копия проверена.'),
    ('stale', None, 'Облачная копия устарела.'),
    ('degraded', None, 'Облачную копию не удалось обновить.'),
    ('ready', 'cloud_drill_due', 'Пора проверить восстановление из облака.'),
    ('ready', 'cloud_drill_failed', 'Проверка восстановления из облака не завершена.'),
    ('error', None, 'Состояние облачной копии неизвестно.'),
])
@pytest.mark.parametrize('width,theme', [(1280, 'light'), (390, 'light'), (1280, 'dark'), (390, 'dark')])
def test_cloud_status_is_read_only_and_separate(web_stack, state, warning, expected, width, theme):
    page = web_stack.page
    requests = []
    def cloud_status(route):
        requests.append(route.request.method)
        route.fulfill(status=503 if state == 'error' else 200, content_type='application/json',
                      body=json.dumps({} if state == 'error' else payload(state, warning)))
    def local_status(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(local_payload('ready')))
    page.route('**/api/backup/cloud/status*', cloud_status)
    page.route('**/api/backup/status*', local_status)
    page.set_viewport_size({'width': width, 'height': 900})
    page.add_init_script(f"localStorage.setItem('theme', '{theme}');")
    try:
        page.goto(web_stack.web_base + '/today')
        banner = page.get_by_test_id('cloud-backup-status')
        expect(banner).to_contain_text(expected)
        expect(page.get_by_test_id('backup-status')).to_contain_text('Резервная копия проверена.')
        if state in {'ready', 'stale', 'degraded'}:
            for label in ('Локальные данные проверены:', 'Чтение из облака проверено:', 'Восстановление проверено:'):
                expect(banner).to_contain_text(label)
        elif state in {'unknown', 'error'}:
            expect(banner).to_contain_text('Время последней проверенной облачной копии неизвестно.')
        expect(banner.get_by_role('button')).to_have_count(0)
        assert requests and set(requests) == {'GET'}
        assert 'cloud_' not in banner.inner_text() and '/private/' not in banner.inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        if state == 'stale' or warning == 'cloud_drill_failed':
            evidence = ROOT / 'docs/design/evidence/issue-757'
            evidence.mkdir(parents=True, exist_ok=True)
            banner.screenshot(path=str(evidence / f'cloud-{state}-{warning or "none"}-{width}-{theme}.png'))
    finally:
        page.unroute('**/api/backup/cloud/status*', cloud_status)
        page.unroute('**/api/backup/status*', local_status)
