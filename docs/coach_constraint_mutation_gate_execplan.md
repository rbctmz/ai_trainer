# Gate Coach constraint mutations behind proposals and atomic apply

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must stay current
throughout issue #483. This file follows `.agent/PLANS.md`.

## Purpose / Big Picture

Today a language model can choose `create_plan_constraint`,
`retract_plan_constraint`, or `repair_plan_day` and immediately change the
constraint ledger or active planning checkpoint. A model-selected tool call is
not an athlete confirmation, so this violates ADR-0004 and ADR-0010. Retraction
also commits the constraint deactivation before attempting plan recovery, which
can leave the ledger and plan inconsistent when recovery fails.

After this change, all three Coach tools only create a bounded pending proposal.
The proposal card shows the exact date, sport scope, operation, active base
checkpoint, and expected plan effect. Nothing durable changes until the athlete
presses the proposal confirmation button. Approval first atomically claims the
proposal, then a separate SQLite writer transaction commits the constraint
status plus any child checkpoint as one unit. Stale bases, missing donors,
validation failures, and replayed approvals leave the plan and constraint
ledger unchanged. A process crash between claim and apply can leave a visible
`applying` proposal; automatic lease recovery is explicitly outside #483.

The behavior is visible by opening `/coach`, reporting a one-day constraint,
and observing a confirmation card while `/planning` remains unchanged. After
confirming the card, the exact date/sport changes once. Rejecting or replaying
the proposal never creates a second change. No provider delivery occurs in this
flow.

## Progress

- [x] (2026-08-20) Synced merged `main`, created
  `codex/issue-483-coach-mutation-gate`, and moved #483 to `status: in progress`.
- [x] (2026-08-20) Read the process baseline, ASR catalog, ADR-0004, ADR-0006,
  ADR-0010, and the earlier proposal/constraint ExecPlans.
- [x] (2026-08-20) Completed two independent Luna audits: SQLite atomicity and
  proposal/UI lifecycle reuse.
- [x] (2026-08-20) Established focused baseline: 74 passed across AI tools,
  native runtime, decisions, constraints/retraction, and ProposalCard contracts.
- [x] (2026-08-20) Added contract-first RED tests for proposal-only tools, zero writes,
  fingerprint/base binding, atomic failures, replay, and native/marker parity.
- [x] (2026-08-20) Implemented pure previews plus one-transaction
  create/retract/repair apply.
- [x] (2026-08-20) Extended proposal persistence, decisions dispatch, web types, ProposalCard,
  and decisions history for the three actions.
- [x] (2026-08-20) Ran focused, web lint/build, contract freshness, Ruff, and
  contributor-safe pytest.
- [x] (2026-08-20) Independent checker found one P1 post-commit status hazard;
  fixed it and added regression coverage plus the requested base/fingerprint
  and approve-vs-reject evidence.

## Surprises & Discoveries

- Observation: both native and marker runtimes already converge on the same
  `AITools.execute_tool` boundary, so changing the three tools to return
  `is_proposal=True` fixes both model paths without provider-specific logic.
  Evidence: `models/ai_coach_runtime.py:293-325,396-421,480-497`.

- Observation: `api/routers/coach.py` already persists every tool result marked
  `is_proposal`; the missing actions are rejected only by the database allowlist.
  Evidence: `api/routers/coach.py:157-186` and
  `data/database.py:2596-2616`.

- Observation: `approve_proposal` atomically claims only `recovery_replan`.
  Build, adjust, and any new mutation action can currently be applied twice by
  concurrent requests.
  Evidence: `api/routers/decisions.py:182-204`.

- Observation: create uses two committed SQLite connections: constraint insert,
  then optional checkpoint insert. Retract commits deactivation before donor
  recovery. Neither can be repaired reliably with a compensating write.
  Evidence: `data/database.py:1315-1347,3102-3181,3240-3265`,
  `api/planning_service.py:3038-3093`, and
  `api/routers/planning.py:195-219`.

- Observation: the existing `ProposalCard` approve/reject endpoints are generic,
  but unknown actions render as `adjust_plan`; TypeScript also has a closed
  three-action union. A small explicit mutation branch is required.
  Evidence: `web/components/ui/ProposalCard.tsx:428-545,701-760` and
  `web/lib/types.ts:290-350`.

