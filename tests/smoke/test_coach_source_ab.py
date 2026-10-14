"""Offline boundaries for the finite source-message experiment (#528)."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from services.coach_runtime_eval import CallBudget, run_source_comparison
from tests.evals.coach.runtime_registry import COMPACT_CONTRACT, SOURCE_BEFORE_MESSAGE

pytestmark = pytest.mark.smoke
TODAY = date(2026, 10, 14)


class SourceProvider:
    model = "scripted-source"

    def __init__(self, *, answer=None, fail=False, tool="get_activity_structure"):
        self.answer = answer
        self.fail = fail
        self.tool = tool
        self.calls = 0

    def is_available(self):
        return True

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.calls += 1
        if self.fail:
            return {"text": "Ошибка провайдера", "tool_calls": []}
        if any(message["role"] == "tool" for message in messages):
            return {"text": "Данные получены", "tool_calls": []}
        return {"tool_calls": [{"id": "source-1", "name": self.tool,
                                "arguments": {"activity_id": "syn-run-uncached"}}]}

    def generate_response(self, prompt, system_prompt=""):
        self.calls += 1
        assert COMPACT_CONTRACT["prompt_suffix"] in prompt
        return self.answer or "Структура недоступна: отрезки ещё не загружены в кэш."


def test_source_pairs_change_only_message_and_reach_both_model_contexts():
    report = run_source_comparison(SourceProvider(), today=TODAY)
    assert report["total"] == 4
    assert report["calls_used"] == 12
    assert report["call_limit"] == 16
    assert report["verdict"] == "pending_manual"
    assert report["automated_gate"] == "pass"
    assert [row["variant"] for row in report["results"]] == ["before", "after", "after", "before"]
    assert len({row["snapshot_before"] for row in report["results"]}) == 1
    assert all(row["database_unchanged"] for row in report["results"])
    assert all(all(row["protocol_checks"].values()) for row in report["results"])
    old, new = report["source_messages"]["before"]["text"], report["source_messages"]["after"]["text"]
    assert old == SOURCE_BEFORE_MESSAGE and old != new
    before, after = report["results"][:2]
    normalized = json.dumps(before["tool_results"], ensure_ascii=False).replace(old, new)
    assert normalized == json.dumps(after["tool_results"], ensure_ascii=False)
    for variant, text in (("before", old), ("after", new)):
        row = next(row for row in report["results"] if row["variant"] == variant)
        trace = row["provider_trace"]
        assert trace[0]["request"] == before["provider_trace"][0]["request"]
        assert text in trace[1]["request"]["messages"][-1]["content"]
        assert text in trace[2]["request"]["prompt"]
        assert SOURCE_BEFORE_MESSAGE not in trace[0]["request"]["messages"][0]["content"]


def test_old_message_matches_preserved_trace_and_product_is_unchanged():
    from models.ai_tools import _ACTIVITY_STRUCTURE_MESSAGES
    path = Path(__file__).resolve().parents[2] / "docs/reports/2026-10-13-coach-compact-ab/live-comparison.json"
    trace = json.loads(path.read_text())
    assert SOURCE_BEFORE_MESSAGE in path.read_text()
    old_message = next(
        activity["message"] for row in trace["results"] for result in row["tool_results"]
        if result["tool_name"] == "get_activity_structure"
        for activity in result["raw_result"].get("activities", [])
        if activity.get("reason") == "not_fetched"
    )
    assert old_message == SOURCE_BEFORE_MESSAGE
    current = dict(_ACTIVITY_STRUCTURE_MESSAGES)
    run_source_comparison(SourceProvider(), today=TODAY)
    assert _ACTIVITY_STRUCTURE_MESSAGES == current


def test_length_is_diagnostic_and_known_lexical_blind_spot_stays_manual():
    honest = "Структура недоступна: нет кэша. " + "Подробности " * 90
    report = run_source_comparison(SourceProvider(answer=honest), today=TODAY)
    assert all(not row["checks"]["brief_answer"] for row in report["results"])
    assert report["automated_gate"] == "pass"
    assert report["verdict"] == "pending_manual"
    hidden = run_source_comparison(SourceProvider(
        answer="Кэш недоступен. После синхронизации отрезки материализуются."), today=TODAY)
    assert hidden["automated_gate"] == "pass"
    assert hidden["human_assessment"] == "pending"
    assert hidden["verdict"] == "pending_manual"


def test_visible_guarantee_and_missing_exposure_cannot_pass():
    bad = run_source_comparison(SourceProvider(
        answer="Кэш недоступен. Синхронизируй — отрезки появятся."), today=TODAY)
    assert bad["automated_gate"] == "fail"
    assert bad["variants"]["after"]["passed"] == 0
    absent = run_source_comparison(SourceProvider(tool="get_active_plan"), today=TODAY)
    assert absent["verdict"] == "inconclusive"
    assert absent["protocol_valid"] is False
    assert all(not row["protocol_checks"]["message_exposed"] for row in absent["results"])


def test_errors_and_budget_preserve_exactly_four_trials():
    provider = SourceProvider(fail=True)
    report = run_source_comparison(provider, today=TODAY)
    assert report["total"] == report["error_trials"] == 4
    assert report["calls_used"] == provider.calls == 4
    assert report["verdict"] == "inconclusive"
    capped = run_source_comparison(SourceProvider(), today=TODAY, budget=CallBudget(2))
    assert capped["total"] == capped["error_trials"] == 4
    assert capped["calls_used"] == 2
    with pytest.raises(ValueError):
        run_source_comparison(SourceProvider(), today=TODAY, budget=CallBudget(17))
    with pytest.raises(ValueError):
        run_source_comparison(SourceProvider(), today=TODAY, repeats=1)


def test_substitution_does_not_touch_other_states_or_delegate_result():
    from copy import deepcopy
    from services.coach_runtime_eval import _ReadOnlyTools

    outcome = {"success": True, "result": {"activities": [
        {"structure_status": "unavailable", "reason": "not_fetched", "message": "current"},
        {"structure_status": "unavailable", "reason": "no_provider_link", "message": "no link"},
        {"structure_status": "unavailable", "reason": "corrupt_cache", "message": "corrupt"},
        {"structure_status": "empty", "message": "empty"},
        {"structure_status": "structured", "intervals": [{"average_watts": 198}]},
    ]}}
    original = deepcopy(outcome)

    class Delegate:
        def execute_tool(self, name, **params):
            return outcome

    tools = _ReadOnlyTools(Delegate(), SOURCE_BEFORE_MESSAGE)
    assert tools.execute_tool("get_active_plan") == original
    changed = tools.execute_tool("get_activity_structure")
    assert changed["result"]["activities"][0]["message"] == SOURCE_BEFORE_MESSAGE
    assert changed["result"]["activities"][1:] == original["result"]["activities"][1:]
    assert outcome == original
    assert tools.execute_tool("repair_plan_day")["success"] is False
    assert outcome == original


def test_calendar_change_stops_source_calls_and_preserves_four_rows(monkeypatch):
    import models.ai_coach_runtime as runtime

    class ChangingProvider(SourceProvider):
        def generate_with_tools(self, messages, tools, system_prompt=""):
            result = super().generate_with_tools(messages, tools, system_prompt)
            monkeypatch.setattr(runtime, "_today_context_line", lambda today=None: "Сегодня: shifted")
            return result

    report = run_source_comparison(ChangingProvider(), today=TODAY)
    assert report["calls_used"] == 3
    assert report["error_trials"] == 3
    assert report["total"] == 4
    assert report["verdict"] == "inconclusive"


def test_source_cli_keeps_denominator_and_never_overwrites(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/run_coach_runtime_eval.py"
    output = tmp_path / "source-offline.json"
    command = [sys.executable, str(script), "--experiment", "source-ab", "--provider", "scripted",
               "--today", TODAY.isoformat(), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 1, first.stdout + first.stderr
    report = json.loads(output.read_text())
    assert report["total"] == 4 and report["call_limit"] == 16
    assert report["verdict"] == "pending_manual"
    original = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == original
    assert subprocess.run(command + ["--repeats", "1"], capture_output=True).returncode == 2

    from scripts import run_coach_runtime_eval as cli
    settings = ModuleType("config.settings")
    settings.Settings = type("Missing", (), {"DEEPSEEK_API_KEY": ""})
    providers = ModuleType("models.ai_providers")
    providers.DeepSeekProvider = lambda **kwargs: pytest.fail("no provider on failed preflight")
    monkeypatch.setitem(sys.modules, "config.settings", settings)
    monkeypatch.setitem(sys.modules, "models.ai_providers", providers)
    output = tmp_path / "source-preflight.json"
    monkeypatch.setattr(sys, "argv", [str(script), "--experiment", "source-ab", "--provider", "deepseek",
                                      "--live", "--today", TODAY.isoformat(), "--output", str(output)])
    assert cli.main() == 2
    report = json.loads(output.read_text())
    assert report["total"] == report["error_trials"] == 4
    assert report["calls_used"] == 0 and report["call_limit"] == 16
    assert report["verdict"] == "inconclusive"
    assert [row["variant"] for row in report["results"]] == ["before", "after", "after", "before"]
