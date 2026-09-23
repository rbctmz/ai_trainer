# Slice Spec: #609 Session-first plan/fact projection

- Issue / PR: #609 / not opened yet
- Author / checker / merge owner: Codex (Spec / Architecture Owner) / independent native reviewer / human repository owner
- Date: 2026-09-23
- Candidate head SHA: pending UI checkpoint

## Change Class

- Class: A
- Rationale: the slice establishes one evidence-sensitive identity and composition contract across planning, reconciliation, activities, feedback, API, and future web consumers.
- Automatic escalation triggers checked: public API/TypeScript contract; evidence identity; ambiguous and partial data; cross-surface reuse. No migration, destructive action, credential, or provider-write trigger applies.
- Review budget used: 0 / 2 rounds
- Review trigger mode: manual
- Review acceptance head SHA: pending GREEN candidate
- Review budget exception: N/A

## Scope

- Behavior that changes: add one canonical, read-only projection for one planned parent session. It composes the existing reconciliation row, current immutable match revision, current feedback fact, and same-day unassigned activities into separate `plan`, `fact`, `deviation`, `cause`, `confidence`, `data_quality`, `load`, and `evidence_revision` fields.
- Files/modules in scope: new pure composer `models/session_projection.py`; new bounded orchestration `services/session_projection.py`; additive planning API schema/route; mirrored TypeScript contract; focused model/service/API contract tests; minimal reuse wiring for Today, Planning, and Activity after the server contract is GREEN.

The first delivery milestone in this branch is intentionally smaller: this spec plus RED contract fixtures only. It does not implement the composer, service, route, or UI consumer.

## Non-goals

- Behavior deliberately unchanged: existing `build_reconciliation` precedence, match thresholds, TSS/duration/adherence calculations, feedback persistence, checkpoints, readiness, provider synchronization, and historical records.
- No second matcher, no name-based fallback, no persistence or backfill, no inferred causal claim, no final Today visual design, no broad UI redesign, and no provider call on the projection read path.
- Deferred work and owner: #610 owns the Today decision story and interaction design; #367 owns athlete acceptance; the human merge owner decides whether a minimal cross-surface rendering is sufficient to close #609 after the DTO is implemented.

## Definition of Done

- [x] Acceptance criteria are observable in the RED matrix and fixtures.
- [x] Required focused and broad checks are named.
- [x] Merge and cleanup owner is the human repository owner; implementation does not authorize merge.
- [x] Pure composer and provider-free service are GREEN.
- [x] Additive API/TypeScript contract is extracted and all three consumers use the shared projection without browser-side recomposition.
- [x] Focused, contributor-safe, Ruff, web lint/build, and contract inventory checks are green.
- [ ] Isolated browser clickthrough: the repository's `run_acceptance.sh` launches the legacy Streamlit surface, not the Next.js routes changed here; a web-specific isolated acceptance harness is not available in this worktree.

## Public Contracts

| Contract | Classification | Intended contract and proof |
| --- | --- | --- |
| Python pure composer | changed compatibly | `build_session_projection(reconciliation, *, session_id, match_revision=None, feedback=None) -> dict[str, Any]`; new module and RED fixtures. |
| Python read service | changed compatibly | `session_projection_at(db, *, session_id, as_of=None, weeks=1) -> dict[str, Any]`; always calls canonical `reconciliation_at(..., include_provider=False)` and performs no write. |
| HTTP API | changed compatibly | Additive `GET /api/planning/session-projection/{session_id}`; Planning includes the same projection per reconciliation row, and Activity includes the proven session id plus projection when the active checkpoint can resolve it. OpenAPI/API tests plus contract extraction cover the route. |
| TypeScript | changed compatibly | `SessionProjection` mirror in `web/lib/types.ts`; Today fetches by session id, while Planning and Activity consume the server projection. `contract:extract -- --check` and API inventory are green. |
| SQLite schema/data | unchanged | Existing planning checkpoint, plan/actual ledger, feedback fact, and activities are read only. No migration, cursor, or new row. |
| Provider/config/CLI | unchanged | No credentials, provider client, environment variable, or command is added. |
| User-visible wording | unchanged in RED milestone | Final wording and layout remain #610/UI scope; stable machine statuses are introduced server-side first. |

