# #749 — legacy schema recognition for validated snapshots

Author: Spec / Architecture Owner, then Domain / API Implementer (explicit
handoff below). Merge owner: Greg. Independent checker: assigned after RED/GREEN.
Date: 2026-11-05. Candidate HEAD: pending implementation.

## Change Class

Class A: compatibility of the persistent-store recognition contract used for
migration and automatic recovery artifacts. Manual review, native rounds 0/2;
no automatic trigger, acceptance or budget exception. One implementation PR;
no separate spec-only delivery or new architecture boundary.

## Scope

`services/sqlite_snapshot_core.py::inspect_database` recognizes one additional
legacy activities declaration without rewriting it. `migrate plan/apply` and
automatic snapshots consume this same inspector. Existing schema fingerprint,
typed row multiset, SQLite Backup API and stopped-service restore stay intact.

The two supported signatures are ordinary activities tables containing
activity_id, date, sport and duration_minutes:

1. Existing signature: the sole primary key is activity_id declared TEXT;
   existing declarations of the other required columns remain accepted.
2. Legacy signature: no primary key on any column, activity_id declared
   INTEGER, date TEXT, sport TEXT, duration_minutes REAL. Compare declared type
   names case-insensitively after trimming whitespace. Extra columns and
   already-supported extra tables/indexes/views/triggers are preserved.

This is structural application-schema recognition, not proof of ownership:
explicit source selection and existing path/alias checks remain required.
Do not validate row IDs as unique, non-null or exclusively integer: SQLite's
non-PK INTEGER column can contain duplicates, NULL, TEXT and BLOB. Those stored
values must survive, without coercion, normalization or deduplication.

## Non-goals

No personal database access, ALTER, startup schema migration, application
activation, configuration changes, service restart, UI/API/TypeScript changes,
new CLI flags, recognizer override, backup engine or dependency. No support for
INTEGER PRIMARY KEY, TEXT without PK, composite PK or other unobserved
activities declarations. No claim that arbitrary old domain writers are fully
compatible merely because their store can be backed up. Off-device is #626.

## Definition of Done

- [ ] Empty and populated legacy fixtures plan/copy/snapshot/restore safely.
- [ ] Full logical equality and explicit SQLite schema/type/rowid assertions
      prove no schema/ID/duplicate/raw value rewriting.
- [ ] Committed WAL, retry/dedup, fresh writes and reset-state rollback pass.
- [ ] Unsupported shape and path/alias regressions remain refused.
- [ ] Focused/full contributor-safe checks, Ruff and independent checker finish.
- [ ] Native review/owner merge remain explicitly separate handoff gates.

## Public Contracts

CLI recognition changes compatibly by admitting signature 2; existing report
keys, refusal codes, confirm-stopped and no-clobber rules are unchanged.
Snapshot manifest/fingerprint version, SQLite schema, persisted data, API,
TypeScript and configuration are unchanged. Existing #624 recognition wording
and the operator runbook receive a narrow compatibility amendment.

## Failure, Reset, Rollback, Idempotency

No new persistent state is added. Wrong/foreign shapes still return
unsupported_source_schema (automatic checks report their existing degraded
reason); virtual/shadow/invalid stores keep existing refusals. Failed apply
keeps source/config unchanged and must not clobber target/rollback. Same-path
retry refuses an existing target. An unchanged automatic generation reuses its
snapshot; changed legacy contents produce a new generation. Reset policy and
pin/retention ownership do not change. Synthetic restore over a reset store
must first preserve that store's rollback and recover the saved legacy data.
No live reset or runtime Database initialization is part of this slice.

## State Boundaries and Identity

The selected source SQLite transaction is authoritative. The helper still
hashes schema SQL and all existing tables, preserving storage classes and raw
JSON/BLOB/NULL and multiset duplicates without inventing a primary key.
Physical Backup API copies preserve implicit rowids as asserted in fixtures;
fingerprints remain row-multiset based, not a new rowid-based generation format.
WAL inclusion, source-change checks, namespace locking and no-clobber publication
are existing mechanisms, not modified here.

## Evidence Boundary Matrix

| Shape / identity | State | Expected result |
| --- | --- | --- |
| canonical TEXT PK | empty/populated | unchanged supported behavior |
| exact legacy INTEGER/no PK | empty/populated/duplicate/null/mixed storage class | preserve schema/rows/rowids |
| legacy with committed WAL | main lacks new marker | target/rollback/snapshot contain committed marker |
| legacy unchanged / new write | retry/restart | same generation / new valid generation |
| wrong type/missing field/TEXT-no-PK/INTEGER-PK/composite/view/virtual | partial or foreign | fail closed, no published DB |
| valid signature in aliased or overlapping endpoints | conflicting path | existing path guard refuses |
| saved legacy snapshot / reset target | stopped restore | original restored, reset state retained as rollback |

## RED Matrix

| Invariant | RED probe | Expected initial failure |
| --- | --- | --- |
| legacy is recognized without mutation | real CLI plan/apply with synthetic legacy store | unsupported_source_schema |
| shared automatic inspector works | check_snapshot → manifest → operator restore | degraded, no ready snapshot |
| corrupt/foreign rejection stays strict | negative shape matrix | already-green characterization; not claimed RED |

## ASR / ADR Traceability

ASR-DEP-2, ASR-REL-3, ASR-MOD-3 and ASR-SEC-1; reuse ADR-0002. Extend only the
recognition predicate, keeping full comparison and publication/rollback tactics.
Trade-off: one more explicitly defined structural signature is admissible;
arbitrary SQLite is not accepted. No new ADR or application boundary is needed.

## Delivery Slices

One bounded slice: spec and synthetic RED, minimal predicate extension, GREEN
including migration/automatic restore and existing path/failure regression,
self-review and independent checker, then one stable PR/native-review handoff.
Spec → Domain handoff: implement precisely the two signatures above in the
existing inspector; tests may create only owned synthetic tmp_path stores.

## Evidence Bundle

See [ExecPlan](legacy_snapshot_schema_execplan.md). Initial rollout preparation
already reproduced INTEGER/no-PK refusal against TEXT-PK control without data
writes; this branch adds durable automated regression. Personal paths, schema
dumps and rows are excluded from repository evidence.

## Review Findings

No checker/native findings yet. Findings use severity → Observed → Inferred →
Verified by → merge/follow-up gate; every native finding receives written
fixed-in/follow-up/disputed disposition.

## Native Review Rounds

0/2. Manual trigger only after stable candidate/CI and owner request. Local
checker is separately identified; no accepted label or merge is authorized.

## Final Verdict

PENDING implementation and checks. Greg owns review acceptance and merge.
Live rollout remains pending after merge and requires a fresh preview and
separate owner decision. No third full-diff native review loop.
