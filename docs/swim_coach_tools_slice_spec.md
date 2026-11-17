# M2C: Коуч работает с одним сохранённым черновиком

Issue #771 / parent #762 / epic #760. Spec / Architecture Owner,17.11.2026.
Depends on M2B #769 / PR #770, merged ee8279b after owner acceptance17.11.2026.
Current branch codex/issue-771-swim-coach-tools follows that merged main.
ClassA: trusted context, model capability and API/SSE/source identity. Human
merge/cleanup owner Greg; native manual review budget0/2. No paid calls approved.

## Purpose, scope and non-goals

The athlete sends a saved source to Coach, answers a clarification and requests
one edit. Coach reads or changes the same M2B server draft shown in the editor.
The library is unchanged until the athlete prepares/confirms a human preview.
Source capture already succeeds through /api/swim-imports without any provider.

Add an explicit import-turn branch in the Coach HTTP boundary and a small
provider-independent tool adapter over services/swim_imports.py and the existing
library/catalog. Do not give the model ordinary Coach planning/recovery tools
in this mode. Do not run the ordinary readiness/recovery mutation preparation
as a side effect of importing a program. General Coach requests stay unchanged.

No UI layout/styles, dates/calendar/load/watch delivery, personal data import,
new live-model experiment, global ChatManager migration or universal provider
rewrite. Full M2 is not complete until #772 browser acceptance. Existing6/6paid
DeepSeek calls are exhausted. Native stub tests prove software contracts only.

## Observed extension points and minimal falsifiers

Observed: api/routers/coach.py strips req.message and resolves a provider before
ChatManager.add_message; ChatManager.add_message returns bool, not a durable
message id. Inferred: do not use normalized chat history as the import source.
Verified by: current source inspection17.11.2026. Instead the explicitly captured
M2B source_id is the authoritative original, retrieved from selected-store DB.

Observed: run_native_tool_loop receives all schemas from its ai_tools adapter
and runs at most2rounds; marker regex ends at a closing bracket. Inferred: a
restricted native adapter can reuse execution without exposing other tools;
recursive marker input must not be advertised as supported. Verified by:
current runtime code and earlier synthetic nested-marker probe. New RED must
capture actual schemas/tool calls and attempt a forbidden ordinary Coach tool.

Observed: the OpenAI normalizer converts malformed native JSON to empty args.
Inferred: required-field validation in this adapter can report invalid arguments
without rewriting every provider. Verified by: NOT YET; new malformed-args test.

## Public contracts and trusted context

Add POST /api/coach/swim-import with message, import_id UUID, expected_revision
nonnegative strict integer, request_id UUID and optional chat_id/provider. The
existing /api/coach/chat request and behavior stay unchanged. A separate route
keeps import authority apart from the ordinary recovery/planning pipeline.
Client supplies a fresh turn UUID and the revision it saw;
HTTP boundary loads that draft and rejects a stale revision before a paid call.
The turn UUID is a model-command idempotency key, never model-generated.

Import source is captured explicitly before Coach invocation via M2B API. It is
never inferred from arbitrary chat prose or changed by the model. The adapter
receives an immutable server-owned context: selected db, import id, expected
revision and turn id. Model schemas cannot select another import, actor, source,
program identity, request UUID or base library revision. Historical source and
exercise reads remain selected-store/private. Existing ChatManager content may
retain dialogue for history, but it is not the original source owner.

The explicit route calls api/swim_coach_service.py without entering the normal
metric/recovery pipeline. Source remains readable on unavailable,
unsupported, truncated or failed provider. Failure response contains a safe code
and draft identity/revision, never raw provider exception or submitted JSON.

Provider capability is explicit: initial support requires supports_native_tools
and callable generate_with_tools. Unsupported marker-only providers get a clear
refusal before model invocation or draft mutation; no silent marker fallback.
This is a new mode boundary, not a claim that ordinary marker tools are broken.
Read/search/parse/patch use one source-bound adapter for the native tool runtime.

## Narrow tool authority

models/swim_coach_tools.py implements the same get_tool_schemas/execute_tool
surface used by run_native_tool_loop, but registers only swimming operations:
read current source/draft, search/read exact exercise revisions, read saved
program versions, initial parse, one typed bounded patch and an explicit
read-only clarification question. It never exposes
capture/replace source, prepare human confirmation, acknowledge source gaps,
approve/save/send or ordinary planning/recovery operations. The model can keep
ambiguities as unresolved nodes/questions or propose an explicit variant; it
cannot pretend catalog search proves identity with a trainer nickname.

