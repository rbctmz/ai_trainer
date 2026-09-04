# Preserve confirmed plan-to-actual matches across session identity changes

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

An athlete who explicitly confirms that a completed activity matches a planned session must not see that activity become unmatched after an unrelated edit to the same training day. The production incident behind issue #529 happened when a sport-scoped coach constraint removed a swim session from a bike-plus-swim day: the unchanged bike session acquired a new identity during checkpoint persistence, so its confirmed match became unreachable. After this work, the unchanged survivor keeps its identity through persistence, and reconciliation also has a bounded fallback for a legitimate one-hop parent-session replacement on the same date and sport.

The outcome is observable through smoke tests that exercise a temporary SQLite database. One test confirms a bike activity, applies and persists a swim-only constraint, restores the resulting checkpoint, and still sees the bike as matched. A second test supplies a current session whose `replaces_session_id` names the confirmed predecessor and verifies that the current row claims the activity instead of reporting it as unplanned.

## Progress

- [x] (2026-09-02 09:47 MSK) Reproduced the production read failure against a read-only local database snapshot and separated the checkpoint source from inherited near-term-edit metadata.
- [x] (2026-09-02 09:47 MSK) Ran the pre-change smoke baseline: 112 tests passed.
- [x] (2026-09-02 09:47 MSK) Created this ExecPlan and the Class A slice spec.
- [x] (2026-09-02 09:54 MSK) Added the writer-path and reader-path RED regressions; two intended behavior tests failed and two fail-closed boundaries passed before product changes.
- [x] (2026-09-02 09:58 MSK) Implemented the writer identity-preservation fix using the existing previous-plan stamping mechanism.
- [x] (2026-09-02 09:58 MSK) Implemented the bounded reconciliation lineage fallback with current-id precedence and ambiguity/date/sport guards.
- [x] (2026-09-02 10:03 MSK) Ran the 132-test focused contour, the 2,244-selected contributor-safe contour, full Ruff, and `git diff --check`; all required checks passed.
- [x] (2026-09-02 10:06 MSK) Completed self-review, removed an accidental additive DTO field before final validation, and recorded the evidence bundle and retrospective.
- [x] (2026-09-02 10:12 MSK) Pushed `codex/issue-529-match-handoff` and opened PR #530 against `main`; CI and independent review remain human-gated delivery steps.
- [x] (2026-09-04 12:01 MSK) Reproduced all three native-review P2 findings with six failing assertions across admin resolution, predecessor reservation, writer conflict, and downstream revision provenance.
- [x] (2026-09-04 12:01 MSK) Fixed the review findings in `ce815d1`, preserved byte-equivalent public reconciliation responses, and passed 214 focused plus 2,244 contributor-safe tests.

## Surprises & Discoveries

- **Observed**: planning checkpoint #129 has `checkpoint_source=coach_constraint`, while its inherited `constraint_summary.near_term_edit.origin_kind` is `recovery_replan` with `origin_checkpoint_id=118`. Coach constraint row #4 removed only swim from 2026-08-31 at the exact checkpoint creation time.
  **Inferred**: the production identity change was caused by the sport-scoped constraint persistence path, not by a new recovery replan. The cheapest falsifying check was to apply the recorded constraint to checkpoint #128 and compare the surviving parent-session id before and after checkpoint construction.
  **Verified by**: the pure probe kept `ats_f6987bb48aa48bb99bae7cd2` immediately after `apply_constraints_to_goal_plan`, but `build_planning_checkpoint` changed it to `ats_9f00d3bdbda089e1a6159b30` with `replaces_session_id=ats_ed3deb7cb9dcace65d7840d5`.

- **Observed**: `ats_ed3deb7cb9dcace65d7840d5` existed in checkpoints #110 through #128 as the day-level `template.session_id`, while the confirmed match and executable bike parent used `sessions[0].session_id=ats_f6987bb48aa48bb99bae7cd2`.
  **Inferred**: the replacement link crossed identity grains, from a parent session to a day projection, so it could not own the confirmed match. The cheapest falsifying check was to query both JSON paths across checkpoints.
  **Verified by**: read-only `json_tree` queries found the two ids at their distinct paths and found the new parent pointing at the former day projection in checkpoint #129.

