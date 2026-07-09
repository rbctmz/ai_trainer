"""Smoke coverage for AI coach output formatting and browser helpers."""
from __future__ import annotations

import pytest

from ui.components import ai_coach_output
from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyPlaceholder:
    def __init__(self):
        self.history = []

    def markdown(self, text):
        self.history.append(text)


def test_page_wrapper_preserves_tool_formatting_contract():
    formatted = ai_coaching.format_tool_result(
        "compare_periods",
        {
            "period2_days": 30,
            "recent_period": {
                "activity_count": 12,
                "total_duration": 600.0,
                "total_tss": 420.0,
                "activities_per_week": 2.8,
            },
            "previous_period": {
                "activity_count": 10,
                "no_data": False,
            },
            "comparison": {
                "activity_count_change": 2,
                "volume_change": 90.0,
                "tss_change": 40.0,
            },
        },
    )

    assert "## 📈 Прогресс за период" in formatted
    assert "**Итоги текущего периода**" in formatted
    assert "**Динамика vs предыдущие 30 дней**" in formatted
    assert "- TSS: +40 ↑" in formatted


def test_format_get_active_plan_shows_current_week_and_weeks_table():
    formatted = ai_coach_output.format_tool_result(
        "get_active_plan",
        {
            "has_plan": True,
            "goal": {
                "goal_type": "Триатлон",
                "distance": "Олимпийка",
                "event_date": "2026-08-31",
                "weeks_to_race": 7,
            },
            "events": [
                {"date": "2026-08-31", "priority": "A", "label": "Главный старт"},
                {"date": "2026-07-26", "priority": "B", "label": "Контрольный старт"},
            ],
            "timeline": {
                "today": "2026-07-09",
                "plan_start": "2026-06-29",
                "plan_end": "2026-08-30",
                "weeks_elapsed": 1,
                "weeks_remaining": 7,
                "status": "active",
            },
            "current_week": {
                "index": 2,
                "week_start": "2026-07-06",
                "week_end": "2026-07-12",
                "phase": "base",
                "weekly_tss": 110,
            },
            "phases": ["base", "build"],
            "totals": {"total_tss": 745, "peak_tss": 400, "total_weeks": 4},
            "weekly_tss_plan": [85, 110, 150, 400],
            "weeks_preview": [
                {"week": 1, "week_start": "2026-06-29", "week_end": "2026-07-05", "phase": "base", "weekly_tss": 85, "is_current": False},
                {"week": 2, "week_start": "2026-07-06", "week_end": "2026-07-12", "phase": "base", "weekly_tss": 110, "is_current": True},
                {"week": 3, "week_start": "2026-07-13", "week_end": "2026-07-19", "phase": "build", "weekly_tss": 150, "is_current": False},
                {"week": 4, "week_start": "2026-07-20", "week_end": "2026-07-26", "phase": "build", "weekly_tss": 400, "is_current": False},
            ],
        },
    )

    assert "## 🗓️ Активный план" in formatted
    assert "Триатлон Олимпийка" in formatted
    assert "До старта: **7 нед.**" in formatted
    assert "Текущая неделя: 2 из 4" in formatted
    assert "Плановый TSS: **110**" in formatted
    assert "A · Главный старт" in formatted
    assert "B · Контрольный старт" in formatted
    assert "2 ← текущая" in formatted
    # weeks table is rendered explicitly, not collapsed by the default formatter
    assert "[данные доступны]" not in formatted
    assert "| Неделя | Старт недели | Фаза | TSS |" in formatted


def test_format_get_active_plan_no_plan_message():
    formatted = ai_coach_output.format_tool_result(
        "get_active_plan",
        {"has_plan": False, "message": "Активный план не найден. Пользователь ещё не построил план."},
    )
    assert "Активный план не найден" in formatted