Initial parse consumes M2B InitialContent only; server injects source/id/hash/
snapshots. Patch consumes M2B PatchOperation with the human-only acknowledgement
excluded. Context supplies actor=coach, request UUID and expected revision.
At most one successful mutation per turn: an additional differing operation is
refused; identical retry reuses the retained M2B command receipt. Failed validation
does not consume this allowance. A user asking for another edit starts a new turn
on the read-back revision. This bounds accidental multi-tool rewrites.

Mutation schemas are generated from the actual typed DTO with all reachable
$defs at the parameters root. Test every ref target and the actual provider
wire-builder, not just a hand-copied schema. Native output argument values are
validated before execution; empty/malformed/truncated JSON cannot become a
successful no-op. Do not leak Pydantic input or full raw args into errors/logs.

Supply the exact retained source/current draft as JSON-labelled data in the
source-bound system prompt, so two native rounds can search variants then parse.
Questions are explicit tool results (at most3), not unchecked status prose.
Reuse run_native_tool_loop with an optional source-bound system-prompt override;
the default remains byte-for-byte old behavior. Bound adapter reads to8 and
successful mutations to1 per turn; no generic engine rewrite is required.
Return useful bounded summaries from writes
and full latest draft via HTTP readback. Technique snapshot never overwrites the
source prescription. Unknown ranges/time/effort retain M2B semantics; source span
offsets remain Unicode code points. No embedded private corpus or model tuning.

## Result, SSE and human saving

Emit one typed swim_import event for the whole program, carrying import id,
revision and server status (unparsed/draft/error); the UI retrieves the exact
draft. Do not write an ordinary coach_proposal or emit three competing workout
proposals. The server event/status is authoritative: a successful tool mutation
means draft updated, never library saved. Human preview/confirm remains the
existing M2B/M1 route and is not exposed in tool schemas.

Import-turn narrative must preserve this distinction even if a provider returns
a false completion claim. Use server status text after mutation/error and
explicit unresolved/clarification questions from structured tool/draft data;
unchecked free-form provider text is not rendered as a completion claim.
Test the malicious narrative “saved and
sent” against the actual response. No provider text may manufacture a success
event or hide a failed tool call. Preserve an explicit failure/unsupported state
when no valid initial parse or edit occurred.

No new domain persistence is planned: M2B revisions/command receipts own results.
HTTP retry after a lost response may encounter an already advanced revision and
must provide readback/conflict, not silently pay for an automatic retry. Handling
of duplicate provider requests is not a promise of exactly-once billing. A future
turn ledger would be a new state boundary and requires an explicit spec update.

## RED / acceptance and state matrix

| Boundary | Falsifier / expected behavior |
| --- | --- |
| missing provider | captured source remains exact/readable; no mutation |
| no explicit context | swim tools absent; ordinary Coach unchanged |
| foreign identity/source/actor args | schema rejects; no different draft touched |
| initial parse | synthetic2200/2000/1900nested program reaches same M2B draft |
| pause edit | one rest range changed; every sibling/source unchanged |
| malformed/truncated args | safe failure; no revision/no fake saved event |
| duplicate/differing tools | same receipt or bounded refusal; at most one new revision |
| stale HTTP/model turn |409/readback; no overwrite/provider retry |
| catalog ambiguity | explicit unresolved variant/question; no silent gear rewrite |
| marker unsupported | refusal before paid call/write; source/manual fallback retained |
| provider says saved/sent | authoritative response remains draft/error; library empty |
| unrelated recovery/planning | spies show no mutation/preparation or proposal save |
| store/demo/restart | source/draft/receipt remain selected-store; no personal paths |

Tests to add before implementation: tests/smoke/test_swim_coach_tools.py,
test_api_swim_coach.py and narrow provider-wire fixtures. RED is not yet run.
Existing native/marker Coach and M2B/library/catalog tests are regressions.
API/TS/SSE mirrors and populated conformance must be checked, plus normal
contributor-safe CI, Ruff, web lint/build and one independent bounded review.
No browser screenshots here (no screen changes); #772 owns visible acceptance.

