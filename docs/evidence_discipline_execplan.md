# ExecPlan: issue #464 — Evidence Discipline

This is a living ExecPlan for issue #464, maintained according to
`.agent/PLANS.md`. It is self-contained so a contributor can resume the work
from this document and the current repository tree.

## Purpose / Big Picture

After this change, contributors and coding agents must distinguish what was
observed, what was inferred, and what was actually verified whenever they make
a causal claim in an ExecPlan or engineering conclusion. An unverified
hypothesis is visibly marked `NOT YET` instead of being written with the
grammar of a fact. Before naming a bug or root cause, the author runs one cheap
check that could disprove the claim.

The primary coach runtime already received the matching output discipline in
issue #465: its prompt separates “Наблюдение” from “Вывод” and requires honest
data-gap language. Issue #464 does not duplicate or broaden that runtime
behavior; it makes the engineering process use the same evidence boundary.

## Progress

- [x] (2026-08-20) Read issue #464, `.agent/PLANS.md`, the canonical AI feature
  workflow, `AGENTS.md`, `CLAUDE.md`, and the relevant documentation smoke
  tests.
- [x] (2026-08-20) Confirmed the existing focused documentation baseline:
  11 tests passed.
- [x] (2026-08-20) Added the deterministic docs rot-guard; RED produced five
  expected failures across the canonical form, example, workflow, and two
  agent entry points.
- [x] (2026-08-20) Updated `.agent/PLANS.md`, the canonical workflow, and both
  agent entry points with one normative contract and short links.
- [x] (2026-08-20) Focused docs suite passed 16 tests; full Ruff and
  `git diff --check` passed; contributor-safe pytest passed 1992 tests with 3
  environment/dependency skips and 26 deselections.
- [x] (2026-08-20) Completed file-scoped self-review; clarified that the filled
  example is illustrative and strengthened the rot-guard to require the
  falsifying check before the causal claim.
- [x] (2026-08-20) Addressed PR review P1/P2 locally: every discovery now names
  its cheapest falsifying check, the reference plan has its own rot-guard, and
  executable instructions use a checkout-independent repository root. The
  post-review contributor-safe suite passed 1993 tests with 3 skips and 26
  deselections.

## Surprises & Discoveries

- **Observed**: before the #464 edits, `.agent/PLANS.md` asked for
  `Observation` plus `Evidence` without an explicit hypothesis or verification
  status.
  **Inferred**: the baseline process did not enforce a separate, falsifiable
  hypothesis or visible verification state. The cheapest falsifying check was
  to run a docs test requiring all three fields against the preimplementation
  tree; a pass would have rejected this inference.
  **Verified by**: `test_evidence_discipline_docs.py` produced five expected
  failures before the docs changed, including the missing canonical form,
  example, workflow section, and entry-point links.
- **Observed**: issue #465 added prompt-level separation of “Наблюдение” and
  “Вывод” to every primary coach prompt path on merge commit `5967678`.
  **Inferred**: #464 can remain docs-only without weakening that runtime
  boundary. The cheapest falsifying check is to run the existing all-prompts
  guardrail test after the docs change and inspect the branch file list; a test
  failure or a runtime-file diff would reject this inference.
  **Verified by**:
  `test_all_runtime_prompts_include_cognitive_guardrails` passed, and
  `git diff --name-only main...HEAD` listed only the six #464 docs/test files.
- **Observed**: PR review found that this ExecPlan's first three `Inferred`
  entries omitted falsifying checks even though the new repository rule
  required them; the existing five docs tests still passed.
  **Inferred**: the reference plan could normalize violating its own evidence
  contract. The cheapest falsifying check is a rot-guard that parses every
  discovery in this ExecPlan and requires the three fields plus an explicit
  falsifying check.
  **Verified by**: the new self-referential test first failed with
  `reference ExecPlan has no structured discoveries`, then passed after all
  three entries were rewritten with the required fields and checks.

## Decision Log

- Decision: `.agent/PLANS.md` is the normative source for the full three-field
  form; other repository guides link to it and summarize the rule.
  Rationale: duplicating a long template in four files would drift.
  Date/Author: 2026-08-20 / Codex.
