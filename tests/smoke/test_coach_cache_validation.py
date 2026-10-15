"""Offline protocol boundaries for final live cache-condition validation."""
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

from services.coach_runtime_eval import CallBudget, run_cache_validation
from tests.evals.coach.runtime_registry import (
    COMPACT_CONTRACT, build_cache_validation_database, build_cache_validation_schedule,
)

pytestmark = pytest.mark.smoke
TODAY = date(2026, 10, 15)


class ValidationProvider:
    model = "scripted-cache-validation"

    def __init__(self, *, fail=False, wrong_target=False, long=False, bad_empty=False):
        self.calls = 0
        self.fail = fail
        self.wrong_target = wrong_target
        self.long = long
        self.bad_empty = bad_empty

    def is_available(self):
        return True

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        self.calls += 1
        if self.fail:
            return {"text": "Ошибка провайдера", "tool_calls": []}
        if any(row["role"] == "tool" for row in messages):
            return {"text": "Данные получены", "tool_calls": []}
        question = messages[0]["content"]
        case = next(case for case in build_cache_validation_schedule(TODAY)
                    if question.startswith(case.scenario.prompt))
        activity_id = "syn-bike-cached" if self.wrong_target else case.activity_id
        return {"tool_calls": [{"id": "validation-1", "name": "get_activity_structure",
                                "arguments": {"activity_id": activity_id}}]}

    def generate_response(self, prompt, system_prompt=""):
        self.calls += 1
        assert COMPACT_CONTRACT["prompt_suffix"] in prompt
        if "Синтетика — анализ без отрезков" in prompt and not self.bad_empty:
            answer = "Анализ сессии не нашёл отрезков. Это подтверждённая пустая структура."
        elif "Синтетика — вело с кэшем" in prompt:
            answer = "Факт: 11:00 при 128 Вт и 2:00 при 198 Вт."
        else:
            answer = "Структура недоступна: отрезки ещё не получены в кэш."
        return answer + (" Подробности" * 90 if self.long else "")


def test_fixed_four_turns_preserve_three_states_and_policy_exposure():
    report = run_cache_validation(ValidationProvider(), today=TODAY)
    assert report["total"] == 4 and report["calls_used"] == 12
    assert report["call_limit"] == 16
    assert report["verdict"] == "pending_manual" and report["automated_gate"] == "pass"
    assert report["protocol_valid"]
    assert [row["expected_structure_status"] for row in report["results"]] == [
        "unavailable", "structured", "empty", "unavailable"]
    assert [row["repeat"] for row in report["results"]] == [1, 1, 1, 2]
    assert len({row["snapshot_before"] for row in report["results"]}) == 1
    assert all(row["database_unchanged"] for row in report["results"])
    assert all(all(row["protocol_checks"].values()) for row in report["results"])
    assert report["shared_guardrails_sha256"]
    for row in report["results"]:
        activity = row["tool_results"][0]["raw_result"]["activities"][0]
        assert activity["activity_id"] == row["expected_activity_id"]
        assert activity["structure_status"] == row["expected_structure_status"]
        formatted = row["tool_results"][0]["formatted_result"]
        assert formatted == row["provider_trace"][1]["request"]["messages"][-1]["content"]
        assert formatted in row["provider_trace"][2]["request"]["prompt"]


def test_canonical_fixture_has_coherent_cached_missing_and_analyzed_empty(tmp_path):
    from models.ai_tools import AITools
    database = build_cache_validation_database(tmp_path / "validation.db", TODAY)
    tools = AITools(database)
    for case in build_cache_validation_schedule(TODAY):
        activity = tools.get_activity_structure(activity_id=case.activity_id)["activities"][0]
        assert activity["structure_status"] == case.expected_status
        assert activity["date"] == case.scenario.target_date.isoformat()
    empty = database.get_activity_intervals("syn-run-empty")
    assert empty["analyzed"] and empty["intervals"] == []
    assert database.get_activity_intervals("syn-run-uncached") is None
    bike = database.get_activity("syn-bike-cached")
    intervals = database.get_activity_intervals("syn-bike-cached")["intervals"]
    assert bike["duration_minutes"] * 60 == sum(row["moving_time"] for row in intervals)
    assert bike["distance_km"] == pytest.approx(sum(row["distance_km"] for row in intervals))
    assert database.get_activity("syn-run-empty")["avg_power"] is None