## ASR / ADR, failure and review

Reuse ADR0001 web-primary, ADR0002 read-only Coach authority and SQLite durability
decisions. ASR-MOD-2/3: same Python draft rules/compatible general Coach path;
REL-1/2: exact original and explicit failure/unknown; REL-3/DEP-2: retained draft
receipt/reset/restore inherited from M2B; SEC-1: private safe errors/no credentials.
Trade-off: explicit native-only import support and one mutation per turn reduce
tool ambiguity while preserving manual fallback. This does not certify live
understanding, provider availability, or watch compatibility.

SSE shapes: meta(chat_id); tool_call(name,tool_name,status done/error);
swim_import(import_id,revision,status draft/unparsed/error,code nullable);
token(text) for server-composed status/questions; done(chat_id,import_id,revision).
Pre-stream HTTP errors: detail(code,import_id,revision) for domain/provider/context
failure; validation omits input/source as M2B does. Provider calls run only after
context/capability checks; streaming exceptions emit safe error+readback identity.
Persist user/server-rendered assistant messages through existing ChatManager on
its owned configured path; it is conversation history, not the source authority.

Spec verdict: ready for Domain/API RED implementation, not merge readiness.
Spec Owner explicitly hands this contract to Domain/API Implementer in this task.
Independent review0/2; implementation/CI/owner merge gate pending. UI handoff is
only typed requests/events/errors; #772 owns styling/interaction and screenshots.

## Slice review template completion / evidence

Author/checker/merge owner: Domain/API Implementer / native manual review /
Greg. Candidate/acceptance SHA pending; budget0/2, no exception. ClassA triggers:
model authority/source identity, API/SSE/shared runtime extension. Screenshots
N/A until #772. Observable acceptance, checks and cleanup owner are assigned.

Public contracts: additive explicit POST and typed SSE; mirrored types.ts and
populated conformance in web CI. Ordinary ChatRequest/SSE and marker dispatch
unchanged. Native loop's optional system_prompt_override preserves its default.
No new config/CLI/table/cursor/chat metadata. M2B receipts and existing chat
history retain their reset/lifecycle semantics; DB reset is not redefined as
deletion of historical chat files. Source of truth stays selected-store M2B.
Context keys are import UUID, expected revision and user request UUID; actor is
server-owned coach. Same call retry returns prior result; differing second write
fails. Rollback is a reviewed bounded edit, not removal of retained history.

| State / invariant | RED or falsifier | GREEN checkpoint |
| --- | --- | --- |
| no source/id/actor/save authority |63f28da: adapter absent |5initial adapter cases PASS |
| recursive schema/native args | real DeepSeek wire builder stub | root refs retained; broken JSON no write |
| one mutation/retry/stale | second operation and old revision | refusal or same receipt |
| no recovery/planning side effects |302495d: API contract absent; spies forbid old pipeline | dedicated endpoint avoids it |
| false saved/sent narration | injected provider completion claim | server draft/error, library empty |
| unavailable/unsupported provider | pre-stream refusal | source retained, zero generate calls |
| failure before/after write | provider/history faults | safe actual revision readback |
| three-workout program | parse plus title-only next turn |6100metres, one program event |
| wrong store/corrupt source | demo source in real request; corrupt row |404/503 before provider, no echo |

Current/empty/parsed/historical draft × same/stale/retry × missing/unsupported/
error/partial provider × real/demo × failed/working history are exercised where
relevant. M2B restart/reset/Backup API restore regressions remain green; no new
domain state is introduced. ASRs/ADRs/tactics/trade-offs are recorded above.

Tool GREEN eb4b91e:62focused adapter/native/runtime checks PASS. API working
GREEN:74combined Coach checks PASS, including TS and history/context faults.
Combined final focused M1/catalog/M2B/Coach/contract contour215PASS; Ruff, diff,
extractor freshness and web lint/build PASS (Node22). Source-hash extraction
needed regeneration after types.ts changed, even for separate SSE roots.
Broad/CI/native pending. No paid provider call or private corpus read occurred.

Self-review: no reproduced open blocker in new behavior. Live interpretation
and actual provider schema acceptance remain unverified; SDK wire stubs prove
neither. Native round1 not requested yet. Final verdict BLOCK pending required
broad/CI/independent review and explicit owner merge; final bundle belongs in PR.
