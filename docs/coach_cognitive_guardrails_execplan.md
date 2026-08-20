# ExecPlan: issue #465 — cognitive guardrails for the AI coach

This is a living ExecPlan for issue #465, maintained according to
`.agent/PLANS.md`. It is self-contained so a contributor can resume the work
from this file and the current repository tree.

## Purpose / Big Picture

After this change, every primary AI-coach chat path receives the same explicit
epistemic safety rules. The coach must separate observations from hypotheses,
verify relevant metrics before recommending an action, acknowledge missing or
conflicting evidence, and avoid inventing a coherent causal story. A
contributor can observe the behavior contract through deterministic smoke tests
that inspect the system prompts without calling a live AI provider.

This change is a prompt-level guardrail, not a deterministic validator of model
output. It reduces the chance of fabrication but does not prove that every
provider will obey every instruction. No API, database, planning, or web
contract changes.

## Progress

- [x] (2026-08-20) Read issue #465, `.agent/PLANS.md`, the canonical AI feature
  workflow, the ADD 3.0 analysis, ASR catalog, and web-primary ADR.
- [x] (2026-08-20) Located the canonical prompt builders in
  `models/ai_coach_runtime.py` and confirmed the existing focused baseline:
  39 tests passed across `test_ai_coach_runtime.py` and
  `test_coach_decisions.py`.
- [x] (2026-08-20) Added a deterministic prompt-contract test; RED failed on
  the absent `КОГНИТИВНЫЕ GUARDRAILS` header as expected.
- [x] (2026-08-20) Added one shared cognitive-guardrail block to the tool,
  native, synthesis, and compatibility full-context prompt paths.
- [x] (2026-08-20) Updated ASR-REL-2 verification notes; focused suite passed
  55 tests, Ruff and diff-check passed, and the contributor-safe suite passed
  1987 tests with 3 environment/dependency skips and 26 deselections.
- [x] (2026-08-20) Completed file-scoped self-review; no unresolved
  correctness, compatibility, security, or complexity findings remain.

## Surprises & Discoveries

- Observation: native tool calling and legacy marker tool calling already share
  `create_chat_system_prompt_with_tools`; native delegates directly to it.
  Evidence: `models/ai_coach_runtime.py` functions
  `create_chat_system_prompt_with_tools` and `create_native_chat_system_prompt`.
- Observation: the web/API flow uses a second synthesis prompt after tool
  execution, so protecting only the first prompt would leave the final answer
  phase without the same epistemic rules.
  Evidence: `api/routers/coach.py` calls
  `create_chat_synthesis_system_prompt` before final generation.
- Observation: `models/coach_decisions.py` is not an appropriate place for a
  string detector because reliable fabrication detection cannot be reduced to
  deterministic keyword matching.
  Evidence: issue #465 marks that detector optional; no validated output schema
  currently carries observation/inference provenance.
- Observation: the synthesis phase receives tool results but cannot initiate a
  new tool call, so a phase-neutral rule must refer to metrics actually
  obtained through tools instead of commanding another call.
  Evidence: self-review changed “проверь ... через инструменты” to “опирайся на
  ... фактически полученные через инструменты”; all focused and broad tests
  stayed green.

## Decision Log

- Decision: define one private shared prompt block and include it in the tool,
  synthesis, and full-context prompt builders.
  Rationale: one source prevents native, marker, synthesis, and compatibility
  prompt paths from drifting while adding no public interface.
  Date/Author: 2026-08-20 / Codex.
- Decision: test prompt behavior directly with deterministic string assertions
  instead of making an AI call.
  Rationale: a live or mock model response would test provider behavior rather
  than whether the runtime always supplies the safety contract.
  Date/Author: 2026-08-20 / Codex.
- Decision: do not add post-hoc fabrication detection to
  `models/coach_decisions.py`.
  Rationale: keyword classification would create false confidence and is not
  required by acceptance criteria.
  Date/Author: 2026-08-20 / Codex.
- Decision: keep the action guardrail phase-neutral.
  Rationale: the same block is intentionally reused before tool execution and
  during final synthesis, where only previously retrieved evidence is
  available.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

The runtime now injects one five-rule cognitive guardrail into every primary
coach prompt phase. Deterministic tests cover all named failures, required
uncertainty/data-gap language, relevant metric evidence, native and marker
composition, synthesis, compatibility full-context, and a captured mock
provider call. Existing coach decision behavior did not regress.

Validation completed with 55 focused tests and 1987 contributor-safe tests
passing; Ruff and `git diff --check` are clean. The remaining limitation is
intentional and explicit: a prompt is probabilistic guidance, not deterministic
proof that an external model will comply. Structured output enforcement would
be a separate feature.

## Context and Orientation

`models/ai_coach_runtime.py` owns the primary coach chat execution boundary.
`create_chat_system_prompt_with_tools` supplies instructions before native or
marker tool execution. `create_native_chat_system_prompt` delegates to that
builder. `create_chat_synthesis_system_prompt` supplies instructions for the
final user-facing response after tool results are available.
`create_chat_system_prompt` is a compatibility full-context builder in the same
module. The API route `api/routers/coach.py` uses the tool and synthesis phases;
the legacy Streamlit wrapper also imports the shared runtime builder rather
than defining new coaching rules.