The v1 DTO is additive and uses this shape:

```text
schema_version: "session_projection_v1"
session_id: stable planned parent id
projection_status: matched | partial | needs_confirmation | unmatched | data_gap
evidence_revision:
  planning_checkpoint_id
  match_revision_id
  match_revision
  feedback_revision_id
  feedback_revision
  reconciliation_rule_version
  as_of
  provider_status: disabled
plan:
  date, sport, role, name, duration_minutes, load_tss
  legs[]: leg_id, leg_index, sport, duration_minutes, load_tss
  transition: planned_minutes
fact:
  completion_status: complete | incomplete | needs_confirmation | not_observed
  actual_activity_ids[]
  duration_minutes, load_tss
  legs[]: planned_leg_id, leg_index, activity_id, sport, duration_minutes, load_tss
  transition: actual_minutes
deviation:
  adherence, duration_delta_minutes, load_delta_tss, structure_match,
  transition_delta_minutes
cause:
  status: supported | unknown | needs_confirmation
  code
  evidence_refs[]
confidence:
  status: confirmed | computed | partial_evidence | needs_confirmation | data_gap
  score, match_status, match_method, evidence[]
data_quality:
  status, reasons[]
load:
  planned_tss, matched_tss, other_matched_tss,
  additional_unmatched_tss, day_total_tss
```

`matched_tss` includes only activities actually attributed to this parent by the canonical reconciliation row. A partial brick may therefore have non-zero matched load while remaining incomplete. Candidate-only ambiguous activities stay unassigned and appear in `additional_unmatched_tss`. Activities attributed to another parent on the same date are exposed as
`other_matched_tss`, so the complete invariant is
`day_total_tss = matched_tss + other_matched_tss + additional_unmatched_tss`.
Activity IDs are de-duplicated before summing; no leg or parent total is added
on top of its activities, and no window-level load is substituted for the day total.

`cause.status = supported` is legal only with an explicit, addressable evidence reference from an authoritative match lineage, structured athlete feedback fact, or active planning constraint. Free-text interpretation, sport/name similarity, load magnitude, and missing evidence cannot manufacture a cause. `unknown/no_explicit_cause_evidence` is the normal safe result; ambiguity uses `needs_confirmation/ambiguous_match`.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing session returns a stable not-found API result; malformed plan/leg/actual evidence returns `data_gap` while preserving valid plan or actual facts; ambiguous evidence returns `needs_confirmation`; missing cause evidence returns `unknown`; absent timestamps leave transition/ordering claims null rather than guessed.
- Retry/idempotency key and duplicate behavior: reads have no idempotency key because they create no state; identical source revisions produce byte-equivalent DTOs.
- Rollback procedure and proof: revert/remove the additive route, types, service, and model; no schema/data rollback exists. Compare tracked-table snapshots before/after the read.
- [x] Does this add **new persistent state**? No.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A: the slice introduces none.
- [x] Restart and partial-failure recovery are covered: recompute from durable existing evidence; partial/malformed evidence fails closed.

## State Boundaries and Identity