- Decision: require `Verified by: NOT YET` for an unverified hypothesis, not an
  empty verification field.
  Rationale: absence is ambiguous, while `NOT YET` makes incomplete evidence
  visible during review.
  Date/Author: 2026-08-20 / Codex.
- Decision: define minimal disproof as one cheap check that could falsify a
  causal claim, and require it before calling something a bug or root cause.
  Rationale: the rule must change claim timing, not merely add documentation
  after a conclusion is already accepted.
  Date/Author: 2026-08-20 / Codex.
- Decision: do not update the ASR catalog or runtime code.
  Rationale: #464 changes engineering evidence process and introduces no new
  runtime quality attribute, API, data, provider, or UI contract.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

Evidence Discipline is now normative in `.agent/PLANS.md`, including the
three-field form, `NOT YET`, one filled example, minimal disproof before claim,
and final-tree verification before close. The canonical workflow applies the
same timing rule to ExecPlans, reviews, and coach conclusions. `AGENTS.md` and
`CLAUDE.md` point to those two sources without duplicating the template.

The RED rot-guard failed in five expected places and now passes. Focused docs,
full contributor-safe tests, Ruff, and diff checks are green. The intentional
limitation remains: documentation and a rot-guard cannot prove that the cited
evidence is scientifically or logically sufficient; human/agent review must
still evaluate evidence quality.

PR review exposed and locally fixed two gaps in this plan itself: its discovery
entries did not name falsifying checks, and its commands assumed the author's
absolute checkout path. A new self-referential rot-guard prevents the first gap
from recurring; the commands now start from a portable repository-root
definition.

## Context and Orientation

`.agent/PLANS.md` defines the mandatory shape of all repository ExecPlans.
`docs/AI_Feature_Development_Workflow.md` defines the canonical SpecDD, BDD,
TDD, implementation, and self-review flow. `AGENTS.md` is the repository entry
point for Codex-style agents; `CLAUDE.md` is the corresponding entry point for
Claude Code. A short rot-guard in `tests/smoke/` can prevent later edits from
silently removing the evidence contract.

In this plan, an observation is a fact directly read or measured, with its
source. An inference is a proposed explanation that goes beyond the observed
fact and names the check that would confirm or refute it. Verification is the
exact check that was actually run and its result; if no check ran, the field is
`NOT YET`. A causal claim is a statement that names a bug, cause, or mechanism,
not merely a description of what happened.

## ASR / Risk Traceability

No runtime ASR changes. The process supports every ASR by making evidence for
quality-attribute conclusions reviewable, but it changes neither the status nor
the verification mechanism of any entry in
`docs/architecture/asr_catalog.md`. Therefore the catalog is intentionally out
of scope.

## BDD Scenarios

Given an ExecPlan discovery contains a measured failure, when the author records
it, then `Observed` names the fact and source, `Inferred` names the hypothesis
and falsifying check, and `Verified by` names the executed check or `NOT YET`.

Given an author suspects a root cause, when one cheap check could disprove it,
then the check is named and run before the text calls the suspicion a bug or
cause.

Given the cheap check contradicts the hypothesis, when the ExecPlan is updated,
then the hypothesis remains an inference and the rejected result is recorded;
it is not rewritten as a confirmed explanation.

Given a coding agent enters through `AGENTS.md` or `CLAUDE.md`, when it prepares
a causal engineering claim, then the guide points it to the Evidence Discipline
section of the canonical workflow and the normative ExecPlan form.

Given the coach runtime describes athlete evidence, when this docs-only change
is applied, then no provider prompt, API contract, or application behavior is
changed; the already merged #465 guardrail remains the runtime boundary.

## Plan of Work

First add `tests/smoke/test_evidence_discipline_docs.py`. It will read the four
process documents and assert that `.agent/PLANS.md` contains the complete
three-field form, definitions, `NOT YET`, one filled example, and the
minimal-disproof timing rule. It will also assert that the workflow and both
agent entry points link the rule to `.agent/PLANS.md` and the canonical
Evidence Discipline section. Run the new file alone and record the expected
RED failures.

