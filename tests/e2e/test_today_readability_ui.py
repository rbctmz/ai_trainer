"""User-visible readability and preserved decision boundaries on synthetic evidence."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from test_today_decision_story_ui import _today_payload, _has_horizontal_overflow

pytestmark = pytest.mark.e2e


def test_readable_today_preserves_action_and_uncertainty(web_stack):
    page = web_stack.page
    payload = _today_payload(web_stack.api_base)
    payload["state"] = "silence"
    payload["briefing"] = {"frequency": "daily", "is_quiet_day": True}
    payload["pending_proposal"] = None
    payload["gate"].update(conflicts=[], data_gap=False, proposal_gap=None)
    payload["readiness"].update(score=68, status="ready", stale=False, freshness=None)
    payload["subjective_wellness"] = {
        "status": "current", "source": "intervals", "date": payload["date"],
        "mapping_version": "intervals_subjective_v1", "age_days": 0,
        "items": [
            {"key": key, "label": label, "state": "present", "value": value, "value_label": value_label}
            for key, label, value, value_label in [
                ("sleepQuality", "Качество сна", 3, "Плохое"),
                ("soreness", "Болезненность", 1, "Низкая"),
                ("fatigue", "Усталость перед тренировкой", 1, "Низкая"),
                ("stress", "Субъективный стресс", 1, "Низкий"),
                ("mood", "Настроение", 2, "Хорошее"),
                ("motivation", "Мотивация", 1, "Высокая"),
                ("injury", "Травма — самооценка", 1, "Нет"),
                ("hydration", "Гидратация — самооценка", 1, "Нормальная"),
            ]
        ],
    }
    page.add_init_script("localStorage.setItem('theme', 'dark')")
    payload["session"] = {
        "session_id": None, "date": payload["date"], "name": "Recovery Run",
        "role": "easy", "role_label": "лёгкая", "sport_label": "бег",
        "is_key": False, "tss": 23, "duration_minutes": 30,
        "stimulus": "low-cost running frequency", "fatigue_cost": [1, 1, 0],
        "expected_recovery_hours": 12, "sessions": [],
        "steps": [
            {"name": name, "duration_seconds": seconds, "segment_kind": kind,
             "intensity": "easy", "target": {"type": "pace", "unit": "seconds_per_km", "fast": 360, "slow": 390}}
            for name, seconds, kind in [("Warm-up", 300, "warmup"), ("Recovery", 1200, "stage"), ("Cool-down", 300, "cooldown")]
        ],
    }
    reason = "Готовность ready (68.0/100) не противоречит сессиям ближайших 3 дн. — вмешательство не требуется."
    story = payload["decision_story"]
    story["next_action"].update(kind="follow_plan", summary=reason, enabled=True)
    story["interpretation"].update(status="consistent", summary=reason, caveat=None)
    story["recommendation"].update(kind="follow_plan", summary=reason)
    story["fact"]["completion_status"] = "not_observed"
    story["evidence"] = [
        {"kind": "session", "source": "session_projection", "status": "unmatched", "ref": "session_123", "freshness": "current", "observation_date": payload["date"]},
        {"kind": "readiness", "source": "canonical_snapshot", "status": "ready", "ref": "snapshot_123", "freshness": "current", "observation_date": payload["date"]},
        {"kind": "subjective_wellness", "source": "intervals", "value_label": "Нет", "ref": "intervals_subjective_v1", "freshness": "current", "observation_date": payload["date"]},
    ]
    current = {"value": payload}

    def serve(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(current["value"], ensure_ascii=False))

    page.route("**/api/today?demo=1", serve)
    artifacts = Path(os.environ["TODAY_UI_SCREENSHOTS"]) if os.environ.get("TODAY_UI_SCREENSHOTS") else None
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
    try:
        for width in (390, 1280):
            page.set_viewport_size({"width": width, "height": 1000})
            current["value"] = payload
            page.goto(f"{web_stack.web_base}/today", wait_until="networkidle")
            page.get_by_role("heading", name="План остаётся без изменений").wait_for()
            region = page.get_by_role("region", name="Решение на сегодня")
            assert region.get_by_text("Оценка восстановления: нормальная", exact=False).count() == 1
            assert page.get_by_text("Восстановительный бег", exact=True).is_visible()
            assert page.get_by_text("6:00–6:30 /км", exact=False).count() == 3
            body = page.locator("main").inner_text()
            for raw in ("ready", "Fatigue", "low-cost", "Recovery Run", "Warm-up", "Cool-down", "session_projection", "canonical_snapshot", "today_decision_story_v1"):
                assert raw not in body, raw
            assert not _has_horizontal_overflow(page)
            if artifacts:
                page.screenshot(path=str(artifacts / f"today-{width}.png"), full_page=True)
            region.get_by_text("На каких данных основано").click()
            assert region.get_by_text("Intervals.icu", exact=False).is_visible()
            assert region.get_by_text("Нормальная", exact=True).is_visible()
            assert "snapshot_123" not in region.inner_text()
            assert not _has_horizontal_overflow(page)

            stale = deepcopy(payload)
            stale["decision_story"]["next_action"]["summary"] += " Свежего ответа о травме нет; это не подтверждение отсутствия симптомов."
            stale["decision_story"]["evidence"][1]["freshness"] = "stale"
            current["value"] = stale
            page.reload(wait_until="networkidle")
            assert region.get_by_text("Свежего ответа о травме нет", exact=False).is_visible()
            region.get_by_text("На каких данных основано").click()
            assert region.get_by_text("Данные устарели", exact=False).is_visible()

            conflict = deepcopy(payload)
            conflict["subjective_wellness"]["items"][6].update(value=2, value_label="Дискомфорт")
            conflict["decision_story"]["evidence"][2]["value_label"] = "Дискомфорт"
            conflict["decision_story"]["next_action"].update(kind="inspect_evidence", summary="Проверьте отмеченное самочувствие перед решением по сессии.")
            conflict["decision_story"]["interpretation"].update(status="conflicting_evidence", summary="Свежая самооценка травмы требует внимания.")
            conflict["decision_story"]["recommendation"].update(kind="non_prescriptive_review", summary="Свежая самооценка травмы требует внимания.")
            current["value"] = conflict
            page.reload(wait_until="networkidle")
            assert page.get_by_role("heading", name="Перед тренировкой нужно уточнение").is_visible()
            assert page.get_by_role("heading", name="План остаётся без изменений").count() == 0
            assert region.get_by_text("Свежая самооценка травмы требует внимания.", exact=True).count() == 1
            assert not _has_horizontal_overflow(page)
            if artifacts:
                page.screenshot(path=str(artifacts / f"conflict-{width}.png"), full_page=True)

            ambiguous = deepcopy(conflict)
            ambiguous["decision_story"]["next_action"].update(kind="confirm_match", summary="Подтвердите сопоставление активности с планом.")
            ambiguous["decision_story"]["interpretation"].update(status="needs_confirmation", summary="Факт активности неоднозначен и требует подтверждения.")
            ambiguous["decision_story"]["recommendation"].update(kind="confirm_match", summary="Подтвердите, какая активность относится к плановой сессии.")
            ambiguous["decision_story"]["fact"].update(session_id="session one", completion_status="needs_confirmation")
            current["value"] = ambiguous
            page.reload(wait_until="networkidle")
            assert region.get_by_role("link", name="Уточнить выполненную тренировку").get_attribute("href") == "/planning?session_id=session%20one"
        assert not web_stack.js_errors
    finally:
        page.unroute("**/api/today?demo=1", serve)
