# S2 whole-delivery acceptance — #693

Date: 2026-10-19. Role: Supervisor / Integrator. Scope: the approved S2
AC1–AC10 in [#693](https://github.com/rbctmz/ai_trainer/issues/693) and
[slice specification](../../planning_cycle_lifecycle_slice_spec.md).
The [ExecPlan](../../planning_cycle_lifecycle_execplan.md) retains all milestone
RED/GREEN evidence and written review dispositions. Parent #677 keeps S3/S4.

## Candidate and boundaries

Fresh fetch confirms main `93fa4f4d8d41c9e392093538900f471903b6c331`, unchanged
from the S2 baseline. Candidate branch: `codex/issue-693-s2-acceptance`, built
from M4 `10178aa0e41b80c60c08cd2160de204b4fec5000`. M0–M4 drafts #694–#700
remain historical checkpoints; the final PR targets main and contains their
complete implementation. Separate S1 post-merge documentation #692 is excluded.
No intermediate branch is merged as part of this acceptance.

All probes use temporary synthetic SQLite, fixed athlete clocks and isolated
web ports. Provider credentials are disabled by the E2E harness; delivery tests
stub the provider boundary. No personal database, backfill, live provider write,
deployment or user-observed UX acceptance is claimed. Native review is a
separate current-head signal; local independent reviews do not substitute for it.

## Acceptance map

This maps observable behavior to executable evidence, rather than inferring
completion from a passing build. Paths are repository relative.

| AC | Behavior and executable evidence |
| --- | --- |
| AC1 | `test_planning_cycle_projection.py` and `test_planning_cycle_storage.py`: inclusive bounds, captured athlete day/timezone, missing/corrupt context, read-only GET and WAL snapshot. `test_planning_cycle_readers.py`: shared Planning/Today/Coach state, no current Race Week after the period, no current partial week after the saved end. |
| AC2 | `test_planning_cycle_commands.py`: early/ended/no-event/indeterminate closure; null selection with history retained; exact old checkpoint/fact bytes and successful receipt; no generated replacement. Lifecycle browser tests close without declaring participation. |
| AC3 | `test_planning_cycle_build.py`, `test_planning_cycle_build_v2.py`, `test_planning_cycle_identity.py`: explicit new-cycle inputs, actual mid-week floor, real-day aggregates/forecast, new namespace/legs, no inherited events/phases/lineage. Browser tests check clean choices, source-labelled availability and replacement acknowledgement. |
| AC4 | `test_planning_cycle_build_v2.py`: ten publication fault stages, real two-connection replacement/close races, stale same-head context, old successful replay, backup/reset. Original S1 confirmation/storage/commit/Coach tests preserve frozen publication and identity-only retries. Browser tests include cancel, lost response and external close during an unresolved edit. |
| AC5 | `test_planning_cycle_commands.py`: explicit unknown/DNS/participated/correction, audit receipts, event identity, stale correction and no reopen. Lifecycle browser tests correct historical outcome separately from historical completion facts. |
| AC6 | `test_planning_cycle_storage.py` and characterization/identity suites: latest-only import, exact old JSON/ledgers, migration rollback, concurrent init, restart/reset/Backup API restore. `test_planning_cycle_readers.py`: ambiguous legacy IDs need an explicit checkpoint; inherited match revision stays bound to that historical version after closure. Original v1 confirmation oracles remain unchanged. |
| AC7 | `test_planning_cycle_writer_guards.py`: twelve prescription writer families plus explicit Coach retract/direct commit across closed/ended/replaced contexts; complete persisted-table comparisons on rejection/rollback; captured restore context; mapping/settings/Coach ledger atomicity; real writer race. Existing Coach constraint gate, recovery, restore and legacy-cache tests cover their public adapters. Frozen M1 caller inventory remains an inventory of the baseline, not a generated new oracle. |
| AC8 | `test_planning_cycle_build_v2.py::test_constraints_are_owned_and_unknown_never_disappears` and storage/command suites: athlete/cycle/unknown scope, stored binding, date/sport protections, explicit conflict resolution, stale scope digest. Original Coach constraint/retraction tests retain bounded mutation behavior. |
| AC9 | `tests/e2e/test_planning_cycle_lifecycle_ui.py` and `test_planning_build_confirmation_ui.py`: expired → unknown/DNS close → history → new/cancel/confirm/retry, factual correction, repeated acknowledgements, empty/scheduled/indeterminate, keyboard and 390/900/1280 in both themes. Synthetic images: `docs/design/evidence/issue-693/`. Full E2E also exercises neighboring Today/Coach surfaces. |
| AC10 | Full contributor-safe suite without bespoke deselection, full isolated E2E, Ruff, API/TS freshness/inventory, web lint/build; original milestone RED and independent review dispositions in ExecPlan. Native current-head review and explicit human merge acceptance are recorded separately below. |

## M5 evidence improvement

**Observed:** M3c review recorded that the legacy `evidence_bytes` helper covers
original history/facts/settings but deliberately omits lifecycle/constraint
tables. The restore family case also omitted the expected cycle fields, so its
rejection alone did not prove the captured-context boundary.

**Inferred:** a writer could leave an unintended lifecycle/constraint write
without that particular assertion detecting it. This is a proof gap, not an
observed partial mutation. The cheap falsifying check is to compare all persisted
tables before and after each rejected operation and injected failure.

**Verified by:** M5 adds a writer-local read-transaction snapshot of every
persisted table, including cycle state, commands, ownership, constraints,
preview receipts and SQLite sequences. It leaves the legacy helper unchanged,
passes captured expected restore fields and adds stale Coach retract/direct
commit plus create/retract mapping-failure probes. Results are recorded below.
No new runtime behavior or acceptance criterion is introduced by these tests.

## Reproduction and results

Run from `/Users/gregkisel/Developer/ai_trainer` using `ai_trainer_env/bin/python`.

    ai_trainer_env/bin/python -m pytest tests/smoke/test_planning_cycle_*.py tests/smoke/test_planning_build*.py tests/smoke/test_coach_constraint_mutation_gate.py tests/smoke/test_constraint_retraction.py tests/smoke/test_sqlite_backup_restore.py -q --tb=short
    ai_trainer_env/bin/python -m pytest -q -m 'not live and not debug and not e2e' tests/ -W error::pytest.PytestReturnNotNoneWarning --tb=short
    ai_trainer_env/bin/python -m ruff check .
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest -m e2e tests/e2e -q --tb=short

M5 final counts, source commit, current-head CI and native review: pending.
Earlier M4 results (3665 contributor-safe / 36 selected browser GREEN) are not
silently relabelled as the new whole-delivery run.

## Review budget and remaining decisions

M0 spec review is closed, budget 2/2. Per-milestone implementation reviews and
all blocking dispositions are retained in the ExecPlan. M5 requests one
consolidated native full-diff review on the final main-based candidate. Any
correction request must name the fixing delta after that reviewed SHA; no
additional full-diff loop is requested. Each finding needs reproduction or a
named violated AC/invariant, and a written fixed-in/follow-up/disputed outcome.

Two M4 nonblocking UI follow-ups remain in #693/parent S4: re-acknowledge other
goal-field changes and recover stale builder context without explicit refresh.
M3c nonblocking restore error/doc consistency and internal athlete-scope
validation remain explicitly assigned to Domain/API in #693. The M3c complete
writer-state evidence suggestion is addressed by the M5 tests above. These are
not silently treated as already fixed runtime defects.

No acceptance label, waiver, PR merge or rollout is performed by this record.
The final human decision is separate from completed synthetic acceptance and
native review.
