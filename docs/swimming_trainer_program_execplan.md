# Сохранить точную авторскую программу плавания и провести её к учёту


Living ExecPlan per `.agent/PLANS.md`; epic #760. Historical implementation sections below describe M1 #761; M1 is merged
in PR #766 at5042102. M2A #768 is merged d2e1cf3; current M2B #769 follows
docs/swim_coach_import_execplan.md; roadmap docs/swimming_trainer_program_roadmap.md owns M2–M5. Contract
is docs/swim_program_library_slice_spec.md. Owner Greg authorized implementation
16.11.2026; merge and live writes remain explicit owner decisions.

## Purpose / Big Picture


The athlete receives a durable program library that preserves the trainer's
original text, nested metre-based series, instructions, equipment and resting
semantics. M1 exposes preview/confirm/history through API, not yet a browser
importer. Later M2 supplies text input/web, M3 calendar protection, M4 FR255
serialization/readback and M5 factual accounting. The complete user outcome is
three reference workouts2200/2000/1900m surviving the full chain without silent
changes. Unknown full duration/TSS are not invented to fit an old planner budget.

## Progress


- [x] 16.11.2026: research on main59c5435; 144 existing tests and4 synthetic probes.
- [x] Owner clarified pool25/50, open water, FR255, subjective50–90%, open rest/Lap
  and immutable trainer structure with approval for proposed changes.
- [x] Publish preflight: correct origin, live main59c5435, write tools available.
- [x] Epic760 and five bounded child issues761–765 created; M1 in progress.
- [x] M1 contract written before production edits; role handoff Spec → Domain/API.
- [x] Behavioral RED: three new suites failed collection before implementation
  because the domain/store/router modules did not exist.
- [x] M1 GREEN domain, immutable preview/version store, API and reset hook;
  44 focused tests passed before the final nested-TypeScript conformance check.
- [x] M1 contracts/checks/self-review and native review completed in PR #766.
- [x] M1 PR #766 pushed, checks and bounded native review accepted by owner.
- [x] Owner accepted and merged #766 on16.11.2026, main5042102.
- [x] M2A #767 / #768 exercise catalog/API merged d2e1cf3 after owner acceptance.
- [ ] M2 #762: rich drafts #769, Coach and browser per swim_coach_import_execplan.md.

## Context and Orientation


Current main is59c5435. models/workout_catalog.py creates four swim templates,
with second-based legacy structure, not a trainer-authored workout model.
api/planning_service.py and models/planning_near_term.py own current planning;
this slice does not insert a library document into them. data/database.py owns
SQLite construction/schema/reset; services/snapshot_runtime.py coalesces existing
post-commit backups. api/main.py registers routers; api.deps.get_database selects
real/demo stores. web/lib/types.ts and tests/contracts/registry.json mirror the
HTTP contract. All business rules stay in Python.

The API receives explicit structured input in M1. That is a contract for the M2
parser/editor, not a requirement for athletes to write JSON. Original source_text
is retained unchanged alongside normalized typed structure. Synthetic fixtures
represent equivalent series without publishing private coach/athlete records.

## Plan of Work


First characterize the new model with RED tests. In models/swim_program.py define
strict versioned recursive nodes: swim, rest, group. Enforce identity uniqueness,
explicit environment and resource bounds before traversing large trees. Derive
exact metre totals and compatibility warnings. Qualitative effort/technique and
open/approximate rest remain explicit; never estimate unknown full time or TSS.

Next add data/swim_program_store.py with two additive tables and connection-bound
transactions. A preview retains exact document/summary/hash and base_revision for
24h. A confirm serializes writes with BEGIN IMMEDIATE, verifies retained content,
checks the base, appends one version and marks the preview receipt atomically.
Retries return that version, never whichever one is current later. Historical
reads and rollback-as-new-version preserve provenance. A corrupt current record
refuses rather than silently picking old history. Full reset and Backup API
restore prove ownership of every row, including applied receipts.

Then expose this through services/swim_programs.py and explicit Pydantic/API
contracts in api/swim_program_contract.py and api/routers/swim_programs.py.
Validation errors contain safe locations/codes, not the submitted source text.
Confirm uses the existing snapshot boundary only after actual commit, so a failed
backup never replays a program write. Registration is additive in api/main.py.
Mirror public types and extract their contract; add a synthetic POST-preview
conformance scenario without registering a dead frontend GET before M2.

Finally run focused and contributor-safe broad checks. The first native review
checks the complete specification and candidate; any second is a scoped delta.
No additional executor is queued: issue bodies were completed after their open
event, because codex-assign uses that event body and would otherwise duplicate
this local owner. This does not change repository automation or permissions.

## Milestones and handoffs


M1a is a pure model demonstrable by exact totals and failure cases. M1b adds a
restartable library and immutable preview/confirm with concurrency/reset/restore
proofs. M1c exposes the same contract over HTTP and mirrored types; no business
rules are added in TypeScript. These three internal steps form one #761 PR.
After M1 stabilizes, a documented Domain/API → UI Specialist handoff for #762
names exact routes/types and acceptance fixtures; UI uses them rather than
changing domain contracts. Later #763–#765 have their own implementation specs.

## Concrete Steps


