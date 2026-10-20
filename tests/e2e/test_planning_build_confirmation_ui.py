"""#685 M4 existing UI wired to prepared confirmation, on an isolated web stack."""
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def step3(web_stack):
    page = web_stack.page
    page.unroute_all()
    page.goto(f"{web_stack.web_base}/planning", wait_until="domcontentloaded")
    page.get_by_text("Текущий статус нагрузки", exact=True).wait_for(timeout=60000)
    page.get_by_role("button", name="Изменить план", exact=True).click()
    page.get_by_role("button", name="Ручные фазы Фазы задаёте вы", exact=True).click()
    page.get_by_role("button", name="Далее", exact=True).click()
    # Reuse the declared executable manual demo; separate API tests cover refusals.
    page.get_by_role("slider").fill("8")
    page.get_by_role("button", name="Далее", exact=True).click()
    return page


def ready(web_stack):
    page = step3(web_stack)
    with page.expect_response("**/api/planning/build?*") as built:
        page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    assert built.value.status == 200, built.value.text()
    page.get_by_text(re.compile("План собран: изменение нагрузки")).wait_for(timeout=60000)
    page.get_by_role("button", name="Далее", exact=True).click()
    expect(page.get_by_role("heading",name="Настройка плана — шаг 4: Подтверждение",exact=True)).to_be_focused()
    return page


def test_real_confirm_uses_only_identity_and_no_profile_put(web_stack):
    page = ready(web_stack)
    sent, profiles = [], []
    page.on("request", lambda req: sent.append(req.post_data_json)
            if "/api/planning/build/confirm" in req.url else profiles.append(req.url)
            if "/api/onboarding/planning" in req.url and req.method == "PUT" else None)
    with page.expect_response("**/api/planning/build/confirm*") as response:
        page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    assert response.value.status == 200
    expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()
    assert set(sent[-1]) == {"preview_id", "confirm"} and sent[-1]["confirm"] is True
    assert not profiles


def test_lost_response_locks_reset_and_retries_same_identity(web_stack):
    page = ready(web_stack)
    page.set_viewport_size({"width":390,"height":950})
    sent = []

    def lose(route):
        sent.append(route.request.post_data_json)
        response = route.fetch()
        assert response.status == 200
        route.abort("failed")  # commit happened; browser did not receive the result

    page.route("**/api/planning/build/confirm*", lose)
    page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен. Повторите проверку")).to_be_visible()
    expect(page.get_by_text("Предпросмотр · План ещё не сохранён",exact=False)).to_have_count(0)
    expect(page.get_by_role("button", name="Отменить", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Назад", exact=True)).to_be_disabled()
    expect(page.get_by_role("button", name="Изменить план", exact=True)).to_be_disabled()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifact = Path(__file__).parents[2] / "docs/reports/2026-10-20-planning-readiness-m3/browser"
    artifact.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(artifact/"planning-uncertain-390.png"),full_page=True)
    page.unroute("**/api/planning/build/confirm*", lose)
    with page.expect_response("**/api/planning/build/confirm*") as retry:
        page.get_by_role("button", name="Повторить проверку", exact=True).click()
    result = retry.value.json()
    assert result["confirmation"]["replayed"] is True
    assert result["confirmation"]["preview_id"] == sent[0]["preview_id"]
    expect(page.get_by_text("План сохранён и стал активным", exact=False)).to_be_visible()


def test_distance_edit_discards_late_preview(web_stack):
    page = step3(web_stack)
    waiting = []

    def hold(route):
        waiting.append(route)

    page.route("**/api/planning/build?*", hold)
    page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True).click()
    page.get_by_role("navigation", name="Шаги настройки плана").get_by_role("button").first.click()
    distance = page.get_by_role("combobox").nth(1)
    distance.select_option("half")
    assert waiting
    route = waiting.pop()
    response = route.fetch()
    route.fulfill(response=response)
    page.unroute("**/api/planning/build?*", hold)
    page.get_by_role("button", name="Далее", exact=True).click()
    page.get_by_role("button", name="Далее", exact=True).click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("button", name="Далее", exact=True)).to_be_disabled()
    expect(page.get_by_text(re.compile("Сначала соберите предпросмотр"))).to_be_visible()


