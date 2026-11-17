# M2A: личный справочник упражнений плавания

Issue #767, parent #762 / #760. Owner/merge owner: Greg. Date: 17.11.2026.
Spec/Architecture Owner hands the following bounded contract to Domain/API
Implementer in this local task. No additional executor is queued. UI handoff is
separate: M2 still owns the Coach/import/editor flow.

## Change Class

Class A: additive persistent state, identity/provenance, new HTTP contract.
Review trigger: manual; native review budget 0/2, acceptance head pending.
Checker: independent native reviewer after stable candidate/CI. No merge authority.

## Scope and public contract

A private exercise definition describes technique, one named variant, aliases,
stroke, equipment, applicable environments and optional source excerpts/video
cues. It contains no prescribed metres, duration, rest, TSS or personal zones.
A cue identifies a source label and integer start/end seconds; it does not serve
or fetch a local file or remote URL. No private corpus is seeded automatically.
Different variants/names may coexist; matching never merges definitions.

`models/swim_exercise.py` owns strict version1 documents: UUID id; nonblank name
and variant up to200chars; at most20 distinct nonblank aliases; instructions
1–2000chars; stroke/equipment enums compatible with M1; at least one distinct
pool/open_water environment; optional source_label200/source_text6000; up to20
video cues with nonblank source_label200 and 0≤start<end≤86400seconds. Unknown
fields, boolean/fractional seconds and duplicate enums fail validation.
Source excerpts are preserved as entered. Names/aliases are not translated.

POST `/api/swim-exercises/preview`: `{document}` → normalized document plus
SHA-256 fingerprint. This preview is pure, not a retained M1 preview/receipt;
there is no persistent draft, expiry or write at this endpoint.
POST `/api/swim-exercises/confirm`: `{document,fingerprint,base_revision,
request_id,confirm:true}` → exact stored version. Document hash must equal the
reviewed fingerprint. base_revision is strict integer≥0; request_id UUID.
A current head different from base produces409. A request_id replay returns
its original version even after later revisions; changing its document/base
returns409. Literal boolean true is mandatory. No LLM mutation tool is added.
GET `/api/swim-exercises?q=` lists current versions, matching name/variant/alias
with casefolded literal substring; no fuzzy merge. GET `/{id}` reads current;
GET `/{id}/versions/{revision}` reads exact immutable history. Invalid requests
return safe422 codes, absent404, conflict409, corrupt/unavailable store503,
without submitted private values in errors. Search query is bounded200chars.

POST `/api/swim-exercises/resolve`: pinned exercise UUID/revision, M1 node id,
explicit metres and optional assignment instruction up to500chars → full exact
exercise version snapshot plus an M1 SwimStep. Step copies name/stroke/equipment;
instructions combine named variant, definition and assignment note. No inference
of distance or effort. This operation is read-only. A consumer must keep the
returned version snapshot for later lineage; M1 itself stores the fully copied
step content, not a live reference. Persisting a rich composition/lineage envelope
and the web constructor belongs to the next M2 slice; this PR does not claim it.
An exercise update never changes existing M1 documents/fingerprints or receipts.

TypeScript mirrors all envelopes in web/lib/types.ts. Register synthetic pure preview and refresh extracted contract. Catalog GETs
are not dead frontend entries; populated list/resolve envelopes are additionally
checked with standalone extractor roots until M2 wires actual consumers. No
existing M1 schema/hash changes; no new provider/CLI/event/config contracts.

## State, failures, reset and rollback

One additive table `swim_exercise_versions`, primary(exercise_id,revision), unique
request_id, stores full canonical document/hash/base_revision/time. BEGIN IMMEDIATE
owns CAS, duplicate handling and append. Read paths validate bytes, identity,
hash, revision/base relationship, UUID request id and UTC timestamp. Corrupt head
never falls back to old content. Historical independent reads remain available.
All versions are retained for this personal library; full reset deletes all rows.
No filesystem media state is introduced. SQLite Backup API includes the table;
restore into an owned new DB recovers exact historical/current content/replays.
Post-commit snapshot is invoked through existing backup_operation; failure marks
degradation and never repeats business write. A retry does not snapshot again.
A failed insert leaves head/receipt unchanged. Rollback is a newly confirmed
copy of an earlier definition at the current base, preserving every old revision.
Code rollback leaves additive rows; no destructive migration is required.

## Non-goals

Coach tool wiring, browser screens, automatic import of personal material,
training generation/load selection, lossless timed/range M2 drafts, calendar,
watch/provider writes, Garmin compatibility certification and public media hosting.
The existing legacy workout_catalog is a whole-workout template catalog and
continues unchanged. No general-purpose persistence framework/refactor.

## Acceptance and RED matrix

| Scenario | Required observation / test |
| --- | --- |
| Define → preview → confirm → reopen | Pure preview leaves list empty; exact source/cues roundtrip after restart |
| Same names, different variants | Distinct ids retained; alias search finds candidates without merging |
| Lost response / newer head | Same request replays original receipt; changed request/base409; concurrent same-base one winner |
| Update or rollback | rev1 stays exact after rev2/rev3; resolving rev1 returns old instructions |
| Reuse in M1 | Resolve pinned version, save its step in a synthetic M1 program, edit catalog; saved M1 bytes/hash/readback unchanged |
| Corruption/insert failure | No head fallback, safe503, retry succeeds after injected fault removed |
| Backup/reset/restore | All exercise revisions/receipts restored; reset removes all local exercise rows |
| Snapshot boundary | Fresh connection observes committed version before backup; replay no extra backup |
| API/privacy/isolation | Explicit true; no private values in422/503; demo store separated; mirrored TS validates populated recursive response |

