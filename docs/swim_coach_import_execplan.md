# Довести программу тренера до проверяемого сохранения через Коуча

Living ExecPlan per .agent/PLANS.md; parent #762 / epic #760. Owner Greg set the
active goal17.11.2026. M1 #766 and exercise catalog #768 are merged; current main
is d2e1cf364e988cf1a64dd64b1de8060f2b5e23d6. M2 spans explicit Domain/API and UI
handoffs, with a reviewable checkpoint per bounded issue. No new paid AI calls,
personal DB changes, provider/watch writes or automatic merges are authorized.

## Purpose / Big Picture


The athlete pastes a trainer program into Coach, clarifies its ambiguous parts,
checks exercises and nested series next to the original, edits one element,
explicitly saves and opens the same result again without another model call.
Pool/open-water context, source wording, exercise versions, ranges and time-based
work survive. Unknown distance/duration/load are displayed rather than invented.

## Progress


- [x]17.11.2026: owner approved #768 review/merge; main d2e1cf3, issue767 closed.
- [x] Active M2 goal and five-step plan recorded in #762; private24-case corpus remains ignored.
- [x] M2B #769 created, branch codex/issue-769-swim-import-draft based on merged main.
- [x] M2B contract/RED/GREEN: source-bound rich documents and editable retained drafts.
- [x] Domain RED: test_swim_program_v2.py collection fails because the version-aware adapter does not yet exist; frozen V1 warning order verified against main.
- [x] Domain GREEN: 54 focused V1/V2/exercise tests pass; strict version dispatch, Unicode source spans and resource bounds checked.
- [x] Store RED→GREEN: retained source/draft, bounded edits, stale generic confirm, exact exercise snapshot, race, corruption, rollback and Backup API restore; 54 focused store/domain checks pass.
- [x] API RED→GREEN and populated TS:139 combined focused checks PASS, then2 additional atomic/snapshot cases PASS in a33-test final focused run. Ruff/diff, extractor, web lint/build PASS with Node22.
- [x] Full contributor-safe pass completed with disclosed local limitations; baseline disproof and separate permitted reruns recorded below. Linux CI/native complete.
- [x] M2B reviewable PR, CI, bounded independent review and explicit owner merge decision.
- [x] M2B #770 merged ee8279b17.11.2026 08:54:02UTC after explicit owner approval. CI4645PASS/46skip/156deselected, E2E132PASS, native clean3bce1d6 (1/2), zero threads. #769 closed.
- [x] M2C #771 and M2D #772 created with bounded scope/acceptance; next branch codex/issue-771-swim-coach-tools based on merged main. M2C spec handed to Domain/API for RED.
- [x] M2C Coach read/prepare/patch tools with trusted turn binding and provider-path checks.
- [x] M2C tools RED63f28da→GREENeb4b91e;8adapter/wire +54existing native/runtime checks PASS. API RED302495d→GREEN74combined Coach checks; separate HTTP/SSE mode, no screen changes. Combined final focused215PASS; lint/build/contracts/Ruff PASS.
- [x] M2C broad/CI, independent review and owner merge gate (receipt below).
- [x] M2C #773 opened. Native round1 on3fd2669 found2P2; own RED d227749 reproduces3failures. Bounded question-claim guard and truthful last-confirmed revision/readback_status pass156focused checks; final CI/delta review pending.
- [ ] M2D web source/structure/editor/save/readback and isolated user acceptance.
- [x] M2C #773 owner accepted/merged8ba8e4917.11.2026 14:15:18UTC; #771 closed. Final CI4677PASS/47skip/156deselected, E2E132PASS, populated TS3PASS, scoped native round2 clean, bothP2 resolved. No additional model calls.
- [x] M2D #772 contract and actual browser RED: missing Coach entry link,1FAIL39.13s. First setup attempt lacked Chromium in scratch HOME; installed in separate /private/tmp/ai-trainer-playwright and reran. No personal app/DB.
- [x] M2D first source prototype GREEN: actual browser source capture/exact Unicode/spacing→URL→reload,1PASS8.08s; no AI request. New route/entry, input recovery buffer, selected-source read and root-list errors.94contract checks and web lint/build PASS. Structure/Coach/editor/save controls are not yet implemented.
- [x] M2D whole-program renderer RED cc345d1 (2FAIL17.07s)→GREEN (3PASS9.33s): all3workouts/server6100m and unknown total with fixed1000m + timed175/25cycle. Web lint/build PASS. Pinned technique/source fragments are readable; Coach/edit/save are pending.
- [x] M2D Coach journey RED68426f2(1FAIL35.66s disabled action)→GREEN1PASS7.32s: real API/DB + guarded synthetic native provider,3workouts→question→one context patch→full preview→explicit confirm→actual version GET→no-AI reopen. Separate source/boundary suite5PASS plus1expectedRED for absent manual editor; lost confirm response retries identical token into one version, concurrent draft rejects stale save.96contract checks PASS. This is not live model quality evidence.
- [ ] Full-goal audit: actual source→clarification→single edit→save→reload, current CI/review, explicit limitations.