def test_verification_observation_preserves_clean_first_answers():
    report = run_cache_validation(ValidationProvider(), today=TODAY)
    for row in report["results"]:
        observation = row["answer_verification"]
        assert observation["version"] == "coach_answer_verification_observation_v1"
        assert observation["initial_answer"] == row["final_answer"]
        assert observation["initial_gate"] == row["narrative_gate"]
        assert observation["correction_attempted"] is False
        assert observation["correction_trace_indices"] == []
        assert observation["correction_calls"] == observation["correction_provider_elapsed_ms"] == 0
        assert observation["verification_elapsed_ms"] >= 0
        assert observation["fallback_delivered"] is False


class RejectedEmptyProvider(ValidationProvider):
    def __init__(self, corrected):
        super().__init__()
        self.corrected = corrected

    def generate_response(self, prompt, system_prompt=""):
        if "Синтетика — анализ без отрезков" in prompt:
            self.calls += 1
            if "ВАЖНО — ИСПРАВЛЕНИЕ:" in prompt:
                return self.corrected
            return "Проверка карточки активности подтвердит гипотезу об отрезках. private-token"
        return super().generate_response(prompt, system_prompt)


@pytest.mark.parametrize("corrected,fallback,error", [
    ("Анализ сохранённых данных не нашёл отрезков.", False, False),
    ("Проверка карточки подтвердит гипотезу об отрезках.", True, False),
    ("Ошибка провайдера", True, True),
])
def test_verification_observation_distinguishes_correction_and_fallback(corrected, fallback, error):
    report = run_cache_validation(RejectedEmptyProvider(corrected), today=TODAY, secrets=("private-token",))
    empty = next(row for row in report["results"] if row["expected_structure_status"] == "empty")
    observation = empty["answer_verification"]
    assert "private-token" not in json.dumps(report)
    assert "[REDACTED]" in observation["initial_answer"]
    assert observation["initial_gate"]["outcome"] == "replaced"
    assert observation["correction_attempted"] is True
    assert observation["correction_calls"] == 1
    assert observation["correction_trace_indices"] == [3]
    trace = empty["provider_trace"][3]
    assert observation["correction_provider_elapsed_ms"] == trace["elapsed_ms"]
    assert observation["verification_elapsed_ms"] >= observation["correction_provider_elapsed_ms"] - 1
    assert observation["fallback_delivered"] is fallback
    assert empty["narrative_gate"]["outcome"] == ("replaced" if fallback else "pass")
    assert report["calls_used"] == 13
    assert report["error_trials"] == int(error)
    # Existing lexical empty predicate misses the factual fallback's
    # "не выявил" wording. Keep it unchanged and expose the false negative.
    assert empty["status"] == ("error" if error else "fail" if fallback else "pass")
    if fallback and not error:
        assert empty["acceptance_checks"]["analyzed_empty_acknowledged"] is False
        assert "анализ сохранённых данных не выявил отрезков" in empty["final_answer"]


def test_soft_data_gap_is_not_reported_as_a_factual_fallback():
    class SoftGapProvider(ValidationProvider):
        def generate_response(self, prompt, system_prompt=""):
            if "Синтетика — анализ без отрезков" in prompt:
                self.calls += 1
                return "Восстановление плохое — нагрузку нужно снизить."
            return super().generate_response(prompt, system_prompt)
    report = run_cache_validation(SoftGapProvider(), today=TODAY)
    empty = report["results"][2]
    assert empty["narrative_gate"]["outcome"] == "data_gap"
    assert empty["final_answer"] == empty["answer_verification"]["initial_answer"]
    assert empty["answer_verification"]["fallback_delivered"] is False


def test_verification_observation_retains_cap_interruption_and_denominator():
    report = run_cache_validation(RejectedEmptyProvider("unused"), today=TODAY, budget=CallBudget(9))
    empty = report["results"][2]
    observation = empty["answer_verification"]
    assert observation["correction_attempted"] is True
    assert observation["correction_calls"] == 0
    assert observation["correction_trace_indices"] == []
    assert observation["fallback_delivered"] is True
    assert empty["error_kind"] == "CallLimitError"
    assert report["results"][3]["answer_verification"] == {}
    assert report["total"] == 4 and report["calls_used"] == 9
    assert report["verdict"] == "inconclusive"