def test_format_get_active_plan_not_started():
    formatted = ai_coach_output.format_tool_result(
        "get_active_plan",
        {
            "has_plan": True,
            "goal": {"goal_type": "Бег", "distance": "Марафон", "event_date": "", "weeks_to_race": 9},
            "timeline": {
                "today": "2026-07-09",
                "plan_start": "2026-07-13",
                "plan_end": "2026-09-06",
                "weeks_elapsed": 0,
                "weeks_remaining": 9,
                "status": "not_started",
            },
            "current_week": None,
            "phases": ["base"],
            "totals": {"total_tss": 800, "peak_tss": 120, "total_weeks": 8},
            "weekly_tss_plan": [100] * 8,
            "weeks_preview": [],
        },
    )
    assert "План ещё не начался" in formatted
    assert "← текущая" not in formatted


def test_format_get_upcoming_workouts_lists_sessions():
    formatted = ai_coach_output.format_tool_result(
        "get_upcoming_workouts",
        {
            "has_plan": True,
            "days": 7,
            "sessions": [
                {
                    "date": "2026-07-10",
                    "sport": "bike",
                    "sport_label": "вело",
                    "tss": 20,
                    "name": "Триатлон Олимпийка — Восстановление",
                    "phase": "recovery",
                },
                {
                    "date": "2026-07-12",
                    "sport": "run",
                    "sport_label": "бег",
                    "tss": 55,
                    "name": "Триатлон Олимпийка — Темповый бег",
                    "phase": "build",
                },
            ],
        },
    )

    assert "## 📅 Ближайшие плановые тренировки (7 дней)" in formatted
    assert "Пт 10.07" in formatted
    assert "**Триатлон Олимпийка — Восстановление**" in formatted
    assert "вело" in formatted
    assert "TSS 20" in formatted
    assert "фаза: recovery" in formatted
    assert "**Триатлон Олимпийка — Темповый бег**" in formatted
    # sessions are rendered explicitly, not collapsed by the default formatter
    assert "[данные доступны]" not in formatted


def test_format_get_upcoming_workouts_no_plan_message():
    formatted = ai_coach_output.format_tool_result(
        "get_upcoming_workouts",
        {"has_plan": False, "message": "Активный план не найден."},
    )
    assert "Активный план не найден" in formatted


def test_format_get_upcoming_workouts_empty_sessions():
    formatted = ai_coach_output.format_tool_result(
        "get_upcoming_workouts",
        {
            "has_plan": True,
            "days": 7,
            "sessions": [],
            "message": "Нет плановых тренировок в ближайшие 7 дней (возможно, уже выполнены или до них ещё далеко).",
        },
    )
    assert "Нет плановых тренировок" in formatted
    assert "[данные доступны]" not in formatted


def test_streaming_response_keeps_cursor_during_long_output(monkeypatch: pytest.MonkeyPatch):
    placeholder = _DummyPlaceholder()
    monkeypatch.setattr(ai_coach_output.time, "sleep", lambda _seconds: None)

    text = (
        "Первое предложение достаточно длинное для стриминга и специально растянуто, "
        "чтобы превысить порог быстрого вывода. "
        "Второе предложение тоже довольно длинное и должно попасть в промежуточный кадр."
    )
    ai_coach_output.simulate_streaming_response(placeholder, text)

    assert placeholder.history[0].endswith("▋")
    assert placeholder.history[-1] == text
    assert len(placeholder.history) >= 2


def test_speak_text_sanitizes_markdown_and_truncates(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    def fake_html(body, *, unsafe_allow_javascript=False, width="stretch"):
        captured["html"] = body
        captured["unsafe_allow_javascript"] = unsafe_allow_javascript

    # speak_text now uses st.html(unsafe_allow_javascript=True); mock it on the
    # streamlit module the production code imports.
    monkeypatch.setattr(ai_coach_output.st, "html", fake_html)

    long_markdown = "# Заголовок\n**Жирный** [линк](https://example.com) `" + ("x" * 520) + "`"
    ai_coach_output.speak_text(long_markdown)

    html = captured["html"]
    assert captured["unsafe_allow_javascript"] is True
    assert "Заголовок" in html
    assert "Жирный" in html
    assert "линк" in html
    assert "**Жирный**" not in html
    assert "](https://example.com)" not in html
    assert "..." in html
