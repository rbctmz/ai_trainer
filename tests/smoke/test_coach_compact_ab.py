"""Offline checks for a frozen paired compact-contract experiment (#528)."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

import pytest

from services.coach_runtime_eval import run_comparison
from tests.evals.coach.runtime_registry import (
    COMPACT_CONTRACT,
    build_comparison_database,
    build_comparison_scenarios,
)

pytestmark = pytest.mark.smoke
TODAY = date(2026, 10, 13)


class PairedProvider:
    model = "scripted-paired"

    def __init__(self, *, fail=False, correction=False):
        self.requests = []
        self.fail = fail
        self.correction = correction
        self.synthesis_calls = 0

    def is_available(self):
        return True

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.requests.append(messages[0]["content"])
        if self.fail:
            return {"text": "Ошибка провайдера", "tool_calls": []}
        if any(m["role"] == "tool" for m in messages):
            return {"text": "Данные получены", "tool_calls": []}
        question = messages[0]["content"]
        scenario = next(s for s in build_comparison_scenarios(TODAY) if question.startswith(s.prompt))
        return {"text": "", "tool_calls": [{"id": "pair-call", "name": scenario.required_tool,
                                            "arguments": {"date": scenario.target_date.isoformat()}}]}

    def generate_response(self, prompt, system_prompt=""):
        self.requests.append(prompt)
        self.synthesis_calls += 1
        if self.correction and self.synthesis_calls == 1:
            return "Сегодня 2025-01-01."
        if "день отдыха" in prompt.split("РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ:")[0]:
            answer = "Плановый день отдыха. Тренировки и интервалов не назначено."
        elif "выполненной беговой" in prompt:
            answer = "Отрезки недоступны: нет кэша. Для структуры нужны выгруженные интервалы."
        elif "выполненной велосессии" in prompt:
            answer = "Факт: 11:00 при 128 Вт и 2:00 при 198 Вт."
        else:
            answer = "План: разминка, основная часть 10×0:30 с восстановлением 2:30 и заминка."
        if COMPACT_CONTRACT["prompt_suffix"] not in prompt:
            answer += " " + "Подробности " * 90
        return answer


def test_paired_report_is_complete_and_candidate_improves_scripted_baseline():
    report = run_comparison(PairedProvider(), today=TODAY, repeats=2)
    assert report["total"] == 16
    assert report["calls_used"] == 48
    assert report["variants"]["current"]["passed"] == 0
    assert report["variants"]["compact"]["passed"] == 8
    assert report["candidate_gate"] == "pass"
    assert report["observed_improvement"] is True
    assert len({r["snapshot_before"] for r in report["results"]}) == 1
    assert all(r["database_unchanged"] for r in report["results"])
    assert [r["variant"] for r in report["results"][:4]] == ["current", "compact", "compact", "current"]
    assert {r["split"] for r in report["results"]} == {"regression", "control"}


def test_contract_reaches_selection_synthesis_and_correction():
    from services.coach_runtime_eval import run_trial
    provider = PairedProvider(correction=True)
    result = run_trial(provider, build_comparison_scenarios(TODAY)[0], today=TODAY,
                       response_contract=COMPACT_CONTRACT,
                       fixture_factory=lambda path: build_comparison_database(path, TODAY))
    assert provider.synthesis_calls == 2
    assert result["error_kind"] is None
    for entry in result["provider_trace"]:
        request = entry["request"]
        user_text = request["messages"][0]["content"] if "messages" in request else request["prompt"]
        assert COMPACT_CONTRACT["prompt_suffix"] in user_text


def test_fixture_summary_matches_interval_totals_and_run_is_plausible(tmp_path):
    database = build_comparison_database(tmp_path / "fixture.db", TODAY)
    bike = database.get_activity("syn-bike-cached")
    intervals = database.get_activity_intervals("syn-bike-cached")["intervals"]
    assert bike["duration_minutes"] * 60 == sum(i["moving_time"] for i in intervals)
    assert bike["distance_km"] == pytest.approx(sum(i["distance_km"] for i in intervals))
    assert database.get_activity("syn-run-uncached")["distance_km"] == 10
    assert database.get_activity("syn-run-uncached")["avg_power"] is None


def test_provider_failures_keep_all_planned_trials():
    report = run_comparison(PairedProvider(fail=True), today=TODAY, repeats=2)
    assert report["total"] == 16
    assert report["error_trials"] == 16
    assert report["verdict"] == "inconclusive"
    assert report["candidate_gate"] == "inconclusive"


def test_global_budget_limits_calls_without_losing_pairs():
    from services.coach_runtime_eval import CallBudget
    report = run_comparison(PairedProvider(), today=TODAY, budget=CallBudget(2))
    assert report["calls_used"] == 2
    assert report["total"] == 16
    assert report["error_trials"] == 16


def test_missing_cache_guarantee_is_replaced_before_scoring_delivery():
    from services.coach_runtime_eval import run_trial

    class GuaranteedProvider(PairedProvider):
        def generate_response(self, prompt, system_prompt=""):
            return "Кэш недоступен. Синхронизируй активность — интервалы появятся."

    result = run_trial(GuaranteedProvider(), build_comparison_scenarios(TODAY)[2], today=TODAY,
                       fixture_factory=lambda path: build_comparison_database(path, TODAY))
    assert result["checks"]["explicit_data_gap"] is True
    assert result["narrative_gate"]["outcome"] == "replaced"
    assert "ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED" in result["narrative_gate"]["reason_codes"]
    assert any("интервалы появятся" in str(entry.get("response")) for entry in result["provider_trace"])
    assert result["checks"]["no_unverified_fetch_promise"] is True
    assert "интервалы появятся" not in result["final_answer"]


def test_short_plan_without_essential_steps_cannot_pass():
    from services.coach_runtime_eval import run_trial

    class EmptyPlanProvider(PairedProvider):
        def generate_response(self, prompt, system_prompt=""):
            return "План: разминка, основная часть и заминка."

    result = run_trial(EmptyPlanProvider(), build_comparison_scenarios(TODAY)[0], today=TODAY,
                       fixture_factory=lambda path: build_comparison_database(path, TODAY))
    assert result["checks"]["essential_facts"] is False
    assert result["status"] == "fail"


def test_cli_comparison_and_preflight_preserve_sixteen_trials(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/run_coach_runtime_eval.py"
    output = tmp_path / "offline-ab.json"
    command = [sys.executable, str(script), "--experiment", "compact-ab", "--provider", "scripted",
               "--today", TODAY.isoformat(), "--output", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["total"] == 16
    assert report["candidate_gate"] == "pass"
    assert report["call_limit"] == 64
    assert report["variants"]["compact"]["total"] == 8
    assert report["candidate_fingerprint"]

    from scripts import run_coach_runtime_eval as cli
    from types import ModuleType
    settings = ModuleType("config.settings")
    settings.Settings = type("Missing", (), {"DEEPSEEK_API_KEY": ""})
    providers = ModuleType("models.ai_providers")
    providers.DeepSeekProvider = lambda **kwargs: pytest.fail("provider must not be constructed")
    monkeypatch.setitem(sys.modules, "config.settings", settings)
    monkeypatch.setitem(sys.modules, "models.ai_providers", providers)
    preflight = tmp_path / "preflight-ab.json"
    monkeypatch.setattr(sys, "argv", [str(script), "--experiment", "compact-ab", "--provider", "deepseek",
                                      "--live", "--today", TODAY.isoformat(), "--output", str(preflight)])
    assert cli.main() == 2
    report = json.loads(preflight.read_text())
    assert report["total"] == 16
    assert report["calls_used"] == 0
    assert report["call_limit"] == 64
    assert report["candidate_gate"] == "inconclusive"
    assert report["variants"]["compact"]["total"] == 8
    assert report["candidate_fingerprint"]


def test_calendar_change_stops_further_provider_calls(monkeypatch):
    import models.ai_coach_runtime as runtime

    class ClockChangingProvider(PairedProvider):
        def generate_with_tools(self, messages, tools, system_prompt=""):
            result = super().generate_with_tools(messages, tools, system_prompt)
            monkeypatch.setattr(runtime, "_today_context_line", lambda today=None: "Сегодня: shifted")
            return result

    report = run_comparison(ClockChangingProvider(), today=TODAY, repeats=2)
    assert report["calls_used"] == 3
    assert report["total"] == 16
    assert report["error_trials"] == 15
    assert report["verdict"] == "inconclusive"
