# M2B: источник, полная структура и редактируемый черновик

Issue #769, parent #762 / epic #760. Base d2e1cf3. Owner/merge owner Greg.
Date17.11.2026. ClassA (persistent source/provenance and cross-module contract).
Manual native review, budget0/2, candidate/acceptance SHA pending.
Spec Owner explicitly hands this contract to Domain/API Implementer in this
local task. UI/Coach implementation follows separately on these contracts.

## Scope and non-goals

Store a trusted source, versioned rich structure, pinned exercises and bounded
edits; prepare exact current content for human confirmation into the existing
library. No LLM parser/tools, UI styling, personal-data import, dates/calendar,
provider/watch writes, inferred training load or generic persistence framework.
No historical data migration/backfill or schema1 canonical serialization change.

## Document V2

Keep models/swim_program.py and its schema1 dump/hash semantics unchanged. Add
models/swim_program_v2.py and models/swim_program_documents.py with strict
schema_version discriminator1/2 validation, fingerprint and summary dispatch.
V2 owns origin trainer_authored, program UUID, title, source UUID, original
source_text≤50000, SHA-256 matching that text, optional source label/week label,
1–30workouts and exercise bindings. Source metadata is server-injected for imports.

Workout context remains pool/open_water; pool length10–100m required only for
pool. IDs are unique ASCII identifiers across workouts/nodes. Nodes≤1000,depth≤6;
known count expansion≤10000; groups have at most100children, counts1–100,
metres1–100000 and known distance≤1000000. Timed groups are traversed once for
summary, never expanded into invented cycles. Source spans use Unicode code-point
start-inclusive/end-exclusive offsets and must be in bounds; source text is not
normalized. UI rendering must not treat these as UTF16 offsets.

A swim node owns name/instructions/stroke/equipment and an explicit quantity:
distance(metres), duration(seconds), attempts(min/max and optional informational
metre hint) or open. An attempt hint is never prescribed metres. A rest owns
fixed/approximate/open mode, seconds range or breath range (strict integers,
min≤max); fixed requires equal second bounds; open has no seconds, may have
breaths; no midpoint or breath→seconds conversion. A group owns child steps,
count range or timed repeat(seconds,finish at timer/current_cycle), instructions
and last_rest include/omit/unspecified. Subjective effort remains percentage with
explicit scope within_node/across_repetitions, never CSS/HR conversion.
An unresolved node preserves source spans, literal instruction and a question;
it is not a fabricated swim/zero-distance step.

Document-level exercise binding identifies exactly one swim node and an exercise
UUID/revision/fingerprint/full definition snapshot. Stored snapshot's id/hash must
validate; server resolves references against the exact catalog revision when
parsing/linking, not the current head. Prescription fields from the source are
separate and are never silently replaced by catalog defaults. Applicability to
workout environment is checked in shared Python and reported/blocking before
confirmation. Historical library reads use the retained snapshot, not a live
catalog/chat lookup.

V2 summary has nullable exact distance, known fixed-distance portion, null whole
duration/TSS, per-workout totals and stable warning codes. A timed repetition
contributes no invented fixed metres; its cycle distance can be reported separately.
A count range is retained, not replaced by its midpoint/minimum as an exact total.
Unknown distance remains null. Fixed/open/approx rest contributes zero metres.
Pool leaf compatibility warnings do not declare the training physically invalid.

## Source and draft lifecycle

POST /api/swim-imports captures explicit user text plus optional title/label and
request UUID, creating one immutable source and revision0 with no parsed document.
It succeeds without AI. Internal Coach integration may later bind exact raw
current/selected user text with server-owned chat/message identity. Model arguments
cannot supply/replace source text or actor identity. Source capture is before
normalization/provider work; M2C must not reuse stripped chat text as original.

Meta source row, append-only revision rows and import-preview bindings persist
until full reset. There are no external files/media artifacts. Empty/failed-AI
drafts remain readable after restart. A canonical V2 library version includes
its own original source and exercise snapshots so reopening needs no AI.

GET /api/swim-imports and /{id} return selected-store drafts/current revisions;
GET /{id}/revisions/{revision} reads historical draft. POST /{id}/parse accepts
expected_revision, request UUID, title/workouts/source spans and exercise references
only. First parse is allowed when no document exists. Server injects original,
source hash, program identity and exact catalog snapshots. No full-document
regeneration update endpoint is exposed after initial parse. A new explicit
reparse creates a separate draft; original/history are not overwritten.

