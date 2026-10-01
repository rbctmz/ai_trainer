# Preserve daily session facts and canonical readiness freshness (#673)

This living ExecPlan follows `.agent/PLANS.md`. Maintain Progress, Surprises & Discoveries, Decision Log and Outcomes & Retrospective at every milestone.

## Purpose / Big Picture

An athlete with two independent workouts must see the completed bike and the still-unobserved run in both Today and Coach, without a warning created by looking up the calendar ID as a session. Fresh measured recovery data must have a consistent freshness label in the card and its explanation. A brick (one workout with bike/run legs) stays one parent; missing legs are never invented. The user authorized fixes after a read-only audit; live data and merge are excluded.

## Progress

- [x] (2026-10-01) Verified source and remote main `6d97787f49ce89502bfafed35a6f9f18e1a5e306`; reused isolated audit worktree and created `codex/daily-loop-consistency-20261001`.
- [x] (2026-10-01) Created issue #673 and Class A contract/spec below.
- [x] (2026-10-01) Independent specification read-back: no blockers; RED 7 failed, 9 passed on real evidence.
- [x] (2026-10-01) Domain/API implementation, optional per-parent fact contract and regenerated extraction.
- [x] (2026-10-01) Focused 85 passed; contributor-safe 2973 passed, 18 skipped, 46 deselected; Ruff, web lint/build and contract checks passed.
- [x] (2026-10-01) Six real API/browser scenarios (seven variants), 67 screen states, exact Today/Coach parity; independent full round plus scoped delta cleared G1/G2/S1.
- [x] (2026-10-01) Current-commit evidence read-back PASS on 65881db; durable report and synthetic evidence saved; no unresolved blockers.

## Surprises & Discoveries

Observed: the audit found Today/Coach data_gap on a valid two-parent day; individual parent projections retained facts. Inferred: calendar ID lookup caused the gap. Verified by: the audit ID-only falsifier and persisted API evidence; rerun on final source is required. Observed: real freshness state fresh was unknown in the story. Inferred: the helper recognizes a factor-state name instead of the aggregate contract. Verified by: state-only falsifier in the audit; final regression still pending.

## Decision Log

Decision: Class A because canonical identity/evidence and additive shared contracts change. Date/author: 2026-10-01, Spec / Architecture Owner. Decision: use `fact.sessions` containing canonical per-parent story facts for multiple independent parents, not a guessed first parent or brick legs. Preserve single/rest/brick shape. Date/author: 2026-10-01, Spec / Architecture Owner. Decision: reuse one local reconciliation snapshot when assembling multiple parents; never run Today/recovery lifecycle from a read adapter. Freshness is descriptive evidence, not permission to train. No score, matching or persistence rules change.

## Outcomes & Retrospective

Both audited P2 behaviors are corrected and the required source/runtime checks passed. Independent delta and final current-commit evidence read-back have no unresolved blockers. Durable report and evidence are complete. Product correction commit 65881db; final bookkeeping is docs-only. No push/PR, native acceptance or merge. Primary report: `docs/issue_673_daily_story_consistency_report.md` will distinguish completed, unverified and excluded behavior.

## Context and Orientation

The isolated checkout is `/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer`. Python runtime is `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python`. `api/today_snapshot.py` owns source assembly and existing Today lifecycle; `api/routers/coach.py` supplies the same frozen checkpoint/action/readiness to the read-only story adapter. `models/today_decision_story.py` is a pure composer: it receives facts and returns an explanation without database/provider calls. `models.plan_actual_reconciliation.iter_parent_sessions` identifies executable parent sessions: independent bike/run are two parents, brick is one parent with legs. `services.session_projection` exposes their canonical plan/fact/provenance. A checkpoint is the saved version of the training plan; mixing parent projections from different versions must fail closed while retaining other known facts. `services/readiness_snapshot.build_readiness_freshness` supplies summary state fresh/provisional/data_gap, anchor and per-factor buckets. Fresh requires confirmed sleep, HRV and resting HR, not merely current TSB.

## Plan of Work

First add spec-bound tests using temporary SQLite and real saved plans. RED must reproduce the false day warning and fresh-to-unknown label; add boundaries for unobserved parents, partial brick, ambiguity, parent failure, checkpoint mismatch, stale/provisional/blocked data and no-plan compatibility. Implement canonical day parent selection in the shared read boundary; Today and Coach pass the same explicit parent IDs from their saved plan. Read multi-parent projections through one reconciliation snapshot and retain each parent fact DTO in an optional additive `fact.sessions`. Compose each parent under the existing evidence rules, then produce a summary action with real data gaps first, ambiguity next, injury conflict next and supplied eligible action otherwise. Known other-parent facts remain present on failure. Summary session_id is null on multi-parent days; general Planning can resolve either parent. Totals may sum only disjoint attributed activity evidence, not candidates or repeated day totals. Unknown load remains explicit; no aggregate cause/deviation is invented. Single-parent and brick composition stays unchanged.

Update freshness recognition using the canonical current anchor and confirmed primary measurement set, without treating blocked/provisional/data-gap data as current. Mirror optional `sessions?: TodayDecisionSessionFact[]` in `web/lib/types.ts`, regenerate extraction and exercise existing UI rendering. No CSS/layout changes are planned. Hand off any necessary interaction changes to UI / Design Specialist explicitly; otherwise Domain/API implements within the approved contract. The role transition from Spec / Architecture Owner to Domain / API Implementer begins only after the spec read-back.

## Concrete Steps

