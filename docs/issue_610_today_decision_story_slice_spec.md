# Slice Spec: #610 Today decision story

- Issue / PR: #610 / #632 (draft)
- Author / checker / merge owner: Codex (Spec / Architecture Owner) / independent reviewer / human repository owner
- Date: 2026-09-23
- Review-fix code head SHA: `a8b9cb5f8c572fc43bd89043b0ae87dbebaf3818` (pushed; CI pending)

## Change Class

- Class: A
- Rationale: this is the primary safety-sensitive composition of plan/fact, readiness, athlete-reported observations, and next action, with an additive API contract and web/Coach consumers.
- Automatic escalation triggers checked: public API/TypeScript contract; safety-sensitive evidence; cross-surface consistency; accessibility/mobile states. No new persistence, provider write, migration, or external delivery is in scope.
- Review budget used: 2 / 2 full-diff rounds; one scoped delta follow-up
- Review trigger mode: manual
- Review acceptance head SHA: owner delta read-back accepted on base `440d1795`; native review of `20694750cb48894fab6bda3aab67869f9b2c846f` and scoped delta review of `3d11bde9ce3125561568dbce74db588f10c35af7` are addressed; current-head acceptance pending
- Review budget exception: N/A

## Scope

- Behavior that changes: add a server-owned, versioned Today decision-story projection with separate `fact`, `interpretation`, `recommendation`, `evidence`, and `next_action` fields. It reuses #609 session projection and the existing canonical readiness, conflict, proposal, and subjective-wellness sources; it does not rematch or rescore them.
- Files/modules in scope: proposed pure composer in `models/today_decision_story.py`; bounded provider-free source assembly in `services/today_decision_story.py` if existing API assembly cannot provide a stable read boundary; additive `api/today_snapshot.py` / Coach tool adapters and `web/lib/types.ts`; Today and Coach consumers; focused contract/evidence tests and isolated Next.js browser acceptance. UI implementation and visual decisions require a UI / Design Specialist handoff; this spec owns semantics and acceptance only.

## Non-goals

- Behavior deliberately unchanged: ACWR mathematics/classification; readiness scoring; readiness conflict thresholds; session matching and deviation/cause calculation; plan checkpoint, proposal, or provider-delivery state; user feedback persistence.
- No autonomous plan edit, approval, delivery, provider request on render/expand, medical diagnosis, injury prediction, or AI-authored causal explanation.
- No `follow_plan` clearance based on readiness alone when current athlete-reported injury evidence says otherwise. In v1, a current explicit injury self-rating other than “Нет” changes the displayed next step to non-prescriptive evidence review; it does not mutate the plan or declare training medically unsafe. Other subjective scales remain visible evidence but do not acquire new intervention thresholds in this slice.
- Deferred work and owner: any prescriptive pause/modify rule or threshold for soreness/fatigue is a separate owner-approved safety spec; #367 owns moderated athlete acceptance; remaining #608 corroborated-intervention work stays deferred unless this slice establishes a real, separately specified consumer.

## Definition of Done

- [x] Acceptance criteria have observable server and visible-UI assertions.
- [x] RED fixtures cover normal, current negative injury self-rating, stale/missing self-report, ambiguous/partial session projection, and provider-free disclosure.
- [x] Additive API/TypeScript contract is extracted and freshness/inventory checks pass.
- [x] `decision_story.next_action` has priority over legacy `state`/`reason` in both compact and expanded Today; Coach uses the same story composer and canonical action/session resolvers; no browser-side policy logic.
- [ ] Keyboard/screen-reader, 390 px and 1280 px browser acceptance, loading/empty/error/stale states, no overflow, and no console errors pass.
- [x] Focused tests, contributor-safe suite, Ruff, web lint/build, and isolated browser acceptance are recorded in the integration evidence below; explicit screen-reader and loading/empty/error/stale browser checks remain unverified.
- [x] Merge and worktree cleanup remain with the human repository owner.

## Public Contracts

