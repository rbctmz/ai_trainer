"""Offline regressions for the bounded live Coach experiment (#528)."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from services.coach_runtime_eval import CallBudget, run_experiment, run_trial
from tests.evals.coach.runtime_registry import build_scenarios

pytestmark = pytest.mark.smoke
TODAY = date(2026, 10, 13)


class ScriptedProvider:
    model = "scripted-test"

    def __init__(self, tool=None, answer=None, error=False):
        self.tool = tool
        self.answer = answer
        self.error = error
        self.calls = 0

    def is_available(self):
        return True

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.calls += 1
        if self.error:
            return {"text": "Ошибка DeepSeekProvider: private-key", "tool_calls": []}
        if any(message["role"] == "tool" for message in messages):
            return {"text": "Готово", "tool_calls": []}
        question = messages[0]["content"]
        scenario = next(s for s in build_scenarios(TODAY) if s.prompt == question)
        return {"text": "", "tool_calls": [{
            "id": "call-1", "name": self.tool or scenario.required_tool,
            "arguments": {"date": scenario.target_date.isoformat()},
        }]}

    def generate_response(self, prompt, system_prompt=""):
        self.calls += 1
        if self.answer is not None:
            return self.answer
        if "выполненной беговой" in prompt:
            return "Отрезки не выгружены, структура недоступна. Нужен кэш отрезков."
        if "выполненной велосессии" in prompt:
            return "Факт: два отрезка, 128 Вт и 198 Вт. Это выполненная велосессия."
        return "План: разминка, основная часть и заминка. Это плановая велотренировка."


def test_real_runtime_executes_tools_and_keeps_fresh_fixture_unchanged():
    report = run_experiment(ScriptedProvider(), today=TODAY, repeats=2)
    assert report["total"] == 6
    assert report["verdict"] == "pass", report["results"]
    assert report["pass_rate"] == 1
    assert report["calls_used"] == 18
    for result in report["results"]:
        assert result["database_unchanged"] is True
        assert result["provider_trace"]
        assert result["tool_results"]
        assert result["final_answer"]
    assert {r["split"] for r in report["results"]} == {"development", "holdout"}


def test_wrong_generated_numbers_fail_even_when_the_tool_data_are_correct():
    result = run_trial(ScriptedProvider(answer="Факт: 999 Вт и 888 Вт."),
                       build_scenarios(TODAY)[1], today=TODAY)
    assert result["status"] == "fail"
    assert result["checks"]["factual_power_anchors"] is False
    assert result["checks"]["required_tool"] is True


def test_missing_cache_cannot_pass_with_invented_intervals():
    result = run_trial(ScriptedProvider(answer="Пробеги 5 отрезков по 400 метров."),
                       build_scenarios(TODAY)[2], today=TODAY)
    assert result["status"] == "fail"
    assert result["checks"]["explicit_data_gap"] is False


def test_denied_mutation_never_runs_and_cannot_pass(monkeypatch):
    from models.ai_tools import AITools
    calls = []

    def trap(*args, **kwargs):
        calls.append(True)
        return {"success": True}

    monkeypatch.setattr(AITools, "repair_plan_day", trap)
    result = run_trial(ScriptedProvider(tool="repair_plan_day"),
                       build_scenarios(TODAY)[0], today=TODAY)
    assert result["status"] == "fail"
    assert result["denied_tools"] == ["repair_plan_day"]
    assert result["database_unchanged"] is True
    assert result["checks"]["allowed_tools_only"] is False
    assert calls == []


@pytest.mark.parametrize("answer", ["", "Ошибка DeepSeekProvider: private-key"])
def test_provider_error_and_empty_answer_are_errors_not_quality_pass(answer):
    result = run_trial(ScriptedProvider(answer=answer),
                       build_scenarios(TODAY)[0], today=TODAY,
                       secrets=("private-key",))
    assert result["status"] == "error"
    assert result["error_kind"] == "ProviderOutputError"
    assert "private-key" not in str(result)


def test_provider_error_stops_trial_before_synthesis():
    provider = ScriptedProvider(error=True)
    result = run_trial(provider, build_scenarios(TODAY)[0], today=TODAY)
    assert result["status"] == "error"
    assert provider.calls == 1


def test_global_budget_prevents_further_calls_and_retains_failed_denominator():
    provider = ScriptedProvider()
    report = run_experiment(provider, today=TODAY, repeats=1, budget=CallBudget(2))
    assert provider.calls == 2
    assert report["total"] == 3
    assert report["pass_rate"] == 0
    assert report["verdict"] == "inconclusive"
    assert all(r["status"] == "error" for r in report["results"])


def test_schemas_hide_all_mutation_tools():
    class InspectProvider(ScriptedProvider):
        def generate_with_tools(self, messages, tools, system_prompt=""):
            names = {tool["name"] for tool in tools}
            assert names == {"get_active_plan", "get_upcoming_workouts",
                             "get_workout_structure", "get_activity_structure"}
            return super().generate_with_tools(messages, tools, system_prompt)
    result = run_trial(InspectProvider(), build_scenarios(TODAY)[0], today=TODAY)
    assert result["status"] == "pass"


def test_quality_failures_count_in_property_denominator():
    report = run_experiment(ScriptedProvider(answer=""), today=TODAY, repeats=1)
    assert report["total"] == 3
    assert report["pass_rate"] == 0
    assert report["error_trials"] == 3
    assert report["property_rates"]["brief_answer"]["total"] == 3


def test_cli_offline_report_and_existing_file_guard(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/run_coach_runtime_eval.py"
    output = tmp_path / "report.json"
    command = [sys.executable, str(script), "--provider", "scripted", "--today", TODAY.isoformat(),
               "--repeats", "1", "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    report = json.loads(output.read_text())
    assert report["mode"] == "scripted"
    assert report["verdict"] == "pass"
    original = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 2
    assert output.read_bytes() == original


def test_cli_requires_explicit_live_flag_before_loading_credentials(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/run_coach_runtime_eval.py"
    result = subprocess.run([sys.executable, str(script), "--provider", "deepseek",
                             "--today", TODAY.isoformat(), "--output", str(tmp_path / "never.json"),
                             "--env-file", str(tmp_path / "absent.env")],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "--live" in result.stderr
    assert not (tmp_path / "never.json").exists()


def test_missing_data_disclaimer_does_not_excuse_invented_counts():
    result = run_trial(ScriptedProvider(answer="Кэш недоступен. Было 5 отрезков по 400 метров."),
                       build_scenarios(TODAY)[2], today=TODAY)
    assert result["checks"]["explicit_data_gap"] is True
    assert result["checks"]["no_invented_interval_counts"] is False
    assert result["status"] == "fail"


def test_unsupported_power_does_not_pass_with_correct_anchors():
    result = run_trial(ScriptedProvider(answer="Факт: 128 Вт, 198 Вт и 999 Вт."),
                       build_scenarios(TODAY)[1], today=TODAY)
    assert result["checks"]["factual_power_anchors"] is True
    assert result["checks"]["no_unsupported_power"] is False
    assert result["status"] == "fail"


def test_cli_missing_configuration_retains_planned_trials(tmp_path, monkeypatch):
    from scripts import run_coach_runtime_eval as cli
    settings_module = ModuleType("config.settings")

    class MissingSettings:
        DEEPSEEK_API_KEY = ""

    settings_module.Settings = MissingSettings
    providers_module = ModuleType("models.ai_providers")

    class NoNetworkProvider:
        def __init__(self, **kwargs):
            raise AssertionError("preflight must not create provider")

    providers_module.DeepSeekProvider = NoNetworkProvider
    monkeypatch.setitem(sys.modules, "config.settings", settings_module)
    monkeypatch.setitem(sys.modules, "models.ai_providers", providers_module)
    output = tmp_path / "missing-provider.json"
    monkeypatch.setattr(sys, "argv", ["run_coach_runtime_eval.py", "--provider", "deepseek",
                                      "--live", "--today", TODAY.isoformat(), "--output", str(output)])
    assert cli.main() == 2
    report = json.loads(output.read_text())
    assert report["total"] == 6
    assert report["error_trials"] == 6
    assert report["calls_used"] == 0
    assert report["registry_version"]
    assert report["base_sha"]
