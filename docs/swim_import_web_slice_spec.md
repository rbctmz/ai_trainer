# M2D: программа тренера в пользовательском web-сценарии

Issue #772 / parent #762 / epic #760. Spec Owner17.11.2026. Depends on M2B
#770 merged ee8279b and M2C #773 merged8ba8e49 after owner acceptance.
ClassA: new import/edit/human-confirmation flow. Merge/cleanup owner Greg.
Spec Owner hands the approved Python/API/TS semantics below to UI / Design
Specialist; styling/interaction follows docs/design/README.md, ui_standard.md
and workflow.md. Supervisor owns isolated test harness changes. No subagent or
new external platform is required. Review manual, budget0/2, candidate pending.

## User outcome and boundaries

The athlete opens the swimming-program workspace from Coach, pastes the trainer
text and retains it before AI work. Coach prepares/clarifies the whole program;
the athlete sees every workout next to the original, edits one element, prepares
the exact server preview, explicitly confirms and reopens the saved version
without another model call. Program/draft/library/catalog identities remain
server-owned. This is not a calendar/active-plan or watch-delivery action.

Use a dedicated /coach/swim workspace so a multi-workout/source/editor does not
compete with Today context and the existing single ordinary Coach proposal.
Keep the ordinary Coach page/flow and add a clear link. A selected source/draft
or library version is addressable in the URL; refresh/reopen restores it from
the server. Temporary form input is a recoverable browser buffer, not a second
canonical program. No personal DB/app, provider/watch writes or paid calls.

No new business rules in React: no metre/TSS/duration sums, source-gap readiness
inference, catalog-dose inheritance, schema migration, automatic workout changes
or fake saved state. Python summaries/prepare/confirm own these decisions. V1
library content is readable with its unchanged semantics; V2 retains rich
quantities and pinned exercise definitions. No private corpus seeding/media host.

## UI brief and contracts

First view: create source, resume a retained draft, open a saved program, or view
exercise definitions. In an open draft show source/program title, number of
workouts, pool/OW, exact or unknown distance with known fixed portion, unresolved
questions/coverage warnings and current operation state. Expand nested series,
equipment, technique notes, source fragments and pinned variant/version.
Do not replace unknown with zero or turn range/breath rest into one number.

The main action prepares a server preview, then clearly confirms that exact
snapshot. Edits direct or in dialogue update the same draft through M2B CAS;
the UI clears a no-longer-current preview. The backend still rejects stale/expired
tokens independently of UI. After successful confirm/readback show the immutable
saved version and its confirmation time; reopen uses library GET, not AI.

Source: CaptureSource/SwimImportDraftResponse; interpretation: #773 typed
SwimCoachTurnRequest/SwimCoachEvent; edits: InitialContent/PatchOperation;
confirmation: SwimImportPreviewResponse and common SwimProgramConfirmRequest;
readback: SwimProgramAnyVersionResponse and program list. Catalog uses existing
M2A preview/confirm/current/history/search and M2B exact exercise references.
Display instructions/gear from the prescription and pinned technique separately;
linking a definition never silently rewrites original equipment or dose.

Reuse existing semantic tokens, Markdown, disclosure/form/button patterns and
max-w-5xl layout. No unrelated visual overhaul. UI chooses composition after
the brief, implements a small synthetic interactive example with real components
and records screenshots/keyboard behavior; a picture alone is not acceptance.
No extra design approval gate: already approved source/one-program/explicit-save
concept applies; materially missing semantics get a clean Domain/API handoff.

## Direct/manual behavior

Source capture has no provider dependency. Preserve exact text/Unicode/spacing
and a stable request UUID through network retry. Unsent input/form staging may
use a per-demo/real browser recovery buffer; after server receipt the source is
read-only and URL-addressable. Do not store secrets or canonical preview truth
in a browser cache. Never send input automatically to AI after reload.

Without AI, provide an ordinary form for an initial multi-workout structure,
not a raw-JSON requirement. Name/context and nested swim/rest/group/unresolved
elements are explicit user input. Quantities cover distance, duration, attempts
range and open; repetitions count range or time/finish-current-cycle; rest
fixed/approximate/open and seconds/breath ranges; subjective effort has scope.
Initial form submits once to the existing parse API. Later direct changes use
one bounded server operation and read back the result. Local input defaults do
not become inferred training distance/duration/load.

Allow source-fragment selection/linking. Browser selection offsets must be
translated from UTF16 to Unicode code points for the existing API; displaying
fragments reverses that representation correctly. Coverage comes from backend
summary. Human acknowledgement of a non-instruction fragment includes its span
and reason; the model never receives that authority. Unresolved stays explicit
until a human/Coach bounded edit resolves it. Never hide a backend refusal.

Exercise list/search/version and create/edit forms use exact catalog DTOs and
human preview/confirmation. A selected definition can be attached with exact
revision; initial manual content can include exercise_references atomically.
Definition changes do not replace a program's retained snapshot. Dose is entered
for the assignment, not added to the technique definition. No automatic live
personal-library filling. Video cues are reference labels/times, not media hosting.

## Streaming, errors and confirmation

Use a source-specific SSE client for /api/coach/swim-import; retain the ordinary
Coach client. Safe nested error codes map to useful Russian messages. A missing
provider/native-only refusal keeps manual/source UI available. An error is not
an empty program; a read-only/no-change turn is not a successful interpretation.
Whole program has one card/context, not competing single-workout proposals.