- Source of truth and owner: existing `services.reconciliation.reconciliation_at` owns matching and precedence; planning checkpoints own planned identity; `plan_actual_matches` owns explicit immutable match revisions; `athlete_feedback_facts`/session feedback own athlete evidence; local activities own facts.
- Stable identity/provenance keys: parent `session_id`; `leg_id = <parent>:<leg_index>` from the stamped plan; actual `activity_id`; planning checkpoint id; match id/revision; feedback fact id/revision; reconciliation rule version and `as_of`.
- Cursor/checkpoint lifecycle: read the latest active plan checkpoint and latest immutable match/feedback revisions already selected by their stores. No cursor or checkpoint is created.
- Concurrency and stale-write behavior: no write exists. A response names every revision it used, so a later correction produces a different evidence revision instead of silently changing the meaning of a cached DTO.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| Single parent + one actual | current checkpoint + computed or explicit match | complete | allowed | `matched`, one actual id, plan/fact totals, no invented cause. Falsifier: two parents or missing revision. |
| Brick parent + two stamped legs | current checkpoint + authoritative ordered activities | complete | allowed | one parent, two ordered leg ids, evidenced transition, no double count. Falsifier: two independent parent sessions or summed load twice. |
| Brick parent + bike leg only | current checkpoint + partial external-id lineage | partial | fail closed | `partial`/`incomplete`, one actual leg retained, run and transition not synthesized. |
| Single parent + two plausible activities | same date, heuristic candidates only | ambiguous | fail closed | `needs_confirmation`, zero attributed activities, candidate evidence retained, no completion/cause claim. |
| Parent after explicit correction | latest immutable ledger leaf | present | authoritative existing precedence | latest confirm/reject/unmatch replaces computed ambiguity and response names its id/revision. |
| Legacy parent/leg | checkpoint known, identity or numeric field malformed | partial/missing | fail closed | valid known facts survive, invalid claims are null and `data_quality.reasons` names the gap. |
| Any supported identity | local SQLite revisions | provider unavailable/raises | provider forbidden | same local projection succeeds; provider client is never touched. |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Matched single session has one identity, revisions, consistent totals, and unknown cause without explicit evidence | `test_single_session_projection_keeps_identity_revisions_and_day_load` | missing `models.session_projection` / contract | Exact DTO assertions; day equation 52 + 0 + 8 = 60. |
| Complete bike-to-run brick is one parent with ordered legs and transition | `test_two_leg_brick_is_one_parent_with_ordered_fact_and_no_double_count` | missing composer / leg projection | Two stamped leg ids, two actual ids in start order, transition 6, day equation 73 + 5 = 78. |
| Partial brick remains incomplete and does not invent run/transition | `test_partial_brick_preserves_only_observed_leg`, `test_partial_run_leg_keeps_second_planned_identity` | missing composer / partial status | Bike-only retains leg 1; run-only retains leg 2; neither invents the missing leg or transition; `projection_status=partial`. |
| Ambiguous candidates require confirmation and cannot claim cause or completion | `test_ambiguous_match_needs_confirmation_without_cause_or_completion` | missing composer / ambiguity contract | Candidate ids retained, attributed ids empty, cause `needs_confirmation`, status not complete, data quality is `data_gap/ambiguous_match`. |
| Read is local, bounded, repeatable, and non-mutating | `test_session_projection_read_is_provider_free_and_non_mutating` | missing `services.session_projection` | Provider stub that raises is untouched; tracked SQLite snapshots equal before/after repeated reads. |
| Multi-session day does not assign a sibling's load to this parent | `test_day_load_keeps_other_matched_session_separate` | added during GREEN self-review | `other_matched_tss` contains the sibling load and the de-duplicated day equation holds. |
| Latest explicit correction wins | `test_latest_explicit_match_revision_wins_without_a_second_matcher` on real ledger revisions | missing service at RED | Confirm then unmatch revisions pass through canonical reconciliation; response names ids/revisions 1 and 2. |
| Malformed legacy evidence fails closed | `test_malformed_legacy_numbers_fail_closed_without_losing_known_facts` | missing composer at RED | Known plan identity and actual facts survive; invalid planned values are null with stable reason codes. |
| API/TS consumers share exact DTO | future API/types/cross-surface tests | N/A until server DTO is GREEN | OpenAPI + contract extractor + Today/Planning/Activity identity/totals equivalence. |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: `ASR-REL-1` stable session/leg identity and immutable lineage; `ASR-REL-2` explicit fail-closed partial/ambiguous states; `ASR-PERF-1` bounded local read; `ASR-MOD-2` one server-owned DTO; `ASR-MOD-3` additive contract without backfill.
- ADRs reused or required: `ADR-0001` web-primary UI; domain semantics remain in shared Python and reach web through FastAPI. No new ADR is required for this additive projection.
- Tactic and trade-off: compose existing evidence instead of duplicating matching. This minimizes drift but makes the DTO explicitly dependent on named source revisions and exposes data gaps rather than smoothing them.
- New architecture boundary discovered during review: current reconciliation already attributes partial composite-leg evidence under an ambiguous parent and carries actual activities; the projection must translate that to `partial`, not rerun matching.

## Delivery Slices

1. Spec + RED contract (this milestone):
   - RED: five fixtures named above.
   - GREEN: deliberately deferred until the boundary is reviewed.
   - Refactor/contract refresh: none.
   - Verification: focused test file must collect and fail only because the new composer/service contract is absent.