## Context and Orientation


models/swim_program.py is the frozen schema1 contract. data/swim_program_store.py
retains24-hour previews and immutable library versions. models/swim_exercise.py
and data/swim_exercise_store.py own reusable definitions; catalog resolve returns
both pinned version content and a copied M1 step. No exercise lineage is yet
stored in complete programs. models/ai_tools.py owns Coach's tools;
models/ai_coach_runtime.py runs native/marker tool paths. api/routers/coach.py
saves user messages through models/chat_manager.py and owns the trusted request
boundary. Current message content is stripped before general chat storage, so
M2 import must capture explicit source text before any normalization/model call.
web/app/coach/page.tsx currently holds one proposal; a whole program must remain
one proposal with multiple workouts. api/routers/decisions.py owns existing human
confirmation, but model tools must never gain a self-approve operation.

## Plan of Work


M2B first creates models/swim_program_v2.py and a document adapter in
models/swim_program_documents.py. Schema1 classes/serialization stay unchanged;
only the library's validator/summary dispatch becomes version-aware. V2 stores
source spans, time/count ranges and full exercise snapshots. New
models/swim_import.py/data/swim_import_store.py/services/swim_imports.py and
api/swim_import_contract.py/api/routers/swim_imports.py own one persisted source,
append-only draft revisions and preview bindings. The public M1 preview request
stays schema1; V2 prepares only through source-bound import. All confirmations,
including the old M1 endpoint, enforce the central draft-revision guard.

M2C adds only bounded read/initial-parse/patch tools. Trusted source comes from
an explicit source selected/captured by the API, never a model's source_text
argument. The server injects source, stable program identity and exact catalog
snapshots. Initial parsing is separate from later targeted changes. Marker/native
handling is tested at the actual runtime boundary with deterministic providers;
malformed args and unsupported paths show failure. No additional real provider
call is made until an explicit budget is approved. The offline experiment is not
proof of live model quality and the corpus curator is not blind to held-out data.

M2D's UI Specialist consumes those contracts: source capture before AI, complete
program preview with original and unresolved fragments, exercise lookup, direct
and conversational edits of one server draft, explicit save and historical
readback. Narrow/wide, both themes, focus/keyboard and failure/stale/retry/reload
states are checked on an owned scratch API/web surface with synthetic data.
No personal application instance or athlete database is started or rewritten.

## Milestones


M2B has an observable API journey independent of AI: create from source, retain
an empty draft through restart, parse anonymous structure, bind an exercise
revision, patch one pause, reject old confirmation, save current version and
reopen exact bytes. V1 old JSON/fingerprint/summary also survives adapter changes.
After this checkpoint the rich source/draft contract is available to Coach/UI.

M2C adds a deterministic native and marker Coach journey against the same store.
It proves server binding, bounded edits and human-only saving with fake providers,
not live DeepSeek's understanding. The owner can approve a separately prepared
small live evaluation after this software path is concrete and reviewable.

M2D provides the user flow and isolated browser proof. The final goal is not met
by backend tests alone: visible original/structure, one-element edit, save/reload
and no-AI fallback must be observed. Calendar/delivery/factual accounting remain
M3/M4/M5 after M2 and are not silently included in this goal.

## Surprises & Discoveries


Observed: M1 quantity/rest/repeat fields are single positive integer metres or
counts; private corpus includes time-based patterns and ranges. Inferred: forcing
those into schema1 would alter meaning. Verified by: four existing representation
probes and current code inspection; V2 preserves them without midpoint estimates.

Observed: Pydantic rejects a field discriminator when the frozen V1 version field
has a before-validator. Inferred: callable tagged dispatch can retain that exact
validation without editing V1. Verified by: the same collection failure disappears
with tagged dispatch; frozen hash and strict bool/float/string-version tests pass.

Observed: generic M1 confirm accepts any retained preview UUID. Inferred: a
M2-only endpoint guard would be bypassed by generic confirm. Verified by: API/store
call tracing; RED must attempt both paths after changing the draft. No causal
claim of an existing product bug: this is a new ownership boundary.

## Decision Log


Decision: keep schema1 classes and canonical dump unchanged; version-aware adapter
supports V2 without inventing migration/backfill. Rationale: historical hashes and
receipts must remain valid. Date/author17.11.2026, Spec Owner.

