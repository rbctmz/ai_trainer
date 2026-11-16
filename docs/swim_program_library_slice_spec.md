# M1: неизменяемая библиотека программ плавания

Issue #761, epic #760. Author: Codex; independent checker: final manual native
review of the complete candidate; merge owner: Greg. Date16.11.2026. Base59c5435.

## Change Class

Class A — Full: новый persistent/provenance и cross-module contract. Native
manual only, budget two rounds. Final exact-head evidence is kept in the PR.

## Scope и роли

Spec/Architecture Owner defines this contract first, then explicitly hands it to
Domain/API Implementer for models/swim_program.py, data/swim_program_store.py,
services/swim_programs.py, api/swim_program_contract.py, api/routers/swim_programs.py,
additive Database schema/reset hooks, registration and contract-backed tests.
M1 adds mirrored TypeScript types for M2. No CSS/layout/interaction choice belongs
to this slice; UI Specialist consumes the stabilized API in #762.

## Non-goals

No NLP/LLM parser, UI, calendar assignment, provider write, runtime Personal API,
TSS/CSS formula/generator change, automatic rescale or athlete-history repair.
The input is an explicit structured document; M2 prepares it from text. No user
credentials, personal database or real provider calls in development/tests.

## Public document contract

A schema_version=1 trainer_authored document owns program UUID, title, unchanged
source_text, optional source_week_label and 1–30 workouts. Each workout has a
stable local ID, title, explicit pool/open_water environment, optional metric
pool_length_meters (required for pool; absent for OW), and recursive steps.
IDs are ASCII local identifiers, unique across all workouts/nodes in a program.

A swim node has integer distance_meters, instructions, stroke and equipment. A
rest node has fixed/approximate/open mode: fixed/approximate require seconds;
open has no seconds and may retain a breath count. All retain instructions.
A group has repetitions, child steps, optional subjective-effort progression
and explicit last_rest policy include/omit/unspecified. A distance block with
internal parts is a one-repeat group; totals are derived only from its leaves.
No extra fields, booleans-as-numbers, NaN/infinity or arbitrary coercion.

Subjective percentage uses its own scale, never CSS/RPE conversion. Equipment
placement and qualitative technique remain instructions. Unknown pause and
unverified technique remain unknown. Total distance is exact; full duration and
TSS remain null in M1. Pool-incompatible leaf distances produce stable warnings
with node/workout ID; library storage is allowed, execution is a later gate.

Resource bounds are protocol limits, not training guidance: ≤1000 stored nodes,
depth≤6, ≤10000 expanded nodes, repeats≤100, source_text≤50000 characters,
name≤200 and instructions≤3000. Distance≤100000m per swim node; total≤1000000m.

## API contracts

POST /api/swim-programs/preview accepts document + strict base_revision≥0.
It validates, derives summary and retains an opaque preview UUID for24h without
creating a library version or affecting a planning checkpoint. Response returns
exact document, summary, fingerprint, base_revision, preview_id and expires_at.

POST /api/swim-programs/confirm accepts only preview_id and confirm=true. It
publishes the retained bytes as a new immutable revision if library head still
equals base_revision. Retry of an applied preview returns its original revision,
even after another version or expiry. New draft against a stale base is409.
Missing preview/version is404; expired unapplied preview409; corrupt stored
payload503; malformed requests422 without echoing raw original text in errors.

GET /api/swim-programs lists current summaries. GET /api/swim-programs/{id}
returns current immutable version; GET /api/swim-programs/{id}/versions/{revision}
returns an old one. No delete/update-in-place endpoint or planning activation.
Origin is the single-athlete DB selected by the existing dependency (demo stays
isolated). No frontend formulas or public implicit persistence flags are added.

## State, concurrency, failure/reset/rollback

Two additive tables: swim_program_previews and swim_program_versions. They own
only this library, not activity/provider/cycle IDs. Versions have unique
(program_id,revision) and preview_id; immutable document/summary/fingerprint.
BEGIN IMMEDIATE encloses stale check, version insertion and applied receipt.
A failure rolls back all three; a retry after a lost response reads the receipt.
Every read validates retained document/hash/derived summary; never fall back to
an older revision when current content is corrupt. Errors expose safe codes.

Old previews expire after24h; successful preview creation prunes only expired,
unapplied drafts in its transaction. Applied receipts/versions persist until full
reset. Full reset clears both tables atomically. Backup API includes both and
restore preserves revision/receipt identity; confirm triggers the existing
post-commit snapshot boundary only for a new version. No snapshot before commit.
Rollback of an authored edit is explicit preview/confirm of the old document
against the current revision, appending history rather than deleting it.

## Evidence boundary / RED matrix

| Boundary | RED or falsifier | Expected GREEN |
| --- | --- | --- |
| Nested series / fixed-open-approx / subjective effort | New model absent | Exact2200/2000/1900, unchanged source, null duration/TSS |
| Pool25 / Pool50 / OW | Missing environment contract | Compatible/warning/OW constraints, no silent adaptation |
| Invalid/unknown/deep/large/duplicate IDs | Strict contract absent | Named safe422, no writes |
| New/current/stale/historical | Library absent | CAS, immutable reads and append-only rollback |
| Commit / injected partial failure / lost response | Store absent | Atomic rollback / same receipt on retry |
| Two concurrent confirms | No serialization contract | Exactly one revision at a base; other409 |
| Existing DB / restart / reset / Backup API restore | No lifecycle | Additive migration, all rows retained/restored or reset |
| Corrupt current/preview bytes | No read gate | Safe503, no old-version fallback / no confirm |

## ASR / ADR

ASR-REL-1: preserve author identity/history; REL-2: unknowns are explicit;
REL-3/DEP-2: atomic writes, reset and Backup API drill; MOD-3: additive schema;
SEC-1: source text isn't an exception/log payload. Reuse ADR-0001 API/web direction,
ADR-0002 SQLite/Backup and ADR-0006 append-only/CAS tactics. This library isn't a
new active-plan selector; calendar ownership remains #763.

## Checks, review, verdict

BDD/TDD domain, storage, HTTP, invalid/corrupt/concurrent/replay/reset/restore;
contributor-safe broad suite, Ruff, TS extractor and current CI. Mirrored types
must pass web lint/build; no UI screenshot because no UI in M1. One native full
review plus scoped verification only when needed, no more than two rounds.

Current verdict: implementation pending. Completion is M1 API foundation, not
completed swim UX or live FR255 acceptance. Exact checks/results and remaining
M2–M5 are reported in the issue/PR and ExecPlan.