2. Pure composer + local service:
   - RED: existing five fixtures plus explicit revision and malformed legacy cases (`7 failed`, missing future modules only).
   - GREEN: `models/session_projection.py` composes canonical reconciliation; `services/session_projection.py` performs the bounded provider-free read and supplies latest existing match/feedback revisions.
   - Refactor/contract refresh: no API/types yet.
   - Verification: projection `9 passed`; focused reconciliation/feedback/activity/Today `121 passed`; contributor-safe `2801 passed, 40 skipped, 38 deselected`; full Ruff green. Additional projection cases were added during GREEN self-review for multi-session day load accounting and partial run-leg identity.
3. Additive API/types + consumer reuse:
   - RED: API route/errors/types and shared-consumer tests; API RED `5 failed`, then consumer RED `3 failed` at their respective checkpoints.
   - GREEN: additive route and typed DTO; Planning composes from one provider-free snapshot, Activity carries identity from the immutable match, and Today/Planning/Activity render the shared summary component.
   - Refactor/contract refresh: TypeScript contract extracted; dynamic API path explicitly declared in inventory; no matching or load composition in the browser.
   - Verification: focused projection/API/consumer suites `60 passed`, then `117 passed` before UI GREEN; contributor-safe `2835 passed, 16 skipped, 38 deselected`; full Ruff green; contract extraction freshness and API inventory green; web lint and production build green. First broad pass had one harness-only failure (`python` missing from PATH); isolated reproduction was green with the repository venv added to PATH, then the complete pass succeeded.
   - Browser acceptance remains outstanding: current acceptance launcher is Streamlit-only and does not exercise the Next.js pages. No claim of browser clickthrough is made.

## Evidence Bundle

- Head SHA: pending UI checkpoint
- Changed invariants: one parent projection; partial brick remains incomplete; ambiguity needs confirmation; latest explicit revision wins through canonical reconciliation; malformed plan numbers fail closed; same-day load buckets reconcile without assigning sibling load to the target.
- Focused and broad tests: projection `9 passed`; focused set `121 passed`; contributor-safe `2801 passed, 40 skipped, 38 deselected`; Ruff green.
- CI checks/reruns/flakes: local only; CI not run because no PR exists. An initial contributor-safe run from the system worktree failed because that directory forbids relative SQLite writes; a second `/tmp` cwd removed SQLite failures but broke repository-relative file tests. The authoritative run used a complete temporary copy in `/private/tmp` and passed.
- Lifecycle/probe evidence: provider client configured to raise was untouched; repeated reads returned equal DTOs; tracked SQLite table snapshots were unchanged.
- Changed contracts: additive provider-free API, OpenAPI path, mirrored TypeScript DTO, Planning/Activity envelopes, and shared Today/Planning/Activity rendering.
- Unresolved review-thread count: N/A before PR/review.
- Residual risks and follow-ups: explicit-cause source vocabulary needs validation against existing structured constraints; cross-surface rendering remains later delivery slice and #610 owns design.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P2 | GREEN self-review: the initial three-bucket day equation could not reconcile a second planned session. Falsified with a two-parent same-day fixture; `other_matched_tss` now keeps sibling load separate and the five-term identity is tested. | resolved before review | Codex / fixed locally |
| P2 | GREEN self-review: `needs_confirmation` initially left local `data_quality` as sufficient. The ambiguous fixture now requires `data_gap/ambiguous_match`. | resolved before review | Codex / fixed locally |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | continue |
| 2 | pending | verification | pending | stop unless documented exception |

## Final Verdict

- Verdict: BLOCK for closing #609; READY for the bounded composer/service checkpoint.
- Blocking findings remaining: additive API/TypeScript contract and shared Today/Planning/Activity consumption remain delivery slice 3.
- Review rounds used: 0
- Accepted risk or follow-up issue: UI decision-story work remains #610; athlete acceptance remains #367.
- Merge owner final gate: human repository owner after GREEN evidence and accepted native review on the current head.
- Post-merge sync/branch/worktree/progress cleanup: update #609 and the parent ExecPlan, sync Roadmap state, remove isolated worktree only after merge/read-back.