def test_stale_requires_explicit_new_preview(web_stack):
    from data.database import Database
    from tests.athlete_clock import athlete_today

    page = ready(web_stack)
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    db.save_activities([{"activity_id": "s1-ui-late", "date": athlete_today().isoformat(),
                         "sport": "cycling", "duration_minutes": 90, "tss": 100}])
    page.get_by_role("button", name="Подтвердить и сохранить", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="Данные изменились — пересоберите предпросмотр")).to_be_visible()
    expect(page.get_by_role("button", name="Подтвердить и сохранить", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Вернуться к предпросмотру", exact=True).click()
    expect(page.get_by_role("button", name="🧭 Предпросмотр плана", exact=True)).to_be_enabled()


@pytest.mark.parametrize("width,theme", [(390,"light"),(900,"dark"),(1280,"light"),(1280,"dark")])
def test_confirmation_controls_keyboard_and_viewport(web_stack, width, theme):
    page = ready(web_stack)
    page.set_viewport_size({"width":width,"height":950})
    page.evaluate("theme => { document.documentElement.classList.toggle('dark', theme === 'dark'); document.documentElement.dataset.theme = theme; }",theme)
    button = page.get_by_role("button", name="Подтвердить и сохранить", exact=True)
    button.focus()
    page.keyboard.press("Shift+Tab")
    expect(page.get_by_role("button",name="Отменить",exact=True)).to_be_focused()
    page.keyboard.press("Tab")
    expect(button).to_be_focused()
    expect(page.get_by_text("Предпросмотр · План ещё не сохранён", exact=False)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    artifact = Path(__file__).parents[2] / "docs/reports/2026-10-20-planning-readiness-m3/browser"
    artifact.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(artifact/f"planning-confirm-{width}-{theme}.png"),full_page=True)
    page.get_by_role("button", name="Отменить", exact=True).click()


@pytest.mark.parametrize("code,status,retry", [
    ("preview_not_found",404,False),("preview_corrupt",500,False),
    ("preview_checkpoint_missing",409,False),("invalid_confirmation",422,True),
    ("planning_busy",503,True),
])
def test_unresolved_errors_preserve_locked_attempt(web_stack, code, status, retry):
    page = ready(web_stack)

    def failure(route):
        route.fulfill(status=status,json={"detail":"Проверка сохранения", "code":code,
                                         "retryable":code == "planning_busy"})

    page.route("**/api/planning/build/confirm*",failure)
    page.get_by_role("button",name="Подтвердить и сохранить",exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен")).to_be_visible()
    expect(page.get_by_role("button",name="Отменить",exact=True)).to_be_disabled()
    expect(page.get_by_role("button",name="Изменить план",exact=True)).to_be_disabled()
    expect(page.get_by_role("button",name="Повторить проверку",exact=True)).to_have_count(1 if retry else 0)
    page.unroute("**/api/planning/build/confirm*",failure)


def test_historical_retry_does_not_claim_active_plan(web_stack):
    import json
    from data.database import Database
    from data.planning_build_preview_store import get_preview

    page = ready(web_stack)
    first = []

    def lose(route):
        first.append(route.request.post_data_json["preview_id"])
        assert route.fetch().status == 200
        route.abort("failed")

    page.route("**/api/planning/build/confirm*",lose)
    page.get_by_role("button",name="Подтвердить и сохранить",exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен")).to_be_visible()
    page.unroute("**/api/planning/build/confirm*",lose)
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    row = get_preview(db,first[0],origin="planning_ui")
    params = json.loads(row["parameters_json"])
    from services.planning_cycles import current_cycle_context
    context = current_cycle_context(db)
    params.update(action="edit_current", base_cycle_id=context["cycle_id"],
                  base_cycle_revision=context["cycle_revision"], base_selection_revision=context["selection_revision"],
                  base_checkpoint_id=context["checkpoint_id"], replace_current_cycle=False, start_date=context["start_date"])
    next_preview = page.request.post(f"{web_stack.api_base}/api/planning/build?demo=1",data=params)
    assert next_preview.status == 200
    later = page.request.post(f"{web_stack.api_base}/api/planning/build/confirm?demo=1",
        data={"preview_id":next_preview.json()["confirmation"]["preview_id"],"confirm":True})
    assert later.status == 200
    page.get_by_role("button",name="Повторить проверку",exact=True).click()
    expect(page.get_by_text("Этот вариант уже сохранялся; сейчас действует другой план",exact=False)).to_be_visible()
    assert db.get_latest_planning_checkpoint()["id"] == int(later.json()["plan_id"])


@pytest.mark.parametrize("outcome",["success","lost","stale"])
def test_coach_card_uses_bound_approval_and_safe_retry(web_stack,outcome):
    import json
    from data.database import Database
    from api import planning_service as ps
    from models.planning_build_confirmation import BuildParameters
    from tests.athlete_clock import athlete_today

    db = Database(str(web_stack.tmp_dir / "demo.db"))
    from services.planning_cycles import current_cycle_context
    context = current_cycle_context(db)
    # This scenario verifies the UI approval/replay adapter; real AITools builds
    # have separate synthetic HTTP/tool tests, including unsupported event refusal.
    shown = ps.prepare_plan_build(db, parameters=BuildParameters.from_mapping({
        "action": "start_new", "base_cycle_id": context["cycle_id"],
        "base_cycle_revision": context["cycle_revision"], "base_selection_revision": context["selection_revision"],
        "base_checkpoint_id": context["checkpoint_id"] or 0, "replace_current_cycle": context["cycle_id"] is not None,
        "start_date": context["athlete_day"], "goal_type": "triathlon", "distance": "olympic",
        "planning_mode": "manual", "horizon_weeks": 8, "events": [],
        "manual_phases": ["Recovery", "Base", "Build", "Recovery", "Base", "Base", "Build", "Recovery"],
        "available_hours": 8, "available_days": ["mon", "tue", "wed", "thu", "sat", "sun"],
    }), origin="coach")
    raw = {"action": "build_plan", "params": {"preview_id": shown["confirmation"]["preview_id"],
        "base_checkpoint_id": shown["preview"]["base_checkpoint_id"]},
        "preview": {"goal": shown["goal"], "confirmation": shown["confirmation"]}}
    proposal = db.save_coach_proposal(action=raw["action"],params=raw["params"],preview=raw["preview"])
    event = {"type":"proposal","proposal_id":proposal["id"],"action":proposal["action"],
             "status":"pending","params":proposal["params"],"preview":proposal["preview"]}
    body = "".join("data: "+json.dumps(item)+"\n\n" for item in (event,{"type":"done"}))
    page = web_stack.page
    page.unroute_all()
    page.route("**/api/coach/chat*",lambda route: route.fulfill(content_type="text/event-stream",body=body))
    with page.expect_response("**/api/dashboard/summary*") as hydrated:
        page.goto(f"{web_stack.web_base}/coach",wait_until="domcontentloaded")
    assert hydrated.value.status == 200
    page.get_by_placeholder(re.compile("Спросите тренера")).fill("Подготовь синтетический план")
    page.get_by_role("button",name="Отправить",exact=True).click()
    expect(page.get_by_text("Предложение нового плана",exact=True)).to_be_visible()
    approve = f"**/api/decisions/proposals/{proposal['id']}/approve*"

    def lose(route):
        assert route.fetch().status == 200
        route.abort("failed")

    if outcome == "lost":
        page.route(approve,lose)
    if outcome == "stale":
        db.save_activities([{"activity_id":"coach-ui-late","date":athlete_today().isoformat(),
                             "sport":"cycling","duration_minutes":90,"tss":105}])
    page.get_by_role("button",name="Подтвердить",exact=True).click()
    if outcome == "stale":
        expect(page.get_by_text("Предложение устарело. Запросите новый предпросмотр в Коуче.",exact=True)).to_be_visible()
        expect(page.get_by_role("button",name="Подтвердить",exact=True)).to_be_disabled()
        assert db.get_coach_proposal(proposal["id"])["status"] == "pending"
    else:
        if outcome == "lost":
            expect(page.get_by_role("status").filter(has_text="Статус сохранения неизвестен")).to_be_visible()
            expect(page.get_by_text("Не удалось применить изменение",exact=True)).to_have_count(0)
            expect(page.get_by_role("button",name="Отменить",exact=True)).to_be_disabled()
            expect(page.get_by_role("button",name="+ Новый",exact=True)).to_be_disabled()
            expect(page.get_by_role("button",name="Отправить",exact=True)).to_be_disabled()
            artifact = Path(__file__).parents[2] / "docs/reports/2026-10-20-planning-readiness-m3/browser"
            artifact.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(artifact/"coach-uncertain.png"),full_page=True)
            page.unroute(approve,lose)
            with page.expect_response(approve) as replay:
                page.get_by_role("button",name="Повторить проверку",exact=True).click()
            assert replay.value.json()["result"]["confirmation"]["replayed"] is True
        expect(page.get_by_text(re.compile("✅ План сохранён"))).to_be_visible()
        assert db.get_coach_proposal(proposal["id"])["status"] == "approved"
    page.unroute_all()


def test_cancel_ready_changes_no_active_plan_or_settings(web_stack):
    from data.database import Database
    from tests.smoke._planning_build_confirmation import protected_state

    page = ready(web_stack)
    db = Database(str(web_stack.tmp_dir / "demo.db"))
    before = protected_state(db)
    page.get_by_role("button",name="Отменить",exact=True).click()
    expect(page.get_by_role("heading",name="Настройка плана — шаг 1: Подход и цель",exact=True)).to_be_focused()
    assert protected_state(db) == before
    expect(page.get_by_text("Предпросмотр · План ещё не сохранён",exact=False)).to_have_count(0)


def test_edit_goal_change_does_not_require_hidden_new_cycle_ack(web_stack):
    page = step3(web_stack)
    page.get_by_role('navigation', name='Шаги настройки плана').get_by_role('button').first.click()
    page.get_by_role('combobox').first.select_option('run')
    expect(page.get_by_role('button', name='Далее', exact=True)).to_be_enabled()


def test_unresolved_edit_survives_external_close_and_replays_as_history(web_stack):
    from data.database import Database
    from tests.smoke.test_planning_cycle_writer_guards import close
    page = ready(web_stack)
    def lose(route):
        assert route.fetch().status == 200
        route.abort('failed')
    page.route('**/api/planning/build/confirm*', lose)
    page.get_by_role('button', name='Подтвердить и сохранить', exact=True).click()
    expect(page.get_by_text(re.compile('Статус сохранения неизвестен'))).to_be_visible()
    db = Database(str(web_stack.tmp_dir / 'demo.db'))
    close(db)
    # SWR focus refresh has a five-second throttle; observe the new server
    # selection in the mounted page, without navigating away from the owner.
    page.wait_for_timeout(5100)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.get_by_role('heading', name='Текущего цикла нет', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Повторить проверку', exact=True)).to_be_visible()
    artifact = Path(__file__).parents[2] / 'docs/design/evidence/issue-693'
    artifact.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifact / 'pending-edit-after-external-close.png'), full_page=True)
    page.unroute('**/api/planning/build/confirm*', lose)
    with page.expect_response('**/api/planning/build/confirm*') as response:
        page.get_by_role('button', name='Повторить проверку', exact=True).click()
    assert response.value.json()['confirmation']['replayed'] is True
    assert response.value.json()['confirmation']['is_current'] is False
    assert db.get_current_planning_checkpoint() is None