def test_failures_and_global_cap_keep_complete_denominator():
    provider = ValidationProvider(fail=True)
    report = run_cache_validation(provider, today=TODAY)
    assert report["total"] == report["error_trials"] == 4
    assert report["calls_used"] == provider.calls == 4
    assert report["verdict"] == "inconclusive"
    capped = run_cache_validation(ValidationProvider(), today=TODAY, budget=CallBudget(2))
    assert capped["total"] == capped["error_trials"] == 4
    assert capped["calls_used"] == 2
    with pytest.raises(ValueError):
        run_cache_validation(ValidationProvider(), today=TODAY, budget=CallBudget(17))
    with pytest.raises(ValueError):
        run_cache_validation(ValidationProvider(), today=TODAY, repeats=1)


def test_wrong_activity_cannot_establish_protocol_compliance():
    report = run_cache_validation(ValidationProvider(wrong_target=True), today=TODAY)
    assert report["protocol_valid"] is False
    assert report["verdict"] == "inconclusive"
    assert sum(row["protocol_checks"]["activity_evidence_exposed"] for row in report["results"]) == 1


def test_empty_cannot_be_substituted_by_missing_cache_and_length_is_diagnostic():
    report = run_cache_validation(ValidationProvider(bad_empty=True), today=TODAY)
    empty = next(row for row in report["results"] if row["expected_structure_status"] == "empty")
    assert empty["acceptance_checks"]["analyzed_empty_acknowledged"] is False
    assert report["automated_gate"] == "fail"
    long = run_cache_validation(ValidationProvider(long=True), today=TODAY)
    assert all(not row["checks"]["brief_answer"] for row in long["results"])
    assert long["automated_gate"] == "pass"
    assert long["verdict"] == "pending_manual"


def test_calendar_shift_stops_calls_and_keeps_four_trials(monkeypatch):
    import models.ai_coach_runtime as runtime

    class ChangingProvider(ValidationProvider):
        def generate_with_tools(self, messages, tools, system_prompt=""):
            result = super().generate_with_tools(messages, tools, system_prompt)
            monkeypatch.setattr(runtime, "_today_context_line", lambda today=None: "Сегодня: shifted")
            return result

    report = run_cache_validation(ChangingProvider(), today=TODAY)
    assert report["calls_used"] == 3 and report["error_trials"] == 3
    assert report["total"] == 4 and report["verdict"] == "inconclusive"


def test_cli_fixed_schedule_preflight_and_exclusive_output(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/run_coach_runtime_eval.py"
    output = tmp_path / "validation.json"
    command = [sys.executable, str(script), "--experiment", "cache-validation", "--provider", "scripted",
               "--today", TODAY.isoformat(), "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 1, first.stdout + first.stderr
    report = json.loads(output.read_text())
    assert report["total"] == 4 and report["call_limit"] == 16
    assert report["automated_gate"] == "pass" and report["verdict"] == "pending_manual"
    original = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == original
    assert subprocess.run(command + ["--repeats", "1"], capture_output=True).returncode == 2

    from scripts import run_coach_runtime_eval as cli
    settings = ModuleType("config.settings")
    settings.Settings = type("Missing", (), {"DEEPSEEK_API_KEY": ""})
    providers = ModuleType("models.ai_providers")
    providers.DeepSeekProvider = lambda **kwargs: pytest.fail("no provider on missing credential")
    monkeypatch.setitem(sys.modules, "config.settings", settings)
    monkeypatch.setitem(sys.modules, "models.ai_providers", providers)
    output = tmp_path / "preflight.json"
    monkeypatch.setattr(sys, "argv", [str(script), "--experiment", "cache-validation", "--provider", "deepseek",
                                      "--live", "--today", TODAY.isoformat(), "--output", str(output)])
    assert cli.main() == 2
    report = json.loads(output.read_text())
    assert report["total"] == report["error_trials"] == 4
    assert report["calls_used"] == 0 and report["call_limit"] == 16
    assert report["verdict"] == "inconclusive"
    assert len(report["schedule"]) == 4 and report["registry_version"]