- Observation: the old Coach result presenter claimed a constraint was already
  saved immediately after the tool call. Making the backend proposal-only was
  insufficient until this copy also said that nothing had changed yet.
  Evidence: `models/coach_tool_presenter.py` constraint mutation branch.

- Observation: a real SQLite trigger is a better atomicity probe than
  monkeypatching `save_planning_checkpoint`, because the new transaction
  deliberately inserts both rows on one connection and does not compose two
  public save methods.
  Evidence: `test_constraint_apply_rolls_back_ledger_when_checkpoint_insert_fails`
  and `test_retract_rolls_back_status_when_checkpoint_insert_fails`.

- Observation: plan/fact rebind happens after the core transaction. Letting an
  unexpected rebind exception escape would falsely mark an already-applied
  proposal `failed`; it must remain approved with a warning that the web
  confirmation message also exposes to the athlete.
  Evidence: `test_post_commit_rebind_failure_is_an_approved_warning`.

## Decision Log

- Decision: keep the existing Coach tool names but make their behavior
  proposal-only and rewrite their schema/prompt descriptions accordingly.
  Rationale: the names are already part of both native and marker prompts and
  existing tests. Runtime enforcement, not an action name, defines the autonomy
  boundary; retaining names minimizes migration risk.
  Date/Author: 2026-08-20 / Codex.

- Decision: reuse `coach_proposals`, the existing decisions approve/reject API,
  and `ProposalCard`; do not add a second confirmation endpoint or screen.
  Rationale: the existing lifecycle is the canonical audited DDA surface. A new
  path would duplicate state and weaken reviewability.
  Date/Author: 2026-08-20 / Codex.

- Decision: add pure preview functions and a domain-specific Database atomic
  commit method rather than compensating after independent commits.
  Rationale: compensation can fail and cannot guarantee zero partial writes.
  `BEGIN IMMEDIATE` plus an in-transaction base/status recheck gives one
  fail-closed boundary for the ledger and checkpoint.
  Date/Author: 2026-08-20 / Codex.

- Decision: atomically claim every proposal `pending → applying` before any
  apply, not only recovery proposals.
  Rationale: this makes approval replay/concurrency idempotent for the new
  actions and closes the same latent race for build/adjust.
  Date/Author: 2026-08-20 / Codex.

- Decision: keep direct `/api/planning/constraints` and incident repair routes
  as explicit product/admin actions, but route them through the same atomic
  service boundary. They are not exposed as autonomous LLM mutation paths.
  Rationale: #483 changes authorization of Coach inference, not the existence of
  deliberate planning APIs; atomicity must be consistent in both callers.
  Date/Author: 2026-08-20 / Codex.

- Decision: no Intervals.icu/Garmin write is added to mutation approval.
  Rationale: ADR-0010 classifies provider delivery as A4 and requires its own
  explicit delivery surface.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

The three model-facing tools now produce only bounded proposals. Approval
recomputes the exact base/fingerprint, claims every proposal once, and uses one
SQLite writer transaction for constraint status plus child checkpoint. Direct
planning create/retract/repair routes reuse the same primitive. ProposalCard,
decisions history, and tool-result copy make the pre-confirmation state explicit;
no provider delivery was added.

RED evidence before implementation was `6 failed, 1 passed` in the backend gate
file and `3 failed, 1 passed` in the web surface file. Final focused evidence is
`14 passed` for the mutation gate and `88 passed` for the adjacent coach,
decision, constraint, and product-surface contour. Contract extractor/API
inventory is `37 passed`; `ruff check .`, contract freshness, web lint, web
production build, and `git diff --check` are green. The contributor-safe suite
is `1986 passed, 3 skipped, 26 deselected`. After checker review, the focused
mutation gate and product-surface contour is `22 passed`; the checker P1 is
regression-pinned as an approved result with a deferred-rebind warning.

The deliberate remaining limitation is crash recovery for a proposal left in
`applying` after process termination. Such a proposal is visible and cannot
double-apply; an automatic lease/retry policy remains outside #483 because it
needs a separate product decision about whether retrying a human-confirmed
mutation after a crash is still authorized.