Then update `.agent/PLANS.md` in the living-plans guidance and skeleton. Add a
prose-first Evidence Discipline section that defines all three fields, requires
one cheap disproof check before a causal claim, and includes one concrete
filled example. Update `docs/AI_Feature_Development_Workflow.md` with the same
claim-timing rule and a compact form. Add one short guideline to `AGENTS.md`
and `CLAUDE.md` pointing to both canonical sources.

Finally run the new focused test with existing documentation smoke tests, Ruff
on the new Python file, the full contributor-safe suite, and
`git diff --check`. Update this living plan with exact evidence and complete a
file-scoped self-review.

## Concrete Steps

Run from the repository root, meaning the directory that contains `AGENTS.md`,
`.agent/`, `docs/`, and `tests/`:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_evidence_discipline_docs.py -q
    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_evidence_discipline_docs.py \
      tests/smoke/test_architecture_docs.py \
      tests/smoke/test_workflow_issue_linking.py \
      tests/smoke/test_coach_autonomy_boundary_docs.py -q
    ai_trainer_env/bin/python -m ruff check \
      tests/smoke/test_evidence_discipline_docs.py
    ai_trainer_env/bin/python -m pytest \
      -m "not live and not debug and not e2e" tests/
    git diff --check

Web lint/build and API contract extraction are not required because no file in
`web/`, `api/`, or the TypeScript contract changes.

## Validation and Acceptance

Acceptance requires the exact `Observed`, `Inferred`, and `Verified by` form in
`.agent/PLANS.md`; definitions for the source, hypothesis check, executed check,
and `NOT YET`; one filled example; and a minimal-disproof rule that runs before
a bug or cause is named. `AGENTS.md` and `CLAUDE.md` must contain short pointers
to the canonical workflow and `.agent/PLANS.md`. The existing documentation and
full contributor-safe suites must remain green.

The docs cannot mechanically prove that every future author reasons correctly.
The rot-guard proves that the required evidence form and entry-point guidance
remain present; review still evaluates whether the cited evidence is sound.

## Idempotence and Recovery

All changes are documentation plus a read-only file-content smoke test. They do
not touch SQLite, provider data, credentials, or product runtime. Repeated test
runs are safe. A normal Git revert restores the former process.

## Artifacts and Notes

Baseline evidence before the new test: 11 passed in 0.04 seconds across the
existing architecture, workflow-linking, and coach-autonomy documentation
tests. RED evidence: 5 failed in 0.04 seconds because the Evidence Discipline
contract, filled example, workflow section, and entry-point links were absent.
Final focused evidence: 16 passed in 0.05 seconds. Final broad evidence: 1992
passed, 3 skipped, 26 deselected in 66.48 seconds; the three warnings are
pre-existing Starlette and Pydantic deprecations outside this scope. Ruff
reported `All checks passed!` and `git diff --check` was clean.

Review-fix RED/GREEN evidence: the new reference-plan test failed once with
`reference ExecPlan has no structured discoveries`, then passed in 0.02
seconds after the discovery records were corrected. Final post-review evidence:
18 focused tests passed in 0.75 seconds; 1993 contributor-safe tests passed, 3
skipped, and 26 were deselected in 66.17 seconds; Ruff and `git diff --check`
were clean.

## Interfaces and Dependencies

No runtime interface or dependency changes. The process interface added to
`.agent/PLANS.md` is:

    Observed: <fact and source>
    Inferred: <hypothesis and the check that could falsify it>
    Verified by: <executed check and result, or NOT YET>

Revision note (2026-08-20): initial plan created after issue and process-doc
inspection, before documentation edits began.

Revision note (2026-08-20): implementation completed; exact RED/GREEN,
focused/broad validation, illustrative-example clarification, and self-review
evidence were recorded.

Revision note (2026-08-20): PR review fixes added falsifying checks to this
plan's own discoveries, introduced a self-referential rot-guard, and replaced
the author-specific working directory with a portable repository-root rule.