A cognitive guardrail is a system-prompt instruction intended to discourage a
known reasoning failure. The five failures in scope are: inference without
verification, saving without commitment, action without consideration,
narrative fabrication, and presenting inference as observation. A guardrail is
not a deterministic enforcement layer and does not authorize plan mutations;
the approval boundary from ADR-0010 remains unchanged.

## ASR / Risk Traceability

ASR-REL-2 is primary: missing or conflicting health and training evidence must
be represented as a data gap or mixed signals, not replaced with an invented
cause. ASR-MOD-1 is preserved because the rule is assembled above provider
adapters and therefore applies equally to all configured AI providers.
ASR-PERF-2 is unchanged because the implementation adds static prompt text and
no extra provider or database call. ADR-0010 remains authoritative for mutation
approval; prompt guidance cannot replace its deterministic proposal gate.

## BDD Scenarios

Given the coach has observed a metric change but not verified a cause, when a
system prompt is assembled, then it instructs the coach to label the cause as
likely or apparent rather than factual.

Given required TSB, readiness, or HRV evidence was not retrieved, when the
coach considers an action, then the prompt requires verification through tools
or an explicit statement that data is insufficient.

Given available signals conflict, when the coach writes the final answer, then
the prompt requires “signals are mixed” and forbids a plausible invented story.

Given the coach mentions an observation and an inference, when it explains its
reasoning, then the prompt requires the two to be distinguished explicitly.

Given the coach says it saved or remembered a decision, when no persistence
tool confirmed a write, then the prompt forbids claiming that commitment.

## Plan of Work

First add a focused smoke test to `tests/smoke/test_ai_coach_runtime.py`. The
test will assemble the tool, synthesis, and full-context prompts and assert the
shared header, the five named anti-patterns, the uncertainty language, the
data-gap language, and the metric-verification rule. Run only that test and
record the expected RED caused by the absent block.

Then add a private module-level string in `models/ai_coach_runtime.py` and
compose it into all three prompt builders. Keep provider interfaces, prompt
function signatures, tools, and response schemas unchanged. Update the
ASR-REL-2 row in `docs/architecture/asr_catalog.md` with the new prompt-level
defense and focused smoke-test evidence.

Finally run the focused runtime and decision tests, Ruff on changed Python
files, the full contributor-safe test command, and `git diff --check`. Update
the living sections with exact evidence and perform a file-scoped self-review.

## Concrete Steps

Run from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_ai_coach_runtime.py \
      tests/smoke/test_coach_decisions.py -q

Before implementation, run the new test by node id and expect it to fail on
the missing guardrail header. After implementation, run:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_ai_coach_runtime.py \
      tests/smoke/test_coach_decisions.py -q
    ai_trainer_env/bin/python -m ruff check \
      models/ai_coach_runtime.py tests/smoke/test_ai_coach_runtime.py
    ai_trainer_env/bin/python -m pytest \
      -m "not live and not debug and not e2e" tests/
    git diff --check

Web lint/build and API contract extraction are not required because no file in
`web/`, `api/`, or the TypeScript contract changes. If scope expands into those
areas, run their mandatory checks before publication.

## Validation and Acceptance

Acceptance requires deterministic proof that every primary prompt phase names
all five failures and includes these behaviors: hypotheses are marked as
uncertain; missing evidence yields “data insufficient”; conflicting evidence
yields “signals are mixed”; narrative fabrication is forbidden; and actions
require actual TSB/readiness/HRV evidence obtained through available tools.
Existing coach-decision tests must remain green. The full contributor-safe
suite and Ruff must pass without new warnings.

The implementation does not claim deterministic compliance by an external
model. That stronger guarantee would require structured output and a separate
validated enforcement design outside issue #465.

## Idempotence and Recovery

The change is static prompt composition and read-only tests. It writes no
database or provider state and can be rerun safely. A normal Git revert removes
the guardrail block and tests. Local `ai_trainer.db-wal` and
`ai_trainer.db-shm` are unrelated pre-existing sidecars and must not be staged,
deleted, or used as validation artifacts.

## Artifacts and Notes

Baseline evidence before the new test: 39 passed in 3.72 seconds for the
focused runtime and decision files. RED evidence for the new node: 1 failed,
with `tools prompt misses: КОГНИТИВНЫЕ GUARDRAILS`. Final focused evidence:
55 passed in 4.54 seconds. Final broad evidence: 1987 passed, 3 skipped, 26
deselected in 67.24 seconds; the three warnings are pre-existing Starlette and
Pydantic deprecations outside this scope. Ruff reported `All checks passed!` and
`git diff --check` was clean.

## Interfaces and Dependencies

No new dependency or public interface is introduced. Existing functions keep
their signatures:

    create_chat_system_prompt_with_tools(ai_tools, data_context=None) -> str
    create_native_chat_system_prompt(ai_tools=None) -> str
    create_chat_synthesis_system_prompt(goal_plan=None) -> str
    create_chat_system_prompt(data_context) -> str

The only new symbol is a private module-level string used by these builders.

Revision note (2026-08-20): initial plan created after architecture and runtime
inspection, before product code changes began.

Revision note (2026-08-20): implementation completed, synthesis wording refined
during self-review, and exact RED/GREEN/focused/broad validation evidence added.
