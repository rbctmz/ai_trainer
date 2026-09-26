import json
import os
from pathlib import Path
import pytest
from test_today_decision_story_ui import _today_payload, _has_horizontal_overflow

pytestmark = pytest.mark.e2e


def test_today_multisession_and_proposal_presentation(web_stack):
    page = web_stack.page
    writes = []
    page.on(
        "request",
        lambda request: (
            writes.append(request.url)
            if request.method == "POST" and "/proposals/" in request.url
            else None
        ),
    )
    p = _today_payload(web_stack.api_base)
    p.update(
        state="silence",
        briefing={"frequency": "daily", "is_quiet_day": True},
        pending_proposal=None,
    )
    p["gate"].update(conflicts=[], data_gap=False, proposal_gap=None)
    p["readiness"].update(score=68, status="ready", stale=False)
    reason = "Готовность ready (68.0/100) не противоречит сессиям ближайших 3 дн. — вмешательство не требуется."
    p["decision_story"]["next_action"].update(
        kind="follow_plan", summary=reason, enabled=True, caveat=None
    )
    p["decision_story"]["interpretation"].update(summary=reason, caveat=None)
    p["decision_story"]["recommendation"].update(summary=reason)

    def step(name, minutes):
        return dict(
            name=name,
            duration_seconds=minutes * 60,
            segment_kind="stage",
            intensity="easy",
            target=None,
        )

    def leaf(name, sport, tss, minutes):
        return dict(
            kind="single",
            session_id=None,
            group_id=None,
            sport=sport,
            sport_label=sport,
            session_role="easy",
            total_tss=tss,
            name=name,
            materialized_steps=[step(name, minutes)],
        )

    p["session"] = dict(
        session_id=None,
        date=p["date"],
        name="Плавание и бег",
        role="easy",
        role_label="лёгкая",
        sport_label="плавание + бег",
        is_key=False,
        tss=53,
        duration_minutes=70,
        sessions=[
            leaf("Техника плавания", "плавание", 30, 40),
            leaf("Recovery Run", "бег", 23, 30),
        ],
        steps=[],
    )
    page.add_init_script("localStorage.setItem('theme','dark')")
    page.route(
        "**/api/today?demo=1",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(p, ensure_ascii=False),
        ),
    )
    out = Path(os.environ.get("TODAY_UI_SCREENSHOTS", "/private/tmp/today-examples"))
    out.mkdir(parents=True, exist_ok=True)
    for scenario in ["two", "brick", "proposal"]:
        if scenario == "brick":
            p["session"].update(
                name="Велосипед + бег",
                kind="composite",
                sport_label="велосипед + бег",
                tss=75,
                duration_minutes=80,
                transition_minutes=5,
                sessions=[
                    leaf("Велосипед", "велосипед", 60, 60),
                    leaf("Бег после велосипеда", "бег", 15, 15),
                ],
            )
            for i, leaf_session in enumerate(p["session"]["sessions"], 1):
                leaf_session.update(kind="brick_leg", leg_index=i)
        if scenario == "proposal":
            p.update(state="conflict_actionable")
            p["readiness"].update(score=38, status="low")
            why = "Восстановление снижено, а на сегодня запланирована интенсивная тренировка."
            p["decision_story"]["next_action"].update(
                kind="review_proposal", summary=why, enabled=True
            )
            p["decision_story"]["interpretation"].update(summary=why)
            p["session"].update(
                name="Интервальная тренировка",
                sport_label="бег",
                tss=70,
                duration_minutes=60,
                sessions=[],
                steps=[
                    step("Разминка", 15),
                    step("Интервалы", 30),
                    step("Заминка", 15),
                ],
            )
            old = dict(
                name="Интервальная тренировка",
                tss=70,
                duration_minutes=60,
                date=p["date"],
            )
            new = dict(name="Recovery Run", tss=23, duration_minutes=30, date=p["date"])
            p["pending_proposal"] = dict(
                id=42,
                date=p["date"],
                action="recovery_replan",
                status="pending",
                params={"as_of": p["date"]},
                preview=dict(
                    current_session=old,
                    recommended_session=new,
                    total_delta_tss=-47,
                    why_intervene=dict(
                        reason=why,
                        readiness={"score": 38, "status": "low"},
                        severity="moderate",
                    ),
                    what_changes=dict(
                        recommended_kind="downgrade_today",
                        variants=[
                            dict(kind="keep", session=old),
                            dict(kind="downgrade_today", session=new, recommended=True),
                            dict(
                                kind="transfer_1_3d",
                                source_date=p["date"],
                                target_date="2026-09-27",
                            ),
                        ],
                    ),
                    what_is_protected={
                        "by_variant": {
                            "downgrade_today": {
                                "weekly_tss_delta": -47,
                                "weekly_duration_delta_minutes": -30,
                                "mutates_plan": True,
                            }
                        }
                    },
                ),
            )
        for width in [1280, 390]:
            page.set_viewport_size({"width": width, "height": 1100})
            page.goto(web_stack.web_base + "/today", wait_until="networkidle")
            region = page.get_by_role("region", name="Сводка на сегодня")
            region.wait_for()
            assert not _has_horizontal_overflow(page)
            assert page.get_by_role("meter", name="Восстановление").count() == 1
            nav_box = page.locator("nav").first.bounding_box()
            main_box = page.locator("main").bounding_box()
            assert abs(nav_box["width"] - main_box["width"]) <= 2
            if scenario == "brick":
                assert page.get_by_text("↓ Переход · 5 мин", exact=True).is_visible()
            if scenario == "two":
                assert page.get_by_text("Переход", exact=False).count() == 0
            if scenario == "proposal":
                card = (
                    page.get_by_text("Изменение тренировки", exact=True)
                    .locator("../..")
                    .locator("..")
                )
                assert card.get_by_text("Сейчас", exact=True).is_visible()
                assert card.get_by_text("После подтверждения", exact=True).is_visible()
                assert card.get_by_text("60 мин", exact=True).is_visible()
                assert card.get_by_text("30 мин", exact=True).is_visible()
                assert card.get_by_text("Готовность", exact=False).count() == 0
                assert "Recovery Run" not in card.inner_text()
                card.screenshot(path=str(out / f"{scenario}-{width}.png"))
                page.get_by_role(
                    "button", name="Оставить как есть", exact=False
                ).click()
                assert page.get_by_role(
                    "button", name="Оставить план", exact=True
                ).is_visible()
                page.get_by_role(
                    "button", name="Перенести тренировку", exact=False
                ).click()
                assert page.get_by_role(
                    "button", name="Подтвердить перенос", exact=True
                ).is_visible()
            else:
                region.screenshot(path=str(out / f"{scenario}-{width}.png"))
    # A day-level replacement must retain every supplied session on both sides.
    preview = p["pending_proposal"]["preview"]
    unchanged = {"name": "Техника плавания", "duration_minutes": 20, "tss": 10}
    preview["what_changes"]["variants"][1]["day_changes"] = [
        {
            "date": p["date"],
            "before_sessions": [old, unchanged],
            "after_sessions": [new, unchanged],
        }
    ]
    preview["what_is_protected"]["by_variant"]["downgrade_today"] = {
        "mutates_plan": True
    }
    page.reload(wait_until="networkidle")
    assert card.get_by_text("Техника плавания", exact=True).count() == 2
    assert card.get_by_text("Не указано", exact=True).count() == 2
    assert not writes, "Choosing a variant must not write a proposal"
    page.unroute("**/api/today?demo=1")
    assert not web_stack.js_errors
