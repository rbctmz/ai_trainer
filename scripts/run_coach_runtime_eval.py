#!/usr/bin/env python3
"""Run the bounded #528 experiment; explicit live opt-in, synthetic data only."""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ScriptedRuntimeProvider:
    """Offline plumbing probe, deliberately not evidence of model quality."""

    model = "scripted-runtime-probe"

    def is_available(self):
        return True

    def supports_native_tools(self):
        return True

    def generate_with_tools(self, messages, tools, system_prompt=""):
        if any(m["role"] == "tool" for m in messages):
            return {"text": "Данные получены", "tool_calls": []}
        question = messages[-1]["content"]
        name = "get_workout_structure" if "плановой" in question else "get_activity_structure"
        day = re.search(r"\d{4}-\d{2}-\d{2}", question).group()
        return {"text": "", "tool_calls": [{"id": "offline-call", "name": name,
                                            "arguments": {"date": day}}]}

    def generate_response(self, prompt, system_prompt=""):
        if "выполненной беговой" in prompt:
            return "Структура недоступна: отрезки не выгружены. Нужен кэш отрезков."
        if "выполненной велосессии" in prompt:
            return "Факт: два отрезка со средней мощностью 128 Вт и 198 Вт."
        return "План: разминка, основная часть и заминка. Это плановая велосессия."


def _inconclusive_report(args, error_kind, calls_used=0):
    # This lightweight registry imports no settings/provider dependencies.
    from tests.evals.coach.runtime_registry import REGISTRY_VERSION, REPORT_VERSION, build_scenarios
    results = [{"scenario_id": scenario.scenario_id, "split": scenario.split,
                "repeat": repeat, "prompt": scenario.prompt,
                "target_date": scenario.target_date.isoformat(),
                "status": "error", "error_kind": error_kind, "checks": {},
                "final_answer": "", "provider_trace": [], "tool_results": [],
                "database_unchanged": None}
               for scenario in build_scenarios(args.today) for repeat in range(1, args.repeats + 1)]
    return {"report_version": REPORT_VERSION, "registry_version": REGISTRY_VERSION,
            "mode": "live" if args.live else "scripted", "provider": args.provider,
            "model": os.environ.get("DEEPSEEK_MODEL", "unresolved"),
            "today": args.today.isoformat(), "repeats": args.repeats,
            "total": len(results), "passed": 0, "error_trials": len(results), "pass_rate": 0.0,
            "threshold": 1.0, "verdict": "inconclusive", "call_limit": 24,
            "calls_used": calls_used, "error_kind": error_kind, "results": results,
            "human_assessment": "not_run", "property_rates": {}, "token_usage": None, "cost": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True, choices=("scripted", "deepseek"))
    parser.add_argument("--today", required=True, type=date.fromisoformat)
    parser.add_argument("--repeats", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.provider != "scripted" and not args.live:
        parser.error("real providers require explicit --live")
    if args.provider == "scripted" and (args.live or args.env_file):
        parser.error("scripted mode needs neither --live nor credentials")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        artifact = args.output.open("x", encoding="utf-8")
    except FileExistsError:
        print("Output already exists; no calls made.", file=sys.stderr)
        return 2
    with artifact:
        budget = None
        base_sha = None
        try:
            base_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            secrets = ()
            if args.provider == "deepseek":
                if args.env_file:
                    from dotenv import dotenv_values
                    if not args.env_file.is_file():
                        raise ValueError("explicit env file missing")
                    values = dotenv_values(args.env_file)
                    # Only AI settings: never import athlete/provider/DB config.
                    for key in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL"):
                        if values.get(key):
                            os.environ[key] = values[key]
                from config.settings import Settings
                from models.ai_providers import DeepSeekProvider

                class ExperimentSettings(Settings):
                    AI_RESPONSE_MAX_TOKENS = 1800
                    AI_DEEPSEEK_THINKING = False

                if not Settings.DEEPSEEK_API_KEY:
                    raise ValueError("selected provider is not configured")
                provider = DeepSeekProvider(settings=ExperimentSettings)
                if not provider.is_available() or provider.client is None:
                    raise ValueError("selected provider is unavailable")
                provider.client = provider.client.with_options(timeout=45.0, max_retries=0)
                secrets = (Settings.DEEPSEEK_API_KEY,)
                original_create = provider.client.chat.completions.create

                def record_usage(**request):
                    provider.last_usage = None
                    response = original_create(**request)
                    usage = getattr(response, "usage", None)
                    if usage is not None:
                        provider.last_usage = {key: getattr(usage, key, None) for key in (
                            "prompt_tokens", "completion_tokens", "total_tokens")}
                    return response

                provider.client.chat.completions.create = record_usage
            else:
                provider = ScriptedRuntimeProvider()
            from services.coach_runtime_eval import CallBudget, run_experiment
            budget = CallBudget()
            report = run_experiment(provider, today=args.today, repeats=args.repeats,
                                    secrets=secrets, budget=budget)
            report["mode"] = "live" if args.live else "scripted"
            report["base_sha"] = base_sha
            report["budgets"] = {"max_provider_calls": 24, "max_calls_per_trial": 4,
                                  "max_tool_calls_per_trial": 12, "max_output_tokens_per_call": 1800,
                                  "sdk_timeout_seconds": 45, "sdk_retries": 0}
            json.dump(report, artifact, ensure_ascii=False, indent=2)
            artifact.write("\n")
            print(f"{report['verdict']}: {report['passed']}/{report['total']} trials; "
                  f"{report['error_trials']} errors; {report['calls_used']}/24 provider calls")
            return 2 if report["error_trials"] else (0 if report["verdict"] == "pass" else 1)
        except Exception as exc:
            report = _inconclusive_report(args, type(exc).__name__, budget.used if budget else 0)
            report["base_sha"] = base_sha
            json.dump(report, artifact, ensure_ascii=False, indent=2)
            print(f"Experiment inconclusive: {type(exc).__name__}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
