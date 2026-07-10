# Remove FastAPI dependencies on the legacy Streamlit UI

This ExecPlan is a living document. It follows `.agent/PLANS.md`; the sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must remain current while work proceeds.

## Purpose / Big Picture

The FastAPI backend currently imports formatting and dashboard helpers from the legacy Streamlit UI. That reverses the repository's intended dependency direction: the product API can fail to import when Streamlit-only dependencies change, and domain behavior cannot evolve independently of the fallback UI. After this refactor, shared coach presentation and dashboard summary logic will live in headless Python modules. FastAPI and Streamlit will consume the same functions, while existing API responses and rendered Russian text remain unchanged.

## Progress

- [x] (2026-07-10 00:00Z) Read the repository workflow, issue-loop model, web-first ADR, and ExecPlan requirements.
- [x] (2026-07-10 00:00Z) Identified direct `api/` imports from `ui/` in coach and dashboard routers.
- [x] (2026-07-10 00:00Z) Added the coach architecture contract and observed the expected pre-implementation failure: `assert "ui" not in imports`.
- [x] (2026-07-10 00:00Z) Moved coach tool-result formatting to `models/coach_tool_presenter.py`; FastAPI imports it directly and the Streamlit component re-exports it.
- [x] (2026-07-10 00:00Z) Completed self-review and validation on the isolated #147 branch: 43 targeted tests and 441 smoke tests pass, one socket-dependent test is skipped, Python compilation is clean, and Next.js lint/build are green.
- [x] (2026-07-10 00:00Z) Published commit `d08464c` on `codex/issue-147-api-ui-boundary` and opened draft PR #149 closing issue #147.
- [ ] Analyze the dashboard helper dependency graph and repeat the extraction as a separately verifiable milestone.

## Surprises & Discoveries

- Observation: `api/routers/coach.py` imports only one UI symbol, `format_tool_result`, while `api/routers/dashboard.py` imports six private UI helpers.
  Evidence: `rg -n "from ui\\." api --glob '*.py'` returns exactly those two import sites.
- Observation: coach formatting already depends on `utils.product_semantics`, which is a headless shared module.
  Evidence: `ui/components/ai_coach_output.py` imports sport, date, trend, and partial-day labels from that utility.
- Observation: The formatter accepts non-dictionary payloads in fallback branches despite most tool results being mappings.
  Evidence: existing branches explicitly return text for non-dictionary training-status and generic payloads, so the extracted function retains `data: Any` rather than narrowing the runtime contract.

## Decision Log

- Decision: Extract the coach formatter before the dashboard helpers.
  Rationale: It is a single dependency with existing behavioral smoke coverage, so it provides a small independently verifiable milestone and reduces risk before the larger dashboard move.
  Date/Author: 2026-07-10 / Codex.
- Decision: Preserve the existing function signature and output text byte-for-byte.
  Rationale: The change is architectural, not product-facing; changing the SSE/API presentation contract would unnecessarily widen scope.
  Date/Author: 2026-07-10 / Codex.

## Outcomes & Retrospective

The first implementation milestone is complete: the coach API imports no Streamlit UI module, the legacy UI import path remains available, and all repository validation required for this milestone is green. The formatter has one source of truth in `models/coach_tool_presenter.py`; the Streamlit component is now limited to browser speech and simulated streaming helpers. The larger dashboard milestone remains intentionally separate because it involves six coupled private helpers and needs its own contract analysis.

Self-review found no API response, database, concurrency, or security change. The main weakness is that the shared presenter remains large because this milestone moved behavior without redesigning it; splitting individual formatter branches now would combine architectural movement with behavioral refactoring. The current extraction scales better than the old dependency direction because new consumers can import a headless module, but future growth should divide formatter branches by tool domain only when tests demonstrate a maintenance need.

## Context and Orientation

