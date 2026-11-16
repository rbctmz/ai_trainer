"""Synthetic backup warning/retry; never replay a saved business command."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[2]


def payload(state, *, snapshot=True):
    return {'state': state, 'last_checked_at': '2026-11-04T09:00:00+00:00',
            'last_snapshot_at': '2026-11-04T08:00:00+00:00' if snapshot else None,
            'last_snapshot_id': 'a' * 32 if snapshot else None,
            'reason_code': 'backup_io_error' if state == 'degraded' else None}


@pytest.mark.parametrize('state,snapshot,expected', [
    ('disabled', False, 'Автоматические резервные копии выключены.'),
    ('unknown', False, 'Состояние резервной копии неизвестно.'),
    ('ready', True, 'Резервная копия проверена.'),
    ('degraded', False, 'Данные сохранены, резервная копия не обновлена.'),
])
def test_backup_states_are_honest(web_stack, state, snapshot, expected):
    page = web_stack.page
    def handler(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload(state, snapshot=snapshot)))
    page.route('**/api/backup/status*', handler)
    try:
        page.goto(web_stack.web_base + '/today')
        banner = page.get_by_test_id('backup-status')
        expect(banner).to_contain_text(expected)
        if state != 'disabled' and not snapshot:
            expect(banner).to_contain_text('Время последней проверенной копии неизвестно.')
        assert 'backup_io_error' not in banner.inner_text()
        assert 'aaaaaaaa' not in banner.inner_text()
    except Exception:
        web_stack.capture_failure()
        raise
    finally:
        page.unroute('**/api/backup/status*', handler)


@pytest.mark.parametrize('width,theme,success', [(390, 'light', True), (1280, 'dark', False)])
def test_retry_is_bounded_and_does_not_repeat_business_save(web_stack, width, theme, success):
    page = web_stack.page
    phase = [payload('degraded')]
    held = []
    posts = []
    def status_handler(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(phase[0]))
    def retry_handler(route):
        held.append(route)
    def request_seen(request):
        if request.method in {'POST', 'PUT', 'DELETE', 'PATCH'}:
            posts.append(request.url.split('/api/', 1)[-1].split('?', 1)[0])
    page.route('**/api/backup/status*', status_handler)
    page.route('**/api/backup/check*', retry_handler)
    page.on('request', request_seen)
    page.set_viewport_size({'width': width, 'height': 900})
    page.add_init_script(f"localStorage.setItem('theme', '{theme}');")
    try:
        page.goto(web_stack.web_base + '/today')
        banner = page.get_by_test_id('backup-status')
        button = banner.get_by_role('button', name='Повторить проверку резервной копии', exact=True)
        expect(button).to_be_enabled()
        evidence = ROOT / 'docs/design/evidence/issue-623-m3'
        evidence.mkdir(parents=True, exist_ok=True)
        banner.screenshot(path=str(evidence / f'backup-{width}-{theme}.png'))
        button.focus()
        button.press("Enter")
        pending = banner.get_by_role('button', name='Проверяем резервную копию…', exact=True)
        expect(pending).to_be_disabled()
        pending.evaluate('(button) => button.click()')
        assert len(held) == 1
        assert held[0].request.post_data_json == {}
        if success:
            phase[0] = payload('ready')
            held.pop().fulfill(status=200, content_type='application/json', body=json.dumps(phase[0]))
            expect(banner).to_contain_text('Резервная копия проверена.')
            expect(banner.get_by_role('button')).to_have_count(0)
        else:
            held.pop().fulfill(status=503, content_type='application/json', body='{}')
            expect(banner).to_contain_text('Данные сохранять повторно не нужно.')
            expect(button).to_be_enabled()
        assert posts == ['backup/check']
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    except Exception:
        web_stack.capture_failure()
        raise
    finally:
        for route in held:
            route.abort()
        page.remove_listener('request', request_seen)
        page.unroute('**/api/backup/status*', status_handler)
        page.unroute('**/api/backup/check*', retry_handler)


@pytest.mark.parametrize('reason,width,theme', [
    ('backup_retention_failed', 390, 'light'),
    ('backup_reset_pins_unknown', 1280, 'dark'),
])
def test_verified_copy_with_maintenance_warning_can_retry_only_backup(web_stack, reason, width, theme):
    page = web_stack.page
    status = {**payload('ready'), 'reason_code': reason}
    posts = []
    def read(route):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(status))
    def retry(route):
        posts.append(route.request.url.split('/api/', 1)[-1].split('?', 1)[0])
        assert route.request.post_data_json == {}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload('ready')))
    page.route('**/api/backup/status*', read)
    page.route('**/api/backup/check*', retry)
    page.set_viewport_size({'width': width, 'height': 900})
    page.add_init_script(f"localStorage.setItem('theme', '{theme}');")
    try:
        page.goto(web_stack.web_base + '/today')
        banner = page.get_by_test_id('backup-status')
        expect(banner).to_contain_text('Резервная копия проверена.')
        expect(banner).to_contain_text('Очистка старых копий приостановлена')
        expect(banner).not_to_contain_text('резервная копия не обновлена')
        assert reason not in banner.inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        evidence = ROOT / 'docs/design/evidence/issue-623-m4'
        evidence.mkdir(parents=True, exist_ok=True)
        banner.screenshot(path=str(evidence / f'maintenance-{width}-{theme}.png'))
        button = banner.get_by_role('button', name='Повторить проверку резервной копии', exact=True)
        button.focus()
        button.press('Enter')
        expect(banner).not_to_contain_text('Очистка старых копий приостановлена')
        expect(button).to_have_count(0)
        assert posts == ['backup/check']
    except Exception:
        web_stack.capture_failure()
        raise
    finally:
        page.unroute('**/api/backup/status*', read)
        page.unroute('**/api/backup/check*', retry)