| Contract | Classification | Intended shape / proof |
| --- | --- | --- |
| Pure Python composer | new | `compose_today_decision_story(*, as_of, session_projection, readiness, subjective_wellness, primary_action, rule_versions) -> dict`; deterministic and no I/O. |
| Today API | changed compatibly | Add `decision_story` to existing `/api/today` payload; preserve all existing top-level fields. `decision_story` composition adds no writes, but the existing endpoint is not a read-only boundary: it runs `run_recovery_replan_loop`, which persists recovery decisions and may publish proposals. This existing lifecycle is unchanged. |
| Coach tool/context | changed compatibly | Coach's today-action context must carry the same composer version, evidence references, freshness, and next-action semantics. Its read adapter must not call the write-capable recovery loop merely to obtain this read model. Existing required tools remain until replacement is proven. |
| TypeScript | changed compatibly | Typed mirror for story fields; Today/Coach render status and server-supplied labels, never derive eligibility or conflict in React. |
| SQLite | no new state | The pure composer adds no writes. The new Coach read adapter is read-only and is proven with before/after table snapshots. Calling existing `/api/today` may still cause its pre-existing recovery-loop writes; those writes are outside the story composer and are not used to claim that the whole endpoint is read-only. No schema, migration, reset, or backfill is added. |
| Provider/config/CLI | unchanged | No provider calls or new credentials/configuration. |

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing/stale readiness, missing wellness, unavailable session projection, ambiguous match, or absent rule version is explicit in `evidence`/`interpretation`; known facts survive; no cause or permissive action is invented. Malformed DTOs become a stable `data_gap` story rather than an exception.
- Fresh injury-response rule: a current same-athlete-day injury response of “Нет” is **not required** to preserve the existing gate's `follow_plan` action. If the injury response is missing, stale, invalid, or unavailable, the story must not claim “no symptoms” or “cleared”; it preserves the existing gate action and adds an explicit “current injury response unavailable” caveat. A current response other than “Нет” takes precedence over `follow_plan` and yields only `inspect_evidence` / non-prescriptive review. This avoids making optional provider coverage a new mandatory gate while treating explicit current counter-evidence conservatively.
- Retry/idempotency key and duplicate behavior: pure read composition; equal source DTOs and versions yield equal story excluding no generated timestamp (the composer adds none).
- Rollback procedure and proof: remove the additive story, types, and consumers; compare existing `/api/today` response fields before/after. Prove tracked DB tables unchanged only around repeated calls to the new Coach read-only adapter, not around `/api/today`, whose existing recovery loop has write side effects. No new persistent state requires restore.
- [x] Does this add new persistent state? No.
- [x] Does full reset remove every new row/artifact/cursor? N/A: none introduced.
- [ ] Restart and partial-failure recovery are covered by API and service tests.

## State Boundaries and Identity