`api/routers/coach.py` implements FastAPI chat endpoints and passes a formatter callback into functions from `models/ai_coach_runtime.py`. The callback currently comes from `ui/components/ai_coach_output.py`, a Streamlit component module. `ui/pages/ai_coaching.py` and `app.py` also expose this formatter for the legacy application. A headless module is ordinary Python code that imports no Streamlit or UI modules and can therefore be used safely by both HTTP and Streamlit entry points.

The web API contract must remain backward-compatible. In this milestone that means the same tool payload produces the same Markdown string and the coach SSE event shapes do not change. No database schema, endpoint path, request model, or web TypeScript type changes are required.

## Plan of Work

First add an architecture test under `tests/smoke/` that parses `api/routers/coach.py` and asserts it has no import rooted at `ui`. Add or adapt behavior tests so representative performance, activity, health, and proposal payloads still produce the existing strings. Run the new architecture test before implementation and record that it fails on the current UI import.

Next create a small headless formatter module under `models/` or `utils/`, choosing the location that best matches its existing dependencies. Move the formatter implementation without changing its public signature. Update `api/routers/coach.py` and the Streamlit component to import the shared implementation. Keep a compatibility re-export from `ui/components/ai_coach_output.py` because existing legacy imports and tests use that path.

Finally run targeted coach tests, all smoke tests, Python compilation, web lint, and the production web build. Inspect the diff for accidental product changes, circular imports, dead code, and formatting drift. Only after the coach milestone is green should the dashboard dependency graph be extracted in the same test-first manner.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_architecture.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_ai_coach_output.py tests/smoke/test_ai_coach_runtime.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m compileall -q api models services data ui
    cd web && npm run lint && npm run build
    git diff --check

Before implementation, the architecture test must fail because `api/routers/coach.py` imports `ui.components.ai_coach_output`. After implementation, it must pass, existing formatter tests must remain green, and the complete smoke suite must pass without live credentials.

## Validation and Acceptance

Given a Python process imports `api.routers.coach`, when its imports are inspected, then no dependency rooted at `ui` is present in that router.

Given an existing tool result such as performance metrics or recent activities, when both the shared formatter and the compatibility import from `ui.components.ai_coach_output` format it, then they return identical Markdown.

Given the coach endpoint processes a tool call, when it emits SSE events, then event names and payload fields remain unchanged and existing runtime smoke tests pass.

Given no external AI or Garmin credentials, when the contributor-safe smoke command runs, then it completes successfully apart from explicitly documented infrastructure skips.

## Idempotence and Recovery

The refactor changes imports and pure formatting code only; it performs no data migration or external write. Tests and build commands are safe to repeat. If a compatibility regression appears, restore the re-export at the legacy UI path while keeping the new shared implementation and use the behavioral tests to isolate the mismatched branch.

## Artifacts and Notes

Baseline before the boundary refactor:

    ai_trainer_env/bin/python -m pytest tests/smoke -q
    441 passed, 1 skipped

    npm run lint
    No ESLint warnings or errors

    npm run build
    Compiled successfully

## Interfaces and Dependencies

The shared module must expose:

    format_tool_result(tool_name: str, data: dict[str, object]) -> str

It may depend on `utils.product_semantics`. It must not import `streamlit`, `ui`, `api`, or web code. `api/routers/coach.py` and `ui/components/ai_coach_output.py` will import this function. The UI module must continue exposing `format_tool_result` so legacy callers remain compatible.

Revision note (2026-07-10 / Codex): initial plan created after repository-wide audit and before adding the architecture contract.

Revision note (2026-07-10 / Codex): updated after the red TDD run and coach formatter extraction to record compatibility behavior and targeted test evidence.

Revision note (2026-07-10 / Codex): updated after self-review and complete validation to close the coach milestone and leave dashboard extraction as the next independently testable milestone.

Revision note (2026-07-10 / Codex): recorded issue #147, published commit `d08464c`, and draft PR #149 so the living plan matches GitHub state.
