"""S2 M4: complete lifecycle journeys against temporary SQLite and real API."""
from datetime import timedelta
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def setup_ended(web_stack):
    from data.database import Database
    from models.planning_checkpoints import build_planning_checkpoint
    from tests.planning_fixtures import seed_checkpoint
    from tests.smoke._planning_cycle_regressions import plan
    db = Database(str(web_stack.tmp_dir / 'demo.db'))
    db.clear_all_data()
    context = web_stack.page.request.get(f'{web_stack.api_base}/api/planning/cycles/current?demo=1').json()
    from datetime import date
    today = date.fromisoformat(context['athlete_day'])
    seed_checkpoint(db, build_planning_checkpoint(plan(today - timedelta(days=14))))
    page = web_stack.page
    page.unroute_all()
    page.goto(f'{web_stack.web_base}/planning?demo=1', wait_until='domcontentloaded')
    expect(page.get_by_role('heading', name='Период закончился', exact=True)).to_be_visible(timeout=60000)
    return page, db


def close_in_ui(page, *, dns=False):
    page.get_by_role('button', name='Закрыть цикл', exact=True).click()
    if dns:
        page.get_by_label('Участие: Synthetic Olympic').select_option('did_not_participate')
    page.get_by_role('button', name='Подтвердить закрытие', exact=True).click()
    expect(page.get_by_role('heading', name='Текущего цикла нет', exact=True)).to_be_visible()


def new_preview(page):
    page.get_by_role('button', name='Начать новый цикл', exact=True).click()
    expect(page.get_by_label('Дата начала цикла')).to_have_value(re.compile(r'\d{4}-\d{2}-\d{2}'))
    page.get_by_role('button', name='Развивать форму Без выдуманной даты гонки', exact=True).click()
    page.get_by_role('checkbox', name=re.compile('Выбираю эту цель')).check()
    page.get_by_role('button', name='Далее', exact=True).click()
    page.get_by_role('button', name='Далее', exact=True).click()
    with page.expect_response('**/api/planning/build?*') as response:
        page.get_by_role('button', name='🧭 Предпросмотр плана', exact=True).click()
    assert response.value.status == 200, response.value.text()
    result = response.value.json()
    assert result['lifecycle']['action'] == 'start_new'
    assert result['parameters']['events'] == []
    assert result['parameters']['event_date'] is None
    page.get_by_role('button', name='Далее', exact=True).click()
    expect(page.get_by_role('heading', name='Настройка плана — шаг 4: Подтверждение', exact=True)).to_be_focused()
    return result


def test_expired_close_unknown_new_cancel_confirm_and_history(web_stack):
    page, db = setup_ended(web_stack)
    old = db.get_current_planning_checkpoint()
    expect(page.get_by_role('button', name='Изменить план', exact=True)).to_be_disabled()
    close_in_ui(page)
    page.get_by_text('История циклов', exact=True).click()
    expect(page.get_by_text(re.compile('Synthetic Olympic.*Не указано'))).to_be_visible()
    prepared = new_preview(page)
    page.get_by_role('button', name='Отменить', exact=True).click()
    assert db.get_current_planning_checkpoint() is None
    assert db.get_latest_planning_checkpoint()['id'] == old['id']
    # Cancellation preserves form choices but requires a new retained preview.
    page.get_by_role('button', name='Далее', exact=True).click()
    page.get_by_role('button', name='Далее', exact=True).click()
    page.get_by_role('button', name='🧭 Предпросмотр плана', exact=True).click()
    page.get_by_text(re.compile('План собран: изменение нагрузки')).wait_for()
    page.get_by_role('button', name='Далее', exact=True).click()
    with page.expect_response('**/api/planning/build/confirm*') as response:
        page.get_by_role('button', name='Подтвердить и сохранить', exact=True).click()
    assert response.value.status == 200, response.value.text()
    checkpoint = db.get_current_planning_checkpoint()
    assert checkpoint['id'] != old['id']
    assert all(row['date'][:10] >= prepared['lifecycle']['start_date'] for row in checkpoint['goal_plan_snapshot']['daily_plan'])
    page.get_by_role('button', name='Открыть план в Обзоре', exact=True).click()
    expect(page.get_by_role('heading', name='Подготовка идёт', exact=True)).to_be_visible()