- **Observed**: `build_reconciliation` indexes the ledger only by `session:<current session_id>` and globally reserves all activities selected by confirmed rows.
  **Inferred**: even a valid one-hop parent-session replacement cannot consult the predecessor match, and the reservation then prevents heuristic recovery. The cheapest falsifying check was a synthetic current session with `replaces_session_id` and one stored confirmed predecessor match.
  **Verified by**: the pre-change probe returned `match_status=unmatched`, no actual activity ids, and the confirmed activity in `unplanned_activities`.

- **Observed**: the first GREEN implementation carried `replaces_session_id` in `_planned_snapshot`, whose fields are spread directly into every public reconciliation row.
  **Inferred**: leaving that internal field there would create an unnecessary additive DTO change despite the issue declaring API contracts unchanged. The cheapest falsifying check was to trace `_planned_snapshot` to the row construction and inspect the diff.
  **Verified by**: self-review confirmed the spread and the field was removed; the resolver now receives the predecessor id separately from `entry["session"]`. Focused and broad tests remained green.

- **Observed**: `admin_resolve` can represent either a matched administrative decision or an unmatched administrative clearing, but the initial handoff guard checked only `match_method`.
  **Inferred**: an unmatched administrative predecessor could suppress a valid current heuristic match. The falsifying check supplied an `admin_resolve`/`unmatched` predecessor with no selected activities and one compatible current activity.
  **Verified by**: the pre-fix row stayed unmatched; the guard now requires `match_status=matched` and at least one selected activity, after which the same probe resolves through the normal date/sport heuristic.

- **Observed**: a current `user_unmatched` decision won row selection but the predecessor's confirmed row still globally reserved its activity and still blocked a subsequent current-id confirmation.
  **Inferred**: current decision precedence was incomplete across read and write boundaries. The falsifying checks inspected candidates after unmatch and called the production `record_plan_actual_match` reselect path.
  **Verified by**: the predecessor reservation is now shadowed only for a valid unique replacement; the current row exposes the activity as a candidate, confirmation succeeds, and the first current revision links to the predecessor via `supersedes_match_id`.

- **Observed**: adding predecessor `match_revision_id` directly to reconciliation rows fixed downstream provenance but broke four byte-equivalence contract tests.
  **Inferred**: provenance must cross the internal feedback/recovery boundary without changing the public reconciliation DTO. The falsifying check was the full contributor-safe suite.
  **Verified by**: feedback prompt/evidence and recovery materialization now resolve the same guarded predecessor revision internally; the targeted provenance test passes and all four byte-equivalence tests remain green.

## Decision Log

- Decision: Treat checkpoint #129's `checkpoint_source` as the authoritative mutation provenance and treat `near_term_edit.origin_kind` as inherited historical context.
  Rationale: the two fields describe different events; attributing #129 to recovery replan would direct the writer fix to the wrong code path.
  Date/Author: 2026-09-02 / Codex.

- Decision: Deliver two small behavior slices in one Class A issue: stable survivor identity at the writer boundary, then a bounded reader fallback for a valid replacement.
  Rationale: the writer fix prevents recurrence of the observed incident, while the reader fallback enforces the broader immutable-ledger contract for legitimate session rematerialization. Neither slice substitutes for the other.
  Date/Author: 2026-09-02 / Codex.

- Decision: Reader inheritance applies only when no ledger row exists for the current id, exactly one current parent claims the predecessor, the predecessor row is `user_confirmed` or `admin_resolve`, and date and normalized sport agree.
  Rationale: current explicit decisions must win, ambiguous lineage must fail closed, and a replacement must not claim an activity from another calendar or discipline context.
  Date/Author: 2026-09-02 / Codex.

- Decision: A predecessor is inheritable only when its latest row is explicitly `matched` and selects at least one activity; an unmatched `admin_resolve` is not confirmation evidence.
  Rationale: method alone does not distinguish administrative confirmation from administrative clearing.
  Date/Author: 2026-09-04 / Codex.

- Decision: Once a valid replacement has its own explicit decision, shadow the predecessor reservation and connect the first current revision to the predecessor through `supersedes_match_id`.
  Rationale: the athlete must be able to unmatch and reselect, while saved evidence still needs append-only lineage for later revalidation.
  Date/Author: 2026-09-04 / Codex.

- Decision: Resolve inherited revision ids inside feedback and recovery consumers instead of adding a field to reconciliation rows.
  Rationale: the immutable revision remains auditable without changing the byte-equivalent public API contract.
  Date/Author: 2026-09-04 / Codex.

