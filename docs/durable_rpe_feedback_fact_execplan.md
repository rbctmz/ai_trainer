# Add an append-only durable athlete feedback fact

This ExecPlan is a living document. It follows `.agent/PLANS.md` and must be
updated as the work progresses. The first milestone is intentionally narrow:
record a durable, provenance-linked copy of newly submitted athlete feedback;
it does not calibrate TSS, change a plan, or change historical activity facts.

## Purpose / Big Picture

The application already records post-workout RPE and quality in the
`session_feedback` journal. That journal is the correct source for the event,
but it is not yet a stable boundary for a future structured athlete file. This
slice adds that boundary without pretending that one observation is already a
personal calibration.

After this change, each newly accepted feedback revision also produces one
append-only row in `athlete_feedback_facts`. The row keeps the explicit values
the athlete entered, identifies the originating `session_feedback` row and its
revision, and freezes the relevant match/time provenance. Corrections append a
new fact revision; removing feedback appends a withdrawn fact rather than
deleting or rewriting history. A retry is idempotent.

The fact is storage-only in this milestone. No TSS resolver, activity ingest,
readiness calculation, planner, plan checkpoint, provider delivery, or existing
plan-vs-fact binding reads it. There is no aggregation into an RPE baseline and
no automatic adjustment of TSS or training duration.

## Progress

- [x] (2026-08-20 17:04+03:00) Audited the existing workflow, architecture, athlete profile store, and post-workout feedback journal.
- [x] (2026-08-20 17:04+03:00) Chosen the M0 contract: a separate append-only fact ledger linked to `session_feedback`, with no historical backfill and no TSS consumer.
- [x] (2026-08-20 17:05+03:00) Added RED storage, lineage, idempotency, tombstone, atomicity, and no-TSS-effect tests; the initial run failed at the missing Database fact methods as expected.
- [x] (2026-08-20 17:06+03:00) Implemented the smallest data-layer/store change needed to make the tests GREEN: a same-transaction append-only fact ledger with thin Database facades.
- [x] (2026-08-20 17:15+03:00) Ran focused feedback/profile tests (65 passed), full contributor-safe validation (1959 passed, 3 skipped, 26 deselected), full ruff, and diff checks; no TSS/planning/provider consumer was introduced.
- [ ] Commit the M0 slice and hand it off for review; do not merge or enable any TSS correction from this block.

## Surprises & Discoveries

- Observation: raw athlete RPE and quality already persist in `session_feedback` with immutable revisions and frozen match evidence.
  Evidence: `data/database.py::save_session_feedback`, `api/session_feedback.py`, and `docs/post_workout_feedback_execplan.md` define the existing journal.

- Observation: there is no domain-level athlete Preferences/athlete-file store in the current web/API path. `user_settings` is a mutable key/value UI settings table, while `athlete_profile` is an append-only provider threshold snapshot.
  Consequence: copying RPE into either existing table would blur ownership and provenance, so this milestone uses a dedicated feedback-fact ledger.

- Observation: old feedback rows may exist before this table is introduced.
  Consequence: M0 does not backfill them. Only new feedback revisions receive a fact; historical rows remain authoritative in `session_feedback`.

- Observation: the feedback writer already owns a `BEGIN IMMEDIATE` transaction.
  Evidence: `Database.save_session_feedback` inserts the journal row and commits only after all work completes.
  Consequence: appending the fact through the same caller-owned connection gives atomic rollback without introducing a second write transaction.

## Decision Log

- Decision: use a new `athlete_feedback_facts` table instead of adding RPE columns to `athlete_profile` or JSON to `user_settings`.
  Rationale: those tables have different owners and lifetimes; a separate ledger preserves the distinction between provider profile thresholds, UI settings, and athlete-entered training evidence.
  Date/Author: 2026-08-20 / Codex.

- Decision: store one fact per `session_feedback` revision under `fact_type="session_feedback"`.
  Rationale: the source event already contains both RPE and quality, and one fact keeps their shared session/match provenance intact without inventing an aggregate baseline.
  Date/Author: 2026-08-20 / Codex.

