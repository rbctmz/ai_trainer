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
from collections.abc import Callable

from models.ai_coach_runtime import (
    _today_context_line,
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
from tests.evals.coach.runtime_registry import REPORT_VERSION, RuntimeScenario

ALLOWED_TOOLS = frozenset({
    "get_active_plan", "get_upcoming_workouts",
    "get_workout_structure", "get_activity_structure",
})


class CallLimitError(RuntimeError):
    pass


class ProviderOutputError(RuntimeError):
    pass


class CalendarChangedError(RuntimeError):
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
    def __init__(self, delegate: Any, budget: CallBudget, secrets: tuple[str, ...],
                 calendar_guard: str | None = None):
        self.delegate = delegate
        self.budget = budget
        self.secrets = secrets
        self.trace: list[dict[str, Any]] = []
        self.failure_kind: str | None = None
        self.calendar_guard = calendar_guard

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
        if self.calendar_guard is not None and self.calendar_guard not in system_prompt:
            self.failure_kind = "CalendarChangedError"
            raise CalendarChangedError("comparison native calendar changed before model call")
        return self._call("generate_with_tools", messages=messages, tools=tools,
                          system_prompt=system_prompt)

    def generate_response(self, prompt: str, system_prompt: str = "") -> str:
        return self._call("generate_response", prompt=prompt, system_prompt=system_prompt)


class _ReadOnlyTools:
    def __init__(self, tools: AITools, missing_structure_message: str | None = None):
        self.delegate = tools
        self.denied: list[str] = []
        self.calls = 0
        self.missing_structure_message = missing_structure_message

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [s for s in self.delegate.get_tool_schemas() if s["name"] in ALLOWED_TOOLS]

    def execute_tool(self, tool_name: str, **params: Any) -> dict[str, Any]:
        self.calls += 1
        if tool_name not in ALLOWED_TOOLS or self.calls > 12:
            self.denied.append(tool_name)
            return {"success": False, "error": "tool denied by experiment boundary"}
        outcome = self.delegate.execute_tool(tool_name, **params)
        if (self.missing_structure_message is not None and tool_name == "get_activity_structure"
                and outcome.get("success")):
            outcome = copy.deepcopy(outcome)
            for activity in outcome.get("result", {}).get("activities", []):
                if activity.get("structure_status") == "unavailable" and activity.get("reason") == "not_fetched":
                    activity["message"] = self.missing_structure_message
        return outcome


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
        checks["no_unsupported_power"] = watt_claims <= set(scenario.allowed_power)
    if scenario.requires_data_gap:
        checks["explicit_data_gap"] = bool(re.search(
            r"(?:нет|не хватает|недоступ|отсутств|не выгруж|не загруж|нет.*кэш)", answer, re.I))
        checks["no_invented_interval_table"] = not bool(re.search(r"\|.*\|.*\|", answer))
        checks["no_invented_interval_counts"] = not bool(re.search(
            r"\d+\s*(?:отрезк|повтор|интервал)|(?:отрезк|повтор|интервал)\w*\s*[:—-]\s*\d+",
            answer, re.I))
    if scenario.requires_no_fetch_guarantee:
        checks["no_unverified_fetch_promise"] = not _unverified_fetch_promise(answer)
    if scenario.essential_patterns:
        checks["essential_facts"] = all(re.search(pattern, answer, re.I)
                                         for pattern in scenario.essential_patterns)
    if scenario.requires_rest:
        checks["planned_rest"] = bool(re.search(r"отдых|выходн", answer, re.I))
        checks["no_rest_work_prescription"] = not bool(re.search(
            r"(?:сделай|выполни|проведи|пробеги).*(?:интервал|отрезк|повтор)", answer, re.I))
    elif scenario.required_tool == "get_workout_structure":
        checks["plan_labeled"] = bool(re.search(r"план", answer, re.I))
        checks["plan_structure"] = all(re.search(word, answer, re.I) for word in (
            r"размин", r"(?:основн|интервал|отрезк|работа|повтор)", r"замин"))
    return checks


def _unverified_fetch_promise(answer: str) -> bool:
    """Narrow future-success check, always complemented by human assessment."""
    for sentence in re.split(r"[.!?\n]", answer.lower()):
        if re.search(r"(?:возмож|может|могут|если|не гарант|при условии)", sentence):
            continue
        if re.search(r"интервал|отрезк|структур|кэш", sentence) and re.search(
            r"появятся|появится|попадут|станет доступ|станут доступ|будут доступ|выгрузятся", sentence):
            return True
    return False


def run_trial(provider: Any, scenario: RuntimeScenario, *, today: date,
              repeat: int = 1, budget: CallBudget | None = None,
              secrets: tuple[str, ...] = (), response_contract: dict | None = None,
              fixture_factory: Callable[[Path], Any] | None = None,
              calendar_guard: str | None = None,
              missing_structure_message: str | None = None) -> dict[str, Any]:
    """Один shared-runtime turn, изолированный от product persistence и сети tools."""
    recorder = _RecordingProvider(provider, budget or CallBudget(), secrets, calendar_guard)
    started = time.monotonic()
    answer = ""
    results: list[dict[str, Any]] = []
    error_kind = None
    gate_metadata: dict[str, Any] = {}
    fallback = False
    with TemporaryDirectory(prefix="coach-runtime-eval-") as directory:
        path = Path(directory) / "synthetic.db"
        days = synthetic_fixture_days(today - timedelta(days=4))
        database = (fixture_factory(path) if fixture_factory is not None
                    else build_synthetic_coach_database(path, days))
        before = _snapshot(path)
        tools = _ReadOnlyTools(AITools(database), missing_structure_message)
        goal_plan = restore_goal_plan_from_checkpoint(database.get_latest_planning_checkpoint())
        try:
            turn = resolve_turn_tool_results(
                provider=recorder, ai_tools=tools, user_input=scenario.prompt,
                history_messages=[], tool_result_formatter=format_tool_result, today=today,
                response_contract=response_contract,
            )
            results = turn["tool_results"]
            if not results:
                results = build_grounding_tool_results(tools, format_tool_result)
                fallback = True
            answer = synthesize_ai_chat_response(
                provider=recorder, history_messages=[], user_input=scenario.prompt,
                tool_results=results, goal_plan=goal_plan, today=today,
                response_contract=response_contract,
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
                response_contract=response_contract,
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


def run_comparison(provider: Any, *, today: date, repeats: int = 2,
                   budget: CallBudget | None = None, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Парный прогон с общей fixture, фиксированным suffix и AB/BA порядком."""
    from data.database import Database
    from tests.evals.coach.runtime_registry import (
        COMPACT_CONTRACT, COMPARISON_FIXTURE_VERSION, COMPARISON_REGISTRY_VERSION,
        COMPARISON_REPORT_VERSION, build_comparison_database, build_comparison_scenarios,
    )

    if repeats not in {1, 2}:
        raise ValueError("repeats must be 1 or 2")
    budget = budget or CallBudget(64)
    if not 1 <= budget.limit <= 64:
        raise ValueError("comparison call limit must be between 1 and 64")
    results = []
    native_calendar = _today_context_line()
    with TemporaryDirectory(prefix="coach-compact-paired-") as directory:
        canonical = Path(directory) / "canonical.db"
        build_comparison_database(canonical, today)
        canonical_hash = _snapshot(canonical)

        def clone(path: Path) -> Database:
            with sqlite3.connect(f"file:{canonical}?mode=ro", uri=True) as source:
                with sqlite3.connect(str(path)) as target:
                    source.backup(target)
            return Database(str(path))

        for scenario in build_comparison_scenarios(today):
            for repeat in range(1, repeats + 1):
                order = ("current", "compact") if repeat % 2 else ("compact", "current")
                for variant in order:
                    result = run_trial(
                        provider, scenario, today=today, repeat=repeat, budget=budget,
                        secrets=secrets, fixture_factory=clone,
                        calendar_guard=native_calendar,
                        response_contract=COMPACT_CONTRACT if variant == "compact" else None,
                    )
                    result["variant"] = variant
                    result["word_count"] = len(result["final_answer"].split())
                    result["checks"]["same_canonical_input"] = result["snapshot_before"] == canonical_hash
                    if not result["checks"]["same_canonical_input"] and result["status"] != "error":
                        result["status"] = "fail"
                    results.append(result)
        assert canonical_hash == _snapshot(canonical), "canonical fixture changed"
    variants = {}
    for variant in ("current", "compact"):
        rows = [r for r in results if r["variant"] == variant]
        variants[variant] = {
            "total": len(rows), "passed": sum(r["status"] == "pass" for r in rows),
            "error_trials": sum(r["status"] == "error" for r in rows),
            "brief_answers": sum(r["checks"]["brief_answer"] for r in rows),
            "mean_words": sum(r["word_count"] for r in rows) / len(rows),
        }
    candidate = variants["compact"]
    errors = sum(r["status"] == "error" for r in results)
    candidate_gate = ("inconclusive" if candidate["error_trials"] else
                      ("pass" if candidate["passed"] == candidate["total"] else "fail"))
    return {
        "report_version": COMPARISON_REPORT_VERSION, "registry_version": COMPARISON_REGISTRY_VERSION,
        "fixture_version": COMPARISON_FIXTURE_VERSION, "fixture_hash": canonical_hash,
        "native_calendar": native_calendar,
        "candidate_contract": dict(COMPACT_CONTRACT),
        "candidate_fingerprint": hashlib.sha256(str(sorted(COMPACT_CONTRACT.items())).encode()).hexdigest(),
        "today": today.isoformat(), "provider_class": type(provider).__name__,
        "model": str(getattr(provider, "model", "unknown")), "repeats": repeats,
        "call_limit": budget.limit, "calls_used": budget.used, "total": len(results),
        "passed": sum(r["status"] == "pass" for r in results), "error_trials": errors,
        "variants": variants, "candidate_gate": candidate_gate,
        "verdict": "inconclusive" if errors else candidate_gate,
        "observed_improvement": None if errors else candidate["passed"] > variants["current"]["passed"],
        "human_assessment": "pending", "token_usage": _usage_totals(results), "cost": None,
        "limitations": ["small paired sample, no statistical significance claim",
                        "manual factual/semantic assessment required", "restricted read-only surface"],
        "results": results,
    }


def _source_message_exposed(result: dict, expected_message: str) -> bool:
    """Prove the actual target message reached both model input surfaces."""
    matched = [row for row in result["tool_results"]
               if row.get("tool_name") == "get_activity_structure" and row.get("success")
               and _has_target(row.get("raw_result"), result["target_date"])
               and any(activity.get("structure_status") == "unavailable"
                       and activity.get("reason") == "not_fetched"
                       and activity.get("message") == expected_message
                       for activity in row.get("raw_result", {}).get("activities", []))]
    native = [message.get("content", "") for entry in result["provider_trace"]
              for message in entry["request"].get("messages", [])
              if message.get("role") == "tool" and message.get("name") == "get_activity_structure"]
    synthesis = [entry["request"]["prompt"] for entry in result["provider_trace"]
                 if entry["method"] == "generate_response"]
    return (bool(matched) and all(expected_message in row["formatted_result"] for row in matched)
            and any(expected_message in content for content in native)
            and bool(synthesis) and all(expected_message in prompt for prompt in synthesis))


def run_source_comparison(provider: Any, *, today: date, repeats: int = 2,
                          budget: CallBudget | None = None,
                          secrets: tuple[str, ...] = ()) -> dict[str, Any]:
    """Exactly four message-only paired turns; truthfulness needs semantic review."""
    from data.database import Database
    from models.ai_tools import _ACTIVITY_STRUCTURE_MESSAGES
    from tests.evals.coach.runtime_registry import (
        COMPACT_CONTRACT, SOURCE_BEFORE_MESSAGE, build_comparison_database,
        build_source_scenario, source_report_metadata,
    )

    if repeats != 2:
        raise ValueError("source comparison requires exactly 2 repeats")
    budget = budget or CallBudget(16)
    if not 1 <= budget.limit <= 16:
        raise ValueError("source comparison call limit must be between 1 and 16")
    after_message = _ACTIVITY_STRUCTURE_MESSAGES["not_fetched"]
    if after_message == SOURCE_BEFORE_MESSAGE:
        raise ValueError("source comparison requires distinct before/after messages")
    scenario = build_source_scenario(today)
    native_calendar = _today_context_line()
    results = []
    with TemporaryDirectory(prefix="coach-source-paired-") as directory:
        canonical = Path(directory) / "canonical.db"
        build_comparison_database(canonical, today)
        canonical_hash = _snapshot(canonical)

        def clone(path: Path) -> Database:
            with sqlite3.connect(f"file:{canonical}?mode=ro", uri=True) as source:
                with sqlite3.connect(str(path)) as target:
                    source.backup(target)
            return Database(str(path))

        for repeat in (1, 2):
            order = ("before", "after") if repeat == 1 else ("after", "before")
            for variant in order:
                message = SOURCE_BEFORE_MESSAGE if variant == "before" else after_message
                result = run_trial(
                    provider, scenario, today=today, repeat=repeat, budget=budget, secrets=secrets,
                    fixture_factory=clone, calendar_guard=native_calendar,
                    response_contract=COMPACT_CONTRACT,
                    missing_structure_message=SOURCE_BEFORE_MESSAGE if variant == "before" else None,
                )
                result.update({"variant": variant, "word_count": len(result["final_answer"].split()),
                               "source_message_sha256": hashlib.sha256(message.encode()).hexdigest()})
                result["protocol_checks"] = {
                    "selected_target_tool": result["checks"]["required_tool"],
                    "allowed_tools_only": result["checks"]["allowed_tools_only"],
                    "database_unchanged": result["database_unchanged"],
                    "same_canonical_input": result["snapshot_before"] == canonical_hash,
                    "message_exposed": _source_message_exposed(result, message),
                }
                result["truthfulness_checks"] = {key: result["checks"][key] for key in (
                    "explicit_data_gap", "no_invented_interval_table", "no_invented_interval_counts",
                    "no_unverified_fetch_promise")}
                if result["status"] != "error":
                    result["status"] = ("pass" if all(result["protocol_checks"].values())
                                        and all(result["truthfulness_checks"].values()) else "fail")
                results.append(result)
        assert canonical_hash == _snapshot(canonical), "canonical fixture changed"
    errors = sum(row["status"] == "error" for row in results)
    protocol_valid = not errors and all(all(row["protocol_checks"].values()) for row in results)
    variants = {}
    for variant in ("before", "after"):
        rows = [row for row in results if row["variant"] == variant]
        variants[variant] = {
            "total": len(rows), "passed": sum(row["status"] == "pass" for row in rows),
            "error_trials": sum(row["status"] == "error" for row in rows),
            "brief_answers": sum(row["checks"]["brief_answer"] for row in rows),
            "mean_words": sum(row["word_count"] for row in rows) / len(rows),
        }
    automated_gate = ("inconclusive" if not protocol_valid else
                      "pass" if variants["after"]["passed"] == 2 else "fail")
    return {
        **source_report_metadata(after_message), "fixture_hash": canonical_hash,
        "native_calendar": native_calendar, "today": today.isoformat(), "repeats": repeats,
        "provider_class": type(provider).__name__, "model": str(getattr(provider, "model", "unknown")),
        "call_limit": budget.limit, "calls_used": budget.used, "total": len(results),
        "passed": sum(row["status"] == "pass" for row in results), "error_trials": errors,
        "protocol_valid": protocol_valid, "variants": variants, "automated_gate": automated_gate,
        "verdict": "pending_manual" if protocol_valid else "inconclusive",
        "human_assessment": "pending", "token_usage": _usage_totals(results), "cost": None,
        "limitations": ["two repeats per variant, no causal or statistical significance claim",
                        "lexical checks are diagnostics; semantic assessment of all four answers required",
                        "restricted read-only shared runtime; not full API/SSE or coaching validation"],
        "results": results,
    }


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