- Source of truth and owner: session identity/fact/deviation = `services.session_projection`; readiness = canonical readiness snapshot and readiness-conflict gate; athlete report = dated Intervals subjective-wellness projection; proposal status = existing proposal ledger; story composition = pure Python composer.
- Stable identity/provenance keys: `session_id`, `evidence_revision`, readiness source and `as_of`, subjective-wellness date/mapping version, gate rule version, proposal/checkpoint id where applicable, story schema/rule version.
- Cursor/checkpoint lifecycle: none created; read current source revisions only.
- Concurrency and stale-write behavior: no write. Story binds evidence references to source revision and date; stale/missing observations cannot be promoted to current evidence by request time.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| Current planned session | current checkpoint/session projection revision | matched/complete | canonical projection only | preserve one session identity and exact plan/fact; no second matching pass. |
| Current planned session | current projection revision | partial brick | preserve known legs | incomplete fact and explicit unknown deviation; no fabricated segment/transition. |
| Current planned session | current projection revision | ambiguous match | fail closed | ask for match confirmation; do not use candidate deviation as a cause or recommendation input; source fixture has `completion_status=needs_confirmation`, no attributed candidate activity, and `cause` is a sibling of `deviation`. |
| Current readiness | canonical source date/as-of | fresh and eligible | existing gate outcome | describe the source state; readiness alone is not clearance or ACWR-driven prescription. |
| Current self-report | same athlete date, mapping version | injury value present and not “Нет” | explicit evidence review | show conflict with positive readiness, next action is non-prescriptive review; no silent `follow_plan`, no plan mutation. Falsifier: emits clearance or alters checkpoint. |
| Self-report | older date, missing, invalid, or unavailable | stale/unknown | preserve pre-existing gate action with a caveat | same rule for all four states: these do not block an otherwise eligible `follow_plan`, but never count as a negative injury response or clearance; show freshness/date or explicit absence. |
| Any evidence set | provider client configured to raise | local read path | provider forbidden | story/disclosure succeeds without provider access. |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Story keeps fact, interpretation, and recommendation semantically separate | `test_today_story_separates_fact_interpretation_and_recommendation` | missing `models.today_decision_story` composer | Composer DTO assertion and API payload assertion. |
| Same-day negative explicit injury report plus positive readiness cannot render “follow plan” as an unqualified next action | `test_current_injury_self_report_overrides_clearance_with_review_only` | composer absent / no conflict projection | Current dated value is in evidence; next action `inspect_evidence`; no plan/proposal mutation. |
| Stale/missing/invalid/unavailable self-report follows one rule: preserve existing eligible gate action, but do not imply “no symptoms” or clearance | `test_stale_or_missing_self_report_is_not_current_evidence` | composer absent / freshness semantics absent | All cases keep `follow_plan`, expose their distinct freshness state, and add the same no-current-injury-response caveat. |
| Ambiguous #609 projection remains honest and fixture matches its actual DTO shape | `test_ambiguous_session_requires_confirmation_without_deviation_cause` | composer absent / projection fields dropped | Source completion is `needs_confirmation`, candidate activity is not attributed, and `cause` is parallel to `deviation`; story asks for confirmation. |
| Partial #609 projection preserves known fact without inventing a missing leg | `test_partial_session_preserves_known_fact_without_inventing_leg` | composer absent / projection fields dropped | Known plan/fact survive, completion remains incomplete, unknown leg/transition remain absent. |
| Compact and expanded Today visibly prioritize the decision-story next action over legacy “plan in force” text | `tests/e2e/test_today_decision_story_ui.py::test_today_story_owns_compact_and_full_action_at_mobile_and_desktop` | pending UI consumer | Isolated Playwright acceptance verifies server-supplied action in compact and expanded branches at 390/1280 px. Static source-text search is explicitly insufficient. |
| Coach read adapter reuses the shared DTO without provider access or writes | `test_coach_read_adapter_uses_shared_story_without_database_writes` | service/composer boundary absent | Existing local projection path is used; before/after tracked SQLite table snapshots are equal. The existing `/api/today` recovery-loop writes are expressly not covered by this invariant. |
| Coach and Today use the same story version and evidence/next-action vocabulary | `test_coach_readiness_tool_includes_the_same_story_when_attached` plus Today response assertion | Coach context uses readiness/proposal fragments only | Tool result carries the exact shared composer DTO supplied by the route; no new write-capable loop is invoked by the read adapter. |

## ASR / ADR Traceability

- ASR-PERF-1: preserve local Today latency budget; bounded, provider-free reads.
- ASR-REL-1: use canonical session identity and immutable evidence revision.
- ASR-REL-2: stale/missing/ambiguous/conflicting evidence fails closed and preserves known facts.
- ASR-MOD-2: Python owns meaning; web owns presentation and accessibility.
- ASR-MOD-3: additive API/TypeScript compatibility.
- ADR-0001: web-primary; Python domain and API remain the product contract; Streamlit does not receive a feature-only implementation.
- Tactic/trade-off: one pure projection reduces cross-surface semantic drift, while explicit data gaps may be more visible than a confident but unsupported answer.
- New boundaries discovered and verified: current Intervals injury self-rating is carried in Today but does not participate in `detect_readiness_conflicts`; adding it as review-only conflict evidence is a new, narrowly bounded decision-story rule, not an extension of readiness scoring or clinical advice. `models/ai_tools.py::get_readiness_today` performs local readiness/wellness reads, but Today calls `run_recovery_replan_loop` through `api/today_snapshot.py`, and that loop persists recovery decisions and can publish proposals. Therefore Coach must call the pure shared composer through a read-only adapter, never `build_today_decision_snapshot`.