Tests: tests/smoke/test_swim_exercise.py, test_swim_exercise_store.py,
test_api_swim_exercises.py plus M1/API/snapshot/reset/contract regressions.
Contributor-safe suite and Ruff; types.ts changes require web lint/build and
contract:extract freshness. Native review after CI; owner decides merge.

## Evidence boundary matrix

| Identity | Provenance/time | State | Expected |
| --- | --- | --- | --- |
| exact historical | pinned rev1 | rev2 current | resolve rev1, not rev2 |
| current | request already applied | later revisions | original receipt |
| ambiguous alias | distinct variants | both valid | multiple candidates |
| current | corrupt newest bytes | older valid |503, no fallback |
| unknown | unconfirmed definition | pure preview | no persisted record |

## ASR / ADR and review

ASR-MOD-2: shared Python resolves content, browser consumes contract.
ASR-MOD-3/DEP-2: additive schema, restore/reset proof, M1 compatibility.
ASR-REL-3: atomic append and post-commit backup. ASR-SEC-1: private source/error
redaction. Reuse ADR0001 web-first, ADR0002 local SQLite and ADR0006 immutable
versions. Trade-off: simple standalone catalog append API; M1 full program
preview/confirm semantics stay unchanged. No new ADR required.

Spec self-review: observable criteria and ownership explicit; unresolved native
findings NOT YET; final verdict BLOCK until implementation, tests, CI and review.
Merge/cleanup owner Greg; retain this worktree's ignored private corpus.

## Candidate evidence bundle / handoff —17.11.2026

RED415435b: all3new modules absent,3collection errors; RED checkpoint pushed.
GREEN:166focused/new/M1/contract checks PASS on final implementation. Cases
cover copied M1 bytes after definition update, same-name variant candidates,
exact historical snapshot, stale/replay/conflicting command, insert rollback,
additive init, reset and Backup API restore, committed readback before snapshot,
no extra snapshot on replay, private HTTP errors and independent demo store.

Ruff and git diff --check PASS. Node22 web lint/build PASS; contract:extract
--check PASS. Registry only registers pure preview200 until actual web GETs
exist; populated resolve/list and confirm DTOs use standalone extractor roots.
Initial prototype contract-root/inventory errors were corrected before this
checkpoint; default Node25 dylib failure avoided via explicit Node22 child PATH.

Full contributor-safe sandbox run:4621passed,18skipped,156deselected,
3failed/5errors in370.95s. All8failed/error cases reproduced PermissionError
on localhost bind:7Garmin Personal API cases plus isolated Streamlit health.
Separate reruns with localhost permission: full Garmin Personal API module
51passed; isolated health1passed. No live Garmin, credentials, source DB or
persistent app session involved. This is not a claim of one entirely green
local broad run. Current Linux CI remains a required gate.

Self-review: no edits to M1 domain/store/router/contract; no private source
fixtures in tracked diff; new state registered in initialize/reset and backup
roundtrip; no provider I/O. Code supports technique catalog reuse, not full
Coach/importer/composition lineage or current watch capability certification.
No known blocking finding from self-review; independent native review pending.

Domain/API→UI/Coach handoff: use explicit DTOs in api/swim_exercise_contract.py
and web/lib/types.ts, synthetic fixtures in tests/smoke/test_swim_exercise.py.
Preview has no DB side effect; persist only explicit confirmed payload with
fingerprint/base_revision/request_id. Retry unchanged request after lost response.
Select UUID+revision, retain full resolved snapshot alongside future composition
lineage and compare exercise environments to workout context in shared Python.
Do not infer semantic equivalence from alias or shift these rules into React.
M1 stores copied step content only; rich exercise-lineage persistence is not yet
implemented. Temporal/range drafts remain separate M2 work. Watch proof is #764.

Native review rounds:0/2, manual trigger only after CI/head stable. Review
findings and exact dispositions will be recorded in PR. Verdict: implementation
verified locally within disclosed limitations; CI/native review/owner merge
pending. No merge/cleanup performed; preserve ignored corpus in this worktree.

## CI correction before native review

First Linux run43967405731 on a291d5e:4602passed/44skipped/156deselected,
1failure in the new combined HTTP+TS test. Observed stderr ERR_MODULE_NOT_FOUND:
Python contributor job intentionally does not install web/node_modules. The
HTTP calls all returned200. Inferred: new test had an implicit web dependency.
Verified by: actual job log and local restricted-PATH run after splitting:
7HTTP tests PASS, standalone TS check SKIP. With Node22+web deps standalone
populated check PASS. Existing extractor prerequisite guard reused; the populated
check is explicitly added to the Web E2E job after npm ci so CI actually executes
it. Backend implementation unchanged. Next CI and native review still pending.
