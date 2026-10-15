"""Offline gate replay of immutable, sanitized historical outputs; no provider."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from models.coach_narrative_evidence import (  # noqa: E402
    ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED,
    build_coach_narrative_evidence,
    validate_coach_narrative,
)

INPUTS = (
    "2026-10-13-coach-runtime-eval/live-baseline.json",
    "2026-10-13-coach-compact-ab/live-comparison.json",
    "2026-10-15-coach-source-ab/live-comparison.json",
    "2026-10-15-coach-final-validation/live-validation.json",
)
IMPLEMENTATION = (
    "models/coach_activity_structure_evidence.py",
    "models/coach_narrative_evidence.py",
    "models/ai_coach_runtime.py",
    "models/ai_tools.py",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replay() -> dict:
    results, hashes = [], {}
    for relative in INPUTS:
        data = (ROOT / "docs/reports" / relative).read_bytes()
        hashes[relative] = sha(data)
        report = json.loads(data)
        anchor = datetime.fromisoformat(report["today"]).replace(tzinfo=timezone.utc)
        for index, row in enumerate(report["results"]):
            evidence = build_coach_narrative_evidence(
                readiness_snapshot={}, tool_results=row["tool_results"],
                athlete_timezone="Europe/Moscow", observed_at_utc=anchor)
            gate = validate_coach_narrative(row["final_answer"], evidence)
            self_check = validate_coach_narrative(gate.delivered_text, evidence)
            results.append({
                "input": relative, "index": index, "scenario_id": row["scenario_id"],
                "variant": row.get("variant"), "repeat": row["repeat"],
                "source_answer_sha256": sha(row["final_answer"].encode()),
                "historical_gate": row["narrative_gate"], "current_gate": gate.metadata(),
                "activity_claim_blocked": ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED in gate.reason_codes,
                "unchanged": gate.delivered_text == row["final_answer"],
                "delivered_text": gate.delivered_text,
                "delivered_self_check": self_check.metadata(),
            })
        assert sha((ROOT / "docs/reports" / relative).read_bytes()) == hashes[relative]
    return {
        "version": "coach_activity_claim_offline_replay_v1", "date": "2026-10-15",
        "base_commit": "f1b03ce", "provider_calls": 0,
        "boundary": "Saved outputs, not fresh model trials or an estimate of live quality. No correction provider invoked.",
        "inputs_sha256": hashes,
        "implementation_sha256": {name: sha((ROOT / name).read_bytes()) for name in IMPLEMENTATION},
        "summary": {"saved_outputs": len(results),
                    "activity_claim_blocked": sum(row["activity_claim_blocked"] for row in results),
                    "unchanged": sum(row["unchanged"] for row in results),
                    "outcomes": dict(Counter(row["current_gate"]["outcome"] for row in results))},
        "results": results,
    }


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("offline-replay.json")
    report = replay()
    with output.open("x") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