## Delivery Slices

1. Spec + RED contract (completed):
   - RED: pure composer and shared-consumer contract tests for the cases above.
   - GREEN: owner accepted the clarification delta and authorized Domain/API GREEN. No further semantic review is requested for the current fixture refinements.
   - Verification: historical pre-GREEN checkpoint had six expected RED failures, Ruff and diff-check green. Current server-side contract tests pass; compact/full UI requires a separate browser acceptance slice.
2. Pure story composer + Today API integration:
   - RED: step 1 plus additive response/type contracts.
   - GREEN: deterministic Python composer; API adds the story without removing v2 fields.
   - Refactor: no new DB schema and no provider calls; extraction artifact regenerated only if public types change.
   - Verification: focused API/domain tests, contract freshness/inventory, contributor-safe and Ruff.
3. Coach parity + Today/Coach rendering:
   - RED: Coach action claims and Today share source references, freshness, and story version; fixture wording parity.
   - GREEN: adapt Coach read context through a provider-free/read-only adapter over the shared composer; UI specialist owns component/layout/accessibility edits from approved API/TS contracts.
   - Verification: Coach behavioral evals where applicable, web lint/build, isolated Next.js Playwright at 390/1280 px, expanded disclosure with provider clients set to raise.
4. Dogfood boundary:
   - RED/GREEN: none; moderated acceptance evidence is gathered separately and must not be claimed from automated tests.
   - Verification: #367 records time-to-answer and observed failures; this spec alone does not close #367.

## Evidence Bundle

