# Planning S1 — frozen preview and atomic confirmation

Issue: [#685](https://github.com/rbctmz/ai_trainer/issues/685), parent
[#677](https://github.com/rbctmz/ai_trainer/issues/677).
[ExecPlan](planning_preview_confirm_execplan.md).

Author: Codex, Spec / Architecture Owner. Checker: independent read-only agent
`spec_checker`. Merge/rollout owner: human repository owner. Created: 2026-10-16;
revised: 2026-10-17.
Candidate source baseline: `f0f80d335e7f3973a80241a5127d88ba7eca52dc`.
Spec branch: `codex/issue-685-preview-confirm-spec`; this is not an implementation
acceptance SHA. On 2026-10-17 the human owner authorized implementation, beginning
with Domain / API M1 on `codex/issue-685-m1-regressions`. Deployment is a separate
handoff. The reviewed acceptance and public contracts below are unchanged.

## Change Class

- Class A — Full: persistent identity, API write semantics, concurrency and retry.
- Escalation triggers checked: persistent state, provenance, cross-module contract
  and rollback. No provider integration or personal-data migration is introduced.
- Spec review budget: 2/2 used; manual trigger only. Round 2 verified the
  uncertain-state correction and returned READY for specification handoff.
- M3 implementation review budget: 2/2 used (full code at `0fc01c4`, scoped test-only delta at `77b51b2`); zero open blockers. M2 review is separately recorded below. Native/final S1 acceptance remains M5.
- Budget exception: N/A; no extra round requested.

## Scope

Confirming an unchanged, valid prepared build publishes its exact frozen plan.
Relevant input changes reject pending confirmation without changing active state.
Successful retries return the same result. The server owns both freshness and
the atomic write of plan, settings and confirmation receipt.

Scope includes shared build preparation, a single-purpose SQLite preview store,
Planning build HTTP contracts, the existing Coach `build_plan` proposal adapter,
minimal client integration, contracts and tests. File-level work and role handoffs
are in the ExecPlan. A schema/domain change discovered during UI work returns to
Spec/Domain ownership; it is not implemented in the browser.

## Non-goals

Cycle lifecycle, archive/close, participation outcome, old event/date carry-over,
and new-cycle selection belong to #677 S2. Weekly target interpretation, aggregate
inconsistencies and changed training mathematics belong to S3. General step-4
redesign belongs to S4. Recovery/demand/rebalance/repair protocols and provider
writes remain unchanged. Only Coach's existing build action uses S1. No general
transaction ledger, background cleanup service, new authentication system or
rewrite of Streamlit is required. The human owner retains those follow-ups.

## Definition of Done

- [x] AC1–AC8 from #685 mapped to observable behavior below.
- [x] Required tests, migration/reset/replay and failure probes named.
- [x] Human owner assigned merge/rollout; implementing agent owns test-surface and
  branch/worktree cleanup after the explicit handoff.
- [x] (2026-10-17) Independent specification checker has no unresolved blocking findings.
- [ ] All implementation GREEN, contract/UI evidence and review gates complete.

The last two items distinguish a complete specification from a completed fix.

## Public Contracts

### Parameters and preparation

`POST /api/planning/build` remains the preview endpoint. Its existing planning
fields remain accepted: `goal_type`, `distance`, nullable `event_date` and
`start_week`, `planning_mode`, `intent`, `focus`, `horizon_weeks`, nullable
`manual_phases`, `events`, `available_hours`, `available_days`, `demand` and
`base_checkpoint_id`. Defaults and domain normalization remain those of the current
builder. A supplied base is checked against the current checkpoint; otherwise the
server captures it (0 means no checkpoint). `persist` and `confirm` remain accepted
only to make legacy rejection explicit: `persist=true` returns 409
`preview_required`; `persist=false,confirm=true` returns 422 `invalid_confirmation`.
The normal request has both false or omitted. No request can select a trusted
internal origin or provide a frozen checkpoint.

Preparation returns 200 only after a complete artifact is retained. It writes a
pending preview row but does not write a checkpoint, demand or planning profile.
The user-visible label becomes «Предпросмотр · План ещё не сохранён». A failure in
compute, validation, serialization or freshness recheck produces no usable token.
Preparation is not idempotent: a deliberate retry may create another pending
artifact; only one can apply against a common base, and unused artifacts expire.

Define `BuildParameters` as the canonical request representation, using public
goal/distance/day keys (not Russian internal aliases): mode, intent, focus,
goal_type, distance, nullable event_date, normalized events, resolved start_week,
requested horizon_weeks, nullable manual_phases, available_hours, ordered
available_days, resolved demand, and base_checkpoint_id. Resolve all nullable
defaults once. `event_date` is the normalized explicit legacy input, or null;
`events` is the effective normalized list including any converted legacy A event.
The two are not recalculated at confirmation. Record the resolved actual horizon
separately in the stored input snapshot; event mode may differ from requested
horizon. Use the current effective horizon rules unchanged. Existing form fields
and canonical parameters must have characterization tests for all three modes.

### Confirmation and response

New `POST /api/planning/build/confirm` accepts exactly:

```json
{"preview_id":"00000000-0000-4000-8000-000000000001","confirm":true}
```

The UUID above is an example, not a valid seeded preview. Require a UUID value and
a strictly boolean true; forbid extra fields. Missing, false, string or numeric
confirmation gives 422. Do not accept a client plan, base override or new planning
inputs. The route passes origin `planning_ui` internally.

Keep existing `BuiltPlan` unchanged for other consumers. Add typed
`BuildPreviewResponse` and `BuildConfirmResponse` extending it, both containing
`parameters: BuildParameters` and this `confirmation` object:

| Field | Type / definition |
| --- | --- |
| `protocol_version` | integer literal 1 |
| `preview_id` | server-generated UUID string |
| `expires_at` | UTC RFC3339 string; original pending expiration |
| `status` | `pending` for preview; `applied` for success/replay |
| `replayed` | false for preview/first apply, true for a successful repeated confirm |
| `is_current` | null for preview; boolean indicating whether this saved checkpoint is latest at the transaction's read point |

Pending `plan_id=null`, `confirmation_required=true`. Applied `plan_id` is the
checkpoint ID encoded as a string, `confirmation_required=false`. Preserve all
other BuiltPlan values from the frozen response, including `preview` (the original
before/after comparison), goal, events, weeks, totals, forecast and science audit.
Stored full checkpoint remains private to the server; weekly response is a
projection of the same prepared result, not a second computation.

Permitted preview-to-commit differences are only assigned database checkpoint ID,
database row creation time, profile `updated_at`, applied/receipt metadata and the
response fields above. `plan_revision`, session identity, parent/source provenance,
rules, prescriptions and normalized parameters are fixed at preparation. Even
forecast text must not be recalculated. An old successful receipt returns its
original plan with `is_current=false` if another checkpoint is now latest.

Use Pydantic response models and mirror types in `web/lib/types.ts`; extend
`tests/contracts/registry.json` and regenerate `tests/contracts/ts_contract.json`.
Do not make new metadata mandatory on unrelated `BuiltPlan` producers.

### Errors

For new protocol errors return a top-level JSON object
`{detail: string, code: string, retryable: boolean}`. `detail` is a safe Russian
message, never raw SQLite/trace/data content. Keep it a string for existing API
wrappers; add optional `code`/`retryable` fields to `ApiError` compatibly. Normalize
validation errors for these two routes to this envelope without changing the
global error format of unrelated endpoints.

| HTTP | Code | Meaning / retry policy |
| --- | --- | --- |
| 404 | `preview_not_found` | Unknown UUID, other selected DB, wrong origin/binding. No automatic retry. |
| 409 | `preview_required` | Legacy raw save or old Coach build proposal without S1 identity. Request a new preview. |
| 409 | `preview_stale` | Base/dependency/date/timezone/rules changed, including prepare-time recheck. «Данные изменились — пересоберите предпросмотр». |
| 409 | `preview_invalidated` | Previously invalidated pending artifact. Never reapply. |
| 409 | `preview_checkpoint_missing` | Applied receipt whose checkpoint is missing. Preserve unresolved identity for diagnosis; never recreate it. |
| 409 | `proposal_not_pending` | Coach build proposal was rejected/failed/superseded and has no successful receipt. |
| 410 | `preview_expired` | Pending and `now >= expires_at`. «Предпросмотр устарел — пересоберите его». |
| 422 | `invalid_confirmation` / `invalid_build_request` | Invalid identity syntax, confirmation or request parameters. Correct request. |
| 503 | `planning_busy` | SQLite busy/locked; retryable=true, same identity. |
| 500 | `preview_corrupt` | Malformed stored payload/receipt, digest mismatch or unsupported stored schema. No writes or regeneration; retryable=false. |
| 500 | `planning_storage_error` | Transaction failure; retryable=true with same identity. Rollback or replay resolves uncertain commit. |

All unlisted `retryable` values are false. A transport disconnect has no server
envelope and leaves outcome unknown; the client retains the same identity to
retry. Normal validation failure must not be mislabeled storage failure. Once a
successful receipt exists, pending-only stale/expiry/rules checks no longer run.
Verify receipt integrity/schema and checkpoint existence before returning it;
failure must never fall back to constructing a new plan.

### Coach adapter and compatibility

`propose_plan_build` uses origin `coach` and returns `params.preview_id` generated
by the service; its summary comes from the frozen response. Retain existing summary
keys and add confirmation metadata. Correct `base_checkpoint_id` extraction to
the frozen response's `preview.base_checkpoint_id`. No LLM-supplied ID or payload
is accepted as a server-created artifact.

When `api/routers/coach.py` persists this action, the store binds the artifact to
the newly saved proposal in the same transaction; it must be pending, unbound and
origin coach. Reject attempted binding to a second proposal. If existing proposal
deduplication reuses a row, reuse its already-bound preview and summary, never
replace a binding or display a different unused artifact. Orphan preparations
from failed/cancelled chat turns are harmless and expire.

`POST /api/decisions/proposals/{proposal_id}/approve` keeps its request and
`{proposal,result}` wrapper; for action build_plan, `result` is
`BuildConfirmResponse`. Dispatch this action before the generic pending gate and
claim. The store re-reads proposal action, status, preview_id and binding in its
write transaction. For first success require status pending; update proposal to
approved with its result in the same commit as plan/settings/receipt. For replay
require matching approved proposal and receipt, returning the original result
with dynamic replay/current metadata. Rejected/corrupt/mismatched proposals cannot
apply, even if a caller knows another valid token. A race with rejection is
serialized by the same SQLite writer lock. No external provider delivery occurs.

Do not change the other proposal actions. The existing supplemental approval
decision log is best effort after first success only; it is not the canonical
receipt, is not required for replay, and has no new exactly-once claim. A log
failure cannot change the application result to failed. Coach's client must show
the safe stale/retry outcome; only the build branch gets these new semantics.

Read compatibility is additive: old checkpoints/history keep their existing
schema. Unsafe old public write requests and old unbound build proposals are
intentionally rejected. Deploy API and web together; an old browser receives a
clear 409 and must refresh/rebuild. Trusted internal demo/demand and fallback
callers stay explicit, have regression coverage and cannot be selected via HTTP
flags. The guarantee is for the listed build-confirmation protocol, not all legacy
mutations in the application.

## State Boundaries and Identity

### Coherent dependency snapshot

Capture once on one explicit read transaction. Calculate from that capture only;
do not call public Database helpers opening independent connections halfway
through. Re-read the same dependencies on the confirmation transaction's connection.
The fingerprint is SHA-256 of versioned canonical JSON, not a hash of rounded TSS.

| Dependency | Exact inclusion / freshness rule |
| --- | --- |
| Canonical build inputs | All `BuildParameters`, including events, start/horizon, manual phases, hours/days, demand and base. Immutable in stored artifact. |
| Latest checkpoint | ID (0 if none) and full returned checkpoint data used to restore parent plan/provenance; same ID with changed content is stale. |
| Activities | Entire effective `get_activities(90)` view, with provider_external_id and fields used for multisport identity, membership, dates and metrics. Include inserts/deletes/updates; deterministic ordering by stable row identity. Reuse current SQL/read normalization and effective cutoff. |
| Athlete profile | Full current athlete profile read result (empty if absent), including FTP, LTHR and threshold pace units. Conservative changes to any included field invalidate. |
| Active Coach constraints | Exact current `get_coach_constraints(start_date,end_date,active_only=True,limit=500)` result for this generated horizon, ordered by date and ID, including metadata/status. A newly activated/in-range constraint must change the digest. Preserve the existing limit and selection semantics. |
| Planning settings | Raw values of `planning_demand_level` and `planning_profile`, including absent/malformed distinction. Both are protected against overwrite; profile is a dependency even though it is not a training-model input. |
| Time context | Captured athlete-local calendar day, configured IANA timezone, and effective host-date cutoff used by the existing 90-day activity query. Any change is stale. Expiry uses an injected UTC instant. |
| Rules | Protocol version and `PLANNING_BUILD_RULE_VERSION` plus existing catalog, selector, materializer, overlay and science-audit versions. Explicitly bump build-rule version for unversioned math/default/normalization changes. |

Canonical serialization sorts mapping keys; preserves semantically ordered arrays;
sorts set-like row views by stable identities; preserves exact finite numeric
values (no display rounding), date/time/NULL distinctions and normalizes pandas
missing values deterministically. Reject unsupported nonfinite values before
creating a usable artifact; do not silently convert invalid training input to a
plausible value. Canonicalization itself is versioned and fixture-tested. Compute
metrics/target/forecast from captured activities rather than separately caching
them as an alternative source of truth.

Unrelated theme settings, HRV/sleep writes and out-of-window activities do not
invalidate unless they change a listed read view. Metadata changes within included
rows may conservatively invalidate; this is documented, not a promise of minimal
invalidation. A no-op rewrite with identical included values remains valid. No
dependency digest or private row contents are exposed in public errors/logs.

### Storage ownership and retention

Add `planning_build_previews` through idempotent initialization. The selected
Database instance's SQLite namespace is the owner; demo and real stores are
isolated. UUID is an address, not a new authentication boundary. Continue existing
API authentication/access controls.

Minimum columns are `preview_id TEXT PRIMARY KEY`, `schema_version INTEGER`,
`protocol_version INTEGER`, `origin TEXT`, `state TEXT`, `created_at TEXT`,
`expires_at TEXT`, `base_checkpoint_id INTEGER`, `parameters_json TEXT`,
`dependency_context_json TEXT`, `dependency_digest TEXT`, `checkpoint_json TEXT`,
`response_json TEXT`, `settings_write_json TEXT`, `payload_digest TEXT`, nullable
`coach_proposal_id INTEGER UNIQUE`, nullable `applied_checkpoint_id INTEGER UNIQUE`,
nullable `applied_at TEXT`, nullable `applied_response_json TEXT`, nullable
`receipt_digest TEXT`. State is constrained to pending/applied/invalidated;
origin to planning_ui/coach. Required prepared fields are NOT NULL. State applied
requires applied ID/time/response/digest; other states have none. Validate the same
invariants on read, including proposal binding. Do not cascade-delete existing
checkpoints/proposals from preview cleanup.

`dependency_context_json` contains comparison bounds/time/rule versions and
component digests, not duplicated raw activity history. Integrity `payload_digest`
covers schema/protocol/origin/base, canonical parameters, dependency context/digest,
expiry, frozen checkpoint/response and intended settings writes. This detects
accidental storage corruption, not a privileged attacker who can rewrite the DB.
Coach binding is checked against both proposal params and row binding; receipt
digest covers prepared digest, binding, applied checkpoint ID/time and response.
Receipt verification does not run current training rules.

Pending TTL is `Settings.PLANNING_BUILD_PREVIEW_TTL_SECONDS`, default 1800 seconds.
Positive-int validation follows repository settings conventions; no scattered env
lookups. Changing configuration later affects only newly created rows.
`Settings.PLANNING_BUILD_PREVIEW_RETENTION_DAYS`, default 7, controls retention of
expired/invalidated artifacts: on prepare, delete at most 100 such rows with
`expires_at < now - retention`, oldest first, within the store transaction. No
background service or GET-side cleanup. An expired row returns 410 while retained;
after cleanup it is unknown (404). Referenced Coach cards remain readable and
cannot apply after their artifact is gone.

Applied receipts are retained for the checkpoint's lifetime, without TTL cleanup.
Current full reset removes them; adding any future individual checkpoint deletion
must explicitly handle its receipt. If a checkpoint disappears unexpectedly, 409
preview_checkpoint_missing, never recreate. `Database.clear_all_data` deletes preview
rows before checkpoints/proposals, including orphan pending rows. Initialize,
reopen, full reset and backup/restore must all cover this new table.

### Transaction and ordering

Prepare: read snapshot → compute/serialize once outside write lock →
`BEGIN IMMEDIATE` → reread base/dependencies/time/rules → insert pending → commit.
This second check rejects a sync that won during computation. Cleanup may occur
in this same write transaction. Failed recheck never returns a preview ID.

Confirm: `BEGIN IMMEDIATE` → read artifact and origin/binding → verify immutable
data → if applied, validate receipt/checkpoint and return replay → otherwise check
pending state, expiry, base, dependencies and time/rules → insert frozen checkpoint
→ apply frozen settings → mark preview applied with receipt → if Coach, update
proposal approved/result → commit → return. All database steps use that connection.
The freshness check is the transaction's linearization point: a writer before it
is visible and can cause stale; a writer blocked until after commit is a later
event and does not retroactively invalidate the accepted confirmation.

Settings writes are prepared data, not recomputed from a submitted form. For
planning_ui, normalize the profile using `services/planning_profile.py` before
preview persistence: mode, intent, goal_type, distance, hours, ordered days,
requested horizon and source=planning_form. Preserve current event-mode requested
horizon semantics, not the computed race horizon. Set updated_at at commit. Demand
is the canonical resolved level captured in preview; write it in the same
transaction for planning_ui. For coach, preserve existing behavior: no onboarding
profile write, and write demand only if the trusted adapter explicitly requested
a level; the current Coach build tool does not. Include this intent in the frozen
settings payload and digest.

Failed dependency/base/time/rules check changes only the artifact to invalidated
and commits that status; first response is preview_stale, later calls
preview_invalidated. Expiry leaves state pending with a deterministic 410 until
cleanup. A malformed artifact is not repaired automatically. If stale status
commit itself fails, return retryable storage error; never mutate the active plan.

Same-preview concurrent confirmations serialize and yield first-apply plus replay.
Different previews for one base yield one success and one stale rejection. An
applied replay checks current checkpoint only to set `is_current`; it never
restores a checkpoint or rewrites current settings. Pending validation runs no
provider calls, scheduling, materialization, science audit or forecast. Avoid
using `save_planning_checkpoint`/`save_profile` public helpers inside the
transaction because today they open/commit separate connections; extract
connection-bound private primitives instead.

## Failure, Reset, Rollback, Idempotency

- [x] New state owner, TTL, bounded cleanup, receipt retention and full reset are
  specified above and verified by the synthetic implementation suites.
- [x] (2026-10-17) Restart, reset, backup/restore and partial-failure tests pass on synthetic temporary databases; see the final acceptance bundle. Live rollout is separate.

Before commit, any exception rolls back all plan/settings/proposal/receipt writes.
After commit, a lost response is recovered through the same preview ID. Do not
mark a committed build failed because response delivery or supplemental audit
failed. SQLite lock timeout maps to retryable 503 using the existing bounded
busy-timeout policy; tests use a short injected timeout instead of waiting 30 s.
Pre-transaction validation and post-commit serialization must not introduce an
untested partial application: validate/serialize data before writes and retain
the committed response inside the transaction.

Migration is additive `CREATE TABLE IF NOT EXISTS` and indexes, preserving legacy
checkpoint JSON. No live data backfill. Verify twice-run initialization, old DB
read equivalence and reset. Downgrade to an old server is not a safe rollback of
this invariant: it restores the raw-build write bypass. Stop/disable confirmation
writes during downgrade or deploy a compatibility rejection patch, retain new
rows, then regenerate pending previews on re-upgrade. Do not delete applied
receipts as a rollback strategy. All rehearsal databases are synthetic temporary
ones; live migration/backup/deployment requires a separate authorized handoff.

## UI behavior contract

The UI has local states editing, previewing, ready, confirming, uncertain, applied
and needs_preview. These are interaction states, not training-cycle lifecycle.
Before confirmation is sent, any build-input edit or cancel clears the local
preview token and increments a request generation so an older response cannot
restore confirmability. Include distance, mode, intent, focus, events, dates,
hours, days, horizon, phases and demand. This invalidation/reset rule is available
only in editing, previewing, ready and needs_preview states; it must not erase an
unresolved confirmation attempt.

Confirm uses only the received ID; edits and repeat submit are disabled while in
flight. On transport error or retryable server error, enter uncertain, retain the
unresolved identity and keep edit, Cancel and new-preview actions disabled. Show
«Статус сохранения неизвестен. Повторите проверку» and Retry of that exact
confirmation. Retry remains in confirming/uncertain until an authoritative result:
success/replay moves to applied; an explicit not-applied rejection (stale,
invalidated pending, expired or rejected proposal) moves
to needs_preview and unlocks editing. A corrupt/unreadable receipt or missing
checkpoint for an applied receipt, or an unknown identity, cannot prove
non-application: retain the ID
and locked state with the safe error for manual diagnosis, without automatic
retry or another save. A request-validation error alone (422) likewise cannot
settle an earlier lost response: retain the ID and correct/retry the same request
instead of unlocking a new save. Only authoritative terminal outcomes can clear the unresolved
attempt; pre-confirm reset handlers cannot. On conflict/expiry, disable Confirm and show
«Данные изменились — пересоберите предпросмотр» or the expiry message, with an
explicit action back to preview. Never silently re-preview and save. Cancel
while only ready/previewing changes no active state; an abandoned server artifact
can expire. Do not describe cancel as undoing an in-flight confirmation.

Successful confirm/replay uses server parameters, removes the separate profile
PUT, and revalidates Planning status/overview/history/onboarding. If `is_current`
is false, show «Этот вариант уже сохранялся; сейчас действует другой план» and
refresh the current overview. A stale response to the old generation must not
overwrite a newer editor state. The Coach build card follows equivalent conflict
and uncertain retry rules within its existing card flow. Visual polish and
information redesign remain out of scope.

## Evidence Boundary Matrix

| Identity | Time / provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| New pending, base 0 | Same day/rules, before expiry | Complete unchanged inputs | None needed | First plan exactly frozen, one checkpoint |
| Pending on existing base | Same time, same content | Complete unchanged inputs | None needed | New append-only version, history/links preserved |
| Pending, same base ID | Activity/profile/constraint/settings changes | Stale | Fail closed | 409, zero plan/settings writes |
| Pending on old base | Another plan committed | Stale | Fail closed | 409; concurrent two previews cannot both win |
| Pending | Athlete date, timezone, host cutoff or rule version changed | Stale | Fail closed | 409 without regenerating |
| Pending | now == expires_at or later | Expired | Fail closed | 410 even if dependencies equal |
| Applied | After expiry, restart or new data | Valid receipt/checkpoint | Replay only | Same result, no new row/settings write |
| Applied historical | Later checkpoint current | Valid receipt | Replay only | Original ID, is_current=false; no activation |
| Any ID | Other DB/origin/proposal | Unknown/mismatched | Fail closed | 404, no mutation |
| Pending or applied | Stored bytes/digest/schema invalid | Corrupt | Fail closed | 500, no calculation or application |
| Applied | Referenced checkpoint gone | Missing | Fail closed | 409 preview_checkpoint_missing, no recreation or UI reset |
| Pending | No-op values / unrelated setting changed | Still current | None needed | Confirmation succeeds |
| Coach pending | Concurrent approve/reject | Transaction-ordered | No generic claim | Exactly one winner; rejected cannot apply |

## RED Matrix

The table retains the initial planned matrix; executed M1–M4 evidence and actual
commands are recorded in the implementation checkpoints below. M5's
[final acceptance bundle](planning_preview_confirm_acceptance.md) maps each AC
to executed test names and separates green functionality from pending native
and human gates. NOT YET entries below are the historical initial plan, not
current test status. Existing baseline is not new-behavior RED. Proposed names belong in
`tests/smoke/test_planning_build_confirmation.py` (service/HTTP),
`tests/smoke/test_planning_build_confirmation_storage.py` (real SQLite), and
`tests/e2e/test_planning_build_confirmation.py` (isolated web). Split/parameterize
tests when clearer, retaining the named behavior coverage.

| AC / invariant | RED test or probe | Expected before / target assertion | GREEN |
| --- | --- | --- | --- |
| AC1 full exact result | `test_confirm_publishes_frozen_checkpoint` for 3 modes, base 0/existing, nested sessions | Old confirm rebuilds; target complete checkpoint + response equality except allowlist; planner patched to fail if called during confirm | NOT YET |
| AC2 known reproduction | `test_activity_added_after_preview_is_stale` | Old flow saves changed plan; new confirm 409 and no checkpoint/demand/profile writes | NOT YET |
| AC2 complete dependencies | `test_changed_dependency_rejects_confirmation` parametrized insert/update/delete/provider-link, zones, active constraint entering/leaving bounds, settings, same-ID checkpoint content | Current base-only check insufficient; every included changed read view rejects | NOT YET |
| AC2 non-dependencies | `test_unrelated_write_and_identical_values_do_not_invalidate` | New helper characterization: theme/HRV/sleep/out-of-window/no-op leaves preview valid | NOT YET |
| AC2 clocks/rules | `test_day_timezone_cutoff_rule_change_is_stale`; `test_expiry_boundary` | Pending rejects day/zone/cutoff/rule changes, TTL before/equal/after; use injected clock | NOT YET |
| AC1/2 prepare coherence | `test_change_during_prepare_does_not_publish_token` | Barrier changes dependency after capture before artifact insertion; 409, no usable preview/settings | NOT YET |
| AC3 duplicate vs competing | `test_concurrent_same_preview_replays`; `test_competing_previews_have_one_winner` | Two real connections/barriers; one checkpoint per preview/base, result or conflict as specified | NOT YET |
| AC3 writer ordering | `test_dependency_writer_serializes_with_confirm` | Writer before lock causes stale; writer during lock waits/fails busy; no mixed snapshot | NOT YET |
| AC3 rollback | `test_each_write_failure_rolls_back` | Inject after checkpoint, demand, profile, receipt, Coach status, before commit; exact old state restored | NOT YET |
| AC4 uncertain outcome | `test_lost_response_and_reopen_replay`; `test_busy_retry_keeps_identity` | Durable same response after new connection/process; no duplicate; busy 503 retry succeeds | NOT YET |
| AC4 historical replay | `test_replay_does_not_reactivate_or_rewrite_settings` | Apply A then B then retry A; still B current, A response is_current=false even after TTL/rules change | NOT YET |
| AC4 invalid state | `test_unknown_corrupt_missing_receipt_fails_closed` | Bad token/origin/DB/schema/digest/missing checkpoint never rebuilds; exact codes | NOT YET |
| AC5 changed/late UI | `test_edit_distance_and_late_preview_require_new_preview` | Old distance handler leaves preview; all build edits invalidate, delayed response cannot restore it | NOT YET |
| AC5 confirm UX/profile | `test_confirm_retry_stale_cancel_and_profile` | Only ID submitted; disable while pending; same-ID retry; stale explicit rebuild; cancel no active write; no follow-up profile PUT | NOT YET |
| AC4/5 unresolved ownership | `test_lost_response_blocks_edit_cancel_and_new_preview` | Server commits, response is dropped, attempts to edit/cancel/new preview leave controls disabled and preserve ID; Retry returns original result with one checkpoint. Terminal rejection unlocks; corrupt receipt preserves unresolved ID for diagnosis. | NOT YET |
| AC6 old protocol | `test_legacy_raw_confirm_cannot_bypass`; `test_strict_confirm_request` | Old raw save succeeds; new 409; strict true/UUID/extra fields 422 | NOT YET |
| AC6 Coach path | `test_coach_build_binding_replay_and_rejection` | Old rebuild/pending-only gate; new bound exact apply/replay, old proposal blocked, reject race safe; other actions unchanged | NOT YET |
| AC6 legacy | `test_legacy_checkpoint_and_internal_build_equivalence` | Characterization, no invented RED; preserve stored JSON, session links, internal demo/demand paths | NOT YET |
| AC7 lifecycle | `test_preview_migration_cleanup_reset_and_restore` | Table absent at baseline; repeated init/reopen, bounded TTL cleanup, applied retention, full reset, synthetic Backup API restore | NOT YET |
| AC7 downgrade | `test_compatibility_rejects_unbound_public_writes` plus deployment rollback rehearsal | Old binary alone is unsafe; documented disable/rejection patch retains invariant | NOT YET |
| AC8 contract/browser | HTTP fixtures/extractor/inventory, web lint/build, isolated Playwright | Wire schema/codes/strict validation and rendered behavior agree | NOT YET |

Characterization tests must compare old/new computation with fixed clocks before
removing the old computation body. Future matrix expansions require an invariant
or reproduced boundary, not speculative scope growth. All lifecycle/fault tests
use temporary synthetic DBs, no providers and no personal checkpoint fixture.

## ASR / ADR Traceability

ASR-REL-1/2, ASR-MOD-2/3 and ASR-PERF-4 are affected. ADR-0001 remains the policy:
Python owns semantics and API/web is the primary product path. Frozen artifacts
plus one SQLite transaction implement integrity, freshness and replay. Trade-offs:
small persistent storage, conservative invalidation, an intentionally rejected
legacy write protocol and a short writer lock. Check 16-week reference preview
latency, no network/provider work, and no scheduler under that lock. New boundary
found during authoring: Coach build approval and separate UI profile write must
join the S1 contract; this does not authorize migration of other proposal types.

## Delivery Slices

1. **M1 / Domain:** RED for drift, duplicates and raw bypass; unchanged-build
   characterization. Output is reproducible tests and exact failure evidence.
2. **M2 / Domain:** pure prepared artifact and additive store; full dependency
   capture and preview coherence. Verify equivalence and lifecycle tests.
3. **M3 / Domain/API:** one-transaction confirmation and HTTP protocol; concurrency,
   failure, receipt and replay GREEN. Handoff tested schemas/fixtures to UI.
4. **M4 / Domain + separately assigned UI:** bound Coach build adapter and minimal
   frontend contract wiring. Regenerate TS contract; lint/build and browser checks.
5. **M5 / Integrator + Independent Reviewer:** complete evidence bundle, scoped
   review corrections, human merge gate; leave #677 open for remaining slices.

Each milestone has a clean commit boundary. Do not deploy the intermediate state
with an old public save bypass. No parallel agents edit the same checkout. The
current Spec Owner assignment ends with reviewed documents, not with M1 coding.

## Evidence Bundle

Current whole-S1 evidence: [final acceptance bundle](planning_preview_confirm_acceptance.md).
It supersedes the following initial specification-stage snapshot. Native/current-head
results are recorded on the final PR and #685 after publication; no human merge
acceptance is inferred from implementation-stage test results.

- Baseline source SHA: `f0f80d335e7f3973a80241a5127d88ba7eca52dc` (local and GitHub
  main checked 2026-10-16). Reviewed documents are published separately as a
  docs-only draft PR; its existence does not complete #685.
- Observed/inferred/verified distinction: ExecPlan's Surprises & Discoveries.
- Synthetic drift probe rerun: `1914 -> 2205`, weeks differ, checkpoint base
  unchanged. No HTTP transport/provider/network in that probe.
- Existing suites: API planning, overview, M4c editor, Coach decisions:
  **66 passed in 11.69s**. Baseline only.
- SQLite primitive probe: second writer got `database is locked` while first
  connection held `BEGIN IMMEDIATE`. Full transaction algorithm NOT YET tested.
- Planned changed invariants: exact result, dependency freshness, atomic plan /
  settings / receipt / Coach status, replay without reactivation.
- Contract extraction, new RED/GREEN, browser checks, CI: **NOT YET**.
- Native implementation PR review threads: N/A. Spec round 1: one blocking P2;
  correction documented below and verified in scoped round 2. Static review only.
- Residual boundaries: inherited dates/events and lifecycle remain #677; existing
  90-day host cutoff is preserved and explicitly fingerprinted, not corrected here.

## Review Findings

Use severity → Observed → Inferred → Verified by → gate. Blocking findings must
name a violated AC/invariant and evidence; preferences remain non-blocking.

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P2 | Observed: edit/Cancel reset cleared the token, but uncertain retry required retaining it. Inferred: lost response then edit could lose the only attempt identity. Verified by: independent static transition trace and current PlanBuilder finally-unlock path; runtime NOT YET. Correction: pre-confirm reset only, unresolved state locks edit/Cancel/new preview and preserves ID; explicit missing-checkpoint error distinguishes unresolved applied state. Added lost-response/edit/cancel regression. | AC4/AC5, before M1 | Fixed in spec; independent scoped round 2 verified 2026-10-17 |

## Native Review Rounds

M5 final native review has not yet been requested at candidate publication.
Independent implementation checks for M1–M4 are recorded in their checkpoints;
they do not count as authenticated native results. Final native review is one
complete S1 diff against main, then at most one scoped correction round. The
current native head/result and finding dispositions are recorded on the final
PR and #685 to avoid a documentation-only push after review. Specification review
is tracked separately below. No clean result is assumed from passing tests.

| Round | Reviewed artifact | Trigger | Findings disposition | Stop / exception |
| --- | --- | --- | --- | --- |
| Spec 1 | ExecPlan SHA256 0198b8efbb3f3f23be1e0d7caecc0c619a9f6e5b03fe8d3d323870f9218ed46f; spec SHA256 4e8aaeda7cec1f0837bb8da4c2391c1a9f392c33c01225268251979e9510d57d | manual, 2026-10-17 | One blocking P2; corrected as above. Earlier quota-limited attempt returned no review and used no round. | Scoped verification next |
| Spec 2 | ExecPlan SHA256 a3b78d5a652b0c609f1f843556692f56f6c83a1ce264d7575a69cea9ae9ccd36; spec SHA256 ab99c5a3581a0b15164ddf572c122e7c1225468702afe42937c19fa00aa404f1, correction delta after Spec 1 | manual, scoped verification, 2026-10-17 | P2 verified closed; READY for specification handoff | Stop, 2/2 used |

After round 2, author self-review conservatively clarified that a validation-only
422 cannot settle an earlier lost response; it retains the same unresolved ID.
This narrows unlock behavior under the same reviewed invariant. Final edits also
record review/publication status; no new full review was requested.

## Final Verdict

### M5 acceptance checkpoint (2026-10-17)

Supervisor / Integrator prepared the [final evidence bundle](planning_preview_confirm_acceptance.md).
The 203-case focused suite, 70 contract cases and all 40 browser cases pass on the
unchanged M4 product/test tree. Current
GitHub reads confirm intermediate M1/M2 checks intentionally fail, so final
delivery is one main-targeting PR containing the complete S1 implementation.
Native review/current-head CI and explicit human merge acceptance remain gates;
no source code, live database, deployment or merge changed in this M5 step.

### M4 implementation checkpoint (2026-10-17)

Product code at `f681b82` connects both public build callers. Coach tool prepares
origin=coach identity and derives its summary from frozen data; persistence binds
only its saved/deduplicated card in one transaction. Approval precedes the generic
pending claim, verifies action/status/params/binding inside the writer lock and
commits proposal approved/result with checkpoint/settings/receipt. Repeated approval
replays; rejected/mismatched/legacy unbound builds cannot apply. Other actions use
the existing generic path. Supplemental audit remains best effort on first success.

Planning sends only preview_id/confirm and removes the separate profile PUT. Every
pre-confirm edit/cancel, including distance, invalidates request generations.
Confirming/uncertain state retains identity and locks edit/reset/another preview;
explicit stale outcomes unlock an explicit rebuild. Ambiguous/corrupt/missing
receipt and 422 preserve ownership. Historical replay does not claim to activate
the old plan. Parent locks prevent local tab/new-chat controls from discarding an
unresolved attempt. Unknown-outcome text makes no false not-applied claim.

Independent full review: no product P1/blocking P2; one P2 test-fixture mismatch
found (explicit demand passed despite a no-write assertion). Its focused run had
1 failed/170 passed in 23.36s. A fixed timestamp sentinel reproduced both affected
base cases. **fixed-in `495d589`**: helper now reflects omitted demand of the actual
Coach tool; separate same/new explicit-demand cases verify allowed writes,
unchanged profile and write-free replay. Author focused: 173 passed in 21.94s.
Independent scoped round 2: 20 passed in 3.05s, READY for bounded M4 draft handoff,
zero open blockers, budget 2/2 complete. Native/final S1 approval remains M5.

Final contributor-safe run at `495d589`: **3366 passed, 14 skipped, 64 deselected,
7 warnings in 170.80s**, no file exclusions. Skips/warnings are the same environment,
fixture-regeneration and optional dependency limitations recorded in M3. Repository
Ruff/whitespace, web lint/build, API/TS extraction/freshness and conformance/inventory
pass. There are no new TS/public API schema changes in M4; existing M3 contracts
are consumed.

Isolated Chromium: **18 passed in 21.91s** in
`tests/e2e/test_planning_build_confirmation_ui.py` (unique basename avoids smoke
collector collision). Covers both callers, real commit plus dropped response,
strict request/no profile PUT, held late preview after distance change, stale
return, unknown/corrupt/missing/422/busy ownership, historical replay, cancel with
unchanged active state, keyboard and 390/900/1280 light/dark. Synthetic images in
`docs/design/evidence/issue-685/` were visually inspected; no WCAG certification or
live-athlete validation is claimed. Coach SSE is synthetic; binding/approval/replay
use the real API/store. Initial harness locator/hydration issues were corrected
without changing acceptance, and are documented in the ExecPlan.

M4 completes its caller wiring. M5 whole-S1 acceptance, current-head CI/native
review and human merge/rollout remain outstanding. Parent #677 S2 lifecycle,
S3 training mathematics and S4 explanation/redesign are untouched. No athlete DB,
live provider, deployment or merge was used.

### M3 implementation checkpoint (2026-10-17)

Final complete contributor-safe run at `77b51b2`: **3346 passed, 14 skipped,
46 deselected, 7 warnings in 227.62s**, with no file exclusions. All original
20 HTTP RED cases are included and GREEN. Skips: process/socket limitations (2),
explicit fixture regeneration (10), optional garth dependency (2). Warnings:
existing Starlette/httpx deprecation and six synthetic pandas connection-proxy
warnings. Full repository Ruff, whitespace, web lint/build, contract
extraction/freshness/conformance/inventory and ExecPlan structure/links pass.


M3 Domain/API code is accepted for bounded draft handoff at `0fc01c4`, with
protocol-test adaptation `77b51b2`. Independent `m3_checker` completed full-diff
round 1 and scoped round 2, reporting zero actionable P1/blocking P2 or suggestions.
Its independent commands passed 177 cases in 28.05s and 62 cases in 12.39s;
changed Python Ruff and whitespace checks passed. No native GitHub review,
merge approval, deployment or browser acceptance is claimed.

The original M1 HTTP matrix is GREEN without skip/xfail. Backend coverage maps to
the acceptance table above through actual tests in
`tests/smoke/test_planning_build_commit.py`: complete frozen checkpoint/public
response equality for all six mode/base pairs, named dependency and nondependency
changes, stale-only invalidation, expiry before/equal/after, one-winner concurrency,
writer-before/writer-blocked ordering, rollback after every write for first inserts
and existing updates, retry after simulated lost commit response, restart and
Backup API receipt restore, later-plan replay without reactivation, and safe
unknown/corrupt/missing-checkpoint outcomes. Full input/checkpoint oracles remain
unchanged. No planning/forecast/science calculation occurs during confirmation.

Public models in `api/planning_build_contract.py` back the two Planning routes.
The API/TS contract adds dedicated preview/confirm responses; other `BuiltPlan`
producers stay unchanged. POST errors retain safe top-level string detail plus
code/retryable, and unrelated routes retain their original validation envelope.
Conformance now supports explicitly registered POST scenarios on separate
synthetic fixtures; the existing GET inventory obligation remains strict.

The first complete contributor-safe run had 3338 passed and two legacy integration
requests failing on the intentional 409 rejection; `77b51b2` changes only those
requests to the identity route, preserving visibility assertions. Final full-run
evidence follows when complete. Web lint/build and contract extraction/freshness
checks pass. Product changes after the accepted code are NOT required by review.

Outstanding: AC3 Coach proposal-state transaction, AC5 client ownership/error UX,
AC6 Coach adapter, and AC8 browser/final rollout evidence remain M4/M5. The new
service rejects Coach origin until proposal binding is implemented. Existing
Coach internal facade is not yet switched; S1 must not deploy from this milestone.
Cycle lifecycle, date/event carry-over, load interpretation and step-4 redesign
remain parent #677 S2–S4. Human merge ownership is unchanged.

### M2 implementation checkpoint (2026-10-17)

Candidate `24b0448` adds immutable prepared calculation, coherent read capture,
dependency hashing and pending storage. Its initial M2 review found two blocking
P2 violations: a transitive live readiness clock and conflated absent/NULL
settings. Author reproduced three failing cases and corrected both: the core
uses canonical load metrics directly with its explicit day; raw settings keep
row presence. The corrected 75-case M2/characterization suite passes in 15.71s,
without changing any M1 golden. Initial existing-focused pass: 108 tests.

M2 review rounds 1 and 2 completed: **READY for M2 draft handoff at `6516989`**,
both P2 fixed in that commit and verified by the independent checker. Its own
focused run passed 75 cases in 29.07s; no unresolved blocking findings remain.
The final broad pass on `6516989` was **3236 passed, 14 skipped, 46 deselected in
232.04s**, excluding only the separately rerun known M1 HTTP RED file (20 expected
failures). Skips: process/socket capability limitations (2), explicit fixture
regeneration (10), optional garth dependency (2). Repository Ruff/whitespace and
ExecPlan link/structure checks passed. Final 16-week synthetic prepare: 0.339s;
active plan/settings unchanged. Initial pre-fix broad count was 3234 and is not
used as corrected-tree evidence.
No API router, TS contract, Coach proposal adapter or UI was changed in M2;
the old raw-save bypass and new confirmation endpoint remain M3–M4 work.
This intermediate branch must not deploy or merge as completed S1.

### M1 implementation checkpoint (2026-10-17)

Domain/API handoff accepted. Candidate `097cf99` adds test fixtures and progress
only, with no production changes. Independent `m1_checker` reviewed
`e0cd700..097cf99` and returned READY for M1 draft handoff, zero blocking P1/P2.
Its permitted runtime check independently passed all 12 characterization cases
in 4.33s. M1 review round 1 used; no native GitHub review acceptance is claimed.

Author verification: 78 passed in 14.86s (12 characterization + 66 prior tests),
repository Ruff and whitespace clean. HTTP acceptance remains intentionally RED:
20 failed in 5.07s, consisting of four reproduced unsafe writes, four missing
identity preconditions and twelve missing confirm-route cases. No skip/xfail is
used. The draft milestone must not merge until future GREEN. Full S1 contributor,
contract and browser acceptance remain NOT YET. Next: M2's coherent snapshot,
frozen calculation and additive storage; M3 later turns confirmation RED green.

### Specification handoff verdict (2026-10-17)

**READY for specification handoff to Domain / API Implementer, M1.** Independent
spec rounds 1 and 2 completed, with zero open blocking findings. Product
implementation acceptance is NOT YET. The documents are suitable for a docs-only
draft PR using Refs #685; no implementation, merge approval, deployment, personal
DB mutation or provider write is included. Merge owner remains the human owner;
after implementation the Integrator reports branch/worktree cleanup and actual
post-merge verification separately.