- Decision: copy only structured completion/RPE/quality values, not the free-text note.
  Rationale: the note remains in its canonical session journal and should not be duplicated into a future athlete file without a separate privacy/retention contract.
  Date/Author: 2026-08-20 / Codex.

- Decision: corrections and removals append fact revisions; a tombstone is represented as `status="withdrawn"` with null feedback values.
  Rationale: the latest fact must not resurrect a superseded observation while the full audit trail remains recoverable.
  Date/Author: 2026-08-20 / Codex.

- Decision: no historical backfill, RPE aggregation, TSS recalculation, plan mutation, or provider update is part of M0.
  Rationale: one athlete-entered observation is evidence, not a validated personal model. Calibration requires a separate evidence gate and explicit follow-up.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

The implementation provides a small, test-proven persistence boundary that
future Preferences/athlete-file work can consume while existing TSS and
planning behavior remains unchanged. Focused feedback/profile coverage is 65
passed; contributor-safe coverage is 1959 passed, 3 skipped, and 26 deselected;
ruff and `git diff --check` are green. The remaining limitation is deliberate:
there is no Preferences UI, aggregate baseline, or TSS/planning consumer yet.

## Context and Orientation

The web-first product path is `api/` plus `web/`; shared domain and persistence
logic lives in `models/`, `services/`, and `data/`. The current feedback write
path is `api/session_feedback.py::_append_feedback`, which calls
`Database.save_session_feedback` in `data/database.py`. That database method
already allocates immutable feedback revisions under a SQLite immediate
transaction and returns the stored row.

The new store will follow the repository's existing caller-owned-connection
pattern from `data/athlete_profile_store.py`. Its DDL and serialization will be
isolated in `data/athlete_feedback_fact_store.py`; `Database` will retain thin
facades and will create the table during normal initialization. The feedback
write transaction will append the corresponding fact before committing, so a
successful feedback write cannot leave the new fact missing. A retry that finds
the existing feedback fingerprint will not append a second fact.

The fact's `target_key` is the same `session:<session_id>` identity as the
source journal. `revision` is monotonic per target. `supersedes_fact_id` points
to the previous fact revision when one exists. `value_json` contains only
`completion_status`, `completion_pct`, `session_rpe_1_10`, and
`quality_rating_1_5`. `provenance_json` contains the source table, source
feedback id/fingerprint/revision, match revision id, frozen session-end value
and provenance, source rule version, source label, and ownership label.

## ASR / risk traceability

This slice primarily protects ASR-REL-1 (plan/fact evidence and lineage must not
be lost) and ASR-MOD-3 (additive SQLite schema changes remain compatible with
existing databases). It also preserves ASR-REL-2: a missing new fact cannot make
Today, planning, or recovery fail because existing consumers do not read the
table in M0. The checks are the focused ledger tests, the existing
post-workout-feedback smoke tests, and the contributor-safe suite. No provider
or UI latency path is changed, so ASR-PERF-1/3/4 are not new consumers or
budgets in this milestone.

## Plan of Work

First, add the focused RED tests in a new
`tests/smoke/test_athlete_feedback_facts.py` module. The tests will use a
temporary `Database`, the existing `_feedback_payload` shape, and direct
feedback writes so they do not open or mutate the real athlete database. They
will prove round-trip storage, provenance, revision lineage, idempotent retry,
withdrawal behavior, and unchanged activity TSS.

Next, add `data/athlete_feedback_fact_store.py` with the table definition,
append/read helpers, strict JSON serialization, and no transaction ownership.
Extend `Database.init_tables`, `save_session_feedback`, reset/clear handling,
stats, and read facades only as needed. The new insert must happen inside the
existing feedback transaction and must use the already stored feedback row, not
browser payload values, so provenance cannot drift from the source journal.

Finally, update the existing feedback ExecPlan with a short cross-reference,
run focused tests, ruff, the contributor-safe pytest pass, and inspect the diff
for any TSS/planning/provider call. No web surface is added in M0 because there
is no user-facing Preferences contract yet.