Decision: source plus append-only draft revisions persist until explicit full
reset; confirmation tokens keep M1's24-hour expiry. Rationale: recover user work
from failed AI without promising immortal unconfirmed M1 previews. This adds
private SQLite state only, no media/filesystem repository.
Date/author17.11.2026, Spec Owner.

Decision: document-level exercise bindings pin node id, definition id/revision/hash
and full definition snapshot. Model input passes references only; server loads
the content. Rationale: preserve source prescription separately from technique;
no automatic equipment/pace rewrite. Date/author17.11.2026, Spec Owner.

Decision: extract only transaction-scoped preview creation; common confirm already
owns one writer transaction, so call the V2 binding guard there directly rather
than add an unused confirm wrapper. Import preview rows retain replay receipts
alongside draft history until reset, but expire as authority after24h. Rationale:
retry must return the original token even after a draft edit; retaining it never
bypasses expiry/current-revision checks. Date/author17.11.2026, Domain/API handoff.

## Concrete Steps


Work in task checkout on codex/issue-769-swim-import-draft. Python is
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python; use explicit Node22
PATH for extractor subprocesses. Before implementation run focused RED:

    python scripts/run_isolated_tests.py tests/smoke/test_swim_program_v2.py tests/smoke/test_swim_import_store.py tests/smoke/test_api_swim_imports.py -q

Then add frozen V1 fingerprint/readback tests, exercise/catalog regressions,
concurrency/reset/Backup API restore and token-bypass tests. Run the full normal
contributor-safe contour, Ruff, contract extraction and web lint/build. Socket
sandbox failures get named permitted reruns rather than changing product guards.
Publish each completed milestone; no merge without explicit owner approval.

## Validation and Acceptance


On synthetic source a three-workout program totals2200/2000/1900m. A separate
source has a fixed1000m portion plus30min repetitions of175+25 with finish-current-
cycle: exact whole distance and whole duration remain null. A10–15attempt drill
keeps its range;~10m orientation does not become prescribed distance. Rest60–70s
and3–4breaths survive as ranges. Save/reload keeps them and pinned exercise
snapshots after the catalog changes. Changing one rest leaves every other field
identical; old un-applied preview fails409 through every confirm entry point.
Applied retry returns its original version even after new draft/library revisions.
Missing/corrupt/expired/stale state has safe visible output and no partial writes.

## Idempotence and Recovery


Additive tables are initialized on owned SQLite and deleted by full reset.
BEGIN IMMEDIATE serializes source/revision/preview/confirm transitions. Request
receipts reject changed command replays. Rollback appends a reviewed earlier
structure as a new draft/library revision; no source overwrite. SQLite Backup API
restore into a new owned target recovers drafts, histories and receipts. Confirm's
post-commit snapshot sees the whole committed state and replay does not snapshot.
Code downgrade leaves additive state; old code cannot execute unrecognized V2.

## Interfaces and Dependencies


The M2B slice spec is docs/swim_import_draft_slice_spec.md. V2 is a separate model;
a TypeAdapter discriminates schema_version1/2. Generic library readers accept
both and direct legacy preview input stays V1. Import endpoints own source capture,
initial parsing, patch, current/history and prepare-confirmation. The final human
confirm stays on the common program path and always validates import binding.
No new packages, provider clients or frontend domain formulas.

## Artifacts and Notes


#768 receipt: merged17.11.2026 07:55:43UTC, merge d2e1cf3; clean native fd66f9d,
1/2rounds, CI4603PASS/45skip/156deselected. First CI test prerequisite mismatch was
fixed, not retried blindly. User checkout/runtime was not updated by remote merge.
Private corpus stays in ignored data_dumps/swim_coach_corpus; do not remove this
worktree or expose source/video/transcript in public fixtures. Confirmed user
clarification: timed block finishes the current full200mcycle.

## Outcomes & Retrospective


M2A/M2B/M2C are merged. M2D contract/browser RED are ready; its UI is not yet
implemented. Active branch codex/issue-772-swim-import-web is based on merged
main8ba8e49. Full goal remains active through UI and acceptance.
M2B final current-head bundle is PR770. Local broad4659PASS/18skip/156deselected
plus7fail/5errors; permitted rerun52PASS,4DSH timeouts remain. One DSH case also
fails on isolated clean baseline d2e1cf3 (60.26s); scripts/tests unchanged. Cause
unknown. Linux CI is green separately; do not claim a fully green local broad.
The complete M2 goal is active, not achieved by catalog API or planning alone.

Revision17.11.2026: initial full-goal plan after owner approval and M2A merge.
Revision17.11.2026: M2B GREEN checkpoints and retained-preview receipt semantics;
kept full-goal distinction and recorded predecessor's actual merge outcomes.
Revision17.11.2026: owner accepted/merged #770; recorded final CI/review/baseline
limitation, created #771/#772 and began explicit M2C contract handoff.
