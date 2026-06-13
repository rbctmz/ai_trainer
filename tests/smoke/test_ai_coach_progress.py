"""Smoke coverage for the AI coach progress-report boundary."""
from __future__ import annotations

import pytest

from ui.pages import ai_coaching


pytestmark = pytest.mark.smoke


class _DummyTools:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def execute_tool(self, tool_name, **kwargs):
        self.calls.append((tool_name, kwargs))
        return self._responses.get(tool_name)


class _DummyState:
    def __init__(self, responses):
        self.ai_tools = _DummyTools(responses)


def _build_success_responses():
    return {
        "compare_periods": {
            "success": True,
            "result": {
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
                    "activity_count_change": -1,
                    "volume_change": -180.0,
                    "tss_change": -55.0,
                },
            },
        },
        "analyze_training_load": {
            "success": True,
            "result": {
                "load_trend": "decreasing",
                "weekly_breakdown": [
                    {"total_tss": 210.0, "session_count": 4},
                    {"total_tss": 190.0, "session_count": 4},
                ],
                "intensity_distribution": {
                    "low_intensity_percent": 72.0,
                    "moderate_intensity_percent": 20.0,
                    "high_intensity_percent": 8.0,
                },
            },
        },
        "analyze_hrv_trends": {
            "success": True,
            "result": {
                "current_rmssd": 35.0,
                "recent_avg_7days": 37.0,
                "baseline_median": 40.0,
                "trend_direction": "declining",
                "recovery_state": "fair",
            },
        },
        "get_sleep_stats": {
            "success": True,
            "result": {
                "has_data": True,
                "statistics": {
                    "avg_sleep_hours": 6.6,
                    "avg_sleep_score": 78.0,
                    "avg_sleep_efficiency": 91.4,
                    "current_sleep_quality": "good",
                },
            },
        },
    }


def test_progress_request_detects_monthly_phrasing():
    assert ai_coaching.is_progress_request("Покажи прогресс за месяц")
    assert ai_coaching.is_progress_request("Monthly progress")
    assert not ai_coaching.is_progress_request("Что по пульсу сегодня?")


def test_build_progress_report_keeps_existing_wrapper_contract():
    state = _DummyState(_build_success_responses())

    report = ai_coaching.build_progress_report(state, period_days=30, previous_days=30)

    assert report is not None
    assert "## 📈 Прогресс за период" in report
    assert "### Нагрузка и восстановление (30 дней)" in report
    assert "### Сон" in report
    assert "### Что сделать дальше" in report
    assert "- HRV (RMSSD): 35.0 мс" in report
    assert "Добавь длительную тренировку на выносливость" in report
    assert state.ai_tools.calls == [
        ("compare_periods", {"period1_days": 30, "period2_days": 30}),
        ("analyze_training_load", {"days": 30}),
        ("analyze_hrv_trends", {"days": 30}),
        ("get_sleep_stats", {"days": 30}),
    ]


def test_progress_report_filtering_preserves_free_text_and_hardens_bad_tool_payloads():
    state = _DummyState(
        {
            "compare_periods": None,
            "analyze_training_load": "bad payload",
            "analyze_hrv_trends": {"success": False, "error": "no hrv"},
            "get_sleep_stats": {"success": False, "error": "no sleep"},
        }
    )

    result = ai_coaching.maybe_append_progress_report(
        state,
        "Покажи прогресс за месяц",
        "Сначала короткий вывод.\n\n## 📊 Анализ тренировочной нагрузки\n\nСлужебный блок",
    )

    assert "Сначала короткий вывод." in result
    assert "## 📊 Анализ тренировочной нагрузки" not in result
    assert "### Что сделать дальше" in result
    assert "Готов помочь составить персональный план" in result