## Context and Orientation

`models/ai_tools.py` registers tools available to the LLM. Both native function
calling and legacy marker parsing execute these methods through
`models/ai_coach_runtime.py`. A tool result with `is_proposal=True` is saved by
`api/routers/coach.py` in `coach_proposals` and emitted as an SSE proposal event.

`api/routers/decisions.py` owns the human approval boundary. It loads the saved
proposal and applies only its stored params. `web/components/ui/ProposalCard.tsx`
calls its approve/reject endpoints. `web/app/coach/page.tsx` shows proposals in
the chat, while `web/app/decisions/page.tsx` shows pending and historical
proposals.

`api/planning_service.py` owns planning orchestration. Constraint creation calls
`apply_constraint_to_active_plan`; day retraction/repair calls
`recover_day_after_constraint_retraction`. `data/database.py` currently opens a
fresh SQLite connection and commits inside each save method, so composing two
methods is not atomic.

A base checkpoint is the exact active plan version used to build a preview. A
preview fingerprint is a SHA-256 hash over the normalized operation, stored
params, base id, and bounded preview. Approval recomputes the preview and rejects
any mismatch before a write. A proposal claim is the atomic status transition
from `pending` to `applying`; only one request can claim a proposal.

## ASR / Risk Traceability

ASR-REL-1 requires a scoped mutation to preserve sibling sports and plan/fact
lineage. ASR-REL-3 requires a failed write not to leave partial durable state.
ASR-MOD-2 requires the web confirmation surface to consume a server-owned
preview rather than reimplement planning logic. ASR-MOD-3 requires additive
proposal actions and payload fields. ADR-0004 requires propose, human confirm,
append, and rollback. ADR-0006 requires an exact base checkpoint and append-only
child plan. ADR-0010 says a model tool call or vague assent is not DDA.

## BDD Scenarios

Given an active plan, when native or marker Coach execution selects
`create_plan_constraint`, then the tool returns a pending proposal and the
constraint count and latest checkpoint id remain unchanged.

Given a user says only `ок`, `согласен`, or states a fact without pressing the
card, when the model selects any of the three mutation tools, then at most a
proposal is stored; no constraint or checkpoint mutation occurs.

Given a scoped swim constraint proposal, when the athlete confirms its exact
card against the unchanged base, then one active constraint is inserted and one
child checkpoint removes only swim while bike/run siblings remain.

Given a retract proposal with a valid donor, when it is confirmed, then the
constraint becomes inactive and the recovered child checkpoint are committed in
the same transaction.

Given a stale base, missing donor, validation error, or injected checkpoint
insert failure, when create/retract/repair is confirmed, then the proposal fails
and both the constraint ledger and latest checkpoint remain byte-observably
unchanged.

Given two approvals or a replay for one proposal, when both requests run, then
exactly one claims and applies it; every other request returns HTTP 409 and no
duplicate constraint/checkpoint is created.

Given a mutation proposal is rejected, when reject wins the status race, then
the proposal becomes rejected and no mutation occurs. If approve already claimed
it, reject returns HTTP 409.

Given any constraint mutation approval, when it completes, then no external
provider delivery method is called.

## Plan of Work

Milestone 1 adds RED behavior tests. Extend
`tests/smoke/test_ai_tools_proposal.py` for proposal-only create and zero writes.
Add a focused `tests/smoke/test_coach_constraint_mutation_gate.py` for approve,
reject, replay, stale, missing donor, injected transaction failure, and
native/marker parity. Extend product-surface smoke to require explicit rendering
and dispatch for all three actions. Run the tests and record the expected RED
failures before implementation.

Milestone 2 separates preview from persistence in `api/planning_service.py`.
Introduce `preview_coach_constraint_mutation(db, *, action, params)` which
normalizes the operation, resolves the exact constraint/date/sport and base,
computes the bounded before/after effect without writes, and returns stored
`params`, `preview`, and `preview_fingerprint`. Introduce
`confirm_coach_constraint_mutation(db, *, action, params,
preview_fingerprint)` which recomputes and compares that fingerprint before
calling the atomic persistence primitive.

