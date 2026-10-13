"""Ограниченный baseline настоящих ответов Coach на синтетике (#528).

Обвязка shared runtime, не новый production путь. Автоматические предикаты
ограничены; report оставляет отдельную человеческую оценку качества pending.
"""
from __future__ import annotations

import copy
import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from models.ai_coach_runtime import (
    build_grounding_tool_results,
    resolve_turn_tool_results,
    revalidate_with_correction,
    synthesize_ai_chat_response,
)
from models.ai_tools import AITools
from models.coach_narrative_evidence import (
    build_coach_narrative_evidence,
    validate_coach_narrative,
)
from models.coach_tool_presenter import format_tool_result
from models.planning_checkpoints import restore_goal_plan_from_checkpoint
from services.coach_behavioral_eval import (
    CoachEvalCase,
    consistency_not_whole_rejection,
    style_brevity_respected,
)
from services.coach_synthetic_eval import (
    build_synthetic_coach_database,
    synthetic_fixture_days,
)

REPORT_VERSION = "coach_runtime_report_v1"
ALLOWED_TOOLS = frozenset({
    "get_active_plan", "get_upcoming_workouts",
    "get_workout_structure", "get_activity_structure",
})


@dataclass(frozen=True)
class RuntimeScenario:
    """Вопрос и ограниченные свойства ответа, без единственного верного текста."""

    scenario_id: str
    split: str
    target_date: date
    prompt: str
    required_tool: str
    factual_power: tuple[int, ...] = ()
    requires_data_gap: bool = False


class CallLimitError(RuntimeError):
    pass


class ProviderOutputError(RuntimeError):
    pass


@dataclass
class CallBudget:
    limit: int = 24
    used: int = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise CallLimitError("provider call budget exhausted")
        self.used += 1