- Base SHA: `440d1795b2313c7ea071e42565fdf3e630a2c58d`; integration commit SHA is recorded in the parent task handoff after commit.
- Changed invariants: same-day explicit injury self-report other than “Нет” changes only the story action to `inspect_evidence`; missing/stale/invalid/unavailable injury is not interpreted as “Нет” and preserves the supplied gate action with caveat. Ambiguous/partial #609 evidence is copied without rematching. Coach uses the same pre-loop checkpoint, proposal resolver, day-session resolver, and pure story composer as Today; its story source adapter does not invoke Today/recovery loop.
- Focused and broad tests: final focused #610/API/Coach set — `37 passed`; combined focused regressions including legacy Coach wellness and Today compact coverage — `50 passed`; contributor-safe suite in a fresh `/private/tmp` copy with a separate `DATABASE_PATH` — `2827 passed, 40 skipped, 39 deselected`.
- CI checks/reruns/flakes: `python -m ruff check --no-cache .`, `git diff --check`, `npm --prefix web run contract:extract -- --check`, `npm --prefix web run contract:inventory`, `npm --prefix web run lint`, and `npm --prefix web run build` passed. Isolated `tests/e2e/test_today_decision_story_ui.py` passed twice (`1 passed` each), including after the final Coach action/session resolver change. Web lint/build and Playwright wrote only ignored worktree artifacts and used temporary E2E databases.
- Lifecycle/probe evidence: Coach read adapter's before/after table snapshots match for the tracked SQLite tables. A regression fixture with a pending proposal based on checkpoint 1 and active checkpoint 2 resolves to `inspect_evidence`, matching Today; `/api/today` continues its pre-existing recovery-loop writes and is not claimed read-only.
- Changed contracts: additive `TodayResponse.decision_story: TodayDecisionStory`; `web/lib/types.ts` and generated `tests/contracts/ts_contract.json` updated. Coach `get_readiness_today` attaches the same composer DTO in the existing tool result.
- Review-fix verification: `44 passed` across `test_today_decision_story.py`, `test_api_today.py`, and `test_coach_fresh_context.py` after the first code push; final backend follow-up passed `203` focused tests, Ruff, and `git diff --check`. Web lint/build, the Today browser regression at 390/1280 px, and the existing web-stack E2E passed after the UI fix.
- CI at `3d11bde`: `27 failed, 2810 passed, 38 skipped, 39 deselected`; five direct Coach regression failures were fixed in `a8b9cb5`. CI at `b23b397` then had `22 failed, 2818 passed, 38 skipped, 39 deselected`; web contract and E2E passed. A read-only archive of current `main` (`9434584`) reproduced the exact same 22 failing test IDs in the affected ten modules under `TZ=UTC` (`22 failed, 100 passed`), while `TZ=Europe/Moscow` passed all 122. This identifies an existing CI date/timezone boundary, not a fix or green CI claim for this PR.
- Unresolved review-thread count: 0 of 8; all eight received written `fixed-in` replies and were resolved on GitHub after the relevant code pushes.
- Residual risks and follow-ups: no prescriptive symptom threshold beyond the explicit current injury response is introduced. Explicit screen-reader assertions and Today loading/empty/error/stale browser states remain unverified. Independent review and owner acceptance are pending. Existing `/api/today` continues its current recovery-loop write lifecycle; only the pure composer and Coach source adapter carry a no-write contract.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P1 | Observed: initial RED expected `follow_plan` for stale injury data but `data_gap` for missing data. Inferred: both lack a current answer, so the action requirement was underspecified. Verified by: contract now states a current injury “Нет” is not required for the existing gate action; stale/missing/invalid/unavailable preserve it only with an explicit no-clearance caveat. | No positive clearance claim; a current non-“Нет” answer still overrides to review-only. | Owner supplied independent review and accepted delta read-back; no semantic re-review requested. |
| P2 | Observed: compact Today rendered a static “План в силе” and `is_quiet_day` can stay true without self-report evidence. Inferred: this could contradict a story action. Verified by: Playwright at 390/1280 px confirms compact and full branches use `decision_story.next_action`; no static source search is used as acceptance. | Main action priority; extended state/accessibility acceptance still pending. | Addressed in local integration; independent review pending. |
| P2 | Observed: Coach originally treated every pending recovery proposal as current, while Today checks its base checkpoint relation. Verified by: checkpoint 1 proposal with active checkpoint 2 reproduced `inspect_evidence` in Today versus `review_proposal` in Coach. | Same action semantics across Today and Coach. | Fixed locally by reusing the pre-loop checkpoint and Today proposal/day-session resolvers; focused regression passes. |
| P2 | Observed: `/api/today` invokes `run_recovery_replan_loop`, which persists decisions and may publish proposals. Inferred: describing the whole endpoint as read-only is false. Verified by: SQLite no-write proof is now scoped only to the new Coach read adapter; existing Today side effects are explicitly unchanged. | No DB immutability claim for `/api/today`. | Addressed in spec; adapter implementation owner. |
| P2 | Observed: the ambiguous RED fixture nested `cause` under `deviation` and retained `completion_status=complete`. Verified by: fixture now places `cause` beside `deviation`, uses `needs_confirmation`, and attributes no candidate activity. | Fixture validity required for GREEN. | Addressed in RED contract. |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | Base `440d1795`, working-tree spec/RED before clarification | Manual independent read-only review supplied by owner | Four findings addressed; owner completed delta read-back and accepted the rule. Three further test-evidence refinements were incorporated without reopening semantics. | GREEN authorized; no further review round requested |
| 2 | `20694750cb48894fab6bda3aab67869f9b2c846f` | Manual `@codex review` | Five findings: malformed list DTO, mixed Coach checkpoint, stale Coach readiness/story pairing, Today proposal action bypass, and missing fallback grounding. Fixes in `af53916`, `5651f20`, and `a428f53`; focused backend and browser regressions pass. | Full-diff budget exhausted; no further full-diff trigger |

Scoped delta review on `3d11bde` found three P2s: synthesis date drift, stale checkpoint proposals, and malformed evidence revision. All were fixed in `a8b9cb5`, answered in their inline threads, and resolved; no further full-diff review was requested.

## Final Verdict

- Verdict: IN PROGRESS
- Blocking findings remaining: current-head review acceptance and green CI, explicit screen-reader and loading/empty/error/stale browser checks, human owner acceptance and merge.
- Review rounds used: 2
- Accepted risk or follow-up issue: none accepted yet.
- Merge owner final gate: human repository owner.
- Post-merge sync/branch/worktree/progress cleanup: pending; draft PR #632 is open, no merge created.