- Decision: Preserve all existing `plan_actual_matches` rows and add no migration or backfill.
  Rationale: the ledger is append-only evidence. Read-time resolution and correct future identity stamping are sufficient.
  Date/Author: 2026-09-02 / Codex.

## Outcomes & Retrospective

The writer now canonicalizes a sport-scoped constraint result against its exact previous plan before checkpoint serialization. A `2 -> 1` day transition therefore preserves the unchanged parent id and its exact match target. Reconciliation now consults a confirmed one-hop predecessor only when the current id has no decision, exactly one current parent owns that predecessor, the predecessor is no longer active, and date and sport agree.

Ten new tests cover the persisted constraint vertical, matched and unmatched administrative decisions, current-id precedence and re-selection, immutable revision propagation into feedback and recovery, date mismatch, sport mismatch, and ambiguous claimant failure. The review-focused contour passed 214 tests. The contributor-safe run passed 2,244 tests, skipped 3 environment-dependent tests, and deselected 26 live/debug/e2e tests. Ruff, byte-equivalence, and whitespace validation passed.

The change adds no schema, persistent row, provider call, API field, or backfill. Existing checkpoint #129 remains historical malformed lineage and is intentionally not rewritten; its athlete-visible state requires an explicit current-id confirmation or separately authorized historical repair. This limitation is recorded rather than hidden because issue scope forbids automatic backfill and historical multi-hop reconstruction.

## Context and Orientation

AI Trainer persists immutable planning checkpoints. Each day has a top-level template, but executable plan-to-actual targets are the parent sessions in `session_templates[i].sessions[]`. The top-level `template.session_id` is a projection of day material and is not a substitute for a parent-session id on a multi-session day.

`models/session_identity.py::ensure_session_identities` assigns content-derived ids. When it receives `previous_goal_plan`, it can preserve an unchanged session across a day cardinality change such as two sessions becoming one. `models/planning_checkpoints.py::build_planning_checkpoint` performs a final identity stamp without previous-plan context. The coach constraint preview in `api/planning_service.py::preview_coach_constraint_mutation` has both the old and updated plans, so it is the narrow writer boundary that can stamp the updated plan with correct prior context before serialization.

`models/plan_actual_reconciliation.py::build_reconciliation` produces one row per executable parent session. It receives current plan data, local activities, and the latest append-only match rows for each target key. A stored match target uses `session:<session_id>`. The current reader reserves activities used by explicit matches so heuristics cannot assign the same activity twice; the replacement fallback must therefore resolve the predecessor ledger before candidate filtering.

The work changes no API, TypeScript, database schema, provider call, Streamlit surface, or heuristic threshold. It affects ASR-REL-1, which requires that reconciliation lose neither completed activities nor executable planned sessions during replanning.

## Plan of Work

First add a production-shaped smoke test using a temporary SQLite database. Seed a two-parent bike-plus-swim day, persist it, save a `user_confirmed` bike match and the completed bike activity, then confirm a swim-only coach constraint through the public planning service mutation functions. Restore and reconcile the resulting checkpoint. Before the writer fix, checkpoint construction changes the surviving bike id and the test fails.

Add a pure reconciliation test for a current session S2 with `replaces_session_id=S1` and a stored confirmed S1 match on the same date and sport. Assert S2 is matched and the activity is not unplanned. Add boundaries showing that a current-id ledger takes precedence and ambiguous or incompatible predecessor claims do not inherit.

In `api/planning_service.py`, stamp the constraint-updated plan with `ensure_session_identities(updated, previous_goal_plan=goal_plan)` before checkpoint provenance and serialization. This uses the existing cross-cardinality survivor mechanism rather than adding a second identity algorithm.

In `models/plan_actual_reconciliation.py`, include `replaces_session_id` in the internal planned snapshot and resolve a predecessor ledger only under the conditions recorded in the Decision Log. Keep the output `target_key` and `session_id` current. Use the inherited explicit ledger only to select activities and evidence; do not create or rewrite a match row.

Finally run the focused new tests, the issue smoke baseline plus coach-constraint tests, the normal contributor-safe suite, and Ruff. Inspect the diff for identity-grain mistakes, accidental broad inheritance, schema changes, or edits outside issue scope.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on branch `codex/issue-529-match-handoff`.

Create the RED tests and run:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_issue_529_match_handoff.py

The new writer and valid-lineage tests failed before product code changes for the expected identity and unmatched assertions, not because of fixture setup. The RED run reported two failed and two passed tests before the boundary matrix was expanded to seven tests.