Workdir is this task checkout, branch codex/issue-761-swim-program-library.
Use the existing primary Python3.11 virtualenv and Node22 (system Node25 has a
known missing dylib; no host repair belongs to this task):

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_isolated_tests.py tests/smoke/test_swim_program.py tests/smoke/test_swim_program_store.py tests/smoke/test_api_swim_programs.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m ruff check .
    env PATH=/opt/homebrew/opt/node@22/bin:/usr/bin:/bin:/usr/sbin:/sbin npm --prefix web run contract:extract
    env PATH=/opt/homebrew/opt/node@22/bin:/usr/bin:/bin:/usr/sbin:/sbin npm --prefix web run lint
    env PATH=/opt/homebrew/opt/node@22/bin:/usr/bin:/bin:/usr/sbin:/sbin npm --prefix web run build
    env PATH=/opt/homebrew/opt/node@22/bin:/usr/bin:/bin:/usr/sbin:/sbin /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_isolated_tests.py -m "not live and not debug and not e2e" tests/ -q
    git diff --check

Tests use only owned pytest SQLite and TestClient, no app startup/provider calls.
Do not run user app, scan credentials or mutate the working athlete database.
A real PR and pushed SHA must exist before declaring delivery complete.

## Validation and Acceptance


Reference fixtures preserve nested rounds and source bytes, sum2200/2000/1900m,
and leave duration/TSS null. Pool25 has compatible distances; pool50 flags25m
parts; OW rejects a pool length. Invalid metadata and overly deep/large trees
produce safe errors without writes. Changes in profile/CSS do not rewrite an
authored library version. A read after restart returns the identical document.
Two concurrent preview confirmations with the same base create one revision;
stale/expired/invalid/corrupt failures do not modify the library. Lost-response
replay returns its exact immutable receipt, including after later revisions.
A failure injected before receipt update must roll back the version insertion.
Full reset empties both tables; Backup API roundtrip retains all versions/receipts.

## Surprises & Discoveries


Observed: prior probes show CSS110→130 retained in captured profile but identical
RPE swim prescriptions, while direct CSS catalog targets change. A25m compact
interval becomes30m; swim threshold structure has four legacy blocks versus
seven run/bike steps. Inferred: separate handoff/precision gaps, not reasons to
rewrite load formula or trainer intent. Verified by: four read-only synthetic
research probes on59c5435; production fixes are owned by #765, not this M1.

Observed: codex-assign queues recognized issue bodies on open/reopen. Inferred:
opening all ready-to-run child specs would create unwanted parallel executors.
Verified by: reading .github/workflows/codex-assign.yml; local owner creates brief
issues then supplies the complete canonical contract using edited events.

## Decision Log


16.11.2026, owner: preserve trainer structure; offer changes for approval, distinguish
pool/OW; FR255, pool25 with50 option, manual Lap and subjective effort supported.

16.11.2026, Spec Owner: split the three product stages into five reviewable issues.
M1 is the library/API foundation; text/web is M2 and calendar is M3 because each
has distinct validation/ownership boundaries. This avoids shipping a cosmetic
text box that loses structure in the existing time/TSS-only planner.

16.11.2026, explicit handoff: Spec/Architecture Owner hands the bounded M1 contract
to Domain/API Implementer. Exact files/acceptance are listed above; no UI design
or adjacent planning math belongs to this role/slice. Independent checker is
manual native GitHub review before owner acceptance, not self-review.

## Idempotence and Recovery


Schema setup is additive and repeatable; no old rows or schema are rewritten.
BEGIN IMMEDIATE + unique keys own CAS/idempotence. Applied receipts/versions age
out only with explicit full reset; expired unapplied previews are pruned on new
preview transactions. Rollback appends a reviewed old document as a new revision.
Backup/restore uses existing SQLite Backup API, never a plain WAL-blind copy.
Source rollback leaves additive tables readable by a later version; explicit
reset remains the deletion boundary. No personal rollout is performed.

## Outcomes & Retrospective


In progress: research, owner choices, issue roadmap and M1 contract are recorded.
Implementation is present; final broad checks and independent review remain.
A complete M1 does not mean web
import, calendar protection, FR255 live delivery or factual swim parity is done.
Final exact-head evidence and merge outcomes belong to #761/PR, with epic progress
updated only when each corresponding criterion is actually achieved.

## Artifacts and Notes


The research baseline is reproduced using anonymous tests; public issue descriptions
contain requirements and totals, not private coach source/history. Original text
submitted by a user remains inside the selected store and explicit API responses.

## Interfaces and Dependencies


Reuse Pydantic2, stdlib JSON/hashlib/SQLite/UUID/datetime and existing FastAPI deps.
No new packages. SwimProgramDocument and summaries are owned by models/swim_program;
API wrappers expose typed preview/confirmation/read envelopes. Storage functions
accept Database and explicit document/base or preview identity, not arbitrary
paths. All metadata is validated on stored reads; failure codes are stable and
exclude submitted payload. This boundary is consumed by #762 and #763 later.

Revision16.11.2026: initial self-contained roadmap/contract before production edits;
M1 scope and role handoff fixed, all later slices remain separately owned.


## Self-review before publication

Correctness is checked through exact nested metres, strict scalar validation,
CAS concurrency, lost-response replay after later revisions, transaction failure,
restart, corruption refusal and Backup API roundtrip. A preview/confirmation never
calls the planner or provider. Reads select the same existing real/demo dependency.
No migration rewrites old data; reset owns both additive tables. Original text is
returned only in explicit library/preview responses, not validation errors.

The main weakness is the deliberately early API-only boundary: M2 must supply the
athlete-facing parser and preview before the product supports text import. A new
schema version must preserve old document validation/fingerprints. Applied receipts
and source versions intentionally accumulate; this is a bounded single-athlete
library, with a 1000-node document cap and 10000 expanded-node ceiling, not a
multi-tenant archive. No new packages, background workers or generic event store
were introduced. Full reset is the explicit deletion boundary.

17.11.2026 revision: recorded actual M1 merge and the owner-approved M2A
exercise-library handoff; earlier M1 implementation notes are historical.
