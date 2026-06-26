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