SwimCoachEvent.library_saved is always false for that turn. A successful
mutation only means draft updated. readback_status=unavailable means revision
is last confirmed, not certified current; fetch the current draft before any
new preview/action. Do not reconstruct success from model prose or a stale
local object. Server-returned draft/summary is the only semantic projection.

For lost confirm response, keep the exact reviewed preview while that action is
pending and offer safe same-token retry/readback. Do not auto-confirm on reload
or recreate a save merely because no response arrived. Opening library content
shows an actual confirmed version, not an inferred match to a pending draft.
Stale/expired/conflicting state asks for a fresh server preview. Original and
local unsent corrections remain accessible rather than silently overwritten.

## Acceptance and evidence matrix

| Fixture / boundary | Observable behavior | Proof |
| --- | --- | --- |
| synthetic full program | source→Coach→clarify/edit→full preview→confirm→reload | real isolated API/DB + test-only native provider + browser |
|3workouts | one card,2200/2000/1900,6100total | API summary/readback and DOM |
| fixed1000 + timed175/25 | whole distance unknown; finish current200cycle retained | DOM + saved document |
| attempts10–15/hint | no invented prescribed metres | DOM + backend bytes |
|60–70seconds/3–4breaths/effort | ranges/scopes preserved | form edit→receipt→readback |
| exercise rev1→catalog rev2 | program displays retained rev1 after reopening | backend snapshot + DOM |
| manual/no-AI | source retained, forms usable, explicit save/readback | no provider or scripted refusal |
| omitted/unresolved/source gap | visible fragment/question, safe prepare refusal | UI plus backend gate |
| stale/expired preview | no stale save; refresh/reprepare | real writer/expiry fault, library count |
| lost response | same token retry yields one version | transport fault after real confirm |
| unavailable final readback | error plus last-known identity; refresh before preview | typed SSE + fresh GET |
| reload/network failure | retained source and staged input recover | browser reload/transport fault |
| real/demo | selected-store draft/catalog/library only | isolated DB assertions |
| V1 historical | old document still readable without conversion/AI | actual V1 fixture/library GET |

Check390/1280CSSpx, both themes,320px overflow, keyboard/focus, labels, form error
and focus return, loading/empty/streaming/stale/saved/history/no-AI states. Use
synthetic screenshots under docs/design/evidence/issue-772 with version/theme/
viewport. Do not claim screen-reader or WCAG certification from ARIA alone.

## Roles, RED, harness and review

UI files: web/app/coach/swim/page.tsx, web/components/swim/*, source-specific
web/lib client/types and Coach entry link. Existing domain semantics are consumed,
not redefined. Add missing GET registry consumers/scenarios once actually used;
selected-ID populated scenarios may use explicit documented inventory exclusions.
Run extractor/inventory freshness, relevant existing contracts and lint/build.

Supervisor-owned harness: add one allowlisted test-only native-provider API app
for the existing owned E2E stack, guarded by scratch identity and E2E scope.
It returns only synthetic fixture calls. This exercises actual Coach/store/
confirm routes end-to-end without network or real-model charges; it is not
evidence of live language quality. Default132E2E behavior remains unchanged.
Do not add a production fake parser or weaken DB guards for browser acceptance.

Before production UI implementation add own RED browser scenario(s), then a small
real-component prototype. Prototype outcomes/owner observations must be recorded
honestly; no invisible acceptance or claim that screenshots prove the workflow.
Run relevant UI/API/contract/full contributor-safe/E2E and CI checks. Native
review is bounded2rounds, merge requires explicit owner decision. Source/draft/
library reset/restore ownership is inherited, no new backend tables/files added.
Browser input buffers are namespaced/clearable, not authoritative snapshots.

ASR-MOD-2/3: consume shared DTOs; REL-1/2: exact meaning/unknown and visible failures;
REL-3/DEP-2: inherited durable source/draft/library; SEC-1: synthetic fixtures,
private safe errors, no provider/personal writes. Reuse ADR0001/0002/SQLite.
Trade-off: a dedicated full-width workspace makes original/structure review
readable while Coach remains the entry. Generic Coach/history is not redesigned.

Status18.11.2026: implemented in draft PR774 with19case isolated browser proof.
Source/dialogue/manual/direct editing, source acknowledgements, catalog and
initial atomic bindings, full preview/human confirm/immutable readback are present.
Own REDs and GREENs are in docs/swim_coach_import_execplan.md; synthetic screen
bundle and UI hashes are in docs/design/evidence/issue-772. Sequential19case
run passed59.40s without cleanup signal; lint/build/Ruff PASS. Local full Python
4709PASS/16skip/174deselected plus4unchanged DSH timeouts, with prior baseline
reproduction disclosed in the ExecPlan. CI, native review (0/2) and owner acceptance
are pending. Model/SDK doubles
do not prove live language quality; fresh paid-call budget remains required.
Full M2 goal stays active through those remaining gates; this is no live rollout.

Self-review handoff: ready for CI/independent review against the named criteria.
No reproduced open new-product blocker remains after the own RED→GREEN fixes.
This is not a merge verdict: current CI and human acceptance remain required.
No new domain/API contract, migration, dependency or provider/watch write was added.
