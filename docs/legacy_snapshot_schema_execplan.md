# Support the observed legacy store without rewriting it (#749)

This living ExecPlan follows `.agent/PLANS.md`. The companion contract is
`docs/legacy_snapshot_schema_slice_spec.md`. One Class A implementation PR is
authorized; personal-store operations and merge are not.

## Purpose / Big Picture

The validated migration and automatic-backup inspector currently refuses an
existing legacy activities declaration. Add narrowly defined recognition so an
operator can copy/back up that store with the same full validation, without
changing its schema, activity IDs or duplicates. A synthetic migration and
automatic-snapshot/restore exercise will demonstrate the behavior. Success
does not activate protection on the owner's data.

## Progress

- [x] 2026-11-05: inspect #749, workflow, shared inspector and existing tests;
      start codex/issue-749-legacy-snapshot-schema from current origin/main.
- [x] 2026-11-05: define exact legacy signature and Spec → Domain handoff.
- [x] 2026-11-05: synthetic RED: 4 failed / 13 passed (1.24s); expected
      unsupported_source_schema and automatic degraded refusal, not fixture errors.
- [ ] Extend recognition only; run GREEN and relevant regression/full checks.
- [ ] Independent read-only checker and self-review; publish stable PR evidence.
- [ ] Separate owner-requested native review, acceptance and merge.

## Surprises & Discoveries

Observed: initial read-only rollout preview failed unsupported_source_schema;
the legacy column declaration was INTEGER with no PK. Inferred: the TEXT-PK-only
recognizer is sufficient to explain refusal, rather than corrupt contents.
Verified by: prior empty synthetic INTEGER/no-PK fixture refused while the
TEXT-PK control planned successfully. Branch regression evidence is pending.

Observed: both migrate and automatic snapshots call the shared inspector in
services/sqlite_snapshot_core.py. Inferred: one predicate extension should
unblock both without changing copy/publication. Verified by: inspected call
sites; migration/check_snapshot lifecycle tests will falsify this assumption.

## Decision Log

2026-11-05: support exactly INTEGER/no-PK plus TEXT/TEXT/REAL companion columns;
retain current TEXT sole-PK signature. Do not loosen recognition to every table
named activities. No source DDL/DML or value validation/coercion is introduced.

2026-11-05: use one PR for specification, tests and implementation rather than
another spec-only merge loop. A local independent checker is required by Class A;
native review remains manual with at most two rounds.

## Context and Orientation

services/sqlite_snapshot_core.py owns inspect_database (read-only transaction,
integrity, schema digest and typed table-row multisets) and copy_sqlite (Backup
API). scripts/sqlite_backup_restore.py wraps it for migrate plan/apply and
stopped restore. services/automatic_snapshots.py validates candidates and stores
manifest/status with generation deduplication; it must not gain another engine.
New tests live in tests/smoke/test_legacy_snapshot_schema.py. Existing relocation,
snapshot, retention and guard suites cover failure/publication boundaries.

## Plan of Work

The first milestone adds tests against current code. Build owned temporary
legacy activities stores, including no rows, repeated integer IDs, NULL, text
and BLOB identities and raw payloads. Keep a committed WAL-only update outside
main, close writers before stopped apply, then compare actual schema, rowids,
values/types and independent domain payload assertions in source/target/rollback.
Expected RED is the existing recognition refusal, not a fixture/import failure.

The second milestone changes only the activities declaration predicate in
inspect_database. Reuse its catalog, column metadata and PK list. Permit the
specified second signature only when no primary key exists anywhere. Keep
all-table fingerprint/copy/publication untouched. Exercise check_snapshot in a
real worker, retry unchanged contents, write new synthetic evidence, check again,
restore the selected copy over a synthetic reset target and inspect its rollback.

The final milestone runs focused and broad checks, updates the compatibility
wording/runbook/ASR test evidence, and obtains a bounded independent read-only
check. Publish a normal branch/PR with Closes #749, explicit limits and real test
results. Do not trigger native review, label accepted or merge without the
appropriate owner request. Record source metrics for this checkpoint without
creating another docs-only branch after review.

## Concrete Steps and Validation

From the repository root, use the available project Python interpreter and the
isolated launcher; it installs test-only DB/credential guards before collection:

    python scripts/run_isolated_tests.py tests/smoke/test_legacy_snapshot_schema.py -q

Record RED before changing product code, then repeat for GREEN. Existing shape
and path cases must also pass:

    python scripts/run_isolated_tests.py tests/smoke/test_legacy_snapshot_schema.py tests/smoke/test_database_relocation.py tests/smoke/test_database_relocation_drill.py tests/smoke/test_automatic_snapshots.py tests/smoke/test_snapshot_retention.py tests/smoke/test_snapshot_runtime.py tests/smoke/test_database_paths.py tests/smoke/test_sqlite_backup_restore.py tests/smoke/test_sqlite_concurrency_policy.py -q
    python -m ruff check .
    python scripts/run_isolated_tests.py -m "not live and not debug and not e2e" tests/ -q

Expected GREEN: exact legacy form passes migrate planned/copied_not_activated
without source mutation, automatic checks ready and deduplicated, restored
schema/data unchanged, negative shapes and path failures still refused. No UI
or contract artifacts change; web lint/build is N/A unless scope changes.

## Idempotence and Recovery

Only tmp_path stores are created or modified by tests. Migration must refuse
existing outputs, preserve source and retain rollback. Automatic generation
dedup and retention use unchanged code. Restore over an existing synthetic
reset store must save its rollback before replacement. No rollback of personal
data, configuration or services is needed because none are touched.

## ASR / Risk Traceability

ASR-DEP-2/REL-3: keep checked Backup API copies and stopped restore; MOD-3: legacy
compatibility without source schema conversion; SEC-1: synthetic-only evidence.
Reuse ADR-0002. Update asr_catalog with actual checks after GREEN, not a claim of
personal rollout, platform-wide compatibility or off-device protection.

## Interfaces and Dependencies

inspect_database(path, *, connect=readonly_connection) keeps its existing result
and SnapshotInspectionError vocabulary. No new config, library, API/TS field,
SQLite object or manifest version. The recognition extension is structural and
does not replace explicit path ownership/selection protections.

## Outcomes & Retrospective

Pending implementation. Live preview/apply remains blocked until the change is
reviewed/merged and a fresh operator decision is made. Native Windows/ACL,
personal data, running services and off-device transport are not exercised.

## Artifacts and Notes

RED command: project Python + scripts/run_isolated_tests.py
tests/smoke/test_legacy_snapshot_schema.py -q. Empty/populated CLI cases fail
with blocked/unsupported_source_schema, automatic case with degraded/
backup_integrity_failed, lower-case legacy declaration with the same recognizer
exception. All 13 near-miss rejection cases already pass; they are regression
baseline, not RED evidence. Scratch audit: 51 allowed, 0 blocked in parent.

Record exact RED/GREEN commands, counts, checker findings and final published
head here. Private rollout diagnostics remain local; do not copy personal DB
metadata beyond the explicitly described structural signature into evidence.

Initial revision 2026-11-05: bounded compatibility slice, one PR, no live rollout.