Milestone 3 adds `Database.commit_coach_plan_mutation(...)`. It opens one
`BEGIN IMMEDIATE` transaction, rechecks the latest checkpoint id and active
constraint status, inserts or deactivates the constraint when required, inserts
the already-built child checkpoint when required, commits once, and rolls back
on every exception. Existing single-row save methods stay backward-compatible.
The direct planning create/retract/repair routes use the same service/atomic
path. Plan/actual match rebindings remain append-only after the core transaction;
their existing best-effort behavior does not define apply success.

Milestone 4 changes the three AITools methods to call the pure preview function
and return `is_proposal=True`. Add the three actions to the proposal allowlist
and decisions dispatcher. `approve_proposal` claims every action before apply;
reject also performs a conditional pending transition. Apply consumes only the
saved proposal, never arbitrary client mutation params.

Milestone 5 extends `CoachProposalAction`, `ProposalCard`, and decisions history
with explicit create/retract/repair labels, bounded preview fields, success
messages, and generic approve/reject dispatch. Regenerate/check the TypeScript
contract only if extraction changes. No new page or provider call is added.

Milestone 6 performs self-review, full validation, and an independent checker
round. Update the ASR catalog from the current #483 yellow gap to the exact
runtime tests that close it.

## Concrete Steps

Run commands from `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest \
      tests/smoke/test_ai_tools_proposal.py \
      tests/smoke/test_coach_constraint_mutation_gate.py \
      tests/smoke/test_coach_native_tools.py \
      tests/smoke/test_constraint_retraction.py \
      tests/smoke/test_coach_decisions.py -q

    ai_trainer_env/bin/python -m ruff check \
      data/database.py api/planning_service.py api/routers/decisions.py \
      api/routers/planning.py models/ai_tools.py models/ai_coach_runtime.py \
      tests/smoke/test_coach_constraint_mutation_gate.py

    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    git diff --check

## Validation and Acceptance

The first test command must fail before implementation on proposal-only, atomic
failure, replay, and new action rendering assertions, then pass after GREEN. The
final contributor-safe contour must have no new failures. Web lint/build and
contract freshness are mandatory because `web/lib/types.ts` and ProposalCard
change.

Manual acceptance uses only a temporary/demo database. In `/coach`, a model
request for a day constraint must show a pending card while `/planning` remains
unchanged. Reject leaves it unchanged. Confirm changes only the previewed
date/sport. Refreshing `/decisions` shows the final lifecycle status. Do not use
live athlete data or deliver to a provider.

## Idempotence and Recovery

All tests use temporary SQLite files and may be rerun. Preview is read-only.
The atomic method rolls back its connection on any exception. A stale proposal
is not silently refreshed; the athlete asks for a new proposal. A proposal
stuck in `applying` after process termination is visible and cannot replay;
automatic lease recovery is outside #483 and may be added only with a separate
issue and crash evidence.

## Artifacts and Notes

Focused pre-change baseline:

    74 passed in 5.32s

Confirmed failure windows:

    create: constraint COMMIT -> checkpoint COMMIT
    retract: deactivate COMMIT -> donor/stale validation -> checkpoint COMMIT

## Interfaces and Dependencies

`api.planning_service` will expose:

    preview_coach_constraint_mutation(
        db: Database, *, action: str, params: dict[str, Any]
    ) -> dict[str, Any]

    confirm_coach_constraint_mutation(
        db: Database, *, action: str, params: dict[str, Any],
        preview_fingerprint: str
    ) -> dict[str, Any]

`data.database.Database` will expose a domain-specific atomic primitive:

    commit_coach_plan_mutation(
        *, action: str, base_checkpoint_id: int,
        constraint_payload: dict[str, Any] | None = None,
        constraint_id: int | None = None,
        checkpoint_data: dict[str, Any] | None = None
    ) -> dict[str, Any]

The allowed proposal actions and `CoachProposalAction` add
`create_plan_constraint`, `retract_plan_constraint`, and `repair_plan_day`.
No new dependency is introduced.

Revision note (2026-08-20): initial issue #483 plan created after the merged
ADR-0010 audit and two read-only implementation audits. The chosen design reuses
the existing proposal card and adds a single SQLite transaction for the core
constraint/checkpoint mutation.