@pytest.mark.parametrize('width,theme', [(390,'light'),(390,'dark'),(900,'light'),(900,'dark'),(1280,'light'),(1280,'dark')])
def test_close_dns_history_keyboard_and_width(web_stack, width, theme):
    page, _db = setup_ended(web_stack)
    page.set_viewport_size({'width':width,'height':950})
    page.evaluate("theme => document.documentElement.classList.toggle('dark', theme === 'dark')", theme)
    page.get_by_role('button', name='Закрыть цикл', exact=True).focus()
    page.keyboard.press('Enter')
    page.get_by_label('Участие: Synthetic Olympic').select_option('did_not_participate')
    button = page.get_by_role('button', name='Подтвердить закрытие', exact=True)
    button.focus()
    page.keyboard.press('Enter')
    expect(page.get_by_role('heading', name='Текущего цикла нет', exact=True)).to_be_visible()
    page.get_by_text('История циклов', exact=True).click()
    expect(page.get_by_text(re.compile('Synthetic Olympic.*Не участвовал'))).to_be_visible()
    page.get_by_label('Исход: Synthetic Olympic').select_option('participated')
    page.get_by_role('button', name='Сохранить исход', exact=True).click()
    expect(page.get_by_text(re.compile('Synthetic Olympic.*Участвовал'))).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    artifact = Path(__file__).parents[2] / 'docs/design/evidence/issue-693'
    artifact.mkdir(parents=True, exist_ok=True)
    expect(page.get_by_role('button', name='Начать новый цикл', exact=True)).to_be_enabled()
    page.screenshot(path=str(artifact/f'cycle-history-{width}-{theme}.png'), full_page=True)


def test_close_lost_response_reuses_original_command_and_locks_new_cycle(web_stack):
    page, db = setup_ended(web_stack)
    sent = []
    def lose(route):
        sent.append(route.request.post_data_json)
        assert route.fetch().status == 200
        route.abort('failed')
    page.route('**/api/planning/cycles/*/close*', lose)
    page.get_by_role('button', name='Закрыть цикл', exact=True).click()
    page.get_by_role('button', name='Подтвердить закрытие', exact=True).click()
    expect(page.get_by_text(re.compile('Результат действия неизвестен'))).to_be_visible()
    expect(page.get_by_role('button', name='Начать новый цикл', exact=True)).to_be_disabled()
    page.unroute('**/api/planning/cycles/*/close*', lose)
    with page.expect_response('**/api/planning/cycles/*/close*') as response:
        page.get_by_role('button', name='Повторить проверку действия', exact=True).click()
    assert response.value.json()['replayed'] is True
    assert response.value.request.post_data_json['command_id'] == sent[0]['command_id']
    assert db.get_current_planning_checkpoint() is None


def test_new_build_lost_response_keeps_preview_identity(web_stack):
    page, _db = setup_ended(web_stack)
    close_in_ui(page)
    prepared = new_preview(page)
    def lose(route):
        assert route.fetch().status == 200
        route.abort('failed')
    page.route('**/api/planning/build/confirm*', lose)
    page.get_by_role('button', name='Подтвердить и сохранить', exact=True).click()
    expect(page.get_by_text(re.compile('Статус сохранения неизвестен'))).to_be_visible()
    expect(page.get_by_role('button', name='Начать новый цикл', exact=True)).to_be_disabled()
    page.unroute('**/api/planning/build/confirm*', lose)
    with page.expect_response('**/api/planning/build/confirm*') as response:
        page.get_by_role('button', name='Повторить проверку', exact=True).click()
    result = response.value.json()
    assert result['confirmation']['preview_id'] == prepared['confirmation']['preview_id']
    assert result['confirmation']['replayed'] is True


def test_replacement_requires_ack_and_cancel_keeps_old_selected(web_stack):
    page, db = setup_ended(web_stack)
    old = db.get_current_planning_checkpoint()['id']
    page.get_by_role('button', name='Начать новый цикл', exact=True).click()
    page.get_by_role('button', name='Развивать форму Без выдуманной даты гонки', exact=True).click()
    page.get_by_role('checkbox', name=re.compile('Выбираю эту цель')).check()
    expect(page.get_by_role('button', name='Далее', exact=True)).to_be_disabled()
    page.get_by_role('checkbox', name=re.compile('При сохранении нового плана')).check()
    page.get_by_role('button', name='Далее', exact=True).click()
    page.get_by_role('button', name='Далее', exact=True).click()
    with page.expect_response('**/api/planning/build?*') as response:
        page.get_by_role('button', name='🧭 Предпросмотр плана', exact=True).click()
    assert response.value.status == 200, response.value.text()
    assert response.value.json()['lifecycle']['closes_cycle_id'] is not None
    page.get_by_role('button', name='Далее', exact=True).click()
    expect(page.get_by_role('note').filter(has_text='прежний цикл закроется')).to_be_visible()
    page.get_by_role('button', name='Отменить', exact=True).click()
    assert db.get_current_planning_checkpoint()['id'] == old


def test_unknown_constraint_scope_is_explicitly_resolvable(web_stack):
    from datetime import date
    page, db = setup_ended(web_stack)
    close_in_ui(page)
    day = page.request.get(f'{web_stack.api_base}/api/planning/cycles/current?demo=1').json()['athlete_day']
    db.save_coach_constraint(day, 'manual_delete', source='test')
    page.reload()
    scope = page.get_by_label(f'Область ограничения на {date.fromisoformat(day)}')
    expect(scope).to_be_visible()
    expect(page.get_by_role('button', name='Подтвердить область', exact=True)).to_be_disabled()
    scope.select_option('athlete')
    page.get_by_role('button', name='Подтвердить область', exact=True).click()
    expect(page.get_by_text('Область ограничения сохранена.', exact=True)).to_be_visible()
    assert db.get_coach_constraints(active_only=True)[0]['cycle_scope'] == 'athlete'