POST /{id}/patch accepts expected_revision/request UUID and one typed operation.
Scalar operations target rest, quantity, instruction, repeat, title/context or an
exercise binding; structural add/remove/move/replace targets one subtree and must
not accept program/source replacement. Resolve-unknown replacement targets only
an existing unresolved node. Whole-workout/program root replacement is forbidden.
All changes revalidate unique IDs, limits, source spans, exercise applicability,
summary and coverage. A rest patch must leave all unrelated fields identical.
Human-only acknowledgement of an uncovered non-instruction source fragment
records its span/reason separately; Coach tools will not receive that operation.
The operation actor is supplied by service boundary, never request/model input.

Every parse/patch appends one revision and receipt under BEGIN IMMEDIATE. Same
command replay returns its original result; mismatched request payload conflicts.
Changed head409; missing404; invalid422; corrupt/unavailable503. Validation errors
contain safe codes/locations, not source input. One draft remains the source of
truth for both dialogue and UI, scoped to selected real/demo store.

## Preview and common confirmation guard

POST /{id}/preview accepts exact draft_revision and base_library_revision plus
request UUID. It refuses unresolved nodes and unacknowledged source gaps, and
prepares M1-style24h preview plus immutable draft-revision binding atomically.
Ranges/time/open quantities are valid semantics, not unresolved parse failures.
A program may have unknown distance; it is not claimed executable on a watch.

The existing human POST /api/swim-programs/confirm remains the save endpoint,
with response unionV1/V2. Its common storage path ALWAYS validates V2's import
binding. An un-applied preview whose draft head changed fails409, including when
called directly through the old M1 endpoint. Applied retry returns the original
saved version even after expiry/later drafts/library versions. A deleted/malformed
binding is corruption, never permission to bypass the draft gate. Public M1
preview request remains schema1; V2 preparation is source-bound import only.
Library current/history readers supportV1/V2; list exposes schema version and
nullable distance/known fixed distance. V1 document/fingerprint/derived summary
bytes and applied receipts remain valid without rewriting rows.

Extract transaction-scoped create/confirm helpers inside swim_program_store so
import revision check, preview binding and library receipt share one connection.
No nested writer transaction or external connection between guard and write.
Post-commit backup occurs only after complete commit, once per new save; replay
and preview-only operations do not snapshot. Crash/injected failure rolls back
binding/version/receipt together. Old un-applied preview expiry remains24h; draft
source/history remain retained. Rollback uses reviewed earlier content as a new
revision/preview, preserving original source and all history.

## Acceptance / RED matrix

| Boundary | Observable proof |
| --- | --- |
| FrozenV1 | Old raw document/hash/summary/receipts roundtrip after adapter/schema init without data rewrite |
| V2 quantities |30min175+25finish-current-cycle and10–15attempts/~10mhint retain intent; total unknown; fixed1000separate |
| Ranges/effort |60–70s,3–4breaths, subjective50→90and scope survive save/reopen |
| Trusted source | Submitted replacement source/id/actor rejected; failed AI needs no source recapture |
| Exact exercise | rev1 snapshot persists after rev2; missing/corrupt/inapplicable variant explicit; no gear inheritance |
| Bounded patch | One pause change has exactly one intended difference; immutable source and siblings |
| Stale token bypass | Change draft after preview; both common/import confirmation paths reject old token |
| Atomic/replay/races | One winner, no partial versions; lost response returns same receipt; applied retry after later revision |
| Reset/restore | All new tables reset; Backup API restore retains source/drafts/snapshots/library/receipts |
| API/contracts | Safe errors, real/demo isolation, mirrored TS and populated conformance |

Required tests: test_swim_program_v2.py, test_swim_import_store.py,
test_api_swim_imports.py; all M1/catalog/contract/snapshot regressions, Ruff,
normal isolated contributor-safe tests, extractor freshness, web lint/build,
current CI and independent native review. No UI surface in this slice; screenshots
belong to subsequent M2D. Snapshot/backup tests use owned scratch only.

## Evidence matrix / ASR / review

Current/historical draft × current/stale/applied/expired preview × source/catalog
present/corrupt/missing × V1/V2 are exercised where meaningful. Historical read
never silently falls back from corrupt head. Binding/source corruption blocks
save; preserved full historical library content remains independently readable.
ASR-REL1/2: source/meaning/unknown retained; REL3/DEP2: atomic append and restore;
MOD2/3: shared rules, compatible old data; SEC1: private errors/source isolation.
Reuse ADR0001/0002/0006. No new provider or filesystem boundary.

Spec self-review verdict: ready for bounded RED implementation, not completion.
Native round0/2; findings/CI/current head recorded in PR. Merge owner Greg.
M2C receives trusted source/draft/patch contracts; UI receives only validated
semantics and DTOs. Full goal remains incomplete until Coach+web acceptance.