After the initial slices, the whole new module reported seven passed tests. After native-review regressions, it reports ten passed tests.

Run the focused regression contour:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_issue_529_match_handoff.py tests/smoke/test_plan_actual_reconciliation.py tests/smoke/test_coach_constraints.py tests/smoke/test_recovery_transfer.py tests/smoke/test_recovery_transfer_identity_handoff.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_api_today.py

Run the contributor-safe contour and lint:

    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    ai_trainer_env/bin/python -m ruff check .

No web contract changed, so Next.js lint/build and contract extraction are not required. If implementation touches `api` response shapes or `web`, this decision must be revisited and the required web checks added.

## Validation and Acceptance

Acceptance requires the following observable behaviors:

An unchanged bike parent on a bike-plus-swim day keeps the exact same `session_id` after a swim-only coach constraint is previewed, confirmed, persisted, and restored. Its existing confirmed match remains `matched`, its activity id is returned by reconciliation, and that activity is absent from `unplanned_activities`.

A legitimately reminted current session on the same date and sport can consult a confirmed predecessor named by `replaces_session_id`. Reconciliation reports the current session and current target key while returning the predecessor-selected activity. No ledger row is rewritten.

If the current id has its own explicit match decision, it wins over predecessor evidence. If more than one current parent claims the same predecessor, or date/sport is incompatible, reconciliation does not inherit the predecessor match. These cases fail closed without duplicate assignment.

Existing reconciliation, transfer, recovery-replan, coach-constraint, and Today smoke tests remain green. The contributor-safe Python contour and Ruff pass.

## Idempotence and Recovery

All tests use temporary SQLite databases and can be rerun safely. The implementation adds no persistent state and requires no migration, reset, or backfill. Reverting the code and tests restores prior behavior. The append-only match ledger and existing athlete database are never modified during development validation.

If a test fixture fails before reaching the intended assertion, correct the fixture and rerun the pre-change tree until the expected behavioral RED is demonstrated. Do not weaken the assertion to make an unrelated failure pass.

## Artifacts and Notes

Pre-change focused baseline:

    112 passed in 2.80s

Pre-change production-shaped identity probe:

    after_constraint_before_restamp = ats_f6987bb48aa48bb99bae7cd2
    with_previous_goal_plan.session_id = ats_f6987bb48aa48bb99bae7cd2
    current_checkpoint_builder.session_id = ats_9f00d3bdbda089e1a6159b30
    current_checkpoint_builder.replaces = ats_ed3deb7cb9dcace65d7840d5

Pre-change reader probe:

    match_status = unmatched
    actual_activity_ids = []
    is_unplanned = true

RED test transcript:

    2 failed, 2 passed in 0.47s

Final focused transcript:

    132 passed in 2.56s

Final contributor-safe transcript:

    2241 passed, 3 skipped, 26 deselected, 3 warnings in 67.97s

Native-review RED transcript:

    6 failed, 4 passed in 0.54s

Native-review focused transcript:

    214 passed in 5.90s

Native-review contributor-safe transcript:

    2244 passed, 3 skipped, 26 deselected, 3 warnings in 69.10s

The warnings are existing FastAPI/Pydantic deprecations. The skipped tests require a local listening socket or the optional `garth` package and are unrelated to this change.

## Interfaces and Dependencies

No new dependency is allowed. Reuse `models.session_identity.ensure_session_identities`, `models.plan_actual_reconciliation.build_reconciliation`, `models.coach_constraints.apply_constraints_to_goal_plan`, and the existing `Database` temporary-file test pattern.

The public signature and result shape of `build_reconciliation` remain unchanged. The resolver reads `replaces_session_id` directly from the current parent session without adding it to the public planned snapshot. The reconciliation result continues to expose the current `session_id` and `target_key`; inherited ledger provenance must not make the output pretend that the historical target is current.

Revision note (2026-09-02): Initial ExecPlan created after the read-only production evidence disproved the issue's original recovery-replan attribution and identified the sport-scoped constraint checkpoint boundary.

Revision note (2026-09-02): Updated after RED/GREEN implementation, self-review, and broad validation; recorded the unchanged public DTO and the explicit no-backfill limitation for historical checkpoint #129.

Revision note (2026-09-02): Linked the completed implementation and evidence to PR #530 after publishing the branch.

Revision note (2026-09-04): Addressed all three round-one P2 findings at `ce815d1`; retained the public DTO after a byte-equivalence falsifier and moved immutable revision resolution into internal consumers.