## Concrete Steps

Work from `/Users/gregkisel/Developer/ai_trainer` on the dedicated branch
`codex/durable-rpe-fact`.

Run the RED tests before implementation:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_athlete_feedback_facts.py -q

The expected initial result was four failing tests at the missing Database fact
methods. After implementation, the focused ledger plus feedback run produced:

    29 passed

After implementation, run:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_athlete_feedback_facts.py tests/smoke/test_post_workout_feedback.py -q
    ai_trainer_env/bin/python -m ruff check data/athlete_feedback_fact_store.py data/database.py api/session_feedback.py tests/smoke/test_athlete_feedback_facts.py
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/

Do not use the real `ai_trainer.db` for these tests. Do not run sync, plan
rebuild, provider delivery, or any live Intervals.icu/Garmin write operation.

## Validation and Acceptance

The M0 acceptance bar is behavioral:

1. A new athlete-entered feedback revision creates exactly one linked fact.
2. Reading the fact after reopening the temporary SQLite database returns the
   explicit RPE/quality values and `provenance["label"]="athlete-entered"`.
3. The fact identifies the source feedback id, fingerprint, target key,
   revision, match revision, session end provenance, and rule version.
4. Repeating the same feedback fingerprint returns the original feedback and
   leaves fact history at one row.
5. A correction creates fact revision 2 and points to fact revision 1; a
   tombstone creates a withdrawn latest fact with null RPE/quality.
6. Existing activity TSS and feedback journal rows are unchanged except for
   the intended new feedback/fact rows. No test imports a TSS resolver from the
   new store, and no planner or provider path is modified.
7. The contributor-safe pytest command and full ruff command finish
   successfully. The observed contributor-safe result is `1959 passed, 3
   skipped, 26 deselected`.

The later milestone may define a Preferences projection or a personal RPE
baseline. It must consume this ledger read-only and must separately specify
sample gates, freshness, confidence, and falsification criteria before it can
affect TSS or planning.

## Idempotence and Recovery

Schema creation is rerunnable. Fact fingerprints are deterministic from the
source feedback fingerprint, so retries cannot duplicate a fact. All new
inserts share the existing feedback transaction; an exception rolls back both
the feedback and its fact. Existing historical feedback is not rewritten. If a
future migration fails, the dedicated table can be left empty while the
existing feedback journal remains usable; this milestone does not require a
destructive migration or a live-data backfill.

## Artifacts and Notes

Primary specification: this file.

Existing source-of-truth journal: `docs/post_workout_feedback_execplan.md` and
`data/database.py::session_feedback`.

Out of scope: automatic TSS correction, replan, provider calendar update,
historical import, athlete-file UI, aggregate RPE baseline, or coach decision
automation.

## Interfaces and Dependencies

The following internal interfaces are required at the end of M0:

    create_athlete_feedback_facts_table(conn: sqlite3.Connection) -> None
    AthleteFeedbackFactStore.append_from_feedback(feedback: Mapping[str, Any]) -> dict[str, Any]
    AthleteFeedbackFactStore.get_latest(target_key: str) -> dict[str, Any] | None
    AthleteFeedbackFactStore.get_history(target_key: str) -> list[dict[str, Any]]
    Database.get_latest_athlete_feedback_fact(session_id: str) -> dict[str, Any] | None
    Database.get_athlete_feedback_fact_history(session_id: str) -> list[dict[str, Any]]

The implementation may use only the Python standard library and the existing
SQLite connection policy. It must not add a provider dependency, a new TSS
formula, a web-only store, or a mutable `current` flag.

Revision note (2026-08-20 17:15+03:00): completed the same-transaction SQLite
implementation and validation. Focused feedback/profile coverage is 65 passed;
the contributor-safe suite is 1959 passed, 3 skipped, 26 deselected; full ruff
is green. The next milestone is review/merge only; automatic TSS correction is
explicitly out of scope.