All Python commands use a launcher modeled on `/private/tmp/ai-trainer-daily-audit-20261001/run.py` and its guard: disable dotenv, clear credentials, SQLite only in `/private/tmp`, external sockets blocked, mock AI only. Create `/private/tmp/ai-trainer-daily-fix-20261001/run.py` with separate runtime/evidence directories and the isolated source path; never inherit live DATABASE_PATH. Run from the isolated checkout:

    <guarded launcher> pytest -m 'not live and not debug and not e2e' tests/smoke/test_daily_story_consistency.py tests/smoke/test_today_decision_story.py tests/smoke/test_api_today.py tests/smoke/test_coach_fresh_context.py -q
    <guarded launcher> pytest -m 'not live and not debug and not e2e' tests/ -q
    <guarded launcher> python -m ruff check .
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory
    npm --prefix web run lint
    npm --prefix web run build

The isolated checkout already has its own compatible node_modules; no live credentials are needed. Reuse copies of the audit six_scenarios.py and browser_audit.py in the new temporary root with paths updated and fixture normalization before comparison. The browser must call the real API over temporary databases, not hand-authored Today response fixtures. API + Next + Chromium start only on loopback; record JSON/text/screenshots and stop their process groups in finally. Screen evidence covers 390/978/1280 px, light/dark, expanded explanations, Planning and activity cards.

## Validation and Acceptance

On the ordinary day no false incomplete warning appears. A completed single bike has one consistent fact. On two independent sessions the completed bike remains attributed and the run stays unobserved; both parent IDs remain visible in DTO and there is no artificial inspect_evidence. Partial brick has only its confirmed bike fact and an unknown run/transition. Ambiguity requests confirmation without inventing attribution. Stale recovery data and explicit injury conflict remain honest/review-only. Today and prepared Coach contexts agree on all seven fixture variants; no real model answer quality is claimed. Independent review has a maximum two consolidated rounds; later checks are scoped deltas with written dispositions.

## Idempotence and Recovery

No new persisted state or migration. New reads cannot rematch, save feedback or run the recovery loop. Repeat requests on the same saved data preserve DTO facts and tracked table snapshots. Existing Today/Coach initialization side effects remain confined to the synthetic fixture database. Rolling back means reverting the code/contract changes; no data recovery is needed. Restart creates new temporary fixture folders. Source worktree stays isolated, live main unchanged, merge requires human authorization.

## Artifacts and Notes

Initial audit report is saved in the owner checkout at `docs/reports/2026-10-01-daily-loop-audit/README.md`; this plan repeats the essential findings because that report is untracked and not part of the base commit. New evidence belongs to `/private/tmp/ai-trainer-daily-fix-20261001/evidence` and the final repository report. Preserve RED and GREEN outputs, exact head, screenshots, independent findings and limitations.

## Interfaces and Dependencies

Reuse existing iter_parent_sessions, reconciliation_at and session_projection_from_reconciliation. Extend the pure composer entry point with an optional ordered list of canonical parent projections or a companion pure day composer; retain the current single projection call for existing consumers. Add optional `session_ids` to the read adapter; omission retains the exact legacy single-ID path. Multi-parent fact.sessions contains copies of per-parent fact DTOs produced by the existing canonical projection composer, never the calendar aggregate ID. No new libraries or external services.

Revision 2026-10-01: created the full isolated correction plan with identity, freshness and completion evidence requirements.

Domain/API handoff 2026-10-01: independent specification round 1 established no blockers. RED: 7 failed, 9 passed; real Today multi-parent action and canonical fresh readiness failed. Implementer now owns the approved Python/API/type slice; no CSS/layout or domain policy change. Scalar reducer: all complete→complete, all unobserved→not_observed, mixed observed/unobserved→incomplete; gap→review, ambiguity→confirmation. Summary projection state prioritizes gap/ambiguity then matched/unmatched/mixed partial. Attributed IDs are ordered union; any unknown load/overlap gives null total; legs/transition remain per-parent only. One session evidence row per parent, one recovery and one injury row.

Review dispositions 2026-10-01: G1 P2 reproduced same-checkpoint A→B confirmation after reconciliation. Bounded revision-head capture/fence added within existing source assembly; inherited match and feedback heads are captured by their service owner, supplied only in private in-process snapshot metadata, never API fields. Affected parent fails closed, unaffected facts remain. G2 P2 malformed/missing identities and mixed revisions now request review with unknown total. P3 malformed readiness bucket reproducibly threw TypeError; now unknown. No persistence or matching changes. Services/session_projection.py is included only for the revision-head read helper. Focused review delta and final acceptance pending.

Verification milestone 2026-10-01: final guarded focused 85 passed; final guarded contributor-safe suite on hash-verified temporary source export 2973 passed, 18 skipped, 46 deselected. First worktree-wide run was blocked for seven legacy relative DB paths; export repeated without relaxing the live-data guard. First export omitted the public tracked .env.example, yielding one missing-template failure; restoring only that public template produced the green full repeat. Final seven real API variants passed exact Today/Coach and canonical parent/activity-card comparisons; 67 browser states have zero page/API errors, attempted writes or horizontal overflow, and both temporary processes stopped. Visually inspected two-parent explanation, ordinary freshness explanation and partial-brick 390px dark screenshot. No pilot, live LLM, spoken screen reader or merge claim.

Completion milestone 2026-10-01: independent scoped evidence read-back PASS, eight source/test/contract hashes match product commit 65881db and exported candidate. G1/G2/S1 fixed-in 65881db. Required six scenario families (seven variants) and 67 browser states satisfy acceptance; skipped/excluded suites and integrator-observed web-log limitation documented. All new evidence/report changes after 65881db are docs-only. Goal correction complete locally, owner merge/pilot/live LLM/screen-reader acceptance excluded.