def _clean(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {str(key): _clean(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item, secrets) for item in value]
    return value


def _invalid_output(output: Any) -> bool:
    text = str(output.get("text") or "") if isinstance(output, dict) else str(output or "")
    if isinstance(output, dict) and output.get("tool_calls"):
        return False
    return not text.strip() or text.startswith(("Ошибка", "Error")) or any(
        phrase in text for phrase in ("ответ не получен", "провайдер не настроен", "клиент не настроен")
    )


class _RecordingProvider:
    def __init__(self, delegate: Any, budget: CallBudget, secrets: tuple[str, ...]):
        self.delegate = delegate
        self.budget = budget
        self.secrets = secrets
        self.trace: list[dict[str, Any]] = []
        self.failure_kind: str | None = None

    def is_available(self) -> bool:
        return bool(self.delegate.is_available())

    def supports_native_tools(self) -> bool:
        return bool(self.delegate.supports_native_tools())

    def _call(self, method: str, **request: Any) -> Any:
        if len(self.trace) >= 4:
            self.failure_kind = "CallLimitError"
            raise CallLimitError("trial call budget exhausted")
        try:
            self.budget.consume()
        except CallLimitError:
            self.failure_kind = "CallLimitError"
            raise
        entry = {"method": method, "request": _clean(copy.deepcopy(request), self.secrets)}
        self.trace.append(entry)
        started = time.monotonic()
        try:
            output = getattr(self.delegate, method)(**request)
            if _invalid_output(output):
                raise ProviderOutputError("provider returned no usable output")
            entry["response"] = _clean(copy.deepcopy(output), self.secrets)
            entry["usage"] = getattr(self.delegate, "last_usage", None)
            return output
        except Exception as exc:
            # SDK/provider exception messages can contain URLs or credentials.
            entry["error_kind"] = type(exc).__name__
            self.failure_kind = type(exc).__name__
            raise
        finally:
            entry["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)

    def generate_with_tools(self, messages: list, tools: list, system_prompt: str = "") -> dict:
        return self._call("generate_with_tools", messages=messages, tools=tools,
                          system_prompt=system_prompt)

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        return self._call("generate_response", prompt=prompt, system_prompt=system_prompt)


class _ReadOnlyTools:
    def __init__(self, tools: AITools):
        self.delegate = tools
        self.denied: list[str] = []
        self.calls = 0

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [s for s in self.delegate.get_tool_schemas() if s["name"] in ALLOWED_TOOLS]

    def execute_tool(self, tool_name: str, **params: Any) -> dict[str, Any]:
        self.calls += 1
        if tool_name not in ALLOWED_TOOLS or self.calls > 12:
            self.denied.append(tool_name)
            return {"success": False, "error": "tool denied by experiment boundary"}
        return self.delegate.execute_tool(tool_name, **params)


def _snapshot(path: Path) -> str:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return hashlib.sha256("\n".join(connection.iterdump()).encode()).hexdigest()


def _has_target(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return any((key == "date" and str(item)[:10] == target) or _has_target(item, target)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_has_target(item, target) for item in value)
    return False


def _checks(scenario: RuntimeScenario, answer: str, results: list[dict],
            tools: _ReadOnlyTools, unchanged: bool, trace: list[dict]) -> dict[str, bool]:
    case = CoachEvalCase(scenario.scenario_id, scenario.scenario_id, "runtime", (),
                         {}, scenario.prompt, answer, "pass")
    selected = {
        call.get("name") for entry in trace
        if isinstance(entry.get("response"), dict)
        for call in entry["response"].get("tool_calls", [])
    }
    target_results = [r for r in results if r.get("tool_name") == scenario.required_tool
                      and r.get("success") and _has_target(r.get("raw_result"), scenario.target_date.isoformat())]
    checks = {
        "required_tool": bool(target_results) and scenario.required_tool in selected,
        "allowed_tools_only": not tools.denied,
        "database_unchanged": unchanged,
        "brief_answer": bool(answer.strip()) and style_brevity_respected(case).passed,
        "useful_answer": bool(answer.strip()) and consistency_not_whole_rejection(case).passed,
    }
    if scenario.factual_power:
        checks["factual_power_anchors"] = all(
            re.search(rf"(?<!\d){number}(?:[.,]0+)?(?!\d)", answer) is not None
            for number in scenario.factual_power
        )
        watt_claims = {float(number.replace(",", ".")) for number in re.findall(
            r"(\d+(?:[.,]\d+)?)\s*(?:Вт|ватт\w*|W)\b", answer, re.I)}
        checks["no_unsupported_power"] = watt_claims <= {128, 198, 178}
    if scenario.requires_data_gap:
        checks["explicit_data_gap"] = bool(re.search(
            r"(?:нет|не хватает|недоступн|отсутств|не выгруж|не загруж|нет.*кэш)", answer, re.I))
        checks["no_invented_interval_table"] = not bool(re.search(r"\|.*\|.*\|", answer))
        checks["no_invented_interval_counts"] = not bool(re.search(
            r"\d+\s*(?:отрезк|повтор|интервал)|(?:отрезк|повтор|интервал)\w*\s*[:—-]\s*\d+",
            answer, re.I))
    if scenario.required_tool == "get_workout_structure":
        checks["plan_labeled"] = bool(re.search(r"план", answer, re.I))
        checks["plan_structure"] = all(re.search(word, answer, re.I) for word in (
            r"размин", r"(?:основн|интервал|отрезк|работа|повтор)", r"замин"))
    return checks


def run_trial(provider: Any, scenario: RuntimeScenario, *, today: date,
              repeat: int = 1, budget: CallBudget | None = None,
              secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Один shared-runtime turn, изолированный от product persistence и сети tools."""
    recorder = _RecordingProvider(provider, budget or CallBudget(), secrets)
    started = time.monotonic()
    answer = ""
    results: list[dict[str, Any]] = []
    error_kind = None
    gate_metadata: dict[str, Any] = {}
    fallback = False
    with TemporaryDirectory(prefix="coach-runtime-eval-") as directory:
        path = Path(directory) / "synthetic.db"
        days = synthetic_fixture_days(today - timedelta(days=4))
        database = build_synthetic_coach_database(path, days)
        before = _snapshot(path)
        tools = _ReadOnlyTools(AITools(database))
        goal_plan = restore_goal_plan_from_checkpoint(database.get_latest_planning_checkpoint())
        try:
            turn = resolve_turn_tool_results(
                provider=recorder, ai_tools=tools, user_input=scenario.prompt,
                history_messages=[], tool_result_formatter=format_tool_result, today=today,
            )
            results = turn["tool_results"]
            if not results:
                results = build_grounding_tool_results(tools, format_tool_result)
                fallback = True
            answer = synthesize_ai_chat_response(
                provider=recorder, history_messages=[], user_input=scenario.prompt,
                tool_results=results, goal_plan=goal_plan, today=today,
            )
            evidence = build_coach_narrative_evidence(
                readiness_snapshot={}, tool_results=results, goal_plan=goal_plan,
                athlete_timezone="UTC",
                observed_at_utc=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
            )
            gate = validate_coach_narrative(answer, evidence)
            gate = revalidate_with_correction(
                provider=recorder, gate_result=gate, evidence=evidence,
                history_messages=[], user_input=scenario.prompt, tool_results=results,
                goal_plan=goal_plan, today=today,
            )
            answer, gate_metadata = gate.delivered_text, gate.metadata()
            # Production correction swallows errors; retain them as experiment errors.
            if recorder.failure_kind:
                error_kind = recorder.failure_kind
        except Exception as exc:
            error_kind = type(exc).__name__
        unchanged = before == _snapshot(path)
        checks = _checks(scenario, answer, results, tools, unchanged, recorder.trace)
        if error_kind:
            checks = {key: False for key in checks}
        status = "error" if error_kind else ("pass" if all(checks.values()) else "fail")
        return _clean({
            "scenario_id": scenario.scenario_id, "split": scenario.split, "repeat": repeat,
            "prompt": scenario.prompt, "target_date": scenario.target_date.isoformat(),
            "status": status, "error_kind": error_kind, "checks": checks,
            "final_answer": answer, "provider_trace": recorder.trace, "tool_results": results,
            "denied_tools": tools.denied, "database_unchanged": unchanged,
            "snapshot_before": before, "snapshot_after": _snapshot(path),
            "fallback_used": fallback, "narrative_gate": gate_metadata,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }, secrets)


def run_experiment(provider: Any, *, today: date, repeats: int = 2,
                   budget: CallBudget | None = None, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Конечный прогон с полным знаменателем, включая provider failures."""
    from tests.evals.coach.runtime_registry import REGISTRY_VERSION, build_scenarios

    if repeats not in {1, 2}:
        raise ValueError("repeats must be 1 or 2")
    budget = budget or CallBudget()
    if not 1 <= budget.limit <= 24:
        raise ValueError("call limit must be between 1 and 24")
    results = [run_trial(provider, scenario, today=today, repeat=repeat, budget=budget,
                         secrets=secrets)
               for scenario in build_scenarios(today) for repeat in range(1, repeats + 1)]
    property_rates = {}
    for key in sorted({k for result in results for k in result["checks"]}):
        applicable = [result["checks"][key] for result in results if key in result["checks"]]
        property_rates[key] = {"passed": sum(applicable), "total": len(applicable),
                               "rate": sum(applicable) / len(applicable)}
    errors = sum(r["status"] == "error" for r in results)
    passed = sum(r["status"] == "pass" for r in results)
    return {
        "report_version": REPORT_VERSION, "registry_version": REGISTRY_VERSION,
        "today": today.isoformat(), "provider_class": type(provider).__name__,
        "model": str(getattr(provider, "model", "unknown")), "repeats": repeats,
        "call_limit": budget.limit, "calls_used": budget.used,
        "total": len(results), "passed": passed, "error_trials": errors,
        "pass_rate": passed / len(results), "threshold": 1.0,
        "verdict": "inconclusive" if errors else ("pass" if passed == len(results) else "fail"),
        "property_rates": property_rates, "human_assessment": "pending",
        "token_usage": _usage_totals(results), "cost": None,
        "limitations": ["restricted read-only tool surface", "lexical/numeric checks require human assessment",
                        "not SSE/API orchestration", "not clinical/coaching validation"],
        "results": results,
    }


def _usage_totals(results: list[dict[str, Any]]) -> dict[str, int] | None:
    usages = [entry["usage"] for result in results for entry in result["provider_trace"]
              if entry.get("usage")]
    if not usages:
        return None
    return {key: sum(int(usage.get(key) or 0) for usage in usages)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
